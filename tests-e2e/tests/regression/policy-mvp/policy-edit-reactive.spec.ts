/**
 * Policy MVP — Reactive policy changes.
 *
 * Owner changes fee_percentage in Settings → homeowner sees the new
 * value on the NEXT page load (no client-side cache stale).
 */
import { test, expect } from '../../../fixtures/auth.fixture';
import { OwnerSettingsPage } from '../../../pages/owner/OwnerSettingsPage';
import { MyBookingsPage } from '../../../pages/homeowner/MyBookingsPage';
import {
  resetPolicy,
  ensureHomeownerClientLink,
  createTestBooking,
  deleteBooking,
} from '../../../helpers/db-helpers';

const HOMEOWNER_EMAIL = process.env.HOMEOWNER_EMAIL!;

test.describe('Policy MVP — Reactive policy edit', () => {
  let bookingId: string;

  test.beforeEach(async () => {
    await resetPolicy({ hours_before: 24, fee_percentage: 50, max_reschedules_per_booking: 1 });
    const clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);
    const tmw = new Date(Date.now() + 12 * 60 * 60 * 1000);
    bookingId = await createTestBooking({
      clientId,
      scheduledDate: tmw.toISOString().split('T')[0],
      scheduledStart: '10:00:00',
      status: 'scheduled',
      quotedPrice: 100,
    });
  });

  test.afterEach(async () => {
    if (bookingId) await deleteBooking(bookingId);
  });

  test('owner fee 50->30 reflects in homeowner cancel banner', async ({ ownerPage, homeownerPage }) => {
    // Baseline: homeowner sees $50 (50% of $100)
    let bookings = new MyBookingsPage(homeownerPage);
    await bookings.goto();
    let modal = await bookings.openCancelModal(0);
    await modal.expectLateFee(50.0);
    await modal.close();

    // Owner updates policy to 30%
    const settings = new OwnerSettingsPage(ownerPage);
    await settings.goto();
    await settings.openGeneralTab();
    await settings.setPolicy({ fee: 30 });
    await settings.savePolicy();

    // Homeowner reloads — sees $30 now
    await bookings.reloadAndHydrate();
    modal = await bookings.openCancelModal(0);
    await modal.expectLateFee(30.0);
    await modal.close();
  });
});
