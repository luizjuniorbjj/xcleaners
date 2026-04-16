---
type: ops-guide
title: "Recurring Auto-Generator — Cron Setup"
project: xcleaners
status: active
tags:
  - project/xcleaners
  - ops
  - recurring
  - sprint-d
---

# Recurring Auto-Generator — Cron Setup

Operational guide for triggering the recurring bookings auto-generator on a daily schedule.

## Overview

Sprint D Track A exposes an HMAC-authed endpoint for cron-triggered multi-day window generation:

```
POST /api/v1/clean/internal/recurring/generate-window
Headers: X-Internal-Signature: <hex HMAC-SHA256 of body>
Body: {"business_id": "<uuid>", "days": 14}
```

The endpoint iterates `daily_generator.generate_daily_schedule` for each date in `[today, today + days - 1]` and returns an aggregate summary.

**Default cadence:** daily at `02:00 UTC`. For 3Sisters NYC (`America/New_York`, UTC-5), this = `21:00 local previous day` — acceptable v1 (booking scheduled_date is already the business-facing date). Future v2 may add per-business timezone support (see ADR-002 Decision 5).

---

## Prerequisites

### 1. Generate HMAC secret

```bash
openssl rand -hex 32
# → e.g. a7f2b9d4e1... (64 chars)
```

### 2. Set server env var

On Railway (`feat/recurring-auto-gen` branch → main after merge):

```
INTERNAL_CRON_SECRET=<secret-from-above>
```

Must match exactly between server and cron caller.

### 3. Install the trigger script

The script lives at `scripts/trigger_recurring.sh` (chmod +x on Linux/Railway).

---

## Option A — Railway Cron (recommended)

Railway supports native cron jobs in-project.

1. In Railway dashboard → select project `xcleaners` → `+ New` → `Cron`
2. Configure:
   - **Schedule:** `0 2 * * *` (daily at 02:00 UTC)
   - **Command:** `./scripts/trigger_recurring.sh <BUSINESS_UUID> 14`
   - **Env vars:** inherit `XCLEANERS_API_URL` + `INTERNAL_CRON_SECRET`

3. For multiple businesses (post-3Sisters cutover), create one cron job per business OR extend the script to loop over a business_ids list fetched from DB.

**Recommended initial setup (3Sisters only):**

```
Schedule: 0 2 * * *
Command:  ./scripts/trigger_recurring.sh 00000000-0000-0000-0000-000000000001 14
```

Replace the UUID with the actual 3Sisters business_id (`SELECT id FROM businesses WHERE slug='3sisters';`).

---

## Option B — GitHub Actions

If Railway cron is unavailable, use GitHub Actions scheduled workflow:

```yaml
# .github/workflows/recurring-cron.yml
name: Recurring Auto-Generator
on:
  schedule:
    - cron: '0 2 * * *'   # daily at 02:00 UTC
  workflow_dispatch:         # manual trigger for testing

jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Trigger recurring window
        env:
          XCLEANERS_API_URL: ${{ secrets.XCLEANERS_API_URL }}
          INTERNAL_CRON_SECRET: ${{ secrets.INTERNAL_CRON_SECRET }}
        run: |
          chmod +x scripts/trigger_recurring.sh
          ./scripts/trigger_recurring.sh ${{ secrets.BUSINESS_ID_3SISTERS }} 14
```

Required secrets in GitHub repo settings:
- `XCLEANERS_API_URL` — production API base URL
- `INTERNAL_CRON_SECRET` — same as server env var
- `BUSINESS_ID_3SISTERS` — business UUID

---

## Manual trigger (testing / operations)

```bash
# From any box with bash + openssl + curl
export XCLEANERS_API_URL=https://api.xcleaners.com
export INTERNAL_CRON_SECRET=<paste-secret>

./scripts/trigger_recurring.sh 00000000-0000-0000-0000-000000000001 14
```

Expected response (success):

```json
{
  "generated": 28,
  "skipped_by_skip_table": 3,
  "pricing_failures": [],
  "unassigned": 0,
  "conflicts": 0,
  "summary": {
    "window_days": 14,
    "business_id": "...",
    "start_date": "2026-04-17",
    "end_date": "2026-04-30",
    "total_schedules_scanned": 31
  }
}
```

---

## Monitoring

### Logs to watch

```
[RECURRING] Starting window <start> → <end>
[RECURRING] Scanned schedules for <date> — N filtered by cleaning_schedule_skips
[RECURRING] Generated booking=<id> schedule=<id> client=<id> final=$X tier=Y
[RECURRING] Pricing failure for schedule=<id>: <reason>. Booking SKIPPED.
[RECURRING] Window complete: generated=X unassigned=Y conflicts=Z failures=F
```

### Alerts to set up

- **HTTP 500 from endpoint** — INTERNAL_CRON_SECRET misconfigured
- **HTTP 401 from endpoint** — signature mismatch (secret out of sync)
- **pricing_failures.length > 0** — owner needs to fix schedule config (missing tier/BR/BA, missing frequency_id, etc.)
- **generated = 0 for >2 consecutive days** — cron not running OR all schedules paused

### Healthcheck query

Weekly:

```sql
SELECT
    DATE(created_at) AS day,
    COUNT(*) AS bookings_created,
    COUNT(*) FILTER (WHERE source = 'recurring') AS recurring_bookings
FROM cleaning_bookings
WHERE created_at >= NOW() - INTERVAL '14 days'
GROUP BY DATE(created_at)
ORDER BY day DESC;
```

Expected: non-zero `recurring_bookings` each weekday for businesses with active recurring schedules.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 401 invalid signature | Secret mismatch | Regenerate, update both server + cron |
| 500 server misconfigured | `INTERNAL_CRON_SECRET` not set on server | Set env var, restart app |
| 500 pricing_engine error | Service missing tier/BR/BA | Backfill service config pre-cutover |
| 0 bookings generated | No schedules match OR all paused | Check `cleaning_client_schedules` status + next_occurrence |
| Duplicate bookings | Should be impossible — Redis lock prevents | Investigate lock TTL expiration |

---

## References

- **ADR-002** — `docs/architecture/adr-002-recurring-auto-generator.md`
- **Sprint Plan** — `docs/sprints/sprint-d-recurring-payroll.md` (Track A)
- **Service** — `app/modules/cleaning/services/recurring_generator.py`
- **Endpoint** — `app/modules/cleaning/routes/recurring_routes.py`
- **Trigger script** — `scripts/trigger_recurring.sh`
