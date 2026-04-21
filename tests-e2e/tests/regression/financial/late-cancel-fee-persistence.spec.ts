/**
 * Financial — Late cancel fee persistence (GAP DETECTION).
 *
 * Documents the current state of late-cancellation fees:
 *   - UI shows the fee banner correctly (covered by Policy MVP specs)
 *   - Backend returns fee_amount in the cancel response
 *   - ⚠️ BUT no DB record (invoice / debit / ledger entry) is created
 *
 * This means currently: homeowner cancels late, UI warns of the fee,
 * but owner has no trail to actually collect it. For 3sisters cutover
 * this is a REVENUE LEAK — document explicitly until fee persistence
 * is implemented in a follow-up sprint.
 *
 * Spec acts as both assertion of the current (limited) behaviour AND
 * guardrail: when fee persistence ships, the last test flips from
 * `expect(0)` to `expect(1)` and surfaces the change.
 */
import { test, expect } from '../../../fixtures/auth.fixture';
import { ApiClient } from '../../../helpers/api-client';
import {
  resetPolicy,
  ensureHomeownerClientLink,
  createTestBooking,
  deleteBooking,
  pool,
  getE2EBusinessId,
} from '../../../helpers/db-helpers';

const HOMEOWNER_EMAIL = process.env.HOMEOWNER_EMAIL!;
const PASSWORD = process.env.TEST_PASSWORD!;

test.describe('Financial — Late cancel fee (persistence gap)', () => {
  let bookingId: string;

  test.beforeEach(async () => {
    await resetPolicy({ hours_before: 24, fee_percentage: 50, max_reschedules_per_booking: 1 });
    const clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);
    // Booking ~10h from now — inside 24h window, late-cancel territory.
    const soon = new Date(Date.now() + 10 * 60 * 60 * 1000);
    bookingId = await createTestBooking({
      clientId,
      scheduledDate: soon.toISOString().split('T')[0],
      scheduledStart: `${String(soon.getHours()).padStart(2, '0')}:00:00`,
      status: 'scheduled',
      quotedPrice: 180,
    });
  });

  test.afterEach(async () => {
    if (bookingId) await deleteBooking(bookingId);
  });

  test('late cancel response reports fee_amount = price * fee_percentage / 100', async () => {
    const api = new ApiClient();
    await api.login(HOMEOWNER_EMAIL, PASSWORD);

    const res = await api.post<{
      success: boolean;
      late_cancellation: boolean;
      fee_amount: number;
      fee_percentage: number;
    }>(`/my-bookings/${bookingId}/cancel`, { reason: 'E2E late-cancel test' });

    expect(res.success).toBe(true);
    expect(res.late_cancellation).toBe(true);
    expect(Number(res.fee_amount)).toBe(90); // 50% of 180
    expect(Number(res.fee_percentage)).toBe(50);
  });

  test('booking row has status=cancelled and cancelled_by=client after late-cancel', async () => {
    const api = new ApiClient();
    await api.login(HOMEOWNER_EMAIL, PASSWORD);
    await api.post(`/my-bookings/${bookingId}/cancel`, { reason: 'E2E' });

    const bizId = await getE2EBusinessId();
    const res = await pool.query<{ status: string; cancelled_by: string }>(
      `SELECT status, cancelled_by FROM cleaning_bookings WHERE id = $1 AND business_id = $2`,
      [bookingId, bizId]
    );
    expect(res.rows[0]?.status).toBe('cancelled');
    expect(res.rows[0]?.cancelled_by).toBe('client');
  });

  test('⚠️ GAP — no invoice/ledger row is created for the fee (documents current state)', async () => {
    const api = new ApiClient();
    await api.login(HOMEOWNER_EMAIL, PASSWORD);
    await api.post(`/my-bookings/${bookingId}/cancel`, { reason: 'E2E fee persistence check' });

    const bizId = await getE2EBusinessId();
    const invoices = await pool.query<{ c: string }>(
      `SELECT COUNT(*)::text AS c FROM cleaning_invoices WHERE booking_id = $1 AND business_id = $2`,
      [bookingId, bizId]
    );
    // Today (pre-fix): 0. When fee persistence ships, flip to expect(1).
    expect(
      parseInt(invoices.rows[0].c, 10),
      'currently NO invoice is created for a late-cancel fee — ' +
        'this spec exists to document the gap and surface the change when fixed'
    ).toBe(0);
  });
});
