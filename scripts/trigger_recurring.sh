#!/usr/bin/env bash
# ============================================================================
# Xcleaners — Recurring Auto-Generator Cron Trigger (Sprint D Track A)
# ============================================================================
# Calls POST /api/v1/clean/internal/recurring/generate-window with HMAC auth.
# Intended for Railway cron OR GitHub Actions scheduled workflow.
#
# Usage:
#   ./trigger_recurring.sh <business_id> [days]
#
# Env vars required:
#   XCLEANERS_API_URL       e.g. https://api.xcleaners.com (no trailing slash)
#   INTERNAL_CRON_SECRET    HMAC secret matching server env (openssl rand -hex 32)
#
# Exit codes:
#   0 = success, 1 = missing args, 2 = missing env, 3 = HTTP error
# ============================================================================

set -euo pipefail

# --- arg parsing ---
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <business_id> [days]" >&2
    exit 1
fi

BUSINESS_ID="$1"
DAYS="${2:-14}"

# --- env validation ---
: "${XCLEANERS_API_URL:?XCLEANERS_API_URL not set}"
: "${INTERNAL_CRON_SECRET:?INTERNAL_CRON_SECRET not set}"

# --- build body ---
BODY=$(printf '{"business_id":"%s","days":%s}' "$BUSINESS_ID" "$DAYS")

# --- compute HMAC-SHA256 signature ---
# openssl dgst -sha256 -hmac "$SECRET" outputs "(stdin)= <hex>"; strip prefix
SIGNATURE=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$INTERNAL_CRON_SECRET" | sed 's/^.* //')

# --- call endpoint ---
URL="${XCLEANERS_API_URL}/api/v1/clean/internal/recurring/generate-window"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Triggering recurring window: business=$BUSINESS_ID days=$DAYS" >&2

HTTP_CODE=$(curl -s -o /tmp/recurring_response.json -w "%{http_code}" \
    -X POST "$URL" \
    -H "Content-Type: application/json" \
    -H "X-Internal-Signature: $SIGNATURE" \
    -d "$BODY")

RESPONSE=$(cat /tmp/recurring_response.json)

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] HTTP $HTTP_CODE — response: $RESPONSE" >&2

if [[ "$HTTP_CODE" != "200" ]]; then
    echo "ERROR: non-200 response ($HTTP_CODE)" >&2
    exit 3
fi

# --- summary for logs ---
if command -v jq >/dev/null 2>&1; then
    GENERATED=$(echo "$RESPONSE" | jq -r '.generated // 0')
    SKIPPED=$(echo "$RESPONSE" | jq -r '.skipped_by_skip_table // 0')
    FAILURES=$(echo "$RESPONSE" | jq -r '.pricing_failures | length')
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] SUCCESS — generated=$GENERATED skipped=$SKIPPED failures=$FAILURES" >&2
fi

exit 0
