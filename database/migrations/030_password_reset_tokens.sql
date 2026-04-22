-- Migration 030: password_reset_tokens
-- Purpose: CREATE TABLE for the password-reset flow. The table was defined in
-- schema.sql (lines 349-358) but never promoted to a numbered migration, so
-- production (bootstrapped via sequential migrations) never had it created.
-- Consequence before this migration: /auth/password-reset → UndefinedTableError
-- (asyncpg) → HTTP 500 on every reset request.
--
-- Idempotent: IF NOT EXISTS guards on table and indexes allow safe re-run.
-- Atomic: wrapped in an explicit transaction so a failure mid-script rolls
-- back cleanly rather than leaving a half-built schema.
-- Extension uuid-ossp is assumed available (declared in schema.sql:8).

BEGIN;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL,
    expires_at  TIMESTAMPTZ  NOT NULL,
    used        BOOLEAN      DEFAULT FALSE,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- UNIQUE index on token_hash.
-- Query patterns in app/core/db/_platform.py:
--   verify_reset_token: WHERE token_hash = $1 AND used = FALSE AND expires_at > NOW()
--   use_reset_token:    WHERE token_hash = $1
-- token_hash is derived from generate_secure_token() (crypto-random). Uniqueness
-- is both an integrity guarantee (collision = RNG bug, fail loud) and the
-- primary lookup path for verify/use. No composite index is warranted — the
-- hash alone narrows to ≤1 row; the used/expires_at filters run on that row.
CREATE UNIQUE INDEX IF NOT EXISTS idx_password_reset_tokens_token_hash
    ON password_reset_tokens (token_hash);

-- Index on user_id (FK).
-- Rationale: ON DELETE CASCADE means Postgres scans this table on every DELETE
-- from users. Without this index, user deletion degrades to a sequential scan
-- here. Cheap to maintain (user_id is written once per row) and future-proofs
-- admin flows that may list/invalidate tokens for a given user.
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id
    ON password_reset_tokens (user_id);

COMMENT ON TABLE password_reset_tokens IS
  'One-time password-reset tokens issued by /auth/password-reset and consumed by /auth/password-reset/confirm. Rows are not auto-pruned — a periodic cleanup job for expired/used rows is a backlog item.';

COMMIT;
