# TASKS.md

Phased delivery plan for **insyrtcrm**. Work one phase at a time. Don't open a new phase until the previous one is merged and the acceptance check passes.

Each task references requirement IDs from `docs/requirements.md`. When you complete a task, tick the checkbox in your local copy and reference the requirement IDs in the commit message.

---

## Phase 0 — Scaffolding

**Goal:** A runnable but empty Django project with linting, tests, and CI wired up. No business logic yet.

- [ ] Confirm `pyproject.toml` from `uv init` is sane. Set Python requirement to `>=3.14,<3.15`.
- [ ] Add core deps via uv: `django>=6.0,<7`, `psycopg[binary]`, `uvicorn[standard]`, `django-q2`, `redis`, `python-dotenv`, `django-environ`.
- [ ] Add dev deps via `uv add --dev`: `pytest`, `pytest-django`, `pytest-cov`, `factory-boy`, `ruff`, `pre-commit`.
- [ ] Configure `ruff` in `pyproject.toml` (line length 100, target py314, select sensible rule groups).
- [ ] Run `django-admin startproject insyrtcrm .` to create the project package.
- [ ] Delete `main.py` from `uv init` if present.
- [ ] Split `insyrtcrm/settings.py` into `insyrtcrm/settings/__init__.py`, `base.py`, `dev.py`, `prod.py`. Default to `dev` in development via `DJANGO_SETTINGS_MODULE`.
- [ ] Create empty app skeletons under `apps/`: `leads`, `activities`, `imports`, `stats`, `accounts`. Register them in `INSTALLED_APPS` as `apps.leads`, etc.
- [ ] Configure i18n: `LANGUAGES = [("de","Deutsch"),("en","English")]`, `LANGUAGE_CODE = "de"`, `USE_I18N = True`, `USE_TZ = True`, `TIME_ZONE = "Europe/Berlin"`. Create `locale/` directory.
- [ ] Configure PostgreSQL in `base.py` reading from env vars (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`).
- [ ] Add a `health/` URL returning 200 OK with a tiny JSON payload `{"status":"ok"}` (needed for TR-DP-13).
- [ ] Configure `pytest-django`: `pyproject.toml` `[tool.pytest.ini_options]` with `DJANGO_SETTINGS_MODULE = "insyrtcrm.settings.dev"`.
- [ ] Add `pre-commit` config running ruff format + ruff check.
- [ ] Add a GitHub Actions workflow `.github/workflows/ci.yml`: install uv, sync, run ruff + pytest against a postgres service container.
- [ ] Write a smoke test that hits `/health/` and asserts 200.
- [ ] Write a stub `README.md` with: how to install uv, how to bring up Postgres locally (docker-compose snippet is fine), how to run `manage.py migrate` and the dev server, how to run tests.

**Acceptance:** `uv run pytest` green, `uv run python manage.py runserver` shows the Django welcome page or redirects to login, `/health/` returns 200, CI green on push.

---

## Phase 1 — Data Model + Django Admin

**Goal:** All entities modelled, migrations applied, every entity creatable/editable through Django admin, domain logic covered by tests.

References: §3.1 (FR-DM-01..05), §3.2 (FR-PL-01..03, FR-DM-ARCH-01), §3.7 (FR-US-01..05).

### Models — `apps/leads`
- [ ] `Stage`: `id`, `name_de`, `name_en`, `order`, `is_final`, `is_archive`. Default fixture: the eight stages from §3.2.
- [ ] `Company`: name, domain (normalised on save: lowercase, strip protocol + `www.`), location, industry, product, size, investors, source, owner (FK to User, nullable), created/updated timestamps. Unique constraint on `(name, domain)` — FR-DM-01.
- [ ] `Contact`: company FK (CASCADE), full_name, position, email, phone, linkedin_url, salutation, first_name, last_name. Multiple per company — FR-DM-02.
- [ ] `PRBriefing`: one-to-one with Company. Fields from FR-DM-04: reality_check, ai_perception, ai_profile_clarity (choices H/M/G), media_hook, value_for_decision_makers, communication_goal, trigger_event, trigger_type, communication_gap, innovation_seriousness, story_potential (1–5), fit_score (1–5), priority (A/B/C), press_news, next_step, last_contact, research_date, last_update, currency_check, update_needed.
- [ ] `StageTransition`: company FK, from_stage, to_stage, transitioned_at, by_user, comment. — FR-PL-02.
- [ ] `Company.current_stage` derived from latest StageTransition, or stored denormalised with a signal.

### Models — `apps/activities`
- [ ] `Activity`: company FK, channel (choices: LETTER, PHONE, LINKEDIN, EMAIL, OTHER), direction (OUT, IN), outcome (CharField with choices), occurred_at, performed_by (FK User), duration_seconds (nullable, for calls), note, contact FK (nullable). — FR-DM-05.
- [ ] Choice list for outcomes from FR-PH-03; extend as needed.

### Models — `apps/imports`
- [ ] `ImportBatch`: source_filename, performed_at, performed_by, rows_created, rows_updated, rows_skipped, errors_json, notes. — FR-IM-05.

### Models — `apps/accounts`
- [ ] Use Django's `User` as-is; define three groups (`Admin`, `PR-Rep`, `Read-only`) via a data migration. — FR-US-02.
- [ ] Add password validators per FR-US-03 (min length 12).
- [ ] Optional: add `django-otp` for TOTP MFA (FR-US-04) — can defer to a later phase if it slows things down. Mark with `TODO(phase-1-mfa)` if deferred.

### Logic
- [ ] `Company.transition_to(stage, user, comment="")` method that creates a `StageTransition` and updates `current_stage`. — FR-PL-02.
- [ ] When transitioning to an `is_archive=True` stage, surface a confirmation in the admin and (later) UI offering data reduction per FR-DM-ARCH-01. Implement the reduction method `Company.archive_and_reduce(reason, user)` even if the UI hook is added in Phase 3.
- [ ] Audit log for security-relevant actions — FR-US-05. Use `django-auditlog` or roll a tiny `AuditEntry` model. Document the choice in the PR.

### Admin
- [ ] Register every model with sensible `list_display`, `search_fields`, `list_filter`, inlines (Contact + PRBriefing inline on Company).
- [ ] Stage admin shows order, is_final, is_archive; can be reordered.
- [ ] Admin is fully usable in German and English.

### Tests
- [ ] Company uniqueness on (name, domain).
- [ ] Domain normalisation.
- [ ] Stage transition creates StageTransition row and updates `current_stage`.
- [ ] Archive-and-reduce deletes the right fields, keeps the right fields.
- [ ] Activity creation links to user and company.
- [ ] Group-based permission test: Read-only user can't add a Company in admin.

**Acceptance:** Spec checklist for §3.1, §3.2, §3.7 satisfied. `pytest` green. You can log into Django admin and manually create a Company → add Contacts → add a PRBriefing → log Activities → transition through stages → archive.

---

## Phase 2 — Import

**Goal:** The real `docs/sample-leads.xlsx` (and its eventual full version) imports successfully with deduplication, preview, and a logged ImportBatch.

References: §3.3 (FR-IM-01..07).

- [ ] Add `openpyxl` and `pandas` to deps.
- [ ] Build `apps/imports/services.py` with a clean `LeadImporter` class taking a file handle, returning a preview structure.
- [ ] Implement column mapping from FR-IM-06. Mapping is declarative (a dict or YAML in `apps/imports/mappings/google_sheet_v1.py`), so we can add new mappings without rewriting the importer.
- [ ] Domain normalisation matches `Company` save logic. Reuse, don't duplicate.
- [ ] Deduplication strategy selectable: `skip` | `update` | `abort` — FR-IM-03.
- [ ] Split multi-contact cells (comma- or newline-separated) into separate `Contact` rows — FR-IM-07.
- [ ] Preview view: upload file → show table of "new", "duplicate (will update)", "duplicate (will skip)", "errors", with row counts and per-row issues. Form to confirm.
- [ ] Commit view: re-validates, runs import inside a transaction, creates an `ImportBatch`.
- [ ] Admin-only access. Add a custom URL like `/admin/import/` and a link from the admin index.
- [ ] CLI fallback: `manage.py import_leads <file> --mapping google_sheet_v1 --on-duplicate skip` — useful for ops and for tests.

### Tests
- [ ] Import the real `docs/sample-leads.xlsx` fixture and assert expected company count, contact count, PRBriefing fields populated.
- [ ] Re-import same file with `skip` → no new rows.
- [ ] Re-import same file with `update` → existing rows updated, no duplicates.
- [ ] Row with two contacts in one cell → two Contact records.
- [ ] Row with malformed domain → still imports, domain blank, flagged in errors.
- [ ] Row missing company name → row rejected, error captured in ImportBatch.

**Acceptance:** Upload the real sample file through the admin import UI, see a preview, confirm, see all rows imported, ImportBatch shows correct counts.

---

## Phase 3 — Web UI

**Goal:** A working CRUD UI for the daily PR-rep workflow. List, detail, activity logging, letter export.

References: §3.4 (FR-PH-01..03, FR-LT-01..03, FR-LI-01..03, FR-EM-01..03, FR-CB-01..03), §3.6 (FR-LI-LST-01..04), §3.8 (FR-I18N-01..03).

- [ ] Login view + logout (use Django's `django.contrib.auth.views`).
- [ ] Language switcher in the header, persisted on the user profile and respected on every request.
- [ ] Lead list view at `/leads/`:
  - Filters: stage, priority, fit, industry, location, owner, last-activity-channel, last-activity-range — FR-LI-LST-02.
  - Full-text search across company, domain, contact names, notes — FR-LI-LST-01.
  - Configurable columns persisted per user — FR-LI-LST-03.
  - CSV/XLSX export of current filter — FR-LI-LST-04.
  - Multi-select with bulk actions: "Export for letter" and "Stage transition".
- [ ] Lead detail view at `/leads/<id>/`:
  - Header with company, domain, stage, priority, fit, owner.
  - Tabs: PR Briefing | Contacts | Activities | History.
  - Activity timeline (FR-CB-01): newest first, channel icon, who, when, outcome, note.
  - Quick-action buttons: Log call, Log email, Log LinkedIn, Log letter, Transition stage.
- [ ] Activity logging forms — one per channel:
  - **Phone** (FR-PH-01..03): date/time defaulting to now, contact dropdown, direction, outcome, duration, note.
  - **Letter** (FR-LT-01..02): typically created by the export flow, but a manual form for one-offs.
  - **LinkedIn** (FR-LI-01..03): activity type (message / connection / comment / reaction), contact, note, link to external profile opens in new tab.
  - **Email** (FR-EM-01..03): subject, recipient (autofilled `mailto:` link), note. No SMTP send.
- [ ] Stage transition dialog: target stage dropdown, optional comment, special UX when target is an archive stage offering data reduction.
- [ ] Letter export (FR-LT-01): bulk action on the list view → generate XLSX with merge fields (company, salutation, first/last name, position, street, postcode, city — see Open Items below), then offer to bulk-log "letter sent" Activities (FR-LT-02).
- [ ] German + English translations for all UI strings. Run `makemessages -l en` and `makemessages -l de`, complete the .po files, `compilemessages`.

### Tests
- [ ] List view filters narrow results correctly.
- [ ] Permission tests: Read-only can't access activity logging forms.
- [ ] Letter export downloads a valid XLSX with the right columns.
- [ ] "Mark letter sent" creates one Activity per selected lead.
- [ ] Stage transition to archive stage offers data reduction; declining keeps data; accepting reduces it.
- [ ] Both languages render without missing translations on key views.

**Acceptance:** A PR-Rep can log into a clean install, see the imported leads, filter them, open one, log a call, transition stages, and export a letter batch — all bilingual.

---

## Phase 4 — Statistics

**Goal:** All seven stats reports from FR-ST.

References: §3.5 (FR-ST-01..07).

- [ ] Dashboard route `/stats/`.
- [ ] Use `django-q2` scheduled jobs to pre-aggregate counts daily, cache results.
- [ ] Charts: use Chart.js from CDN or a small server-rendered approach (SVG via Python). Pick one, document why.
- [ ] Reports:
  - Pipeline funnel (FR-ST-01)
  - Activities per channel over period (FR-ST-02)
  - Activities per user and channel (FR-ST-03)
  - Aging in stage (FR-ST-04)
  - Stage conversion rates and avg dwell time (FR-ST-05)
  - Priority/fit distribution (FR-ST-06)
- [ ] CSV export for each (FR-ST-07).
- [ ] Date-range picker shared across reports.

### Tests
- [ ] Each report renders with seeded data and shows the expected numbers.
- [ ] CSV export round-trips correctly.

**Acceptance:** Stats dashboard shows correct numbers for the imported real data; all reports exportable.

---

## Phase 5 — Deployment

**Goal:** A fresh Ubuntu 24.04 host with Postgres and certbot pre-installed can be brought up with two scripts and a few configuration files.

References: §5.2 (TR-SU-01..05), §5.3 (TR-DP-01..14), §5.4 (TR-SD-01..05), §5.5 (TR-NX-01..05).

- [ ] `deploy/create_service_user.sh` per TR-DP-01..07. Run as root, idempotent, sets up `insyrtcrm` user, `/opt/insyrtcrm`, locked shell, GitHub PAT in git-credentials, git credential helper.
- [ ] `deploy/deploy.sh` per TR-DP-08..14. Run as `insyrtcrm` via sudo, takes a git ref, pulls, `uv sync`, `migrate`, `collectstatic`, daemon-reload, restart services, health check.
- [ ] `deploy/systemd/insyrtcrm.service`: uvicorn under `insyrtcrm` user, binds 127.0.0.1:8000, EnvironmentFile=/etc/insyrtcrm/insyrtcrm.env, Restart=on-failure.
- [ ] `deploy/systemd/insyrtcrm-worker.service`: `manage.py qcluster` under same user.
- [ ] `deploy/nginx/insyrtcrm.conf`: 443 → 127.0.0.1:8000, 80 → 301 redirect (except `/.well-known/acme-challenge/`), HSTS + security headers, static at `/opt/insyrtcrm/static/`.
- [ ] Sample `insyrtcrm.env.example` with all required vars, no real secrets.
- [ ] Ops guide in `docs/operations.md`: first-time install, deploy, token rotation (90 days, TR-SU-04), backup/restore for Postgres, log access via journalctl.

### Tests
- [ ] Lint scripts with `shellcheck`. Wire shellcheck into CI for `deploy/*.sh`.
- [ ] Manual checklist test on a fresh VM (document the result in the PR).

**Acceptance:** Documented walk-through from a fresh Ubuntu 24.04 host with Postgres and certbot pre-installed to a running system reachable via HTTPS. Two scripts, one env file, one nginx config.

---

## Open Items (must resolve before the relevant phase)

These are flagged in §8 of the requirements and should be answered before they block work:

- **Structured address fields** (before Phase 3, letter export): split `location` into street / postcode / city / country at import time, or add structured fields and migrate. Decision: ___
- **Industry / tech focus**: controlled list or free text? Decision: ___
- **Lead owner cardinality**: single user or multiple? Decision: ___
- **Automatic data reduction**: after N days in archive stage, or admin-triggered only? Decision: ___
- **MFA scope** (FR-US-04): in v1 or Phase 2? Decision: ___

When deciding, edit `docs/requirements.md` first, then proceed.
