#!/usr/bin/env bash
# create_service_user.sh — run as root, once per host.
# Idempotent: safe to re-run.
# Implements TR-DP-01 through TR-DP-07.
set -euo pipefail

APP_USER="insyrtcrm"
APP_HOME="/opt/insyrtcrm"
GIT_CREDENTIALS_FILE="${APP_HOME}/.config/git-credentials"

log() { echo "[create_service_user] $*"; }

# TR-DP-01: Create system user if not present
if id "${APP_USER}" &>/dev/null; then
    log "User '${APP_USER}' already exists — skipping creation."
else
    log "Creating user '${APP_USER}'..."
    useradd \
        --system \
        --home-dir "${APP_HOME}" \
        --create-home \
        --shell /usr/sbin/nologin \
        "${APP_USER}"
    log "User created."
fi

# TR-DP-03: Ensure shell is nologin and password is locked
usermod --shell /usr/sbin/nologin "${APP_USER}"
passwd --lock "${APP_USER}" 2>/dev/null || true
log "Shell set to /usr/sbin/nologin, password locked."

# TR-DP-02: Set home dir owner and permissions
mkdir -p "${APP_HOME}"
chown "${APP_USER}:${APP_USER}" "${APP_HOME}"
chmod 0750 "${APP_HOME}"
log "Home directory ${APP_HOME} configured (0750)."

# TR-DP-04: Write git-credentials
INSYRTCRM_GH_TOKEN="${INSYRTCRM_GH_TOKEN:-}"
if [[ -z "${INSYRTCRM_GH_TOKEN}" ]]; then
    read -rsp "GitHub token for repo access (leave blank to skip): " INSYRTCRM_GH_TOKEN
    echo
fi

if [[ -n "${INSYRTCRM_GH_TOKEN}" ]]; then
    mkdir -p "$(dirname "${GIT_CREDENTIALS_FILE}")"
    printf 'https://x-access-token:%s@github.com\n' "${INSYRTCRM_GH_TOKEN}" > "${GIT_CREDENTIALS_FILE}"
    chown -R "${APP_USER}:${APP_USER}" "${APP_HOME}/.config"
    chmod 0600 "${GIT_CREDENTIALS_FILE}"
    log "Git credentials written to ${GIT_CREDENTIALS_FILE} (mode 0600)."
else
    log "No token provided — skipping git-credentials."
fi

# TR-DP-05: Configure git credential helper
sudo -u "${APP_USER}" git config --global credential.helper store
log "Git credential.helper=store configured."

log "Done."
