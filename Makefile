PYTHON   = uv run python
MANAGE   = $(PYTHON) manage.py
VENV_BIN = .venv/bin

.DEFAULT_GOAL := help

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Dev server ────────────────────────────────────────────────────────────────

.PHONY: run
run: ## Start the development server
	$(MANAGE) runserver

.PHONY: worker
worker: ## Start the Django-Q2 background worker
	$(MANAGE) qcluster

.PHONY: shell
shell: ## Open the Django shell
	$(MANAGE) shell

.PHONY: dbshell
dbshell: ## Open a psql shell for the configured database
	$(MANAGE) dbshell

# ── Database ──────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate: ## Apply all pending migrations
	$(MANAGE) migrate --noinput

.PHONY: migrations
migrations: ## Generate new migrations (dry-run first)
	$(MANAGE) makemigrations --dry-run --check && $(MANAGE) makemigrations

.PHONY: migrations-check
migrations-check: ## Fail if there are unapplied model changes (CI use)
	$(MANAGE) makemigrations --check --dry-run

.PHONY: superuser
superuser: ## Create a Django superuser interactively
	$(MANAGE) createsuperuser

# ── Static files & i18n ───────────────────────────────────────────────────────

.PHONY: static
static: ## Collect static files
	$(MANAGE) collectstatic --noinput --clear

.PHONY: messages
messages: ## Extract translatable strings into .po files
	$(MANAGE) makemessages --all --ignore=.venv

.PHONY: compilemessages
compilemessages: ## Compile .po files into .mo files
	$(MANAGE) compilemessages

# ── Background jobs ───────────────────────────────────────────────────────────

.PHONY: setup-schedules
setup-schedules: ## Register Django-Q2 periodic schedules
	$(MANAGE) setup_q_schedules

# ── Code quality ──────────────────────────────────────────────────────────────

.PHONY: lint
lint: ## Run ruff linter
	uv run ruff check .

.PHONY: format
format: ## Auto-format code with ruff
	uv run ruff format .

.PHONY: format-check
format-check: ## Check formatting without writing changes (CI use)
	uv run ruff format --check .

.PHONY: check
check: ## Run Django system checks
	$(MANAGE) check

.PHONY: ci
ci: lint format-check migrations-check check test ## Run all CI checks in one shot

# ── Tests ─────────────────────────────────────────────────────────────────────

.PHONY: test
test: ## Run the test suite
	uv run pytest

.PHONY: test-fast
test-fast: ## Run tests, stop at first failure
	uv run pytest -x

.PHONY: coverage
coverage: ## Run tests with coverage report
	uv run pytest --cov=apps --cov-report=term-missing

# ── Dependencies ──────────────────────────────────────────────────────────────

.PHONY: sync
sync: ## Sync dependencies from uv.lock (including dev)
	uv sync

.PHONY: sync-prod
sync-prod: ## Sync production dependencies only (no dev extras)
	uv sync --frozen --no-dev

# ── Logs (production) ─────────────────────────────────────────────────────────

.PHONY: logs
logs: ## Tail the application service log
	sudo journalctl -u insyrtcrm.service -f

.PHONY: logs-worker
logs-worker: ## Tail the worker service log
	sudo journalctl -u insyrtcrm-worker.service -f

.PHONY: logs-nginx
logs-nginx: ## Tail the nginx access log
	sudo tail -f /var/log/nginx/access.log

.PHONY: status
status: ## Show systemd service status
	sudo systemctl status insyrtcrm.service insyrtcrm-worker.service

# ── Data import ───────────────────────────────────────────────────────────────

.PHONY: import
import: ## Import leads: make import FILE=path/to/leads.xlsx
ifndef FILE
	$(error FILE is required — usage: make import FILE=path/to/leads.xlsx)
endif
	$(MANAGE) import_leads "$(FILE)"

.PHONY: import-dry
import-dry: ## Preview import without writing: make import-dry FILE=path/to/leads.xlsx
ifndef FILE
	$(error FILE is required — usage: make import-dry FILE=path/to/leads.xlsx)
endif
	$(MANAGE) import_leads "$(FILE)" --dry-run

# ── Deployment ────────────────────────────────────────────────────────────────

.PHONY: deploy
deploy: ## Deploy the main branch to production
	bash deploy/deploy.sh main
