#!/usr/bin/env bash
# deploy.sh — run as croessmann (or any sudo-capable user).
# Idempotent. Uses the calling user's SSH key for git authentication.
# Does NOT restart services on pre-restart failure (TR-DP-14).
set -euo pipefail

REPO_DIR="/srv/python/insyrtcrm"
REPO_URL="${REPO_URL:-git@github.com:laxas/insyrtcrm.git}"
VENV="${REPO_DIR}/.venv"
MANAGE="${VENV}/bin/python ${REPO_DIR}/manage.py"
HEALTH_URL="${HEALTH_URL:-https://insyrtcrm.laxas.de/health/}"
LOCAL_HEALTH_URL="http://127.0.0.1:8012/health/"
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

# 2. Validate secrets file — Django reads it directly via read_env() in settings/base.py,
#    so we never source it into bash (values may contain shell-special characters).
if [[ ! -f "${ENV_FILE}" ]]; then
    die "${ENV_FILE} not found — run create_service_user.sh and fill in secrets first."
fi
if [[ ! -r "${ENV_FILE}" ]]; then
    die "${ENV_FILE} exists but is not readable by $(whoami). Run: sudo bash deploy/create_service_user.sh"
fi

# Failsafe: abort early if required variables are missing or empty.
# grep -qE avoids shell-interpreting the values entirely.
_required_vars=(SECRET_KEY DB_NAME DB_USER DB_PASSWORD)
_missing=()
for _var in "${_required_vars[@]}"; do
    grep -qE "^${_var}=.+" "${ENV_FILE}" || _missing+=("${_var}")
done
if [[ ${#_missing[@]} -gt 0 ]]; then
    die "Missing required variable(s) in ${ENV_FILE}: ${_missing[*]}"
fi

# Always use prod settings for deploys. Django reads all other secrets from
# ${ENV_FILE} via environ.Env.read_env() in insyrtcrm/settings/base.py.
export DJANGO_SETTINGS_MODULE=insyrtcrm.settings.prod
log "Config OK — DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}"

# 3. Dependencies
log "Syncing dependencies (uv sync)..."
cd "${REPO_DIR}"

# Put Python in /opt so the insyrtcrm service user can reach it.
# If the venv currently points into a user home directory, blow it away and
# let uv recreate it from the system-accessible location.
export UV_PYTHON_INSTALL_DIR=/opt/uv-python
VENV_PYTHON=$(readlink -f "${REPO_DIR}/.venv/bin/python" 2>/dev/null || true)
if [[ "${VENV_PYTHON}" == /home/* ]]; then
    log "Venv Python is under /home — recreating venv under /opt/uv-python..."
    rm -rf "${REPO_DIR}/.venv"
fi
uv sync --frozen --no-dev

# Transfer venv ownership to the service user so systemd can exec the binaries.
sudo chown -R insyrtcrm:insyrtcrm "${REPO_DIR}/.venv"
# Make the Python runtime world-traversable (lives in /opt, not a home dir).
sudo chmod -R o+rx /opt/uv-python
# The project root must be traversable by the service user.
chmod o+rx "${REPO_DIR}"

# 4. Django
log "Running migrations..."
${MANAGE} migrate --noinput

log "Collecting static files..."
${MANAGE} collectstatic --noinput --clear

# 5. Services — install units and nginx config if missing, then restart
SYSTEMD_DIR="/etc/systemd/system"
for unit in insyrtcrm.service insyrtcrm-worker.service; do
    if [[ ! -f "${SYSTEMD_DIR}/${unit}" ]]; then
        log "Installing ${unit}..."
        sudo cp "${REPO_DIR}/deploy/systemd/${unit}" "${SYSTEMD_DIR}/${unit}"
    fi
done

NGINX_CONF="/etc/nginx/sites-available/insyrtcrm"
if [[ ! -f "${NGINX_CONF}" ]]; then
    log "Installing nginx config..."
    sudo cp "${REPO_DIR}/deploy/nginx/insyrtcrm.conf" "${NGINX_CONF}"
    sudo ln -sf "${NGINX_CONF}" /etc/nginx/sites-enabled/insyrtcrm
    sudo nginx -t
    sudo systemctl reload nginx
fi

sudo systemctl daemon-reload
sudo systemctl enable --now insyrtcrm.service insyrtcrm-worker.service
sudo systemctl restart insyrtcrm.service insyrtcrm-worker.service

# 6. Health checks — local first (direct to uvicorn), then via nginx+TLS
log "Running local health check at ${LOCAL_HEALTH_URL}..."
LOCAL_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" \
    --max-time 10 "${LOCAL_HEALTH_URL}" || echo "000")
if [[ "${LOCAL_STATUS}" != "200" ]]; then
    die "Local health check returned HTTP ${LOCAL_STATUS} — check journalctl -u insyrtcrm.service"
fi
log "Local health check passed (HTTP 200)."

log "Running external health check at ${HEALTH_URL}..."
EXT_STATUS=$(curl --silent --output /dev/null --write-out "%{http_code}" \
    --max-time 10 "${HEALTH_URL}" || echo "000")
if [[ "${EXT_STATUS}" != "200" ]]; then
    die "External health check returned HTTP ${EXT_STATUS} — check nginx config and TLS cert"
fi
log "External health check passed (HTTP 200)."
log "Deploy of '${GIT_REF}' complete."
