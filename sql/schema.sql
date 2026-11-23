-- TicketDesk database schema (PostgreSQL 14+).
-- Safe to run more than once: every statement uses IF NOT EXISTS.
-- Run with:  python -m scripts.init_db      (uses the app's own DB settings)
--       or:  psql "$DATABASE_URL" -f sql/schema.sql

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    full_name     VARCHAR(120) NOT NULL DEFAULT '',
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(16)  NOT NULL DEFAULT 'user'
                  CHECK (role IN ('user', 'agent', 'admin')),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tickets (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    description TEXT         NOT NULL,
    category    VARCHAR(40)  NOT NULL DEFAULT 'Other',
    priority    VARCHAR(16)  NOT NULL DEFAULT 'Medium'
                CHECK (priority IN ('Low', 'Medium', 'High', 'Critical')),
    status      VARCHAR(16)  NOT NULL DEFAULT 'Open'
                CHECK (status IN ('Open', 'In Progress', 'Resolved', 'Closed')),
    created_by  INTEGER      NOT NULL REFERENCES users (id),
    assigned_to INTEGER      REFERENCES users (id),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tickets_status     ON tickets (status);
CREATE INDEX IF NOT EXISTS ix_tickets_created_by ON tickets (created_by);
CREATE INDEX IF NOT EXISTS ix_tickets_updated_at ON tickets (updated_at DESC);

CREATE TABLE IF NOT EXISTS attachments (
    id            SERIAL PRIMARY KEY,
    ticket_id     INTEGER      NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    original_name VARCHAR(255) NOT NULL,
    storage_key   VARCHAR(512) NOT NULL UNIQUE,
    content_type  VARCHAR(127) NOT NULL DEFAULT 'application/octet-stream',
    size_bytes    BIGINT       NOT NULL,
    uploaded_by   INTEGER      NOT NULL REFERENCES users (id),
    uploaded_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_attachments_ticket ON attachments (ticket_id);

CREATE TABLE IF NOT EXISTS ticket_history (
    id          SERIAL PRIMARY KEY,
    ticket_id   INTEGER     NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    from_status VARCHAR(16),
    to_status   VARCHAR(16) NOT NULL,
    note        TEXT        NOT NULL DEFAULT '',
    changed_by  INTEGER     NOT NULL REFERENCES users (id),
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_history_ticket ON ticket_history (ticket_id);
