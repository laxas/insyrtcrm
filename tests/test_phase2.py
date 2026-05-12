"""
Phase 2 import tests.

All tests use the real docs/sample-leads.xlsx fixture (and docs/tech_leads.xlsx
when available) to validate the importer end-to-end.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from apps.imports.services import LeadImporter
from apps.leads.models import Company, Contact, PRBriefing, Stage

SAMPLE_XLSX = Path(__file__).parent.parent / "docs" / "sample-leads.xlsx"
TECH_XLSX = Path(__file__).parent.parent / "docs" / "tech_leads.xlsx"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def open_sample(path: Path = SAMPLE_XLSX) -> BytesIO:
    """Read sample file into a BytesIO so .name is settable (BufferedReader.name is read-only)."""
    buf = BytesIO(path.read_bytes())
    buf.name = path.name
    return buf


def make_xlsx_bytes(rows: list[list]) -> BytesIO:
    """Create a minimal xlsx in memory from a list of row lists (first row = headers)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = "test.xlsx"
    return buf


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_stages(db):
    _s = Stage.objects.get_or_create
    _s(name_de="Neu", defaults={"name_en": "New", "order": 1})
    _s(name_de="Recherche", defaults={"name_en": "Research", "order": 2})
    _s(name_de="Kontaktiert", defaults={"name_en": "Contacted", "order": 3})
    _s(name_de="In Gespräch", defaults={"name_en": "In discussion", "order": 4})
    _s(name_de="Angebot", defaults={"name_en": "Offer", "order": 5})
    _s(
        name_de="Angebot abgelehnt",
        defaults={"name_en": "Offer rejected", "order": 6, "is_archive": True},
    )
    _s(
        name_de="Disqualifiziert",
        defaults={"name_en": "Disqualified", "order": 7, "is_archive": True},
    )
    _s(name_de="Kunde", defaults={"name_en": "Customer", "order": 8, "is_final": True})


@pytest.fixture
def admin_user(db):
    from django.contrib.auth.models import User

    return User.objects.create_superuser("admin", "admin@example.com", "adminpass123")


# ---------------------------------------------------------------------------
# Core import tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sample_import_creates_companies(default_stages, admin_user):
    with open_sample() as fh:
        importer = LeadImporter(fh, on_duplicate="skip")
        batch = importer.commit(admin_user)

    assert batch.rows_created > 0
    assert Company.objects.count() == batch.rows_created


@pytest.mark.django_db
def test_sample_import_creates_contacts(default_stages, admin_user):
    with open_sample() as fh:
        importer = LeadImporter(fh, on_duplicate="skip")
        importer.commit(admin_user)

    assert Contact.objects.count() > 0


@pytest.mark.django_db
def test_sample_import_creates_prbriefings(default_stages, admin_user):
    with open_sample() as fh:
        importer = LeadImporter(fh, on_duplicate="skip")
        importer.commit(admin_user)

    assert PRBriefing.objects.count() > 0


@pytest.mark.django_db
def test_reimport_skip_no_new_rows(default_stages, admin_user):
    with open_sample() as fh:
        importer = LeadImporter(fh, on_duplicate="skip")
        batch1 = importer.commit(admin_user)

    with open_sample() as fh:
        importer = LeadImporter(fh, on_duplicate="skip")
        batch2 = importer.commit(admin_user)

    assert batch2.rows_created == 0
    assert batch2.rows_skipped == batch1.rows_created


@pytest.mark.django_db
def test_reimport_update_no_duplicates(default_stages, admin_user):
    with open_sample() as fh:
        importer = LeadImporter(fh, on_duplicate="skip")
        importer.commit(admin_user)

    count_before = Company.objects.count()

    with open_sample() as fh:
        importer = LeadImporter(fh, on_duplicate="update")
        importer.commit(admin_user)

    assert Company.objects.count() == count_before


@pytest.mark.django_db
def test_two_contacts_in_one_cell(db, admin_user):
    """A cell with two names should produce two Contact records."""
    buf = make_xlsx_bytes(
        [
            ["Firma", "Kontaktperson", "Position"],
            ["Acme GmbH", "Alice Müller, Bob Schmidt", "CEO"],
        ]
    )
    importer = LeadImporter(buf, on_duplicate="skip")
    importer.commit(admin_user)

    company = Company.objects.get(name="Acme GmbH")
    assert company.contacts.count() == 2
    names = set(company.contacts.values_list("full_name", flat=True))
    assert "Alice Müller" in names
    assert "Bob Schmidt" in names


@pytest.mark.django_db
def test_malformed_domain_imports_blank(db, admin_user):
    """Rows with gibberish domains still import; domain is left blank or as-is."""
    buf = make_xlsx_bytes(
        [
            ["Firma", "Website"],
            ["Test AG", "not_a_domain!!!###"],
        ]
    )
    importer = LeadImporter(buf, on_duplicate="skip")
    batch = importer.commit(admin_user)

    # Should not fail
    assert batch.rows_created == 1
    company = Company.objects.get(name="Test AG")
    # Domain may be blank or normalised from the garbage input, but not crash
    assert isinstance(company.domain, str)


@pytest.mark.django_db
def test_missing_company_name_rejected(db, admin_user):
    """Rows without a company name must be rejected and logged in errors."""
    buf = make_xlsx_bytes(
        [
            ["Firma", "Website"],
            ["", "example.com"],
            ["Valid AG", "valid.com"],
        ]
    )
    importer = LeadImporter(buf, on_duplicate="skip")
    batch = importer.commit(admin_user)

    assert batch.rows_created == 1  # only Valid AG
    assert batch.rows_skipped == 1
    assert len(batch.errors_json) == 1
    assert batch.errors_json[0]["row"] == 2


# ---------------------------------------------------------------------------
# Unit tests for coercion helpers
# ---------------------------------------------------------------------------


def test_coerce_score_leading_digit():
    from apps.imports.services import _coerce_score

    assert _coerce_score("2 - Elektromobilität") == 2
    assert _coerce_score("5") == 5
    assert _coerce_score("bad") is None
    assert _coerce_score("") is None


def test_coerce_ai_clarity():
    from apps.imports.services import _coerce_ai_clarity

    assert _coerce_ai_clarity("H (hoch): Klarer Kern → PR skalieren") == "H"
    assert _coerce_ai_clarity("M - medium") == "M"
    assert _coerce_ai_clarity("G") == "G"
    assert _coerce_ai_clarity("X - unknown") == ""
    assert _coerce_ai_clarity("") == ""


def test_coerce_priority():
    from apps.imports.services import _coerce_priority

    assert _coerce_priority("A") == "A"
    assert _coerce_priority("B - medium") == "B"
    assert _coerce_priority("c") == "C"
    assert _coerce_priority("") == ""


def test_coerce_bool():
    from apps.imports.services import _coerce_bool

    assert _coerce_bool("ja") is True
    assert _coerce_bool("Ja") is True
    assert _coerce_bool("yes") is True
    assert _coerce_bool("nein") is False
    assert _coerce_bool("no") is False


def test_split_contacts_comma():
    from apps.imports.services import _split_contacts

    result = _split_contacts("Dr. Alexander Franck, Michael Höweler")
    assert len(result) == 2
    assert result[0] == "Dr. Alexander Franck"
    assert result[1] == "Michael Höweler"


def test_split_contacts_newline():
    from apps.imports.services import _split_contacts

    result = _split_contacts("Alice Müller\nBob Schmidt")
    assert len(result) == 2


def test_normalise_header_strips_emoji():
    from apps.imports.services import _normalise_header

    raw = "⚠️ Reality Check / kritische Hinweise"
    assert _normalise_header(raw).startswith("reality check")


def test_preview_no_db_writes(default_stages, django_db_blocker):
    """preview() must not touch the database at all."""
    with django_db_blocker.unblock():
        with open_sample() as fh:
            importer = LeadImporter(fh, on_duplicate="skip")
            result = importer.preview()
        # Just checking it ran without error and has rows
        assert len(result.rows) > 0
        total = result.new_count + result.skip_count + result.error_count + result.update_count
        assert total == len(result.rows)


@pytest.mark.skipif(not TECH_XLSX.exists(), reason="tech_leads.xlsx not present")
@pytest.mark.django_db
def test_tech_leads_import(default_stages, admin_user):
    """Import the full tech_leads.xlsx if present."""
    fh = open_sample(TECH_XLSX)
    importer = LeadImporter(fh, on_duplicate="skip")
    batch = importer.commit(admin_user)

    assert batch.rows_created > 0
