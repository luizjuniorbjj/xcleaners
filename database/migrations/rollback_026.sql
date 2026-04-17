-- Rollback 026: restore constraint WITHOUT 'processing'
-- WARNING: any row with payment_status='processing' would violate the old
-- constraint. Check before running:
--   SELECT COUNT(*) FROM cleaning_bookings WHERE payment_status = 'processing';
-- Expected 0 before rollback; otherwise UPDATE those rows first.

ALTER TABLE cleaning_bookings
  DROP CONSTRAINT IF EXISTS cleaning_bookings_payment_status_check;

ALTER TABLE cleaning_bookings
  ADD CONSTRAINT cleaning_bookings_payment_status_check
  CHECK (payment_status IS NULL OR payment_status IN (
    'pending', 'succeeded', 'requires_action', 'declined', 'failed'
  ));
