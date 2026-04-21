/**
 * Financial — Late cancel fee persistence (M3 fixed).
 *
 * Validates the late-cancellation fee flow:
 *   - UI shows the fee banner (covered by Policy MVP specs)
 *   - Backend returns fee_amount + fee_invoice_id in response
 *   - Draft invoice is auto-created recording the debit (M3 fix)
 *
 * Before fix: fee was display-only → revenue leak. Now: concrete
 * invoice row in /invoices that owner sends via Stripe or waives.
 */
import { test, expect } from '../../../fixtures/auth.fixture';
import { ApiClient } from '../../../helpers/api-client';
import {
  resetPolicy,
  ensureHomeownerClientLink,
  createTestBooking,
  deleteBooking,
  deleteInvoicesForBooking,
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
    // Order matters: invoice cleanup first (FK booking_id → SET NULL on delete
    // would leave orphans otherwise).
    if (bookingId) {
      await deleteInvoicesForBooking(bookingId);
      await deleteBooking(bookingId);
    }
  });

  test('late cancel response reports fee_amount + fee_invoice_id (post-fix M3)', async () => {
    const api = new ApiClient();
    await api.login(HOMEOWNER_EMAIL, PASSWORD);

    const res = await api.post<{
      success: boolean;
      late_cancellation: boolean;
      fee_amount: number;
      fee_percentage: number;
      fee_invoice_id: string | null;
      fee_invoice_number: string | null;
    }>(`/my-bookings/${bookingId}/cancel`, { reason: 'E2E late-cancel test' });

    expect(res.success).toBe(true);
    expect(res.late_cancellation).toBe(true);
    expect(Number(res.fee_amount)).toBe(90); // 50% of 180
    expect(Number(res.fee_percentage)).toBe(50);
    expect(res.fee_invoice_id, 'fee_invoice_id must be set after late cancel').toBeTruthy();
    expect(res.fee_invoice_number).toMatch(/^INV-/);
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

  test('draft fee invoice persisted with correct total + line item (M3 fix)', async () => {
    const api = new ApiClient();
    await api.login(HOMEOWNER_EMAIL, PASSWORD);
    await api.post(`/my-bookings/${bookingId}/cancel`, { reason: 'E2E fee persistence' });

    const bizId = await getE2EBusinessId();
    const invRes = await pool.query<{
      id: string; total: string; status: string; invoice_number: string;
    }>(
      `SELECT id::text, total::text, status, invoice_number
         FROM cleaning_invoices
         WHERE booking_id = $1 AND business_id = $2`,
      [bookingId, bizId]
    );
    expect(invRes.rows.length, 'exactly one draft fee invoice should exist').toBe(1);
    expect(parseFloat(invRes.rows[0].total)).toBe(90); // 50% of 180
    expect(invRes.rows[0].status).toBe('draft');
    expect(invRes.rows[0].invoice_number).toMatch(/^INV-/);

    // Line item carries the "Late cancellation fee — ..." label owner sees in /invoices
    const itemRes = await pool.query<{ description: string; total: string }>(
      `SELECT description, total::text
         FROM cleaning_invoice_items
         WHERE invoice_id = $1`,
      [invRes.rows[0].id]
    );
    expect(itemRes.rows.length).toBe(1);
    expect(itemRes.rows[0].description).toMatch(/late cancellation fee/i);
    expect(parseFloat(itemRes.rows[0].total)).toBe(90);
  });

  test('fee invoice shows up in owner /invoices listing immediately', async () => {
    const homeowner = new ApiClient();
    await homeowner.login(HOMEOWNER_EMAIL, PASSWORD);
    const cancelRes = await homeowner.post<{ fee_invoice_id: string }>(
      `/my-bookings/${bookingId}/cancel`, { reason: 'E2E owner visibility' }
    );

    const owner = new ApiClient();
    await owner.login(process.env.OWNER_EMAIL!, PASSWORD);
    const list = await owner.get<{ invoices: { id: string; status: string; total: number }[] }>(
      '/invoices?status=draft'
    );
    const found = list.invoices.find((i) => i.id === cancelRes.fee_invoice_id);
    expect(found, 'owner must see the fee invoice in /invoices listing').toBeTruthy();
    expect(found!.status).toBe('draft');
    expect(Number(found!.total)).toBe(90);
  });
});
