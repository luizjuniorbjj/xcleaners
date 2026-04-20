-- Rollback 027: drop client invitation persistence columns
DROP INDEX IF EXISTS idx_cleaning_clients_invite_token;

ALTER TABLE cleaning_clients
  DROP COLUMN IF EXISTS invite_expires_at,
  DROP COLUMN IF EXISTS invite_sent_at,
  DROP COLUMN IF EXISTS invite_token;
