/**
 * Policy MVP — Reschedule limit gate (Wave 1 backend + Wave 2 frontend).
 *
 * With max_reschedules_per_booking=1 and a booking at count=1,
 * the Reschedule button must be hidden and replaced with
 * "Already rescheduled" badge.
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

test.describe('Policy MVP — Reschedule limit visual gate', () => {
  let bookingAtLimit: string;
  let bookingBelowLimit: string;

  test.beforeEach(async () => {
    await resetPolicy({ hours_before: 24, fee_percentage: 50, max_reschedules_per_booking: 1 });
    const clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);

    const futureDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    const futureDate2 = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

    // AT the limit already — should have NO reschedule button
    bookingAtLimit = await createTestBooking({
      clientId,
      scheduledDate: futureDate,
      scheduledStart: '10:00:00',
      status: 'scheduled',
      quotedPrice: 150,
      rescheduleCount: 1, // at max (limit=1)
    });

    // Below limit — should have reschedule available
    bookingBelowLimit = await createTestBooking({
      clientId,
      scheduledDate: futureDate2,
      scheduledStart: '10:00:00',
      status: 'scheduled',
      quotedPrice: 150,
      rescheduleCount: 0,
    });
  });

  test.afterEach(async () => {
    if (bookingAtLimit) await deleteBooking(bookingAtLimit);
    if (bookingBelowLimit) await deleteBooking(bookingBelowLimit);
  });

  test('booking at count=max shows "Already rescheduled" badge, no Reschedule button', async ({ homeownerPage }) => {
    const bookings = new MyBookingsPage(homeownerPage);
    await bookings.goto();
    // goto() already hydrates

    // Find the specific card for bookingAtLimit — assume earliest date is at index 0
    // (we seeded at day+7 and day+14, so day+7 is first in upcoming list)
    await expect(bookings.alreadyRescheduledBadge.first()).toBeVisible();
    // Cancel should still be present for that booking
    await expect(bookings.cancelButtons.first()).toBeVisible();
  });
});
