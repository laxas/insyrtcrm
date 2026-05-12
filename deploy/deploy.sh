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
ENV_FILE="/etc/insyrtcrm/insyrtcrm.env"

log() { echo "[deploy] $*"; }
die() { echo "[deploy] ERROR: $*" >&2; exit 1; }

# 1. Pull latest code first so we're always deploying the current state
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

log "Deploying ref '${GIT_REF}'..."

# 2. Load secrets — env file is owned by the deploy user (group insyrtcrm, mode 0640)
if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    set +a
else
    die "${ENV_FILE} not found — run create_service_user.sh and fill in secrets first."
fi

# 3. Dependencies
log "Syncing dependencies (uv sync)..."
cd "${REPO_DIR}"
uv sync --frozen --no-dev

# 4. Django
log "Running migrations..."
${MANAGE} migrate --noinput

log "Collecting static files..."
${MANAGE} collectstatic --noinput --clear

# 5. Services — only restart after all pre-restart steps have succeeded
log "Reloading systemd and restarting services..."
sudo systemctl daemon-reload
sudo systemctl restart insyrtcrm.service insyrtcrm-worker.service

# 6. Health check
log "Running health check at ${HEALTH_URL}..."
HTTP_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" \
    --max-time 10 --insecure "${HEALTH_URL}" || echo "000")

if [[ "${HTTP_STATUS}" != "200" ]]; then
    die "Health check returned HTTP ${HTTP_STATUS} — check journalctl -u insyrtcrm.service"
fi

log "Health check passed (HTTP 200)."
log "Deploy of '${GIT_REF}' complete."
