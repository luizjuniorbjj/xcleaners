-- Rollback for migration 028: drop reschedule_count from cleaning_bookings
-- Safe to run only if no application code depends on the column. After this,
-- reschedule_booking must stop referencing reschedule_count before re-deploy,
-- otherwise cancel/reschedule flows will 500.

ALTER TABLE cleaning_bookings DROP COLUMN IF EXISTS reschedule_count;
