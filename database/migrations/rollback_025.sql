-- Rollback for migration 025: remove payment tracking from cleaning_bookings
-- Destructive: loses stripe_payment_intent_id + payment_status for all bookings.
-- Use only if migration 025 caused regression; coordinate with Morpheus first.

DROP INDEX IF EXISTS idx_cleaning_bookings_payment_status;
DROP INDEX IF EXISTS idx_cleaning_bookings_stripe_payment_intent_id;

ALTER TABLE cleaning_bookings
  DROP CONSTRAINT IF EXISTS cleaning_bookings_payment_status_check;

ALTER TABLE cleaning_bookings
  DROP COLUMN IF EXISTS payment_status;

ALTER TABLE cleaning_bookings
  DROP COLUMN IF EXISTS stripe_payment_intent_id;
