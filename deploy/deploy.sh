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

# Force Python into /opt/uv-python (not into the deploy user's home directory)
# so the insyrtcrm service user can reach the interpreter.
export UV_PYTHON_INSTALL_DIR=/opt/uv-python
sudo mkdir -p /opt/uv-python
sudo chown "${USER}:insyrtcrm" /opt/uv-python
sudo chmod 775 /opt/uv-python
sudo rm -rf "${REPO_DIR}/.venv"
uv python install 3.14
uv sync --frozen --no-dev

# 3b. Frontend assets — rebuild the purged Tailwind stylesheet from the current
#     templates before collectstatic, so the committed CSS can never go stale.
#     Uses the standalone Tailwind CLI (no Node toolchain). The ~43 MB binary is
#     cached in bin/ (gitignored, survives `git reset --hard`) and only fetched
#     when missing. Keep TAILWIND_VERSION in sync with the Makefile.
TAILWIND_VERSION="v3.4.17"
TAILWIND_BIN="${REPO_DIR}/bin/tailwindcss"
if [[ ! -x "${TAILWIND_BIN}" ]]; then
    log "Downloading Tailwind CLI ${TAILWIND_VERSION}..."
    mkdir -p "${REPO_DIR}/bin"
    curl -sSL -o "${TAILWIND_BIN}" \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-x64"
    chmod +x "${TAILWIND_BIN}"
fi
log "Building Tailwind CSS..."
"${TAILWIND_BIN}" -c "${REPO_DIR}/tailwind.config.js" \
    -i "${REPO_DIR}/tailwind/input.css" \
    -o "${REPO_DIR}/assets/css/app.css" --minify

# Mirror the permission pattern used by other projects on this server:
# owner=croessmann, group=insyrtcrm, with group r+X on all files.
# The insyrtcrm service user is in the insyrtcrm group, so it can read and
# execute everything without needing ownership of individual files.
sudo chgrp -R insyrtcrm "${REPO_DIR}"
sudo chmod -R g+rX "${REPO_DIR}"
[[ -d /opt/uv-python ]] && sudo chmod -R o+rx /opt/uv-python

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

# 6. Health checks — retry for up to 30 s to give uvicorn time to start
_wait_for_http() {
    local url="$1" label="$2" tries=6 status
    for ((i=1; i<=tries; i++)); do
        status=$(curl --silent --output /dev/null --write-out "%{http_code}" \
            --max-time 5 "${url}" 2>/dev/null || echo "000")
        [[ "${status}" == "200" ]] && { log "${label} passed (HTTP 200)."; return 0; }
        log "${label}: attempt ${i}/${tries} returned HTTP ${status} — waiting 5 s..."
        sleep 5
    done
    die "${label} still returning HTTP ${status} after ${tries} attempts"
}

_wait_for_http "${LOCAL_HEALTH_URL}" "Local health check (uvicorn)"
_wait_for_http "${HEALTH_URL}"       "External health check (nginx+TLS)"
log "Deploy of '${GIT_REF}' complete."
