---
type: qa-strategy
id: QAS-1.1
title: "QA Test Strategy — Story 1.1 Pricing Engine Hybrid"
project: xcleaners
author: "@qa (Oracle)"
date: 2026-04-16
story: docs/stories/1.1.pricing-engine-hybrid.md
adr: docs/architecture/adr-001-pricing-engine-hybrid.md
status: ready-for-dev
tags:
  - qa
  - pricing
  - regression
  - tdd
---

# QA Test Strategy — Story 1.1 Pricing Engine Hybrid

## Executive Summary

**Gate:** Story 1.1 cannot merge until:
- 10/10 Launch27 regression tests pass with tolerance ±$0.01
- 7/7 edge case tests pass (ADR-001 Decisions)
- 1/1 integration test pass (booking creation writes price_snapshot)
- Code coverage on `pricing_engine.py` ≥ 90%
- CodeRabbit review CLEAN (no CRITICAL/HIGH findings)

**Authority:** This document is the gate criteria. Both @dev (implementer) and Ana/Mario (3Sisters owners) should be able to reproduce results independently.

**Files delivered in this strategy:**

| File | Purpose |
|------|---------|
| `tests/fixtures/launch27_3sisters_bookings.py` | 10 fixtures + dataclasses + self-validation |
| `tests/test_pricing_engine.py` | Regression + edge cases + integration + meta tests |
| `docs/qa/story-1.1-test-strategy.md` | This document — strategy, risks, coverage |

---

## 1. Test Pyramid

```
                    /\
                   /  \       1 integration test
                  /----\      (booking creation flow, end-to-end)
                 /      \
                /--------\    7 edge case tests
               /          \   (ADR-001 Decisions 1/2/3/5/6/7 + happy + 2 error paths)
              /------------\
             / 10 regression\  10 parametrized tests
            /  ±$0.01 match  \ (Launch27 3Sisters fixtures)
           /------------------\
          /   1 meta-test      \  Canonical equation self-validation
         /----------------------\  of fixture file
```

**Rationale:**
- **Bottom (meta):** ensures fixtures are mathematically consistent before any engine touches them. Catches fixture-file bugs before engine bugs.
- **Middle-low (regression):** validates the engine reproduces Launch27 outputs within tolerance. Critical for 3Sisters cutover trust.
- **Middle-high (edge cases):** validates each ADR-001 decision is implemented correctly, in isolation.
- **Top (integration):** validates the engine integrates with booking creation flow correctly (snapshot written, extras persisted).

---

## 2. Coverage Matrix — Acceptance Criteria → Tests

| AC | Description | Test(s) |
|----|-------------|---------|
| AC1 | Migration 021 applied | (covered by migration-021-validation.md; not in this strategy) |
| AC2 | Pricing engine Python module | `test_pricing_matches_launch27[*]` (10×) + all 7 edge cases + 2 error-path tests |
| AC3 | Preview endpoint | (integration test TBD — out of Story 1.1 Task 2 scope) |
| AC4 | UI EXTEND services.js + bookings.js | (manual UX tests — see Story 1.1 "Manual UX Tests") |
| AC5 | UI 4 new modules | (manual UX tests) |
| AC6 | Snapshot immutable | `test_snapshot_immutable_after_booking` + `test_booking_creation_writes_immutable_snapshot` (integration) |
| **AC7** | **10-booking regression ±$0.01** | **`test_pricing_matches_launch27` parametrized over 10 fixtures** |
| AC7 | 7 edge case tests | 7 dedicated `test_*` functions in `test_pricing_engine.py` |

---

## 3. Fixture Inventory (10 bookings)

| # | Name | Tier | Freq | Extras | Adj | Tax | Provenance |
|---|------|------|------|--------|-----|-----|-----------|
| F1 | 2R×1BA Basic + Stairs, Weekly 15%, adj -$29.58 | Basic | Weekly | 1 | $-29.58 | 4.5% | **REAL** (captured booking #5792) |
| F2 | Studio Basic One Time, no extras | Basic | One Time | 0 | $0 | 4.5% | Derived |
| F3 | Studio Premium + Oven Weekly 15% | Premium | Weekly | 1 | $0 | 4.5% | Derived |
| F4 | 1R×1BA Deep + Windows + Oven Biweekly 10% | Deep | Biweekly | 2 | $0 | 4.5% | Derived |
| F5 | 2R×2BA Basic Monthly 5% adj +$50 | Basic | Monthly | 0 | $+50 | 4.5% | Derived |
| F6 | 3R×1BA Premium + 3 extras Weekly 15% | Premium | Weekly | 3 | $0 | 4.5% | Derived |
| F7 | Studio Deep + Walls One Time | Deep | One Time | 1 | $0 | 4.5% | Derived |
| F8 | 2R×1BA Premium + Laundry Biweekly 10% adj -$20 | Premium | Biweekly | 1 | $-20 | 4.5% | Derived |
| F9 | 1R×1BA Basic One Time, **no tax** (Dallas) | Basic | One Time | 0 | $0 | **0%** | Derived |
| F10 | 3R×1BA Deep + Fridge + Move-in/out Monthly 5% adj +$15 | Deep | Monthly | 2 | $+15 | 4.5% | Derived |

**Coverage distribution:**
- **Tier:** Basic=4, Deep=3, Premium=3 (all ≥2 ✓)
- **Frequency:** One Time=3, Weekly=3, Biweekly=2, Monthly=2 (all ≥2 ✓)
- **Extras:** 0 extras=3, 1 extra=4, 2+ extras=3
- **Adjustment:** negative=2, zero=6, positive=2
- **Tax:** 4.5% NYC=9, 0% Dallas=1
- **Service size:** Studio=3, 1R×1BA=2, 2R×1BA=2, 2R×2BA=1, 3R×1BA=2

All fixtures validated mathematically via canonical equation (see meta-test `test_all_fixtures_satisfy_canonical_equation`).

---

## 4. Known Unknowns & Sampling Risk

### 4.1 The $275 vs $175 discrepancy (F1)

The observed pricing ladder (FASE2 analysis) indicates **2R×1BA Basic = $175**, but the real captured booking #5792 shows **service amount = $275** (before the $30 Stairs extra).

**Possible explanations:**
1. **Owner used an override in Launch27** — Ana set $275 for this specific service row
2. **Booking was actually Deep tier, labeled Basic in summary** — Deep 2R×1BA = $350, still doesn't match
3. **Ladder observation had a sampling issue in FASE2** — some services shown didn't have the `Category` tag, which the analysis inferred but may have mis-categorized
4. **Business rule the analysis missed** — e.g. bedroom-count-specific multipliers

**Fixture F1 honors the observed $275** (reality over model). The 9 derived fixtures use the ladder as stated (since derived values are models of a model — so no double-derivation).

**Action item (pre-cutover):** Ana or Mario should log into Launch27 admin, look at the actual service configuration for "2R×1BA Basic" (or similar), and confirm whether $275 is a formula output, an override, or something else. Document findings in `docs/qa/3sisters-pricing-reconciliation.md`. This investigation is **not** a blocker for merge of Story 1.1 — it is a blocker for cutover.

### 4.2 Sampling risk of 9 DERIVED fixtures

**Acknowledge honestly:** only 1 of 10 fixtures is a 100% captured Launch27 output. The other 9 are mathematically derived using:
- Pricing ladder observed in FASE2
- Standard extras catalog observed (Stairs $30, Inside X $25)
- Frequencies configured in 3Sisters (15%/10%/5%)
- NYC sales tax 4.5%
- Canonical order of operations (subtotal → discount → adjustment → tax)

**Confidence interval:** if the canonical order of operations is correct AND the ladder is correct AND extras prices are correct, the 9 derived fixtures should match Launch27 exactly. But:
- Order of operations was **inferred** from 1 captured booking
- Rounding mode (ROUND_HALF_UP) was **inferred** from 1 captured tax calculation

**Estimate:** 7-9 of 9 derived fixtures will match Launch27 outputs. 0-2 may reveal:
- A rounding edge case we haven't seen
- A pricing rule we haven't observed (e.g. minimum booking charge, weekend surcharge)

### 4.3 Mitigation plan — Capture 5 more REAL fixtures pre-cutover

**Action item (before cutover Week 7):**
Ana/Mario create 5 test bookings in Launch27 admin with varied parameters, screenshot breakdown, then reproduce in xcleaners staging:
1. Studio Basic One Time — no extras (validates F2)
2. 3R×1BA Premium + 3 extras Weekly 15% — (validates F6)
3. 2R×2BA Basic Monthly 5% with positive adjustment — (validates F5)
4. 1R×1BA Deep + 2 extras Biweekly 10% — (validates F4)
5. Same-scale with negative adjustment — (validates tax_base liquid logic)

**Success criterion:** 5/5 validate (±$0.01). If any fail, root-cause BEFORE cutover.

**Fallback:** If staging regression reveals a mismatch, update fixtures OR update engine logic. Document resolution in Story 1.1 Change Log.

### 4.4 Not-modeled scenarios (v1 scope)

The following are **intentionally excluded** from Story 1.1 regression:
- **Tip** — accepted as part of booking total but not in pricing engine scope
- **Gift cards** — not configured in 3Sisters, deferred to Story 1.6+
- **Referral rewards** — not configured in 3Sisters, deferred
- **Minimum booking charge** — not observed; add if Launch27 cross-check reveals it
- **Custom pricing parameters** (`cleaning_pricing_parameters`) — not observed in use; engine v1 ignores

If any of these surface during the 5-booking pre-cutover check, escalate to @architect for ADR-001 amendment.

---

## 5. Edge Case Tests (ADR-001 Decisions)

Each test validates exactly one ADR decision in isolation. See `test_pricing_engine.py` for implementations.

| # | Test | ADR Decision | What It Proves |
|---|------|--------------|----------------|
| 1 | `test_formula_change_keeps_overrides_stale` | Decision 1 | Owner edits formula → existing override preserved (not recomputed) |
| 2 | `test_snapshot_immutable_after_booking` | Decision 2 | Booking's `price_snapshot` unchanged after formula/extras mutation |
| 3 | `test_override_precedence_wins` | Decision 3 | Override exists → override wins over formula computation |
| 4 | `test_tier_multiplier_only_on_base` | Decision 5 | Same extra costs flat across Basic/Deep/Premium (tier multiplier NOT applied to extras) |
| 5 | `test_tax_base_is_liquid` | Decision 6 | Tax on (subtotal − discount − adjustment), NOT on gross subtotal |
| 6 | `test_adjustment_before_tax` | Decision 7 | Positive/negative adjustment adjusts `amount_before_tax`, tax computed on result |
| 7 | `test_happy_path_zero_extras_zero_discount_no_tax` | (Integration) | Minimal case exercises full engine without optional components |

**Error path tests (bonus):**
- `test_missing_formula_raises_pricing_config_error` — ADR-001 Error handling
- `test_missing_tax_config_defaults_to_zero` — ADR-001 Error handling (graceful fallback)

---

## 6. QA Gate Criteria — Pre-Merge (@dev → @qa)

Checklist executed by @qa before approving Story 1.1 PR:

- [ ] **Regression:** 10/10 `test_pricing_matches_launch27` PASS
- [ ] **Edge cases:** 7/7 dedicated edge case tests PASS
- [ ] **Integration:** 1/1 `test_booking_creation_writes_immutable_snapshot` PASS
- [ ] **Meta:** 1/1 `test_all_fixtures_satisfy_canonical_equation` PASS
- [ ] **Error paths:** 2/2 error-path tests PASS
- [ ] **Coverage:** `pytest --cov=app.modules.cleaning.services.pricing_engine` ≥ 90%
- [ ] **CodeRabbit:** run via `*code-review committed` → CLEAN (no CRITICAL/HIGH)
- [ ] **Migration applied cleanly:** migration 021 idempotent verified in staging
- [ ] **Existing tests:** `pytest tests/test_models.py tests/test_routes.py` still PASS (no regression)
- [ ] **Manual UX:** owner can create service with tier, override, revert; booking preview shows breakdown live

**If any item fails:** @qa gate decision = FAIL. @dev receives QA_FIX_REQUEST.md with specific findings.

---

## 7. QA Gate Criteria — Pre-Cutover (xcleaners Semana 7)

Separate gate — validates against **real 3Sisters data**, not fixtures:

- [ ] **Real cross-check 5/5:** Ana/Mario create 5 real test bookings in Launch27 + staging xcleaners. All 5 match within ±$0.01.
- [ ] **Historical validation:** pick 10 historical bookings from 3Sisters Launch27 history (random sample), reproduce in xcleaners staging. 10/10 match within ±$0.01.
- [ ] **Ana sign-off:** Ana herself (not Mario or LPJ team) creates 3 bookings in staging AND confirms prices look correct to her.
- [ ] **F1 reconciliation:** if $275 vs $175 discrepancy was resolved (Section 4.1), document resolution.
- [ ] **Rollback rehearsed:** on staging, apply rollback_021.sql, verify schema reverted, re-apply migration. Prove the round-trip works.

**If any fails:** Cutover blocked. Investigate and remediate.

---

## 8. Test Execution Commands

### Local dev loop
```bash
cd /c/xcleaners

# Activate venv
source venv/bin/activate  # or .venv/Scripts/activate on Windows

# Run pricing tests only (fast feedback)
pytest tests/test_pricing_engine.py -v

# Run with coverage
pytest tests/test_pricing_engine.py \
    --cov=app.modules.cleaning.services.pricing_engine \
    --cov-report=term-missing \
    --cov-fail-under=90

# Run just the regression gate
pytest tests/test_pricing_engine.py::test_pricing_matches_launch27 -v

# Run just edge cases
pytest tests/test_pricing_engine.py -v -k "test_formula_change or test_override_precedence or test_tier_multiplier or test_tax_base or test_adjustment or test_happy_path or test_snapshot_immutable"

# Standalone fixture self-validation (before running engine tests)
python tests/fixtures/launch27_3sisters_bookings.py
```

### CI pipeline
```bash
# Full suite + coverage + CodeRabbit
pytest -v --cov=app --cov-fail-under=80
wsl bash -c 'cd /mnt/c/xcleaners && ~/.local/bin/coderabbit --prompt-only -t committed --base main'
```

---

## 9. Handoff

### @dev (Neo) — consumer of this strategy

Workflow recommended:
1. **Read** `docs/architecture/adr-001-pricing-engine-hybrid.md` — understand ordering, edge cases
2. **Read** `docs/stories/1.1.pricing-engine-hybrid.md` — full story with all ACs
3. **Read** `tests/fixtures/launch27_3sisters_bookings.py` — understand expected outputs
4. **Read** `tests/test_pricing_engine.py` — understand test contract
5. **Run** `python tests/fixtures/launch27_3sisters_bookings.py` — verify fixtures pass self-validation
6. **Implement** `app/modules/cleaning/services/pricing_engine.py` until **all tests pass**
7. **Self-verify**: run `pytest tests/test_pricing_engine.py --cov --cov-fail-under=90`
8. **Request review:** notify @qa for *review + *gate

**TDD flow:** work test-by-test. Start with `test_happy_path_zero_extras_zero_discount_no_tax` (simplest) and progressively enable harder tests by uncommenting `pytest.skip()` or running full suite.

### @smith — adversarial re-verify post-implementation

After @dev completes:
- Use the 10 fixtures as adversarial baseline
- Test 3-5 NEW scenarios not in the fixture file (stress edge cases)
- Try to break the engine with malicious inputs (negative tier multiplier? empty extras list? NaN adjustment?)
- Verify rollback still works if engine is ripped out

### Ana (3Sisters) — final acceptance

Pre-cutover (Section 7 criteria): Ana creates 3 bookings in staging + confirms prices match her Launch27 output. If Ana is satisfied, cutover is GO.

---

## 10. Change Log

| Date | Version | Change | Author |
|------|---------|--------|--------|
| 2026-04-16 | 0.1 | Initial strategy with 10 fixtures (1 REAL + 9 DERIVED), 7 edge cases, 1 integration, 2 error paths | @qa (Oracle) |

---

*Tests are contracts. Fixtures are promises. The engine will match — or I will find out why.*

— Oracle, guardião da qualidade 🛡️
