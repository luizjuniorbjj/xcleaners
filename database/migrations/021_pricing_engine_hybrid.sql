-- ============================================================================
-- Migration 021: Pricing Engine Hybrid (Formula + Override with Snapshot)
-- ============================================================================
-- Purpose: Add pricing engine infrastructure to replicate Launch27 calculations
--          with ±$0.01 tolerance. Supports 3Sisters migration (Epic A Story 1.1).
--
-- References:
--   - ADR-001: projects/xcleaners/architecture/adr-001-pricing-engine-hybrid.md
--   - Story 1.1: projects/xcleaners/stories/1.1.pricing-engine-hybrid.md
--
-- Changes:
--   1. ALTER TABLE (expand existing): cleaning_areas, cleaning_services,
--      cleaning_bookings, cleaning_team_members
--   2. CREATE TABLE (7 new): cleaning_frequencies, cleaning_sales_taxes,
--      cleaning_pricing_formulas, cleaning_extras, cleaning_service_extras,
--      cleaning_booking_extras, cleaning_service_overrides
--   3. Add FKs: cleaning_bookings.frequency_id + location_id,
--      cleaning_recurring_schedules.frequency_id
--   4. Backfill cleaning_recurring_schedules.frequency VARCHAR → frequency_id
--   5. Seed per-business defaults (4 frequencies, 1 formula, 1 default area)
--   6. Soft-deprecate cleaning_pricing_rules (COMMENT ON)
--
-- Idempotent: All statements use IF NOT EXISTS / ON CONFLICT / WHERE NOT EXISTS.
-- Safe to re-run. No destructive operations.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. EXPAND EXISTING TABLES (ALTER TABLE)
-- ============================================================================

-- ---- 1.1 cleaning_areas: promote to first-class locations ------------------
ALTER TABLE cleaning_areas
    ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN cleaning_areas.is_default IS
    'TRUE for the single default location per business (used when booking has no location_id)';

-- ---- 1.2 cleaning_services: tier + BR/BA for formula pricing ---------------
ALTER TABLE cleaning_services
    ADD COLUMN IF NOT EXISTS tier VARCHAR(20)
        CHECK (tier IN ('basic', 'deep', 'premium')),
    ADD COLUMN IF NOT EXISTS bedrooms INTEGER
        CHECK (bedrooms >= 0 AND bedrooms <= 20),
    ADD COLUMN IF NOT EXISTS bathrooms INTEGER
        CHECK (bathrooms >= 0 AND bathrooms <= 20);

COMMENT ON COLUMN cleaning_services.tier IS
    'Quality tier: basic|deep|premium. Used by pricing_engine with tier_multipliers in cleaning_pricing_formulas';
COMMENT ON COLUMN cleaning_services.bedrooms IS
    'Number of bedrooms for formula calculation: (base + bedrooms * bedroom_delta)';
COMMENT ON COLUMN cleaning_services.bathrooms IS
    'Number of bathrooms for formula calculation';

-- ---- 1.3 cleaning_bookings: tax, adjustment, snapshot ----------------------
ALTER TABLE cleaning_bookings
    ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(10,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS adjustment_amount NUMERIC(10,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS adjustment_reason VARCHAR(255),
    ADD COLUMN IF NOT EXISTS price_snapshot JSONB;

COMMENT ON COLUMN cleaning_bookings.tax_amount IS
    'Sales tax computed by pricing_engine on (subtotal - discount - adjustment)';
COMMENT ON COLUMN cleaning_bookings.adjustment_amount IS
    'Manual one-off adjustment (signed: negative for discount, positive for surcharge). Applied BEFORE tax.';
COMMENT ON COLUMN cleaning_bookings.price_snapshot IS
    'Immutable pricing breakdown at booking creation. See ADR-001 Decision 2 for schema.';

-- ---- 1.4 cleaning_team_members: wage % for payroll (Story 1.6 prep) --------
ALTER TABLE cleaning_team_members
    ADD COLUMN IF NOT EXISTS wage_pct NUMERIC(5,2) DEFAULT 60.00
        CHECK (wage_pct >= 0 AND wage_pct <= 100);

COMMENT ON COLUMN cleaning_team_members.wage_pct IS
    'Revenue split percentage the cleaner receives per completed booking. Default 60% (3Sisters model).';

-- ============================================================================
-- 2. CREATE NEW TABLES (no circular FKs first)
-- ============================================================================

-- ---- 2.1 cleaning_frequencies ---------------------------------------------
-- Per-business catalog of booking frequencies with optional recurring discount.
-- Examples: One Time (0%), Weekly (15%), Biweekly (10%), Monthly (5%).
CREATE TABLE IF NOT EXISTS cleaning_frequencies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    interval_weeks INTEGER,                           -- NULL for one-time, 1/2/4 for weekly/biweekly/monthly
    discount_pct NUMERIC(5,2) DEFAULT 0.00
        CHECK (discount_pct >= 0 AND discount_pct <= 100),
    is_default BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(business_id, name)
);

CREATE INDEX IF NOT EXISTS idx_cleaning_frequencies_business
    ON cleaning_frequencies(business_id, is_archived);

COMMENT ON TABLE cleaning_frequencies IS
    'Per-business catalog of booking frequencies. Applied to pricing via discount_pct.';

-- ---- 2.2 cleaning_sales_taxes ---------------------------------------------
-- Temporal sales tax rates per location. Latest effective_date applies.
CREATE TABLE IF NOT EXISTS cleaning_sales_taxes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    location_id UUID NOT NULL REFERENCES cleaning_areas(id) ON DELETE CASCADE,
    tax_pct NUMERIC(5,2) NOT NULL
        CHECK (tax_pct >= 0 AND tax_pct <= 30),
    effective_date DATE NOT NULL,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cleaning_sales_taxes_lookup
    ON cleaning_sales_taxes(location_id, effective_date DESC)
    WHERE is_archived = FALSE;

COMMENT ON TABLE cleaning_sales_taxes IS
    'Temporal sales tax by location. Pricing engine picks row with MAX(effective_date) <= booking date.';

-- ---- 2.3 cleaning_pricing_formulas ----------------------------------------
-- Formula-based default pricing: (base + bedrooms*bed_delta + bathrooms*bath_delta) * tier_multiplier.
-- Per-business + optional per-location for multi-market differentiation.
CREATE TABLE IF NOT EXISTS cleaning_pricing_formulas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    location_id UUID REFERENCES cleaning_areas(id) ON DELETE CASCADE,  -- NULL = default for business
    name VARCHAR(100) NOT NULL,
    base_amount NUMERIC(10,2) NOT NULL
        CHECK (base_amount >= 0),
    bedroom_delta NUMERIC(10,2) NOT NULL DEFAULT 0
        CHECK (bedroom_delta >= 0),
    bathroom_delta NUMERIC(10,2) NOT NULL DEFAULT 0
        CHECK (bathroom_delta >= 0),
    tier_multipliers JSONB NOT NULL,       -- {"basic": 1.0, "deep": 1.8, "premium": 2.8}
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cleaning_pricing_formulas_business
    ON cleaning_pricing_formulas(business_id, is_active);

CREATE INDEX IF NOT EXISTS idx_cleaning_pricing_formulas_location
    ON cleaning_pricing_formulas(location_id)
    WHERE location_id IS NOT NULL;

-- updated_at trigger
DROP TRIGGER IF EXISTS tr_cleaning_pricing_formulas_updated_at ON cleaning_pricing_formulas;
CREATE TRIGGER tr_cleaning_pricing_formulas_updated_at
    BEFORE UPDATE ON cleaning_pricing_formulas
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMENT ON TABLE cleaning_pricing_formulas IS
    'Default pricing formula per business (and optional per-location). Tier_multipliers applied ONLY to (base + BR + BA), not to extras. See ADR-001 Decision 5.';

-- ---- 2.4 cleaning_extras ---------------------------------------------------
-- Global catalog of add-ons per business (e.g. "Stairs +$30", "Inside Oven +$25").
CREATE TABLE IF NOT EXISTS cleaning_extras (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    price NUMERIC(10,2) NOT NULL
        CHECK (price >= 0),
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cleaning_extras_business
    ON cleaning_extras(business_id, is_active, sort_order);

COMMENT ON TABLE cleaning_extras IS
    'Per-business catalog of add-ons. Flat prices, not affected by tier_multiplier (ADR-001 Decision 5).';

-- ---- 2.5 cleaning_service_extras (whitelist M:N) --------------------------
-- Which extras are allowed for which service. Owner defines per service.
CREATE TABLE IF NOT EXISTS cleaning_service_extras (
    service_id UUID NOT NULL REFERENCES cleaning_services(id) ON DELETE CASCADE,
    extra_id UUID NOT NULL REFERENCES cleaning_extras(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (service_id, extra_id)
);

CREATE INDEX IF NOT EXISTS idx_cleaning_service_extras_service
    ON cleaning_service_extras(service_id);

CREATE INDEX IF NOT EXISTS idx_cleaning_service_extras_extra
    ON cleaning_service_extras(extra_id);

COMMENT ON TABLE cleaning_service_extras IS
    'Whitelist M:N — which extras are selectable for each service at booking time.';

-- ---- 2.6 cleaning_booking_extras (booking-level snapshot) -----------------
-- Extras applied to a booking, with price + name snapshot (immutable).
CREATE TABLE IF NOT EXISTS cleaning_booking_extras (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    booking_id UUID NOT NULL REFERENCES cleaning_bookings(id) ON DELETE CASCADE,
    extra_id UUID REFERENCES cleaning_extras(id) ON DELETE SET NULL,
    name_snapshot VARCHAR(100) NOT NULL,                -- preserves name if extra renamed/deleted
    price_snapshot NUMERIC(10,2) NOT NULL,              -- preserves price at booking time
    qty INTEGER NOT NULL DEFAULT 1
        CHECK (qty >= 1),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cleaning_booking_extras_booking
    ON cleaning_booking_extras(booking_id);

COMMENT ON TABLE cleaning_booking_extras IS
    'Snapshot of extras applied to a booking. name_snapshot + price_snapshot are immutable (ADR-001 Decision 2).';

-- ---- 2.7 cleaning_service_overrides (atomic per tier) ---------------------
-- Owner may override formula-computed price for a specific service+tier combo.
-- V1: only price_override (duration/extras are NOT overridable — Decision 3).
CREATE TABLE IF NOT EXISTS cleaning_service_overrides (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_id UUID NOT NULL REFERENCES cleaning_services(id) ON DELETE CASCADE,
    tier VARCHAR(20) NOT NULL
        CHECK (tier IN ('basic', 'deep', 'premium')),
    price_override NUMERIC(10,2) NOT NULL
        CHECK (price_override >= 0),
    reason VARCHAR(255),
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(service_id, tier)
);

CREATE INDEX IF NOT EXISTS idx_cleaning_service_overrides_lookup
    ON cleaning_service_overrides(service_id, tier)
    WHERE is_active = TRUE;

COMMENT ON TABLE cleaning_service_overrides IS
    'Per-service+tier price override. Replaces formula-computed service_amount. Extras stay formula-derived (ADR-001 Decision 3).';

-- ============================================================================
-- 3. ADD FOREIGN KEYS TO EXISTING TABLES (after new tables exist)
-- ============================================================================

-- ---- 3.1 cleaning_bookings.frequency_id + location_id ---------------------
ALTER TABLE cleaning_bookings
    ADD COLUMN IF NOT EXISTS frequency_id UUID
        REFERENCES cleaning_frequencies(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS location_id UUID
        REFERENCES cleaning_areas(id) ON DELETE SET NULL;

COMMENT ON COLUMN cleaning_bookings.frequency_id IS
    'Applied frequency for discount_pct calculation (replaces ad-hoc frequency strings)';
COMMENT ON COLUMN cleaning_bookings.location_id IS
    'Location (area) for sales tax lookup and multi-location differentiation';

-- ---- 3.2 cleaning_recurring_schedules.frequency_id (legacy table) ----------
-- Note: cleaning_recurring_schedules is DEPRECATED (migration 020) but may hold
-- historical rows. Adding FK defensively for backward compatibility.
ALTER TABLE cleaning_recurring_schedules
    ADD COLUMN IF NOT EXISTS frequency_id UUID
        REFERENCES cleaning_frequencies(id) ON DELETE SET NULL;

-- ============================================================================
-- 4. INDEXES ON NEW FKs in cleaning_bookings
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_cleaning_bookings_frequency
    ON cleaning_bookings(frequency_id)
    WHERE frequency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cleaning_bookings_location
    ON cleaning_bookings(location_id)
    WHERE location_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cleaning_recurring_frequency
    ON cleaning_recurring_schedules(frequency_id)
    WHERE frequency_id IS NOT NULL;

-- ============================================================================
-- 5. SEED DATA (per-business defaults, idempotent)
-- ============================================================================

-- ---- 5.1 Four default frequencies per business -----------------------------
-- One Time (0%) — is_default = TRUE
INSERT INTO cleaning_frequencies (business_id, name, interval_weeks, discount_pct, is_default)
SELECT b.id, 'One Time', NULL, 0.00, TRUE
FROM businesses b
WHERE NOT EXISTS (
    SELECT 1 FROM cleaning_frequencies f
    WHERE f.business_id = b.id AND f.name = 'One Time'
);

-- Weekly (15%)
INSERT INTO cleaning_frequencies (business_id, name, interval_weeks, discount_pct, is_default)
SELECT b.id, 'Weekly', 1, 15.00, FALSE
FROM businesses b
WHERE NOT EXISTS (
    SELECT 1 FROM cleaning_frequencies f
    WHERE f.business_id = b.id AND f.name = 'Weekly'
);

-- Biweekly (10%)
INSERT INTO cleaning_frequencies (business_id, name, interval_weeks, discount_pct, is_default)
SELECT b.id, 'Biweekly', 2, 10.00, FALSE
FROM businesses b
WHERE NOT EXISTS (
    SELECT 1 FROM cleaning_frequencies f
    WHERE f.business_id = b.id AND f.name = 'Biweekly'
);

-- Monthly (5%)
INSERT INTO cleaning_frequencies (business_id, name, interval_weeks, discount_pct, is_default)
SELECT b.id, 'Monthly', 4, 5.00, FALSE
FROM businesses b
WHERE NOT EXISTS (
    SELECT 1 FROM cleaning_frequencies f
    WHERE f.business_id = b.id AND f.name = 'Monthly'
);

-- ---- 5.2 Default "Standard" pricing formula per business -------------------
-- Reasonable starting values; owner customizes via UI after migration.
INSERT INTO cleaning_pricing_formulas (
    business_id, name, base_amount, bedroom_delta, bathroom_delta,
    tier_multipliers, is_active
)
SELECT
    b.id,
    'Standard',
    115.00,                                                  -- base
    20.00,                                                   -- per bedroom
    15.00,                                                   -- per bathroom
    '{"basic": 1.0, "deep": 1.8, "premium": 2.8}'::jsonb,
    TRUE
FROM businesses b
WHERE NOT EXISTS (
    SELECT 1 FROM cleaning_pricing_formulas f
    WHERE f.business_id = b.id AND f.name = 'Standard'
);

-- ---- 5.3 Mark first existing cleaning_areas row per business as default ----
-- Only if business has >= 1 area AND no area is currently marked default.
-- Uses DISTINCT ON to pick exactly one row per business deterministically.
WITH defaults_needed AS (
    SELECT DISTINCT ON (a.business_id) a.id, a.business_id
    FROM cleaning_areas a
    WHERE a.is_archived = FALSE
      AND NOT EXISTS (
          SELECT 1 FROM cleaning_areas a2
          WHERE a2.business_id = a.business_id
            AND a2.is_default = TRUE
      )
    ORDER BY a.business_id, a.created_at ASC, a.id ASC
)
UPDATE cleaning_areas a
SET is_default = TRUE
FROM defaults_needed d
WHERE a.id = d.id;

-- ============================================================================
-- 6. BACKFILL cleaning_recurring_schedules.frequency → frequency_id
-- ============================================================================
-- Existing VARCHAR values: 'weekly', 'biweekly', 'monthly', 'custom'.
-- Map to new FK. 'custom' stays NULL (no matching default frequency).
-- Unknown values logged via RAISE NOTICE for ops visibility.

UPDATE cleaning_recurring_schedules crs
SET frequency_id = f.id
FROM cleaning_frequencies f
WHERE crs.frequency_id IS NULL
  AND f.business_id = crs.business_id
  AND (
      (LOWER(crs.frequency) = 'weekly'   AND f.name = 'Weekly')
   OR (LOWER(crs.frequency) = 'biweekly' AND f.name = 'Biweekly')
   OR (LOWER(crs.frequency) = 'monthly'  AND f.name = 'Monthly')
  );

-- Log any unmapped rows (e.g. 'custom' or unknown values) for operator review
DO $$
DECLARE
    unmapped_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO unmapped_count
    FROM cleaning_recurring_schedules
    WHERE frequency_id IS NULL
      AND frequency IS NOT NULL;

    IF unmapped_count > 0 THEN
        RAISE NOTICE 'Migration 021: % cleaning_recurring_schedules rows have frequency VARCHAR but no matching frequency_id (likely ''custom''). They remain NULL and require manual review.', unmapped_count;
    END IF;
END $$;

-- ============================================================================
-- 7. SOFT-DEPRECATE cleaning_pricing_rules
-- ============================================================================

COMMENT ON TABLE cleaning_pricing_rules IS
'DEPRECATED 2026-04-16 — superseded by cleaning_pricing_formulas + cleaning_service_overrides (ADR-001). No code paths active. Candidate for DROP in future cleanup migration.';

-- ============================================================================
-- 8. MIGRATION COMPLETE MARKER
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 021 applied successfully.';
    RAISE NOTICE '  - Tables created: 7 (frequencies, sales_taxes, pricing_formulas, extras, service_extras, booking_extras, service_overrides)';
    RAISE NOTICE '  - Columns added: 11 across cleaning_areas, cleaning_services, cleaning_bookings, cleaning_team_members, cleaning_recurring_schedules';
    RAISE NOTICE '  - Seed data: 4 frequencies + 1 formula + default area per existing business';
END $$;

COMMIT;

-- ============================================================================
-- POST-MIGRATION VALIDATION QUERIES (run manually if desired)
-- ============================================================================
-- Expected counts per business after migration:
--
-- SELECT b.slug,
--        (SELECT COUNT(*) FROM cleaning_frequencies f WHERE f.business_id = b.id) AS freq_count,
--        (SELECT COUNT(*) FROM cleaning_pricing_formulas p WHERE p.business_id = b.id) AS formula_count,
--        (SELECT COUNT(*) FROM cleaning_areas a WHERE a.business_id = b.id AND a.is_default = TRUE) AS default_areas
-- FROM businesses b;
--
-- Expect: freq_count >= 4, formula_count >= 1, default_areas = 1 (if business had >=1 area)
--
-- Unmapped recurring schedules (should be low / 'custom' only):
-- SELECT business_id, frequency, COUNT(*)
-- FROM cleaning_recurring_schedules
-- WHERE frequency_id IS NULL AND frequency IS NOT NULL
-- GROUP BY business_id, frequency;
-- ============================================================================
