-- Rollback for migration 030: drop password_reset_tokens.
--
-- Safe only if no in-flight reset flow is relying on the table.
-- After this rollback, /auth/password-reset will 500 with UndefinedTableError
-- again until the table is recreated.
--
-- Dropping the table automatically drops its indexes (idx_password_reset_tokens_*).
-- No manual DROP INDEX needed.

BEGIN;

DROP TABLE IF EXISTS password_reset_tokens;

COMMIT;
