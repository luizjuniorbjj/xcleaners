/**
 * Financial — Invoice mark paid + LTV aggregation.
 *
 * Validates that when an invoice is marked paid (simulating Stripe webhook
 * or manual entry), the client's lifetime_value in the /clients listing
 * reflects the sum of paid invoices.
 *
 * Covers the commit 9195580 fix (LEFT JOIN LATERAL with invoices SUM)
 * and proves the full billing cycle: booking → invoice → payment → LTV.
 */
import { test, expect } from '../../../fixtures/auth.fixture';
import { ApiClient } from '../../../helpers/api-client';
import {
  ensureHomeownerClientLink,
  createTestBooking,
  deleteBooking,
  deleteInvoicesForBooking,
  getInvoiceStatus,
  getClientLiveLTV,
} from '../../../helpers/db-helpers';

const OWNER_EMAIL = process.env.OWNER_EMAIL!;
const HOMEOWNER_EMAIL = process.env.HOMEOWNER_EMAIL!;
const PASSWORD = process.env.TEST_PASSWORD!;

test.describe('Financial — Invoice mark paid + LTV', () => {
  let bookingId: string;
  let clientId: string;

  test.beforeEach(async () => {
    clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);
    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000);
    bookingId = await createTestBooking({
      clientId,
      scheduledDate: yesterday.toISOString().split('T')[0],
      scheduledStart: '10:00:00',
      status: 'scheduled',
      quotedPrice: 250,
    });
  });

  test.afterEach(async () => {
    if (bookingId) {
      await deleteInvoicesForBooking(bookingId);
      await deleteBooking(bookingId);
    }
  });

  test('mark-paid transitions invoice status from draft/sent to paid', async () => {
    const owner = new ApiClient();
    await owner.login(OWNER_EMAIL, PASSWORD);

    const inv = await owner.post<{ id: string }>('/invoices', { booking_id: bookingId });

    await owner.post(`/invoices/${inv.id}/mark-paid`, {
      method: 'cash',
      amount: 250,
      reference: 'E2E-TEST-PAYMENT',
    });

    const status = await getInvoiceStatus(inv.id);
    expect(status?.status).toBe('paid');
    expect(status?.amount_paid).toBe(250);
  });

  test('paid invoice increments client LTV by invoice total', async () => {
    const ltvBefore = await getClientLiveLTV(clientId);

    const owner = new ApiClient();
    await owner.login(OWNER_EMAIL, PASSWORD);

    const inv = await owner.post<{ id: string }>('/invoices', { booking_id: bookingId });
    await owner.post(`/invoices/${inv.id}/mark-paid`, {
      method: 'zelle',
      amount: 250,
      reference: 'E2E-LTV-TEST',
    });

    const ltvAfter = await getClientLiveLTV(clientId);
    expect(ltvAfter - ltvBefore).toBe(250);
  });

  test('listing endpoint /clients returns LTV that reflects paid invoice (post-fix 9195580)', async () => {
    const owner = new ApiClient();
    await owner.login(OWNER_EMAIL, PASSWORD);

    const inv = await owner.post<{ id: string }>('/invoices', { booking_id: bookingId });
    await owner.post(`/invoices/${inv.id}/mark-paid`, {
      method: 'check',
      amount: 250,
      reference: 'E2E-LISTING-TEST',
    });

    const list = await owner.get<{ clients: Array<{ id: string; lifetime_value: number }> }>(
      '/clients?per_page=100'
    );
    const me = list.clients.find((c) => c.id === clientId);
    expect(me, 'E2E homeowner client should be in listing').toBeTruthy();
    expect(me!.lifetime_value, 'LTV must be > 0 after paid invoice').toBeGreaterThanOrEqual(250);
  });
});
