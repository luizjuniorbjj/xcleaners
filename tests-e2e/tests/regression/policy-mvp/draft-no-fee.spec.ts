/**
 * Policy MVP — Draft bookings pay NO fee even if late.
 * Rule: drafts are pending owner approval → no charge applies.
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

test.describe('Policy MVP — Draft no-fee rule', () => {
  let bookingId: string;

  test.beforeEach(async () => {
    await resetPolicy({ hours_before: 24, fee_percentage: 50, max_reschedules_per_booking: 1 });
    const clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);
    const tmw = new Date(Date.now() + 12 * 60 * 60 * 1000);
    bookingId = await createTestBooking({
      clientId,
      scheduledDate: tmw.toISOString().split('T')[0],
      scheduledStart: '10:00:00',
      status: 'draft',
      quotedPrice: 200,
    });
  });

  test.afterEach(async () => {
    if (bookingId) await deleteBooking(bookingId);
  });

  test('draft within 24h shows amber warning (no fee amount)', async ({ homeownerPage }) => {
    const bookings = new MyBookingsPage(homeownerPage);
    await bookings.goto();
    await homeownerPage.reload();

    const cancel = await bookings.openCancelModal(0);
    await cancel.expectAmberWarning();
    // Red banner (with $X) must NOT appear
    const fee = await cancel.getLateFeeDisplayed();
    expect(fee, 'draft should not show a $ fee').toBeNull();
    await cancel.close();
  });
});
