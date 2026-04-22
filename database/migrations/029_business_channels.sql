-- 029_business_channels.sql
-- HIGH-1 (Sprint 2): per-business persistence for channel configs (WhatsApp first).
-- Story: XCL-HIGH-1.1 — Schema foundation
-- Date: 2026-04-22
-- Author: Aria (@architect) → Tank (@data-engineer) implementation
-- Spec: projects/xcleaners/specs/high-1-channels-ui-spec.md (canonical, section C.1)
-- IDs reais do backfill: PROJECT-CHECKPOINT linhas 124-128 (2026-04-21 22:37 UTC)

BEGIN;

-- =================================================================
-- 1. CREATE TABLE
-- =================================================================
CREATE TABLE IF NOT EXISTS business_channels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    channel_type VARCHAR(20) NOT NULL
        CHECK (channel_type IN ('whatsapp')),
    provider VARCHAR(50) NOT NULL
        CHECK (provider IN ('evolution_api')),
    instance_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'connecting', 'connected', 'disconnected', 'error')),
    last_status_check_at TIMESTAMPTZ,
    last_error TEXT,
    webhook_secret VARCHAR(128) NOT NULL,
    evolution_instance_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    connected_at TIMESTAMPTZ,
    CONSTRAINT uq_business_channel_type UNIQUE (business_id, channel_type)
);

-- =================================================================
-- 2. INDEXES
-- =================================================================
CREATE INDEX IF NOT EXISTS idx_business_channels_business
    ON business_channels(business_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_business_channels_instance
    ON business_channels(instance_name);

CREATE INDEX IF NOT EXISTS idx_business_channels_phone
    ON business_channels(phone_number)
    WHERE phone_number IS NOT NULL;

-- =================================================================
-- 3. TRIGGER updated_at
-- =================================================================
DROP TRIGGER IF EXISTS tr_business_channels_updated_at ON business_channels;
CREATE TRIGGER tr_business_channels_updated_at
    BEFORE UPDATE ON business_channels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =================================================================
-- 4. BACKFILL qatest-cleaning-co (preserva instance LIVE em prod)
-- =================================================================
-- IDs reais conforme PROJECT-CHECKPOINT linhas 124-128 (2026-04-21 22:37 UTC):
--   instance_name        = 'xcleaners'
--   evolution_instance_id = '7a873e27-2e7b-4e2a-9382-711f3febd2d9'
--   phone_number         = '5512988368047' (E.164 sem '+')
--   webhook_secret       = matches Railway env EVOLUTION_WEBHOOK_SECRET
--   status               = 'connected' (instance LIVE atendendo desde marco histórico)
INSERT INTO business_channels (
    business_id,
    channel_type,
    provider,
    instance_name,
    phone_number,
    status,
    webhook_secret,
    evolution_instance_id,
    connected_at
)
SELECT
    id,
    'whatsapp',
    'evolution_api',
    'xcleaners',
    '5512988368047',
    'connected',
    'b4bb19dff1949fb1f26aa28010eb46ea3e13c4ab493eabb29f1ff6bc78eb3876',
    '7a873e27-2e7b-4e2a-9382-711f3febd2d9',
    '2026-04-21 22:37:00+00'
FROM businesses
WHERE slug = 'qatest-cleaning-co'
ON CONFLICT (business_id, channel_type) DO NOTHING;

COMMIT;
