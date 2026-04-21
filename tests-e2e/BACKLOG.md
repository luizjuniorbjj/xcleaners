# E2E Backlog — bugs found, not yet fixed

Items that manual + automated validation surfaced. Not blockers for 3sisters cutover; all are conservative-fix candidates for Sprint N+1.

## MEDIUM

### ~~M1 — Dashboard KPIs show $0/0/0 despite real data~~ ✅ FIXED 2026-04-21 (commit 87380a8)
- **Root cause:** frontend checked legacy field `today_bookings_count` that backend renamed to object `bookings_today` → always fell into zero fallback
- **Fix:** validate object non-empty instead of legacy field key (dashboard.js:132)

### M2 — Reports page renders MOCK/hardcoded data (DEFERRED — not cutover blocker)
- **Where:** `/reports` — "Michael Williams", 63 jobs this month, $9,922 revenue, Team Alpha 16h
- **Root cause confirmed 2026-04-21:** `reports.js` generates ALL data client-side via `Math.random()` + hardcoded names; no backend endpoint exists
- **Fix size:** medium-large (~3-4h): create `GET /reports/summary` endpoint with aggregations (revenue by week, jobs by day, top clients by paid invoices, team performance) + rewrite `reports.js` to consume API
- **Why deferred:** not in critical path for cutover; page is obviously demo; can ship as Sprint N+1 with real aggregations
- **Test coverage:** `tests/negative/reports-not-mock.spec.ts` (TODO add when wired to real API)

### M3 — Wave 2 dead branch in reschedule error parsing
- **Where:** `frontend/cleaning/static/js/homeowner/my-bookings.js` `_submitReschedule`
- **Expected:** parse `err.detail.reason` object to distinguish limit vs window errors
- **Actual:** `homeowner_routes.py:269` raises `HTTPException(detail=message)` as string; CleanAPI stringifies; frontend branch never executes
- **Workaround active:** fallback string fallback shows correct message (not a user-visible bug)
- **Fix size:** small (route + wrapper contract alignment)
- **Impact:** code clarity only

## LOW

### L1 — /formulas deep-link returns 404
- **Where:** direct URL `https://app.xcleaners.app/formulas`
- **Actual:** 404 Page Not Found (correct route is `/pricing`)
- **Fix:** add 301 redirect in router, or rename sidebar target
- **Impact:** users who bookmark deep links

### ~~L2 — LTV=$0 in Clients table~~ ✅ FIXED 2026-04-21 (commit 9195580)
- **Root cause:** listing read `c.lifetime_value` (stale column never updated by billing flow); detail endpoint already aggregated correctly
- **Fix:** LEFT JOIN LATERAL with `SUM(total) FILTER (WHERE status='paid')` from cleaning_invoices; sort-by-lifetime_value uses live value too (client_service.py:412)

### L3 — Ghost setting `max_reschedules_per_month` still in JSONB
- **Where:** `cleaning_settings.cancellation_policy.max_reschedules_per_month` persists in businesses that saved under old UI
- **Impact:** harmless (not read by backend), just pollution
- **Fix:** migration to clean up, or ignore indefinitely

### L4 — Legacy rescheduled bookings have count=0
- **Where:** bookings with `status='rescheduled'` that existed before migration 028
- **Impact:** homeowner can reschedule them once more (one-time bonus in the transition)
- **Fix:** one-shot UPDATE to seed count=1 where status=rescheduled AND created_at < migration date

## Backlog specs to add

- `tests/negative/dashboard-kpis-nonzero.spec.ts` — catch M1 regression
- `tests/negative/reports-not-mock.spec.ts` — catch M2 regression
- `tests/negative/direct-url-routes.spec.ts` — catch L1 + similar
- `tests/regression/owner-payroll.spec.ts` — coverage gap
- `tests/regression/owner-payments-stripe.spec.ts` — coverage gap
- `tests/negative/cross-role-authz.spec.ts` — homeowner cannot access /dashboard, cleaner cannot access /clients, etc
