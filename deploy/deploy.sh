#!/usr/bin/env bash
# deploy.sh — run as the insyrtcrm service user via: sudo -u insyrtcrm deploy.sh [ref]
# Idempotent, does NOT restart services on failure (TR-DP-14).
# Implements TR-DP-08 through TR-DP-14.
set -euo pipefail

APP_HOME="/opt/insyrtcrm"
REPO_URL="${REPO_URL:-https://github.com/insyrt/insyrtcrm.git}"
REPO_DIR="${APP_HOME}/repo"
VENV="${REPO_DIR}/.venv"
MANAGE="${VENV}/bin/python ${REPO_DIR}/manage.py"
HEALTH_URL="${HEALTH_URL:-https://localhost/health/}"
GIT_REF="${1:-main}"

log() { echo "[deploy] $*"; }
die() { echo "[deploy] ERROR: $*" >&2; exit 1; }

log "Deploying ref '${GIT_REF}'..."

# TR-DP-09: Clone or pull repo
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

# TR-DP-10: Install/update dependencies
log "Syncing dependencies (uv sync)..."
cd "${REPO_DIR}"
uv sync --frozen --no-dev

# TR-DP-11: Migrate and collect static files
log "Running migrations..."
DJANGO_SETTINGS_MODULE=insyrtcrm.settings.prod \
    ${MANAGE} migrate --noinput

log "Collecting static files..."
DJANGO_SETTINGS_MODULE=insyrtcrm.settings.prod \
    ${MANAGE} collectstatic --noinput --clear

# TR-DP-12: Reload systemd and restart services
log "Reloading systemd and restarting services..."
sudo systemctl daemon-reload
sudo systemctl restart insyrtcrm.service insyrtcrm-worker.service

# TR-DP-13: Health check
log "Running health check at ${HEALTH_URL}..."
HTTP_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" \
    --max-time 10 --insecure "${HEALTH_URL}" || echo "000")

if [[ "${HTTP_STATUS}" != "200" ]]; then
    die "Health check returned HTTP ${HTTP_STATUS} — deploy may have failed!"
fi

log "Health check passed (HTTP 200)."
log "Deploy of '${GIT_REF}' complete."
