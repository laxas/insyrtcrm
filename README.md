# insyrtcrm

Internal CRM for Insyrt — replaces the Google Sheet lead management workflow.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- PostgreSQL 16
- Redis

## Local Setup

### 1. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Start PostgreSQL and Redis (Docker)

```yaml
# docker-compose.yml (dev only)
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: insyrtcrm
      POSTGRES_USER: insyrtcrm
      POSTGRES_PASSWORD: insyrtcrm
    ports:
      - "5432:5432"
  redis:
    image: redis:7
    ports:
      - "6379:6379"
```

```bash
docker compose up -d
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your local values
```

### 5. Run migrations and create a superuser

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

### 6. Start the dev server

```bash
uv run python manage.py runserver
```

Open [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/).

### 7. Start the background worker (optional for Phase 0)

```bash
uv run python manage.py qcluster
```

## Running Tests

```bash
uv run pytest
```

With coverage:

```bash
uv run pytest --cov=apps --cov-report=term-missing
```

## Linting

```bash
uv run ruff check .
uv run ruff format --check .
```

## Health Check

`GET /health/` returns `{"status": "ok"}` — used by the deploy script.
