-- ============================================================================
-- ROLLBACK 021: Pricing Engine Hybrid
-- ============================================================================
-- Purpose: Revert migration 021_pricing_engine_hybrid.sql in case of
--          catastrophic failure shortly after deployment.
--
-- ⚠️  WARNING — DESTRUCTIVE OPERATION:
-- This rollback DROPS tables and removes columns. Any data written to
-- the new tables/columns since migration 021 was applied will be PERMANENTLY LOST.
--
-- Specifically:
--   - All cleaning_bookings.price_snapshot JSONB values (audit trail)
--   - All cleaning_booking_extras rows (per-booking extras snapshots)
--   - All cleaning_service_overrides rows (owner's custom prices)
--   - All cleaning_pricing_formulas, cleaning_frequencies, cleaning_sales_taxes,
--     cleaning_extras, cleaning_service_extras rows
--   - tax_amount, adjustment_amount, wage_pct values on existing rows
--
-- USE ONLY IF:
--   1. Migration 021 was applied very recently (< 1 hour)
--   2. Critical bug was detected in the new schema
--   3. Application has NOT yet started writing pricing data
--
-- DO NOT USE IF:
--   - Bookings have been created using the new pricing engine
--   - Ana (3Sisters) has configured her pricing formulas/overrides
--   - Production traffic has hit the new code paths
--
-- For later cleanup of this work, prefer a forward migration (022+) that
-- soft-deprecates and eventually drops, rather than using this rollback.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Drop FKs added by 021 (before dropping tables they reference)
-- ============================================================================

-- Note: DROP COLUMN automatically drops FK constraints, indexes, and triggers
-- associated with that column. No explicit DROP CONSTRAINT needed.

ALTER TABLE cleaning_recurring_schedules
    DROP COLUMN IF EXISTS frequency_id;

ALTER TABLE cleaning_bookings
    DROP COLUMN IF EXISTS frequency_id,
    DROP COLUMN IF EXISTS location_id;

-- ============================================================================
-- 2. Drop new tables (reverse FK dependency order)
-- ============================================================================

DROP TABLE IF EXISTS cleaning_service_overrides CASCADE;
DROP TABLE IF EXISTS cleaning_booking_extras CASCADE;
DROP TABLE IF EXISTS cleaning_service_extras CASCADE;
DROP TABLE IF EXISTS cleaning_extras CASCADE;
DROP TABLE IF EXISTS cleaning_pricing_formulas CASCADE;
DROP TABLE IF EXISTS cleaning_sales_taxes CASCADE;
DROP TABLE IF EXISTS cleaning_frequencies CASCADE;

-- ============================================================================
-- 3. Remove columns added to existing tables
-- ============================================================================

-- cleaning_areas
ALTER TABLE cleaning_areas
    DROP COLUMN IF EXISTS is_default,
    DROP COLUMN IF EXISTS is_archived;

-- cleaning_services
ALTER TABLE cleaning_services
    DROP COLUMN IF EXISTS tier,
    DROP COLUMN IF EXISTS bedrooms,
    DROP COLUMN IF EXISTS bathrooms;

-- cleaning_bookings (tax_amount, adjustment_amount, adjustment_reason, price_snapshot)
-- ⚠️ price_snapshot loss is IRRECOVERABLE after this DROP
ALTER TABLE cleaning_bookings
    DROP COLUMN IF EXISTS tax_amount,
    DROP COLUMN IF EXISTS adjustment_amount,
    DROP COLUMN IF EXISTS adjustment_reason,
    DROP COLUMN IF EXISTS price_snapshot;

-- cleaning_team_members
ALTER TABLE cleaning_team_members
    DROP COLUMN IF EXISTS wage_pct;

-- ============================================================================
-- 4. Restore cleaning_pricing_rules deprecation comment to previous state
-- ============================================================================
-- (Previous comment was none or set by earlier migrations; reset to NULL)

COMMENT ON TABLE cleaning_pricing_rules IS NULL;

-- ============================================================================
-- 5. Log completion
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Rollback 021 applied: pricing engine hybrid reverted.';
    RAISE WARNING 'All data in dropped tables/columns has been PERMANENTLY LOST.';
END $$;

COMMIT;

-- ============================================================================
-- POST-ROLLBACK VALIDATION
-- ============================================================================
-- Verify tables no longer exist:
--
-- SELECT table_name FROM information_schema.tables
-- WHERE table_name IN (
--     'cleaning_frequencies', 'cleaning_sales_taxes', 'cleaning_pricing_formulas',
--     'cleaning_extras', 'cleaning_service_extras', 'cleaning_booking_extras',
--     'cleaning_service_overrides'
-- );
-- -- Expected: 0 rows
--
-- Verify columns removed:
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'cleaning_bookings'
--   AND column_name IN ('tax_amount', 'adjustment_amount', 'price_snapshot', 'frequency_id', 'location_id');
-- -- Expected: 0 rows
-- ============================================================================
