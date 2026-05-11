# CLAUDE.md

Project-specific instructions for Claude Code working on **insyrtcrm**.

## Project Summary

insyrtcrm is an internal CRM for Insyrt that manages leads (potential B2B PR customers) and existing customers in one configurable pipeline. It replaces a Google-Sheet-based workflow. The full functional and technical specification lives in `docs/requirements.md` — that file is the source of truth. When the spec and this file conflict, the spec wins, but ping the user before diverging.

## Source of Truth

- `docs/requirements.md` — functional + technical requirements. Reference requirements by ID (e.g. "implement FR-IM-03") in commits and PRs.
- `TASKS.md` — phased delivery plan. Work one phase at a time. Don't start a new phase without explicit approval.
- `docs/sample-leads.xlsx` — real export of the current Google Sheet, used for import testing.

If you think the spec is wrong or ambiguous, propose an edit to `docs/requirements.md` first, get approval, then implement. Don't silently diverge.

## Tech Stack (hard constraints)

These are non-negotiable without explicit user approval:

- **Python 3.14**
- **Django 6** (web framework + admin)
- **uvicorn** as the ASGI server, **nginx** in front as TLS-terminating reverse proxy
- **PostgreSQL 16** (already installed on the target server, do not script its install)
- **Django-Q2** + **Redis** for background jobs
- **uv** for project and dependency management — never `pip install` directly, always `uv add` / `uv sync`. The `uv.lock` file is committed.
- **systemd** for service management on **Ubuntu 24.04 LTS**
- **Let's Encrypt** via the already-installed certbot for TLS — do not script certbot's install

Browser support: current Firefox, Chrome, Edge, Safari. No IE.

## Coding Conventions

### Layout
Follow the repo layout in §5.6 of the spec. Django apps live under `apps/`: `leads`, `activities`, `imports`, `stats`, `accounts`. The Django project package is `insyrtcrm/`. Settings are split: `insyrtcrm/settings/base.py`, `dev.py`, `prod.py`.

### Python style
- Type hints on public functions and Django model methods.
- `ruff` for linting and formatting — config in `pyproject.toml`.
- Docstrings on non-trivial functions, in English.
- Prefer Django's ORM over raw SQL. When raw SQL is necessary, parameterise — never f-string.

### Django
- One model = one migration file at creation time. Don't squash migrations without asking.
- All user-facing strings wrapped in `gettext_lazy` (`_("…")`) from day one. We are bilingual DE/EN, not English-with-translations-added-later.
- Use Django's built-in auth + groups for roles (`Admin`, `PR-Rep`, `Read-only`). No custom permission system.
- Timezone: `TIME_ZONE = "Europe/Berlin"`, `USE_TZ = True`. Store UTC, display Berlin.
- `LANGUAGES = [("de", "Deutsch"), ("en", "English")]`, default `de`.

### Database
- All FK relationships explicit with `on_delete` set deliberately. Default to `PROTECT` for important relationships; `CASCADE` only when the child is truly owned by the parent (e.g. Contact → Company).
- Unique constraints in DB, not just in forms.
- Index foreign keys and frequently filtered columns.

### Tests
- `pytest` + `pytest-django`. No `unittest.TestCase`.
- Factories via `factory_boy`. No fixture JSON files.
- Every model gets at least: creation test, uniqueness test, string representation test.
- Every view gets at least: permission test (allowed role works, denied role gets 403), happy-path test.
- Aim for ≥80% coverage on `apps/`. Don't chase 100%.
- Tests must pass before committing. No `@pytest.mark.skip` without a comment explaining why.

### Frontend
- Django templates + HTMX for interactivity. No SPA, no React, no Vue.
- Use Django's built-in form rendering or `django-crispy-forms` if it gets ugly.
- Tailwind CSS is fine if you want it; plain CSS is also fine. Pick one and stick with it.

## Commands You Should Run

Before claiming a task is done, run all of these and ensure they pass:

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest
```

For running the dev server: `uv run python manage.py runserver`.

For running background workers in dev: `uv run python manage.py qcluster`.

## What's Off-Limits

These are explicitly out of scope for v1 (see §6 of the spec). Don't build them, don't add scaffolding for them, don't add config options for them:

- **No LinkedIn automation, scraping, or API calls.** LinkedIn integration is logging-only, with manual entry by the user.
- **No SMTP sending.** Email workflow is manual logging in v1. The system never sends mail to leads.
- **No automated postal letter dispatch.** Letter workflow is XLSX export for Word mail-merge.
- **No sequence/campaign engine.** Multi-step automation is Phase 2.
- **No external integrations** (calendar, accounting, document storage).
- **No GDPR/compliance modules** (records of processing, subject-access workflows, consent management). The data-reduction routine on archive stage transition (FR-DM-ARCH-01) is the only data-minimisation feature in v1.
- **No multi-tenancy, no SSO, no OAuth.**

If a feature you're working on starts pulling any of these in, stop and ask.

## Service User & Deployment

- Application runs as a dedicated Linux user `insyrtcrm` with no interactive SSH login (TR-SU-02).
- That user has a fine-grained GitHub PAT in `/opt/insyrtcrm/.config/git-credentials` (mode 0600) for pulling the repo.
- `deploy/create_service_user.sh` runs as root once per host. It must be idempotent.
- `deploy/deploy.sh` runs as the service user (`sudo -u insyrtcrm`) for each deploy. It must be idempotent and must not restart services on failure.
- Secrets (Django `SECRET_KEY`, DB password, Redis URL) live in `/etc/insyrtcrm/insyrtcrm.env` (mode 0640, group `insyrtcrm`), referenced by systemd `EnvironmentFile=`.
- Never commit secrets. Never log secrets. Never `print()` secrets in debug code.

## Workflow Expectations

1. **Read before writing.** Re-read the relevant section of `docs/requirements.md` and any existing code before starting.
2. **Plan before coding.** For anything non-trivial, propose a short plan (files to add/change, key decisions) and wait for approval.
3. **Small, reviewable commits.** One logical change per commit. Reference requirement IDs in commit messages: `feat(leads): implement Stage transitions (FR-PL-02)`.
4. **Run the checks above** before declaring done.
5. **Don't touch other phases.** If you're in Phase 1 and notice something needed for Phase 3, leave a `TODO(phase-3):` comment, don't fix it now.
6. **Ask, don't guess.** If the spec is silent on something material, ask. Don't invent.
