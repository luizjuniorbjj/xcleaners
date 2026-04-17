-- Migration 026: add 'processing' to payment_status CHECK constraint
-- Smith finding M1 (sprint 3Sisters): 'processing' is a legitimate Stripe
-- async state and was being mapped to 'pending' for DB acceptance,
-- confusing owner-facing status reports. This migration allows the real
-- state to be persisted.
--
-- Safe: all existing rows have NULL in payment_status (column is brand new
-- from migration 025). NOT VALID + VALIDATE sequential = instant scan.

ALTER TABLE cleaning_bookings
  DROP CONSTRAINT IF EXISTS cleaning_bookings_payment_status_check;

ALTER TABLE cleaning_bookings
  ADD CONSTRAINT cleaning_bookings_payment_status_check
  CHECK (payment_status IS NULL OR payment_status IN (
    'pending', 'processing', 'succeeded', 'requires_action', 'declined', 'failed'
  )) NOT VALID;

ALTER TABLE cleaning_bookings
  VALIDATE CONSTRAINT cleaning_bookings_payment_status_check;

COMMENT ON COLUMN cleaning_bookings.payment_status IS
  'Charge lifecycle: pending | processing | succeeded | requires_action | declined | failed. NULL = not charged yet.';
