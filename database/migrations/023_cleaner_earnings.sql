-- ============================================================================
-- Migration 023: Cleaner Earnings (Payroll 60% Commission Split)
-- ============================================================================
-- Purpose: Materialize cleaner pay per booking with snapshot immutability.
--          Each completed booking produces one earnings row per cleaner.
--          Commission pct is snapshotted at calc time (wage_pct changes
--          AFTER the booking do not retroactively alter earnings).
--
-- References:
--   - Sprint D Track B: docs/sprints/sprint-d-recurring-payroll.md
--   - Sibling to price_snapshot (migration 021) — same immutability pattern
--
-- Changes:
--   1. CREATE TABLE cleaning_cleaner_earnings
--   2. Indexes for common queries (by cleaner+status, by period paid)
--   3. Trigger to auto-update updated_at
--
-- Idempotent: IF NOT EXISTS on all statements. Safe to re-run.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. TABLE: cleaning_cleaner_earnings
-- ============================================================================
-- One row per (booking, cleaner). UNIQUE(booking_id, cleaner_id) enforces
-- that calculating earnings for the same booking twice is idempotent.
-- In v1 we assume one cleaner per booking (lead_cleaner_id); multi-cleaner
-- split is a future story.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cleaning_cleaner_earnings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    booking_id UUID NOT NULL REFERENCES cleaning_bookings(id) ON DELETE CASCADE,
    cleaner_id UUID NOT NULL REFERENCES cleaning_team_members(id) ON DELETE RESTRICT,

    -- Snapshotted amounts (immutable once row exists)
    gross_amount NUMERIC(10,2) NOT NULL CHECK (gross_amount >= 0),
    commission_pct NUMERIC(5,2) NOT NULL CHECK (commission_pct >= 0 AND commission_pct <= 100),
    net_amount NUMERIC(10,2) NOT NULL CHECK (net_amount >= 0),

    -- Payout tracking
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'void')),
    paid_at TIMESTAMPTZ,
    payout_ref VARCHAR(100),                   -- free-text (check #, stripe transfer id, etc.)

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_earnings_booking_cleaner UNIQUE (booking_id, cleaner_id),
    CONSTRAINT chk_earnings_paid_consistent
        CHECK ((status = 'paid') = (paid_at IS NOT NULL))
);

COMMENT ON TABLE cleaning_cleaner_earnings IS
    'Payroll ledger: one row per (booking, cleaner). Snapshot of commission_pct/amounts is immutable once created. Status transitions: pending → paid or pending → void.';
COMMENT ON COLUMN cleaning_cleaner_earnings.gross_amount IS
    'Booking final_price at the moment of earnings calculation. NOT kept in sync if booking is later repriced.';
COMMENT ON COLUMN cleaning_cleaner_earnings.commission_pct IS
    'Snapshot of cleaner wage_pct at calc time. Changes to team_members.wage_pct do NOT affect historical earnings.';
COMMENT ON COLUMN cleaning_cleaner_earnings.net_amount IS
    'gross_amount * commission_pct / 100, rounded HALF_UP to 2 decimals at insertion.';
COMMENT ON COLUMN cleaning_cleaner_earnings.payout_ref IS
    'Free-form reference from the owner: check number, Stripe transfer ID, Zelle confirmation, etc.';

-- ============================================================================
-- 2. INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_earnings_business_cleaner_status
    ON cleaning_cleaner_earnings (business_id, cleaner_id, status);

CREATE INDEX IF NOT EXISTS idx_earnings_business_paid_at
    ON cleaning_cleaner_earnings (business_id, paid_at)
    WHERE paid_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_earnings_business_created_at
    ON cleaning_cleaner_earnings (business_id, created_at DESC);

-- ============================================================================
-- 3. TRIGGER: auto-update updated_at on UPDATE
-- ============================================================================
-- Reuse the shared trigger function if it exists, otherwise create one local.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc WHERE proname = 'update_updated_at_column'
    ) THEN
        CREATE FUNCTION update_updated_at_column() RETURNS TRIGGER AS $func$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $func$ LANGUAGE plpgsql;
    END IF;
END$$;

DROP TRIGGER IF EXISTS trg_earnings_updated_at ON cleaning_cleaner_earnings;
CREATE TRIGGER trg_earnings_updated_at
    BEFORE UPDATE ON cleaning_cleaner_earnings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES (run manually after migration)
-- ============================================================================
-- SELECT count(*) FROM cleaning_cleaner_earnings;
-- \d cleaning_cleaner_earnings
-- SELECT indexname FROM pg_indexes WHERE tablename='cleaning_cleaner_earnings';
