#!/bin/sh
set -eu

# La imagen oficial ejecuta este script solo cuando el volumen está vacío.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=app_user="$DB_USER" --set=app_password="$DB_PASSWORD" <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';
CREATE TABLE notes (
    id BIGSERIAL PRIMARY KEY,
    content VARCHAR(500) NOT NULL CHECK (length(trim(content)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
GRANT USAGE ON SCHEMA public TO :"app_user";
GRANT SELECT, INSERT ON notes TO :"app_user";
GRANT USAGE, SELECT ON SEQUENCE notes_id_seq TO :"app_user";
SQL
