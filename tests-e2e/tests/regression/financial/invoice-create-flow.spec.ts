/**
 * Financial — Invoice create flow.
 *
 * Validates the critical path: owner generates invoice from a booking,
 * invoice appears in owner's /invoices listing AND in homeowner's
 * /my-invoices listing (cross-role visibility).
 *
 * This was NOT covered by any spec before 2026-04-21 — the invoice
 * pages loaded, but no assertion ever ran the create flow end-to-end.
 */
import { test, expect } from '../../../fixtures/auth.fixture';
import { ApiClient } from '../../../helpers/api-client';
import {
  ensureHomeownerClientLink,
  createTestBooking,
  deleteBooking,
  deleteInvoicesForBooking,
} from '../../../helpers/db-helpers';

const OWNER_EMAIL = process.env.OWNER_EMAIL!;
const HOMEOWNER_EMAIL = process.env.HOMEOWNER_EMAIL!;
const PASSWORD = process.env.TEST_PASSWORD!;

test.describe('Financial — Invoice create flow', () => {
  let bookingId: string;

  test.beforeEach(async () => {
    const clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);
    // Past booking (yesterday) — invoice generation does not require 'completed',
    // but this is a realistic fixture for "service done, now billing".
    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000);
    bookingId = await createTestBooking({
      clientId,
      scheduledDate: yesterday.toISOString().split('T')[0],
      scheduledStart: '09:00:00',
      status: 'scheduled',
      quotedPrice: 175,
    });
  });

  test.afterEach(async () => {
    // Invoice cleanup MUST come first (FK → booking)
    if (bookingId) {
      await deleteInvoicesForBooking(bookingId);
      await deleteBooking(bookingId);
    }
  });

  test('owner creates invoice from booking via API — status=draft, total=quoted_price', async () => {
    const owner = new ApiClient();
    await owner.login(OWNER_EMAIL, PASSWORD);

    const inv = await owner.post<{ id: string; status: string; total: number; invoice_number: string }>(
      '/invoices',
      { booking_id: bookingId }
    );

    expect(inv.id).toBeTruthy();
    expect(inv.status).toBe('draft');
    expect(Number(inv.total)).toBe(175);
    expect(inv.invoice_number).toMatch(/^INV-/);
  });

  test('created invoice appears in owner /invoices listing', async () => {
    const owner = new ApiClient();
    await owner.login(OWNER_EMAIL, PASSWORD);

    const created = await owner.post<{ id: string }>('/invoices', { booking_id: bookingId });
    const list = await owner.get<{ invoices: { id: string }[] }>('/invoices');

    const found = list.invoices.find((i) => i.id === created.id);
    expect(found).toBeTruthy();
  });

  test('created invoice appears in homeowner /my-invoices listing (cross-role)', async () => {
    const owner = new ApiClient();
    await owner.login(OWNER_EMAIL, PASSWORD);
    const created = await owner.post<{ id: string }>('/invoices', { booking_id: bookingId });

    const homeowner = new ApiClient();
    await homeowner.login(HOMEOWNER_EMAIL, PASSWORD);
    const list = await homeowner.get<{ invoices?: { id: string }[] } | { id: string }[]>(
      '/my-invoices'
    );

    const invoices = Array.isArray(list) ? list : list.invoices || [];
    const found = invoices.find((i) => i.id === created.id);
    expect(found, `homeowner should see invoice ${created.id} in /my-invoices`).toBeTruthy();
  });

  test('creating invoice twice for same booking returns 409 (idempotency)', async () => {
    const owner = new ApiClient();
    await owner.login(OWNER_EMAIL, PASSWORD);

    await owner.post('/invoices', { booking_id: bookingId });

    await expect(owner.post('/invoices', { booking_id: bookingId })).rejects.toMatchObject({
      status: 409,
    });
  });
});
