-- ============================================================================
-- Rollback 023: Cleaner Earnings
-- ============================================================================
-- WARNING: This drops the entire payroll ledger. Earnings history is lost.
--          Only use in dev/staging for iteration, or pre-cutover cleanup.
-- ============================================================================

BEGIN;

DROP TRIGGER IF EXISTS trg_earnings_updated_at ON cleaning_cleaner_earnings;
DROP TABLE IF EXISTS cleaning_cleaner_earnings;

COMMIT;
