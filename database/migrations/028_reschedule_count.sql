-- Migration 028: add reschedule_count to cleaning_bookings
-- Context: Cancellation/Reschedule Policy MVP. Business rule (Luiz 2026-04-20):
-- homeowners can reschedule a booking a limited number of times (configurable
-- per business, default 1). After the limit, the only action available is
-- cancellation — which itself may carry a late-cancel fee if within the
-- notice window (hours_before, default 24).
--
-- This column is the counter that enforces the limit. It starts at 0 for
-- every booking and is incremented by the reschedule_booking service.
--
-- Safe: NOT NULL + DEFAULT 0 means existing rows backfill to 0 atomically,
-- so current operational state = "no reschedules used yet" (accurate).

ALTER TABLE cleaning_bookings
  ADD COLUMN IF NOT EXISTS reschedule_count INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN cleaning_bookings.reschedule_count IS
  'Number of times the homeowner has rescheduled this booking. Incremented by reschedule_booking. Compared against business_settings.cancellation_policy.max_reschedules_per_booking (default 1) to gate further reschedules.';
