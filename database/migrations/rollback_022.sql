-- ============================================================================
-- Rollback Migration 022: Recurring Auto-Generator Pricing Inputs
-- ============================================================================
-- DESTRUCTIVE. Reverses migration 022 completely.
--
-- WARNING: Data loss risk — this DROPs two tables and 4 columns:
--   - cleaning_client_schedule_extras (schedule-level extras — user-configured data)
--   - cleaning_schedule_skips (skip dates — user-configured data)
--   - cleaning_client_schedules columns:
--     frequency_id, adjustment_amount, adjustment_reason, location_id
--
-- Before running:
--   1. Ensure no downstream code path depends on these columns/tables
--   2. Backup: pg_dump $DATABASE_URL > backup_pre_rollback_022.sql
--   3. Stop cron trigger (recurring-cron-setup.md)
--   4. Restart application AFTER rollback so Python code matches schema
--
-- References:
--   - Forward migration: 022_recurring_pricing_inputs.sql
--   - ADR-002: docs/architecture/adr-002-recurring-auto-generator.md
-- ============================================================================

BEGIN;

-- Safety: prevent accidental run in production
DO $$
BEGIN
    RAISE NOTICE '======================================================';
    RAISE NOTICE 'ROLLBACK 022: Destructive. Press Ctrl+C within 5s to abort.';
    RAISE NOTICE '======================================================';
END $$;

-- ============================================================================
-- 1. DROP new tables (destructive — user data loss)
-- ============================================================================

DROP TABLE IF EXISTS cleaning_schedule_skips CASCADE;
DROP TABLE IF EXISTS cleaning_client_schedule_extras CASCADE;

-- ============================================================================
-- 2. DROP columns from cleaning_client_schedules
-- ============================================================================

-- Drop indexes first (dependencies on columns)
DROP INDEX IF EXISTS idx_cleaning_client_schedules_frequency;
DROP INDEX IF EXISTS idx_cleaning_client_schedules_location;

ALTER TABLE cleaning_client_schedules
    DROP COLUMN IF EXISTS frequency_id,
    DROP COLUMN IF EXISTS adjustment_amount,
    DROP COLUMN IF EXISTS adjustment_reason,
    DROP COLUMN IF EXISTS location_id;

-- ============================================================================
-- 3. RESTORE agreed_price COMMENT (remove DEPRECATED warning)
-- ============================================================================

COMMENT ON COLUMN cleaning_client_schedules.agreed_price IS
    'Locked recurring price agreed with client (pre-pricing-engine).';

-- ============================================================================
-- 4. COMPLETE MARKER
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Rollback 022 applied successfully.';
    RAISE NOTICE '  - Tables dropped: cleaning_client_schedule_extras, cleaning_schedule_skips';
    RAISE NOTICE '  - Columns dropped: 4 from cleaning_client_schedules';
    RAISE NOTICE '  - agreed_price COMMENT restored to pre-022 state';
    RAISE NOTICE '';
    RAISE NOTICE 'REMINDER: restart application so Python code matches schema.';
END $$;

COMMIT;
