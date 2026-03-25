-- ============================================================================
-- Migration 016: Add structured_data to business_personas
-- ============================================================================
-- Purpose: Add structured_data JSONB and prompt_manually_edited columns
--          to business_personas table.
--
-- History: Previously applied inline via app/database.py init_db()
--          (see "Persona structured data (Migration 016 - Story 1.1)" block).
--          This migration file formalizes that change for migration tracking.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS — safe to apply on any database state.
-- ============================================================================

ALTER TABLE business_personas ADD COLUMN IF NOT EXISTS structured_data JSONB DEFAULT NULL;
ALTER TABLE business_personas ADD COLUMN IF NOT EXISTS prompt_manually_edited BOOLEAN DEFAULT FALSE;
