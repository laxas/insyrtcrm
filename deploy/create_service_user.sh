#!/usr/bin/env bash
# create_service_user.sh — run as root, once per host.
# Idempotent: safe to re-run.
# Creates the insyrtcrm service user and the directory/file skeleton.
# The deploy user (croessmann) owns the app files; insyrtcrm only runs them.
set -euo pipefail

APP_USER="insyrtcrm"
APP_DIR="/opt/insyrtcrm"
ENV_DIR="/etc/insyrtcrm"
DEPLOY_USER="${SUDO_USER:-croessmann}"

log() { echo "[setup] $*"; }

# 1. Service user — nologin, no home directory needed
if id "${APP_USER}" &>/dev/null; then
    log "User '${APP_USER}' already exists."
else
    log "Creating service user '${APP_USER}'..."
    useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
fi
usermod --shell /usr/sbin/nologin "${APP_USER}"
passwd --lock "${APP_USER}" 2>/dev/null || true
log "Service user '${APP_USER}' configured (nologin, locked password)."

# 2. Application directory — owned by deploy user, world-traversable so
#    the service user can execute the venv binaries.
mkdir -p "${APP_DIR}/static"
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_DIR}"
chmod 755 "${APP_DIR}"
chmod 755 "${APP_DIR}/static"
log "Application directory ${APP_DIR} created (owner: ${DEPLOY_USER})."

# 3. Env file directory — root:insyrtcrm, 0750 so only the service user can read
mkdir -p "${ENV_DIR}"
chown root:"${APP_USER}" "${ENV_DIR}"
chmod 0750 "${ENV_DIR}"

if [[ ! -f "${ENV_DIR}/insyrtcrm.env" ]]; then
    touch "${ENV_DIR}/insyrtcrm.env"
    chown root:"${APP_USER}" "${ENV_DIR}/insyrtcrm.env"
    chmod 0640 "${ENV_DIR}/insyrtcrm.env"
    log "Created empty ${ENV_DIR}/insyrtcrm.env — fill in all values before starting services."
else
    log "${ENV_DIR}/insyrtcrm.env already exists — not modified."
fi

log "Done. Next steps:"
log "  1. Edit ${ENV_DIR}/insyrtcrm.env (see insyrtcrm.env.example)"
log "  2. Run deploy/create_db.sh to create the PostgreSQL role and database"
log "  3. Run deploy/deploy.sh to clone, migrate, and start services"
