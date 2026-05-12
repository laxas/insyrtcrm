#!/usr/bin/env bash
# deploy.sh — run as croessmann (or any sudo-capable user).
# Idempotent. Uses the calling user's SSH key for git authentication.
# Does NOT restart services on pre-restart failure (TR-DP-14).
set -euo pipefail

APP_DIR="/opt/insyrtcrm"
REPO_DIR="${APP_DIR}/repo"
REPO_URL="${REPO_URL:-git@github.com:laxas/insyrtcrm.git}"
VENV="${REPO_DIR}/.venv"
MANAGE="${VENV}/bin/python ${REPO_DIR}/manage.py"
HEALTH_URL="${HEALTH_URL:-https://localhost/health/}"
GIT_REF="${1:-main}"

log() { echo "[deploy] $*"; }
die() { echo "[deploy] ERROR: $*" >&2; exit 1; }

log "Deploying ref '${GIT_REF}'..."

# Clone or pull
if [[ -d "${REPO_DIR}/.git" ]]; then
    log "Fetching latest changes..."
    git -C "${REPO_DIR}" fetch --tags origin
    git -C "${REPO_DIR}" checkout "${GIT_REF}"
    git -C "${REPO_DIR}" reset --hard "origin/${GIT_REF}" 2>/dev/null \
        || git -C "${REPO_DIR}" reset --hard "${GIT_REF}"
else
    log "Cloning repository..."
    git clone "${REPO_URL}" "${REPO_DIR}"
    git -C "${REPO_DIR}" checkout "${GIT_REF}"
fi

# Dependencies
log "Syncing dependencies (uv sync)..."
cd "${REPO_DIR}"
uv sync --frozen --no-dev

# Django
log "Running migrations..."
DJANGO_SETTINGS_MODULE=insyrtcrm.settings.prod ${MANAGE} migrate --noinput

log "Collecting static files..."
DJANGO_SETTINGS_MODULE=insyrtcrm.settings.prod ${MANAGE} collectstatic --noinput --clear

# Services — only restart after all pre-restart steps have succeeded
log "Reloading systemd and restarting services..."
sudo systemctl daemon-reload
sudo systemctl restart insyrtcrm.service insyrtcrm-worker.service

# Health check
log "Running health check at ${HEALTH_URL}..."
HTTP_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" \
    --max-time 10 --insecure "${HEALTH_URL}" || echo "000")

if [[ "${HTTP_STATUS}" != "200" ]]; then
    die "Health check returned HTTP ${HTTP_STATUS} — check journalctl -u insyrtcrm.service"
fi

log "Health check passed (HTTP 200)."
log "Deploy of '${GIT_REF}' complete."
