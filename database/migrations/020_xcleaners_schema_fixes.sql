-- ============================================================================
-- Migration 020: Xcleaners Schema Fixes
-- ============================================================================
-- Purpose: Add missing client columns, performance indexes, and integrity fixes
--
-- Changes:
--   1. Add missing client property columns (were silently dropped by valid_columns filter)
--   2. Add missing performance indexes identified in audit
--   3. Add unique constraint to prevent duplicate team members per business
--   4. Add invoice item total integrity check constraint
--   5. Deprecation comment on legacy cleaning_recurring_schedules table
--
-- Idempotent: All statements use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Missing client property columns
-- Previously these fields were stored as JSON in the notes column via
-- a __META__ workaround in client_service.py. Now they get proper columns.
-- ============================================================================

ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS preferred_contact VARCHAR(20)
    CHECK (preferred_contact IN ('phone', 'email', 'text', 'whatsapp'));

ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS billing_address VARCHAR(500);

ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';

ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS internal_notes TEXT;

-- Access codes and property access info
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS key_location VARCHAR(255);
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS lockbox_code VARCHAR(50);
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS alarm_code VARCHAR(50);
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS gate_code VARCHAR(50);
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS garage_code VARCHAR(50);
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS parking_instructions VARCHAR(500);

-- Pet details (structured — supplements the legacy pet_details VARCHAR field)
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS pet_type VARCHAR(50);
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS pet_name VARCHAR(100);
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS pet_temperament VARCHAR(100);
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS pet_location_during_cleaning VARCHAR(255);

-- Cleaning preferences
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS products_to_use TEXT;
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS products_to_avoid TEXT;
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS rooms_to_skip TEXT;
ALTER TABLE cleaning_clients ADD COLUMN IF NOT EXISTS preferred_cleaning_order TEXT;

-- ============================================================================
-- 2. Missing indexes identified in audit
-- ============================================================================

-- Booking lookup by assigned team (for team schedule views)
CREATE INDEX IF NOT EXISTS idx_cleaning_bookings_team_id
    ON cleaning_bookings(team_id);

-- Duplicate booking detection: business + client + date range + recurring schedule
CREATE INDEX IF NOT EXISTS idx_cleaning_bookings_recurring_check
    ON cleaning_bookings(business_id, client_id, scheduled_date, recurring_schedule_id)
    WHERE status IN ('confirmed', 'in_progress', 'completed');

-- Checklist items by business (for template listing)
CREATE INDEX IF NOT EXISTS idx_cleaning_checklist_items_biz
    ON cleaning_checklist_items(business_id);

-- Notification retry queue: pending/failed by target
CREATE INDEX IF NOT EXISTS idx_cleaning_notifications_target_status
    ON cleaning_notifications(business_id, target_id, status)
    WHERE status IN ('pending', 'failed');

-- Job logs joined to checklist items
CREATE INDEX IF NOT EXISTS idx_cleaning_job_logs_checklist_item
    ON cleaning_job_logs(checklist_item_id)
    WHERE checklist_item_id IS NOT NULL;

-- Public reviews by business for display (sorted by date)
CREATE INDEX IF NOT EXISTS idx_cleaning_reviews_biz_date
    ON cleaning_reviews(business_id, created_at DESC)
    WHERE is_public = true;

-- ============================================================================
-- 3. Unique constraint: prevent duplicate team members per business
-- Applies only to non-terminated members with a non-null email.
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_cleaning_team_members_biz_email
    ON cleaning_team_members(business_id, email)
    WHERE email IS NOT NULL AND status != 'terminated';

-- ============================================================================
-- 4. Invoice item total integrity check
-- Ensures (quantity * unit_price) == total within floating-point tolerance.
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'cleaning_invoice_items'
          AND constraint_name = 'chk_invoice_item_total'
    ) THEN
        ALTER TABLE cleaning_invoice_items
            ADD CONSTRAINT chk_invoice_item_total
            CHECK (ABS(total - (quantity * unit_price)) < 0.01);
    END IF;
END $$;

-- ============================================================================
-- 5. Deprecation marker on legacy recurring schedules table
-- ============================================================================

COMMENT ON TABLE cleaning_recurring_schedules IS
    'DEPRECATED in v3. Use cleaning_client_schedules instead. Kept for historical data.';

COMMIT;
