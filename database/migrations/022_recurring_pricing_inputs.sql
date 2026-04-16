-- ============================================================================
-- Migration 022: Recurring Auto-Generator — Pricing Inputs on Schedules
-- ============================================================================
-- Purpose: Enable cleaning_client_schedules to carry ALL pricing inputs
--          so daily_generator can delegate to booking_service.create_booking_with_pricing
--          instead of inserting booking with raw agreed_price.
--
-- References:
--   - ADR-002: docs/architecture/adr-002-recurring-auto-generator.md
--   - Sprint Plan: docs/sprints/sprint-d-recurring-payroll.md (Track A)
--   - Closes: Smith C1 finding M2 + R9 (cleaning_client_schedules.frequency_id)
--
-- Changes:
--   1. ALTER cleaning_client_schedules: ADD 4 pricing input columns
--   2. CREATE cleaning_client_schedule_extras (schedule-level extras catalog)
--   3. CREATE cleaning_schedule_skips (skip individual dates without pause)
--   4. Backfill frequency_id (LOWER matching vs cleaning_frequencies.name)
--   5. Backfill location_id (default cleaning_areas row per business)
--   6. Soft-deprecate cleaning_client_schedules.agreed_price (COMMENT only)
--
-- Idempotent: all ADD use IF NOT EXISTS; all INSERT use WHERE NOT EXISTS.
-- Safe to re-run. No destructive operations.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. EXPAND cleaning_client_schedules (ALTER)
-- ============================================================================
-- Each schedule now carries pricing inputs that daily_generator passes to
-- booking_service.create_booking_with_pricing — replicating Launch27's mental
-- model where a client subscribes to service + terms (frequency + extras
-- + adjustment + location).

ALTER TABLE cleaning_client_schedules
    ADD COLUMN IF NOT EXISTS frequency_id UUID
        REFERENCES cleaning_frequencies(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS adjustment_amount NUMERIC(10,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS adjustment_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS location_id UUID
        REFERENCES cleaning_areas(id) ON DELETE SET NULL;

COMMENT ON COLUMN cleaning_client_schedules.frequency_id IS
    'FK to cleaning_frequencies — input for discount_pct calculation by pricing_engine. Replaces legacy VARCHAR frequency for new bookings.';
COMMENT ON COLUMN cleaning_client_schedules.adjustment_amount IS
    'Recurring adjustment applied to every booking generated from this schedule (signed: negative=discount, positive=surcharge). Before tax.';
COMMENT ON COLUMN cleaning_client_schedules.adjustment_reason IS
    'Owner-facing label for the recurring adjustment (auditability).';
COMMENT ON COLUMN cleaning_client_schedules.location_id IS
    'Location for sales tax lookup by pricing_engine. NULL → fallback to default cleaning_areas.is_default=TRUE.';

-- ============================================================================
-- 2. INDEX new FKs
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_cleaning_client_schedules_frequency
    ON cleaning_client_schedules(frequency_id)
    WHERE frequency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cleaning_client_schedules_location
    ON cleaning_client_schedules(location_id)
    WHERE location_id IS NOT NULL;

-- ============================================================================
-- 3. NEW TABLE: cleaning_client_schedule_extras
-- ============================================================================
-- Schedule-level extras (template). Every booking generated inherits these
-- extras. Conceptually a TEMPLATE; booking-level snapshot lives in
-- cleaning_booking_extras (migration 021, created at booking time).

CREATE TABLE IF NOT EXISTS cleaning_client_schedule_extras (
    schedule_id UUID NOT NULL
        REFERENCES cleaning_client_schedules(id) ON DELETE CASCADE,
    extra_id UUID NOT NULL
        REFERENCES cleaning_extras(id) ON DELETE CASCADE,
    qty INTEGER NOT NULL DEFAULT 1
        CHECK (qty >= 1),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (schedule_id, extra_id)
);

CREATE INDEX IF NOT EXISTS idx_cleaning_client_schedule_extras_schedule
    ON cleaning_client_schedule_extras(schedule_id);

COMMENT ON TABLE cleaning_client_schedule_extras IS
    'Schedule-level extras (template). daily_generator JOINs to pass extras[] to pricing_engine. NOT a snapshot — booking-level snapshot lives in cleaning_booking_extras.';

-- ============================================================================
-- 4. NEW TABLE: cleaning_schedule_skips
-- ============================================================================
-- Allows owner to skip individual dates without pausing the entire series
-- (client travels, holiday, one-off agreement).

CREATE TABLE IF NOT EXISTS cleaning_schedule_skips (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_id UUID NOT NULL
        REFERENCES cleaning_client_schedules(id) ON DELETE CASCADE,
    skip_date DATE NOT NULL,
    reason VARCHAR(255),
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (schedule_id, skip_date)
);

CREATE INDEX IF NOT EXISTS idx_cleaning_schedule_skips_lookup
    ON cleaning_schedule_skips(schedule_id, skip_date);

COMMENT ON TABLE cleaning_schedule_skips IS
    'Per-schedule skip dates. daily_generator._collect_jobs filters out matching (schedule_id, target_date). Bookings already generated BEFORE skip added are NOT auto-cancelled — owner decides manually.';

-- ============================================================================
-- 5. BACKFILL frequency_id (LOWER matching vs cleaning_frequencies)
-- ============================================================================
-- Migration 021 already seeded 4 frequencies per business with title-case
-- names: 'One Time', 'Weekly', 'Biweekly', 'Monthly'.
-- cleaning_client_schedules.frequency is lowercase VARCHAR: 'weekly',
-- 'biweekly', 'monthly', 'sporadic'.
-- 'sporadic' has no matching row — remains NULL (pricing_engine gracefully
-- falls back to discount_pct=0).

UPDATE cleaning_client_schedules crs
SET frequency_id = f.id
FROM cleaning_frequencies f
WHERE crs.frequency_id IS NULL
  AND f.business_id = crs.business_id
  AND LOWER(crs.frequency) = LOWER(f.name);

-- Log unmapped rows for ops visibility
DO $$
DECLARE
    unmapped_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO unmapped_count
    FROM cleaning_client_schedules
    WHERE frequency_id IS NULL
      AND frequency IS NOT NULL;

    IF unmapped_count > 0 THEN
        RAISE NOTICE 'Migration 022: % cleaning_client_schedules rows have frequency VARCHAR but NULL frequency_id (expected for ''sporadic'' or unknown values). Pricing engine uses discount_pct=0 for these. Manual review recommended.', unmapped_count;
    END IF;
END $$;

-- ============================================================================
-- 6. BACKFILL location_id (default cleaning_areas per business)
-- ============================================================================
-- Each business has at most one cleaning_areas row with is_default=TRUE
-- (seeded in migration 021). Assign this to schedules without location_id.

UPDATE cleaning_client_schedules crs
SET location_id = a.id
FROM cleaning_areas a
WHERE crs.location_id IS NULL
  AND a.business_id = crs.business_id
  AND a.is_default = TRUE
  AND a.is_archived = FALSE;

-- Log schedules still without location (businesses without default area)
DO $$
DECLARE
    unmapped_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO unmapped_count
    FROM cleaning_client_schedules
    WHERE location_id IS NULL;

    IF unmapped_count > 0 THEN
        RAISE NOTICE 'Migration 022: % cleaning_client_schedules rows have NULL location_id (no default cleaning_areas for their business). Pricing engine will use tax_pct=0 fallback. Assign default area pre-cutover.', unmapped_count;
    END IF;
END $$;

-- ============================================================================
-- 7. SOFT-DEPRECATE agreed_price (COMMENT only; column remains for audit)
-- ============================================================================

COMMENT ON COLUMN cleaning_client_schedules.agreed_price IS
'DEPRECATED 2026-04-16 (migration 022) — price calculated by pricing_engine at runtime using (formula/override + extras + frequency discount + adjustment + tax). Kept for historical audit only. Not used by bookings generated post-migration-022.';

-- ============================================================================
-- 8. MIGRATION COMPLETE MARKER
-- ============================================================================

DO $$
DECLARE
    backfilled_freq INTEGER;
    backfilled_loc INTEGER;
BEGIN
    SELECT COUNT(*) INTO backfilled_freq
    FROM cleaning_client_schedules
    WHERE frequency_id IS NOT NULL;

    SELECT COUNT(*) INTO backfilled_loc
    FROM cleaning_client_schedules
    WHERE location_id IS NOT NULL;

    RAISE NOTICE 'Migration 022 applied successfully.';
    RAISE NOTICE '  - Columns added: 4 (frequency_id, adjustment_amount, adjustment_reason, location_id)';
    RAISE NOTICE '  - Tables created: 2 (cleaning_client_schedule_extras, cleaning_schedule_skips)';
    RAISE NOTICE '  - Indexes added: 3';
    RAISE NOTICE '  - Schedules with frequency_id (backfilled): %', backfilled_freq;
    RAISE NOTICE '  - Schedules with location_id (backfilled): %', backfilled_loc;
END $$;

COMMIT;

-- ============================================================================
-- POST-MIGRATION VALIDATION QUERIES (run manually if desired)
-- ============================================================================
--
-- Coverage of backfill (>= 80% expected for non-sporadic businesses):
-- SELECT
--     b.slug,
--     COUNT(crs.id) AS total_schedules,
--     COUNT(crs.frequency_id) AS with_freq_id,
--     COUNT(crs.location_id) AS with_loc_id,
--     ROUND(100.0 * COUNT(crs.frequency_id) / NULLIF(COUNT(crs.id), 0), 1) AS freq_pct
-- FROM businesses b
-- LEFT JOIN cleaning_client_schedules crs ON crs.business_id = b.id
-- GROUP BY b.slug;
--
-- Unmapped rows (likely 'sporadic' or typos):
-- SELECT business_id, frequency, status, COUNT(*) FROM cleaning_client_schedules
-- WHERE frequency_id IS NULL AND frequency IS NOT NULL
-- GROUP BY business_id, frequency, status;
--
-- Test idempotency: re-run this file. Expected: 0 new columns added,
-- 0 tables created, 0 rows backfilled (already done), no errors.
-- ============================================================================
