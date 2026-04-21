# Contributing to E2E

## Guiding principles

1. **Deterministic state** — every test seeds its own data + cleans up after. Never rely on pre-existing bookings.
2. **POM for anything reused** — if 2+ specs touch the same page, extract a Page Object.
3. **Fast failure** — prefer explicit `.toHaveValue()` / `.toHaveText()` over sleeps. Playwright auto-waits; don't fight it.
4. **Smoke stays lean** — smoke is what runs on every PR. If a new smoke test takes >30s, it belongs in regression.
5. **Test intent, not implementation** — test labels should read like business requirements, not CSS selectors.

## When to put a test where

| What you're testing | Suite |
|---|---|
| "Does the app boot?" / "Can users log in?" | `smoke/` |
| "Does the core business flow work?" | `regression/` |
| "Does the Cancellation Policy work end-to-end?" | `regression/policy-mvp/` |
| "Does the app refuse wrong input?" | `negative/` |
| "Is the API honoring its 409 contracts?" | `negative/` (API-level) or `regression/` (UI-level) |

## Naming

- Files: `kebab-case.spec.ts`
- Describe blocks: `Suite — Area` (e.g., `'Regression — Owner Settings'`)
- Test names: full sentence (e.g., `'fee=0 persists as 0 (not falls back to default 50)'`)

## Anti-patterns to avoid

- ❌ Hardcoding booking UUIDs
- ❌ Asserting on exact CSS class names (they'll change)
- ❌ `await page.waitForTimeout(5000)` — use `waitFor` on a condition
- ❌ Shared fixtures that mutate global state without cleanup
- ❌ Tests that depend on order (`fullyParallel: false` is a safety net, not an excuse)

## Adding a new persona

1. Create user in DB via seed (see `helpers/db-helpers.ts`)
2. Add role assignment in `cleaning_user_roles`
3. Add a fixture in `fixtures/auth.fixture.ts`:
   ```typescript
   newRolePage: async ({ browser }, use) => {
     const ctx = await browser.newContext({ storageState: NEW_ROLE_STORAGE });
     const page = await ctx.newPage();
     await use(page);
     await ctx.close();
   },
   ```
4. Add setup step in `fixtures/auth.setup.ts`
5. Build POM under `pages/<role>/`

## Debugging failures

1. **First check:** `npm run report` — HTML report shows trace + screenshot
2. **Trace viewer:** `npx playwright show-trace reports/test-artifacts/<test>/trace.zip`
3. **Run single:** `npx playwright test path/to/spec.spec.ts --headed --debug`
4. **UI mode:** `npm run test:ui` — best for authoring

## Commit message convention

```
test(e2e): <suite> — <what>

Example:
test(e2e): regression — add policy-edit-reactive spec for fee change propagation
```
