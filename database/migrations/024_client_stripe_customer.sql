-- Migration 024: add stripe_customer_id to cleaning_clients
-- Enables storing the Stripe Customer ID created during SetupIntent flow
-- for later off_session charges (recurring bookings auto-billing).
--
-- Safe: ADD COLUMN nullable sem default = O(1) no Postgres 11+, zero table lock.
-- Idempotente: IF NOT EXISTS em ADD COLUMN, INDEX e COMMENT.

ALTER TABLE cleaning_clients
  ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;

CREATE INDEX IF NOT EXISTS idx_cleaning_clients_stripe_customer_id
  ON cleaning_clients(stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

COMMENT ON COLUMN cleaning_clients.stripe_customer_id IS
  'Stripe Customer ID on the business connected account (set by SetupIntent flow)';
