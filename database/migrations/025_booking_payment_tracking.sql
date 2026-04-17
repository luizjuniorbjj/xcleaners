-- Migration 025: payment tracking columns on cleaning_bookings
-- Enables auto-charge tracking for recurring bookings (off_session PaymentIntents)
-- Links booking to Stripe PaymentIntent + captures charge lifecycle state.
--
-- Safe: ADD COLUMN nullable sem default = O(1), zero lock.
-- Idempotente: IF NOT EXISTS em tudo.
-- CONSTRAINT criado com NOT VALID + VALIDATE sequencial (existing rows all NULL -> trivial scan).

ALTER TABLE cleaning_bookings
  ADD COLUMN IF NOT EXISTS stripe_payment_intent_id TEXT;

ALTER TABLE cleaning_bookings
  ADD COLUMN IF NOT EXISTS payment_status TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'cleaning_bookings_payment_status_check'
  ) THEN
    ALTER TABLE cleaning_bookings
      ADD CONSTRAINT cleaning_bookings_payment_status_check
      CHECK (payment_status IS NULL OR payment_status IN (
        'pending', 'succeeded', 'requires_action', 'declined', 'failed'
      )) NOT VALID;
    ALTER TABLE cleaning_bookings
      VALIDATE CONSTRAINT cleaning_bookings_payment_status_check;
  END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_cleaning_bookings_stripe_payment_intent_id
  ON cleaning_bookings(stripe_payment_intent_id)
  WHERE stripe_payment_intent_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cleaning_bookings_payment_status
  ON cleaning_bookings(payment_status)
  WHERE payment_status IS NOT NULL;

COMMENT ON COLUMN cleaning_bookings.stripe_payment_intent_id IS
  'Stripe PaymentIntent ID from off_session auto-charge (set by recurring_generator hook)';
COMMENT ON COLUMN cleaning_bookings.payment_status IS
  'Charge lifecycle: pending | succeeded | requires_action | declined | failed. NULL = not charged yet.';
