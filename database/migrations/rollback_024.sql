-- Rollback for migration 024: remove stripe_customer_id from cleaning_clients
-- Destructive: loses stripe_customer_id values for all clients.
-- Use only if migration 024 caused regression; coordinate with Morpheus first.

DROP INDEX IF EXISTS idx_cleaning_clients_stripe_customer_id;

ALTER TABLE cleaning_clients
  DROP COLUMN IF EXISTS stripe_customer_id;
