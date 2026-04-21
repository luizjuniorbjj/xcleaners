/**
 * Policy MVP — Timezone-aware late window (Wave 1 fix).
 *
 * Validates the fix for the pre-existing bug where cancelling D-1 23:59
 * for D 08:00 was counted as "not late" (date-only arithmetic). After
 * Wave 1 fix, the gate uses _hours_until_booking via zoneinfo.
 *
 * We seed a booking far away (no late) and one close (within window)
 * and check each produces the expected UI state.
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

test.describe('Policy MVP — Timezone-aware window', () => {
  let farId: string;
  let nearId: string;

  test.beforeEach(async () => {
    await resetPolicy({ hours_before: 24, fee_percentage: 50, max_reschedules_per_booking: 1 });
    const clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);

    const nearWhen = new Date(Date.now() + 10 * 60 * 60 * 1000); // ~10h out
    const farWhen = new Date(Date.now() + 72 * 60 * 60 * 1000);  // ~3 days out

    nearId = await createTestBooking({
      clientId,
      scheduledDate: nearWhen.toISOString().split('T')[0],
      scheduledStart: `${String(nearWhen.getUTCHours()).padStart(2, '0')}:00:00`,
      status: 'scheduled',
      quotedPrice: 120,
    });

    farId = await createTestBooking({
      clientId,
      scheduledDate: farWhen.toISOString().split('T')[0],
      scheduledStart: '10:00:00',
      status: 'scheduled',
      quotedPrice: 120,
    });
  });

  test.afterEach(async () => {
    if (nearId) await deleteBooking(nearId);
    if (farId) await deleteBooking(farId);
  });

  test('near booking (10h) is LATE, far booking (72h) is NOT late', async ({ homeownerPage }) => {
    const bookings = new MyBookingsPage(homeownerPage);
    await bookings.goto();
    // goto() already hydrates

    // Open cancel on the near (first / earliest) booking — expect late fee banner
    const near = await bookings.openCancelModal(0);
    const nearFee = await near.getLateFeeDisplayed();
    expect(nearFee, 'near booking should show late fee').toBeCloseTo(60.0, 2); // 50% of 120
    await near.close();

    // Open cancel on the far booking — expect no banner
    const far = await bookings.openCancelModal(1);
    await far.expectNoLateWarning();
    await far.close();
  });
});
