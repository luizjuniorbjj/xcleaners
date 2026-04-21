/**
 * Smoke — Critical paths that the business cannot operate without.
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { OwnerSettingsPage } from '../../pages/owner/OwnerSettingsPage';
import { MyBookingsPage } from '../../pages/homeowner/MyBookingsPage';

test.describe('Smoke — Critical UI paths', () => {
  test('owner settings render Cancellation Policy section', async ({ ownerPage }) => {
    const settings = new OwnerSettingsPage(ownerPage);
    await settings.goto();
    await settings.openGeneralTab();
    await expect(settings.hoursBeforeInput).toBeVisible();
    await expect(settings.feePercentageInput).toBeVisible();
    await expect(settings.maxReschedulesPerBookingInput).toBeVisible();
    await settings.expectLegacyGhostFieldAbsent();
  });

  test('homeowner my-bookings renders without crash', async ({ homeownerPage }) => {
    const bookings = new MyBookingsPage(homeownerPage);
    await bookings.goto();
    await expect(bookings.heading).toBeVisible();
    await expect(bookings.requestCleaningBtn).toBeVisible();
  });
});
