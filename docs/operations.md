# Operations Guide

Target: Ubuntu 24.04 LTS with PostgreSQL 16, Redis, certbot, nginx, and `uv` pre-installed.

---

## First-time installation

### 1. Create the service user and directory skeleton

```bash
sudo bash deploy/create_service_user.sh
```

This creates the `insyrtcrm` system user (nologin, locked password), sets up `/opt/insyrtcrm/` and the `/etc/insyrtcrm/insyrtcrm.env` placeholder.

### 2. Create the PostgreSQL database

```bash
sudo bash deploy/create_db.sh
```

Prompts for the DB password if not set via `DB_PASSWORD` env var.

### 3. Fill in secrets

```bash
sudo nano /etc/insyrtcrm/insyrtcrm.env
```

Use `insyrtcrm.env.example` as a reference. Required fields:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key — generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `ALLOWED_HOSTS` | Comma-separated list of hostnames (e.g. `crm.example.com`) |
| `DB_PASSWORD` | Password for the `insyrtcrm` Postgres role |
| `REDIS_URL` | Redis URL, default `redis://localhost:6379/0` |

### 4. Install systemd units

```bash
sudo cp deploy/systemd/insyrtcrm.service /etc/systemd/system/
sudo cp deploy/systemd/insyrtcrm-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable insyrtcrm.service insyrtcrm-worker.service
```

### 5. Install nginx config

Replace `HOSTNAME` with the actual domain name, then:

```bash
sudo cp deploy/nginx/insyrtcrm.conf /etc/nginx/sites-available/insyrtcrm
# Edit the file: replace HOSTNAME with the real domain
sudo nano /etc/nginx/sites-available/insyrtcrm
sudo ln -sf /etc/nginx/sites-available/insyrtcrm /etc/nginx/sites-enabled/insyrtcrm
sudo nginx -t && sudo systemctl reload nginx
```

### 6. Obtain TLS certificate

```bash
sudo certbot --nginx -d crm.example.com
```

### 7. First deploy

```bash
bash deploy/deploy.sh main
```

This clones the repo, installs deps, runs migrations, collects static files, and starts services.

### 8. Create the initial superuser

```bash
/opt/insyrtcrm/repo/.venv/bin/python /opt/insyrtcrm/repo/manage.py createsuperuser
```

### 9. Set up the stats cache schedule

```bash
/opt/insyrtcrm/repo/.venv/bin/python /opt/insyrtcrm/repo/manage.py setup_q_schedules
```

---

## Routine deploys

```bash
bash deploy/deploy.sh main
# or a specific tag:
bash deploy/deploy.sh v1.2.0
```

The script is idempotent. It will pull, migrate, collectstatic, restart, and health-check.

---

## GitHub token rotation (every 90 days)

The deploy uses your personal SSH key (`~/.ssh/`) for git authentication. No token rotation is required for deployment. If you rotate your SSH key, update `~/.ssh/authorized_keys` on the server accordingly.

---

## Log access

```bash
# Application logs
sudo journalctl -u insyrtcrm.service -f

# Worker logs
sudo journalctl -u insyrtcrm-worker.service -f

# Last 200 lines
sudo journalctl -u insyrtcrm.service -n 200 --no-pager

# nginx access/error logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

---

## PostgreSQL backup and restore

### Backup

```bash
sudo -u postgres pg_dump insyrtcrm | gzip > insyrtcrm_$(date +%Y%m%d_%H%M%S).sql.gz
```

Store backups off-server (e.g. `scp` to a backup host or S3-compatible storage).

### Restore

```bash
gunzip -c insyrtcrm_TIMESTAMP.sql.gz | sudo -u postgres psql insyrtcrm
```

For a clean restore:

```bash
sudo -u postgres dropdb insyrtcrm
sudo -u postgres createdb insyrtcrm --owner insyrtcrm
gunzip -c insyrtcrm_TIMESTAMP.sql.gz | sudo -u postgres psql insyrtcrm
```

---

## Redis

Redis runs as a system service. Its data is ephemeral (cache + task queue only — no persistent state). Restart is safe:

```bash
sudo systemctl restart redis
```

---

## Checking service status

```bash
sudo systemctl status insyrtcrm.service insyrtcrm-worker.service
curl -sk https://localhost/health/
```
