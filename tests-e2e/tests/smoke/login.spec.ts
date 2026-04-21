/**
 * Smoke — Login as all 3 personas.
 *
 * This is the first gate: if login breaks, nothing else matters.
 * Runs in ~30s, always part of CI smoke.
 */
import { test, expect } from '../../fixtures/auth.fixture';

test.describe('Smoke — Authentication', () => {
  test('owner lands on /dashboard after login', async ({ ownerPage }) => {
    await ownerPage.goto('/dashboard');
    await expect(ownerPage).toHaveURL(/\/dashboard/);
    await expect(
      ownerPage.getByRole('heading', { name: /business overview/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test('homeowner lands on /my-bookings after login', async ({ homeownerPage }) => {
    await homeownerPage.goto('/my-bookings');
    await expect(homeownerPage).toHaveURL(/\/my-bookings/);
    await expect(
      homeownerPage.getByRole('heading', { name: /my bookings/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test('cleaner can reach /today', async ({ cleanerPage }) => {
    await cleanerPage.goto('/today');
    // Cleaner portal exists — just confirm the page loads without 403/redirect-to-login
    await expect(cleanerPage).not.toHaveURL(/\/login/);
  });
});
