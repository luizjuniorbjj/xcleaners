# E2E Backlog — bugs found, not yet fixed

Items that manual + automated validation surfaced. Not blockers for 3sisters cutover; all are conservative-fix candidates for Sprint N+1.

## MEDIUM

### M1 — Dashboard KPIs show $0/0/0 despite real data
- **Where:** `/dashboard` — Revenue This Month, Bookings Today, Active Clients, Overdue Invoices
- **Expected:** reflect aggregation over `business_id` current user owns
- **Actual:** all zeros, while Schedule/Reports aggregate correctly
- **Root cause hypothesis:** KPI query likely missing `WHERE business_id = $1` OR using UTC `CURRENT_DATE` instead of business timezone for "today"
- **Fix size:** small (1-2 query fixes)
- **Test coverage:** `tests/negative/dashboard-kpis-nonzero.spec.ts` (TODO add)

### M2 — Reports page renders MOCK/hardcoded data
- **Where:** `/reports` — "Michael Williams", 63 jobs this month, $9,922 revenue, Team Alpha 16h
- **Expected:** aggregate real DB data filtered by business_id
- **Actual:** fake demo data displayed regardless of real state
- **Root cause hypothesis:** page never wired to real API; UI shows stubs
- **Fix size:** medium (full page rewrite — connect to aggregation endpoints)
- **Test coverage:** asserted via negative spec comparing displayed vs DB-queried totals

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

### L2 — LTV=$0 in Clients table
- **Where:** `/clients` column "LTV"
- **Expected:** sum of paid invoices per client
- **Actual:** all $0
- **Fix:** join `cleaning_invoices` where `status='paid'` and sum `total`

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
