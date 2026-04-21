# Xcleaners E2E — Playwright Test Suite

End-to-end tests for the Xcleaners cleaning-business SaaS. Page Object Model, multi-environment, CI-ready.

## Quick start

```bash
cd tests-e2e
npm install
npx playwright install chromium

# Run tests (defaults to prod, uses .env.prod)
npm test

# Open last HTML report
npm run report
```

## Environment

Three env files supported via `TEST_ENV=prod|staging|dev`:
- `.env.prod` — production (default, points at `https://app.xcleaners.app`)
- `.env.staging` — placeholder
- `.env.example` — template for new envs

Copy `.env.example` → `.env.prod` and fill in values. **Never commit `.env.prod`.**

## Scripts

| Script | What it runs | Time |
|---|---|---|
| `npm test` | everything | ~15min |
| `npm run test:smoke` | smoke only (3 specs) | ~90s |
| `npm run test:policy` | Policy MVP suite (5 specs) | ~6min |
| `npm run test:regression` | regression suite (7 specs) | ~7min |
| `npm run test:negative` | negative paths (2 specs) | ~2min |
| `npm run test:headed` | show browser during run | varies |
| `npm run test:debug` | step through tests in inspector | varies |
| `npm run test:ui` | Playwright UI mode (best for writing) | — |
| `npm run codegen` | record new spec interactively | — |
| `npm run report` | open last HTML report | — |

## Structure

```
tests-e2e/
├── playwright.config.ts        # multi-env + reporters + tracing
├── .env.{prod,staging,example} # env-specific secrets (gitignored)
├── fixtures/                   # auth, db, policy fixtures
│   ├── auth.fixture.ts         # ownerPage / homeownerPage / cleanerPage
│   ├── auth.setup.ts           # runs once, logs in each role, saves storage
│   └── policy.fixture.ts       # resetPolicy helper
├── pages/                      # Page Object Model
│   ├── LoginPage.ts
│   ├── owner/                  # 7 POMs for owner portal
│   ├── homeowner/              # 3 POMs for homeowner portal + modals
│   └── cleaner/                # 1 POM for cleaner portal
├── tests/
│   ├── smoke/                  # 3 specs — run on every PR
│   ├── regression/
│   │   ├── *.spec.ts           # 7 regression specs
│   │   └── policy-mvp/         # 5 specs — CORE VALUE (Waves 1+2+3)
│   └── negative/               # 2 specs — failure paths
├── helpers/                    # db-helpers, api-client, assertions
└── reports/                    # gitignored; HTML + screenshots + traces
```

## Writing a new test

1. **Add Page Object** (if the page doesn't have one):
   ```typescript
   // pages/owner/OwnerFooPage.ts
   export class OwnerFooPage {
     constructor(readonly page: Page) {}
     async goto() { await this.page.goto('/foo'); }
     // ... locators + actions
   }
   ```

2. **Write spec** in the right suite folder:
   ```typescript
   // tests/regression/owner-foo.spec.ts
   import { test, expect } from '../../fixtures/auth.fixture';
   import { OwnerFooPage } from '../../pages/owner/OwnerFooPage';

   test('foo renders', async ({ ownerPage }) => {
     const foo = new OwnerFooPage(ownerPage);
     await foo.goto();
     await expect(foo.heading).toBeVisible();
   });
   ```

3. **Seed test data** via `helpers/db-helpers.ts` — use `createTestBooking` / `resetPolicy` for deterministic state.

4. **Clean up** in `afterEach` — call `deleteBooking` to keep the test business pristine.

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for more patterns.

## CI

Configured in `.github/workflows/e2e.yml`:
- **Every PR:** smoke suite runs (~90s, <3min total with checkout/install)
- **Nightly (06:00 UTC):** full regression against prod
- **Manual dispatch:** any subset via `workflow_dispatch` → `suite` input

Required secrets:
- `E2E_DATABASE_URL` — prod Railway pooler URL
- `E2E_TEST_PASSWORD` — password shared by the 3 test users

## Test business & users

Isolated from real customer data:

| | Email | Role |
|---|---|---|
| Business | slug `e2e-testing-co` (id `329f590d`) | — |
| Owner | `test-e2e-owner@xcleaners.test` | owner |
| Homeowner | `test-e2e-homeowner@xcleaners.test` | homeowner |
| Cleaner | `test-e2e-cleaner@xcleaners.test` | cleaner |

Password for all three is in `.env.prod` (ask team admin).

## Findings + follow-up

See [`BACKLOG.md`](./BACKLOG.md) for known bugs and tech debt surfaced by the suite.
