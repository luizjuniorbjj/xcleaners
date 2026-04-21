/**
 * Policy MVP — Cancel late fee banner (Wave 1 backend + Wave 2 frontend).
 *
 * Seeds a booking that's within the 24h window with a known price,
 * opens the Cancel modal, asserts the red banner shows the exact
 * fee = quoted_price * fee_percentage / 100.
 */
import { test, expect } from '../../../fixtures/auth.fixture';
import { MyBookingsPage } from '../../../pages/homeowner/MyBookingsPage';
import {
  resetPolicy,
  ensureHomeownerClientLink,
  createTestBooking,
  deleteBooking,
} from '../../../helpers/db-helpers';

const HOMEOWNER_EMAIL = process.env.HOMEOWNER_EMAIL!;

test.describe('Policy MVP — Late cancellation fee banner', () => {
  let bookingId: string;

  test.beforeEach(async () => {
    await resetPolicy({ hours_before: 24, fee_percentage: 50, max_reschedules_per_booking: 1 });
    const clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);

    // Booking TODAY at late-afternoon (within 24h window, assuming test runs before then)
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const scheduled = `${hh}:30:00`;
    // Use tomorrow 00:30 so we are safely inside a 24h window but after current moment
    const tmw = new Date(Date.now() + 12 * 60 * 60 * 1000);
    const dateStr = tmw.toISOString().split('T')[0];

    bookingId = await createTestBooking({
      clientId,
      scheduledDate: dateStr,
      scheduledStart: scheduled,
      status: 'scheduled',
      quotedPrice: 200,
    });
  });

  test.afterEach(async () => {
    if (bookingId) await deleteBooking(bookingId);
  });

  test('late cancel shows red banner with exact $100.00 fee (50% of $200)', async ({ homeownerPage }) => {
    const bookings = new MyBookingsPage(homeownerPage);
    await bookings.goto();
    // goto() already hydrates

    const cancelModal = await bookings.openCancelModal(0);
    // Banner + exact fee (math guard — if policy or price mutates, this catches it)
    await cancelModal.expectLateFee(100.0);
    await cancelModal.close();
  });

  test('fee amount scales with policy change (owner-side reactivity)', async ({ homeownerPage }) => {
    await resetPolicy({ fee_percentage: 25 }); // 25% now
    const bookings = new MyBookingsPage(homeownerPage);
    await bookings.goto();
    // goto() already hydrates

    const cancelModal = await bookings.openCancelModal(0);
    await cancelModal.expectLateFee(50.0); // 25% of 200
    await cancelModal.close();
  });
});
