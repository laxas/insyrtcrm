#!/usr/bin/env bash
# create_db.sh — run as root (or a user with sudo access to postgres).
# Creates the insyrtcrm PostgreSQL role and database.
# Idempotent: safe to re-run.
set -euo pipefail

DB_NAME="${DB_NAME:-insyrtcrm}"
DB_USER="${DB_USER:-insyrtcrm}"
ENV_FILE="/etc/insyrtcrm/insyrtcrm.env"

# Prefer the password already committed to the env file so the DB role
# always matches what Django uses. Fall back to a manual prompt.
if [[ -z "${DB_PASSWORD:-}" ]] && [[ -r "${ENV_FILE}" ]]; then
    DB_PASSWORD="$(grep -E '^DB_PASSWORD=' "${ENV_FILE}" | cut -d= -f2- | head -1)"
fi

if [[ -z "${DB_PASSWORD:-}" ]]; then
    read -rsp "Password for PostgreSQL role '${DB_USER}': " DB_PASSWORD
    echo
fi

echo "[create_db] Creating role '${DB_USER}' if it does not exist..."
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE "${DB_USER}" LOGIN PASSWORD '${DB_PASSWORD}';
        RAISE NOTICE 'Role ${DB_USER} created.';
    ELSE
        ALTER ROLE "${DB_USER}" LOGIN PASSWORD '${DB_PASSWORD}';
        RAISE NOTICE 'Role ${DB_USER} already exists — password updated.';
    END IF;
END
\$\$;
SQL

echo "[create_db] Creating database '${DB_NAME}' if it does not exist..."
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
SELECT 'CREATE DATABASE "${DB_NAME}" OWNER "${DB_USER}"'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = '${DB_NAME}'
)\gexec
SQL

echo "[create_db] Done. Connection: psql -h localhost -U ${DB_USER} -d ${DB_NAME}"
