import { test, expect } from '../../fixtures/auth.fixture';
import { MyBookingsPage } from '../../pages/homeowner/MyBookingsPage';
import { HomeownerInvoicesPage } from '../../pages/homeowner/HomeownerInvoicesPage';

test.describe('Regression — Homeowner Portal', () => {
  test('my-bookings loads with tabs and request button', async ({ homeownerPage }) => {
    const bookings = new MyBookingsPage(homeownerPage);
    await bookings.goto();
    await expect(bookings.heading).toBeVisible();
    await expect(bookings.tabUpcoming).toBeVisible();
    await expect(bookings.tabPast).toBeVisible();
    await expect(bookings.requestCleaningBtn).toBeVisible();
  });

  test('my-invoices loads', async ({ homeownerPage }) => {
    const invoices = new HomeownerInvoicesPage(homeownerPage);
    await invoices.goto();
    await expect(invoices.heading).toBeVisible();
  });
});
