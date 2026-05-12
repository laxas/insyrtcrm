"""
LeadImporter — reads an xlsx (or csv) file and maps columns to Company / Contact /
PRBriefing records.

Usage
-----
  importer = LeadImporter(file_handle, on_duplicate="skip")
  preview  = importer.preview()          # list[PreviewRow], no DB writes
  batch    = importer.commit(request.user)  # transactional, returns ImportBatch
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import IO, Any

import openpyxl
import pandas as pd
from django.db import transaction

from apps.leads.models import Company, Contact, PRBriefing, Stage, normalize_domain, parse_address

from .mappings.google_sheet_v1 import HEADER_MAP
from .models import ImportBatch

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PreviewRow:
    row_number: int
    status: str  # "new" | "duplicate_skip" | "duplicate_update" | "error"
    company_name: str
    issues: list[str] = field(default_factory=list)
    # parsed, coerced data — present even for errors so UI can show what was parsed
    company_data: dict[str, Any] = field(default_factory=dict)
    briefing_data: dict[str, Any] = field(default_factory=dict)
    contact_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PreviewResult:
    rows: list[PreviewRow]

    @property
    def new_count(self) -> int:
        return sum(1 for r in self.rows if r.status == "new")

    @property
    def update_count(self) -> int:
        return sum(1 for r in self.rows if r.status == "duplicate_update")

    @property
    def skip_count(self) -> int:
        return sum(1 for r in self.rows if r.status == "duplicate_skip")

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.rows if r.status == "error")


# ---------------------------------------------------------------------------
# LeadImporter
# ---------------------------------------------------------------------------


class LeadImporter:
    """
    Import leads from an xlsx (or csv) file.

    Parameters
    ----------
    file_handle : file-like object opened in binary mode
    mapping : dict mapping normalised header → field path (defaults to google_sheet_v1)
    on_duplicate : "skip" | "update" | "abort"
    """

    SCORE_FIELDS = {"story_potential", "fit_score"}
    DATE_FIELDS = {"last_contact", "research_date", "last_update"}
    BOOL_FIELDS = {"update_needed"}

    def __init__(
        self,
        file_handle: IO[bytes],
        mapping: dict[str, str] | None = None,
        on_duplicate: str = "skip",
    ) -> None:
        if on_duplicate not in ("skip", "update", "abort"):
            raise ValueError(f"on_duplicate must be skip/update/abort, got {on_duplicate!r}")
        self._file = file_handle
        self._mapping = mapping or HEADER_MAP
        self.on_duplicate = on_duplicate
        self._raw_rows: list[dict[str, str]] | None = None  # loaded lazily

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def preview(self) -> PreviewResult:
        """Parse file and return per-row status without writing to the DB."""
        rows = []
        for row_number, raw in enumerate(self._iter_raw_rows(), start=2):
            rows.append(self._analyse_row(row_number, raw))
        return PreviewResult(rows=rows)

    @transaction.atomic
    def commit(self, user) -> ImportBatch:
        """
        Write rows to DB and return an ImportBatch record.
        Rolls back entirely if on_duplicate="abort" and a duplicate is found.
        """
        created = updated = skipped = 0
        errors: list[dict] = []

        for row_number, raw in enumerate(self._iter_raw_rows(), start=2):
            pr = self._analyse_row(row_number, raw)
            if pr.status == "error":
                errors.append({"row": row_number, "company": pr.company_name, "issues": pr.issues})
                skipped += 1
                continue
            if pr.status == "duplicate_skip":
                skipped += 1
                continue
            if pr.status == "duplicate_update":
                if self.on_duplicate == "abort":
                    raise DuplicateAbortError(
                        f"Row {row_number}: duplicate company {pr.company_name!r} — aborting."
                    )
                self._write_row(pr, update=True)
                updated += 1
            else:  # "new"
                self._write_row(pr, update=False)
                created += 1

        batch = ImportBatch.objects.create(
            source_filename=getattr(self._file, "name", "upload"),
            performed_by=user,
            rows_created=created,
            rows_updated=updated,
            rows_skipped=skipped,
            errors_json=errors,
        )
        return batch

    # ------------------------------------------------------------------
    # File reading
    # ------------------------------------------------------------------

    def _iter_raw_rows(self):
        """Yield one dict per data row: normalised_header → raw_string_value."""
        self._file.seek(0)
        filename = getattr(self._file, "name", "")
        if filename.endswith(".csv"):
            yield from self._iter_csv()
        else:
            yield from self._iter_xlsx()

    def _iter_xlsx(self):
        wb = openpyxl.load_workbook(self._file, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        raw_headers = next(rows)
        header_map = self._build_header_map(raw_headers)
        for row in rows:
            if all(v is None for v in row):
                continue
            yield {
                field_path: _str(row[idx])
                for idx, field_path in header_map.items()
                if field_path is not None
            }

    def _iter_csv(self):
        df = pd.read_csv(self._file, dtype=str, keep_default_na=False)
        header_map = self._build_header_map(list(df.columns))
        for _, row in df.iterrows():
            yield {
                field_path: _str(row.iloc[idx])
                for idx, field_path in header_map.items()
                if field_path is not None
            }

    def _build_header_map(self, raw_headers) -> dict[int, str | None]:
        """Map column index → resolved field path (or None if unmapped)."""
        result = {}
        for idx, raw in enumerate(raw_headers):
            if raw is None:
                result[idx] = None
                continue
            normalised = _normalise_header(str(raw))
            field_path = self._resolve_header(normalised)
            result[idx] = field_path
        return result

    def _resolve_header(self, normalised: str) -> str | None:
        for key, field_path in self._mapping.items():
            if normalised.startswith(key):
                return field_path
        return None

    # ------------------------------------------------------------------
    # Row analysis (no DB writes)
    # ------------------------------------------------------------------

    def _analyse_row(self, row_number: int, raw: dict[str, str]) -> PreviewRow:
        company_name = raw.get("name", "").strip()
        issues: list[str] = []

        if not company_name:
            return PreviewRow(
                row_number=row_number,
                status="error",
                company_name="(missing)",
                issues=["Company name is empty"],
            )

        company_data, briefing_data, contact_rows, parse_issues = self._parse_raw(raw)
        issues.extend(parse_issues)

        # Duplicate detection: match on (name, normalised domain)
        domain = company_data.get("domain", "")
        existing = self._find_existing(company_name, domain)

        if existing:
            # abort is enforced at commit() time; here we mark as update
            status = "duplicate_skip" if self.on_duplicate == "skip" else "duplicate_update"
        else:
            # non-fatal issues are warnings; row still imports
            status = "new"

        return PreviewRow(
            row_number=row_number,
            status=status,
            company_name=company_name,
            issues=issues,
            company_data=company_data,
            briefing_data=briefing_data,
            contact_rows=contact_rows,
        )

    def _parse_raw(
        self, raw: dict[str, str]
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[str]]:
        """Split raw field-path dict into company_data, briefing_data, contact_rows, issues."""
        company_data: dict[str, Any] = {}
        briefing_data: dict[str, Any] = {}
        issues: list[str] = []

        # Collect per-contact fields; they are merged below
        contact_names: list[str] = []
        contact_position = ""
        contact_email = ""
        contact_phone = ""
        contact_linkedin = ""

        for field_path, raw_value in raw.items():
            value = raw_value.strip() if isinstance(raw_value, str) else ""

            # ---- special fields ----
            if field_path == "_address":
                addr = parse_address(value)
                company_data["location"] = value
                company_data.update(addr)
                continue
            if field_path == "_contacts":
                contact_names = _split_contacts(value)
                continue
            if field_path == "_contact_position":
                contact_position = value
                continue
            if field_path == "_contact_email":
                contact_email = value
                continue
            if field_path == "_contact_phone":
                contact_phone = value
                continue
            if field_path == "_contact_linkedin":
                contact_linkedin = _extract_url(value)
                continue
            if field_path == "_stage":
                stage = _resolve_stage(value)
                if stage is None and value:
                    issues.append(f"Unknown stage {value!r} — will be left blank")
                company_data["_stage"] = stage
                continue

            # ---- prbriefing fields ----
            if field_path.startswith("prbriefing."):
                br_field = field_path[len("prbriefing.") :]
                coerced, issue = self._coerce_briefing(br_field, value)
                if issue:
                    issues.append(issue)
                if coerced is not None:
                    briefing_data[br_field] = coerced
                continue

            # ---- plain company fields ----
            if field_path == "domain":
                company_data["domain"] = normalize_domain(value)
                if value and not company_data["domain"]:
                    issues.append(f"Could not parse domain from {value!r}")
                continue

            company_data[field_path] = value

        # Build contact rows: one per name
        contact_rows = _build_contact_rows(
            contact_names, contact_position, contact_email, contact_phone, contact_linkedin
        )

        return company_data, briefing_data, contact_rows, issues

    def _coerce_briefing(self, br_field: str, value: str) -> tuple[Any, str]:
        """Return (coerced_value, issue_or_empty)."""
        if not value:
            return None, ""

        if br_field in self.SCORE_FIELDS:
            coerced = _coerce_score(value)
            if coerced is None:
                return None, f"Could not parse score from {value!r} for {br_field}"
            return coerced, ""

        if br_field in self.DATE_FIELDS:
            coerced = _coerce_date(value)
            if coerced is None:
                return None, f"Could not parse date from {value!r} for {br_field}"
            return coerced, ""

        if br_field in self.BOOL_FIELDS:
            return _coerce_bool(value), ""

        if br_field == "ai_profile_clarity":
            return _coerce_ai_clarity(value), ""

        if br_field == "priority":
            return _coerce_priority(value), ""

        return value, ""

    # ------------------------------------------------------------------
    # DB writes
    # ------------------------------------------------------------------

    def _write_row(self, pr: PreviewRow, *, update: bool) -> None:
        company_data = dict(pr.company_data)
        stage = company_data.pop("_stage", None)

        if update:
            domain = company_data.get("domain", "")
            company = self._find_existing(pr.company_name, domain)
            if company is None:
                # Race condition — just create
                update = False

        if update:
            for attr, val in company_data.items():
                setattr(company, attr, val)
            company.save()
        else:
            company = Company(
                name=pr.company_name,
                source="import",
                **{k: v for k, v in company_data.items() if k != "name"},
            )
            company.save()

        if stage is not None and company.current_stage != stage:
            # Use internal assignment to avoid creating StageTransition on import
            Company.objects.filter(pk=company.pk).update(current_stage=stage)

        # PRBriefing
        if pr.briefing_data:
            briefing, _ = PRBriefing.objects.get_or_create(company=company)
            for attr, val in pr.briefing_data.items():
                setattr(briefing, attr, val)
            briefing.save()

        # Contacts
        if pr.contact_rows:
            if update:
                # On update we replace contacts to keep data fresh
                company.contacts.all().delete()
            for cdata in pr.contact_rows:
                Contact.objects.create(company=company, **cdata)

    def _find_existing(self, name: str, domain: str) -> Company | None:
        qs = Company.objects.filter(name=name)
        if domain:
            qs = qs.filter(domain=domain)
        return qs.first()


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class DuplicateAbortError(Exception):
    pass


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _str(value: Any) -> str:
    """Convert any cell value to a stripped string."""
    if value is None:
        return ""
    return str(value).strip()


def _normalise_header(raw: str) -> str:
    """Lowercase, strip whitespace, remove emoji and variation selectors."""
    # Keep only letters, digits, whitespace, hyphens, slashes — strips emoji and variation selectors
    cleaned = re.sub(r"[^\w\s/\-]", "", raw, flags=re.UNICODE)
    return cleaned.strip().lower()


def _split_contacts(value: str) -> list[str]:
    """Split 'Name1, Name2' or 'Name1\nName2' into individual names."""
    if not value:
        return []
    # Split on newlines first, then commas — but be careful: "Dr. Max Muster, CEO" is one name
    # We split on comma only when followed by what looks like a name (capital letter after space)
    parts = re.split(r"\n|,\s*(?=[A-ZÜÖÄ])", value)
    return [p.strip() for p in parts if p.strip()]


def _build_contact_rows(
    names: list[str],
    position: str,
    email: str,
    phone: str,
    linkedin: str,
) -> list[dict[str, Any]]:
    """Build one Contact dict per name. Shared fields (email, phone…) go to the first contact."""
    if not names:
        if any([position, email, phone, linkedin]):
            return [
                {"position": position, "email": email, "phone": phone, "linkedin_url": linkedin}
            ]
        return []
    rows = []
    for i, name in enumerate(names):
        row: dict[str, Any] = {"full_name": name}
        row["position"] = position
        # Assign shared contact fields to the first contact only
        if i == 0:
            row["email"] = email
            row["phone"] = phone
            row["linkedin_url"] = linkedin
        else:
            row["email"] = ""
            row["phone"] = ""
            row["linkedin_url"] = ""
        rows.append(row)
    return rows


def _resolve_stage(value: str) -> Stage | None:
    if not value:
        return None
    try:
        return Stage.objects.get(name_de__iexact=value.strip())
    except Stage.DoesNotExist:
        pass
    try:
        return Stage.objects.get(name_en__iexact=value.strip())
    except Stage.DoesNotExist:
        return None


def _coerce_score(value: str) -> int | None:
    """Extract leading integer 1-5 from strings like '2 - description...'"""
    if not value:
        return None
    m = re.match(r"^([1-5])", value.strip())
    if m:
        return int(m.group(1))
    return None


def _coerce_date(value: str) -> date | None:
    if not value:
        return None
    for _fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return date(*[int(x) for x in re.split(r"[./-]", value.strip()[:10])])
        except ValueError, TypeError:
            pass
    # pandas as last resort
    try:
        return pd.to_datetime(value, dayfirst=True).date()
    except Exception:
        return None


def _coerce_bool(value: str) -> bool:
    return value.strip().lower() in ("ja", "yes", "true", "1", "x")


def _coerce_ai_clarity(value: str) -> str:
    """Extract H / M / G from 'H (hoch): ...' style strings."""
    if not value:
        return ""
    first = value.strip()[0].upper()
    if first in ("H", "M", "G"):
        return first
    return ""


def _coerce_priority(value: str) -> str:
    """Extract A / B / C from 'A', 'A - High', etc."""
    if not value:
        return ""
    first = value.strip()[0].upper()
    if first in ("A", "B", "C"):
        return first
    return ""


def _extract_url(value: str) -> str:
    """
    Pull the first https?:// URL out of a cell value.

    Google Sheets sometimes pads cells with spaces or embeds a visible label
    before the URL, e.g. 'Company | LinkedIn   https://www.linkedin.com/...'
    """
    if not value:
        return ""
    m = re.search(r"https?://\S+", value)
    if m:
        url = m.group(0).rstrip(".,;)")  # strip trailing punctuation
        return url[:500]  # hard cap matches field max_length
    # No URL found — store as-is only if short enough to be a raw URL
    clean = value.strip()
    return clean[:500] if clean.startswith(("http", "www", "linkedin")) else ""
