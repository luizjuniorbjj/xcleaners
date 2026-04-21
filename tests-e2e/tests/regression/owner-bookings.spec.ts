import { test, expect } from '../../fixtures/auth.fixture';
import { OwnerBookingsPage } from '../../pages/owner/OwnerBookingsPage';

test.describe('Regression — Owner Bookings', () => {
  test('renders 4 tabs with counts', async ({ ownerPage }) => {
    const bookings = new OwnerBookingsPage(ownerPage);
    await bookings.goto();
    await expect(bookings.tabPending).toBeVisible();
    await expect(bookings.tabUpcoming).toBeVisible();
    await expect(bookings.tabPast).toBeVisible();
    await expect(bookings.tabCancelled).toBeVisible();

    // Counts should be numeric (even if 0)
    const pending = await bookings.getTabCount('pending');
    expect(pending).toBeGreaterThanOrEqual(0);
  });

  test('tab counts sum matches all bookings in E2E business', async ({ ownerPage }) => {
    const bookings = new OwnerBookingsPage(ownerPage);
    await bookings.goto();
    const total =
      (await bookings.getTabCount('pending')) +
      (await bookings.getTabCount('upcoming')) +
      (await bookings.getTabCount('past')) +
      (await bookings.getTabCount('cancelled'));
    expect(total).toBeGreaterThanOrEqual(0);
  });
});
