-- Migration 027: persist client invitation tokens in cleaning_clients
-- Context: invite_client_route generated a UUID, emailed it, and returned it
-- to the caller — but never stored it. Without persistence there is no way
-- for an accept-client-invite endpoint to validate the token. This adds the
-- three columns needed for that flow.
--
-- Safe: all three columns are nullable; existing clients keep NULL (no invite
-- pending). Index is partial so it only covers active tokens.

ALTER TABLE cleaning_clients
  ADD COLUMN IF NOT EXISTS invite_token UUID,
  ADD COLUMN IF NOT EXISTS invite_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS invite_expires_at TIMESTAMPTZ;

-- Partial unique index: a given token can only point to one client, and we
-- only index rows that currently hold one.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cleaning_clients_invite_token
  ON cleaning_clients(invite_token)
  WHERE invite_token IS NOT NULL;

COMMENT ON COLUMN cleaning_clients.invite_token IS
  'UUID emailed to the homeowner so they can self-register. Cleared after acceptance. NULL = no active invite.';
COMMENT ON COLUMN cleaning_clients.invite_sent_at IS
  'When the invitation email was dispatched. NULL = never invited.';
COMMENT ON COLUMN cleaning_clients.invite_expires_at IS
  'Hard expiry (typically +7d from sent_at). Tokens past this are rejected by accept-client-invite.';
