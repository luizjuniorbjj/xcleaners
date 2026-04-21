/**
 * Negative — Reschedule API rejects bookings within 24h window.
 * Tests the backend gate directly (not UI) because we need structured
 * error shape (status + detail).
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { ApiClient } from '../../helpers/api-client';
import {
  resetPolicy,
  ensureHomeownerClientLink,
  createTestBooking,
  deleteBooking,
} from '../../helpers/db-helpers';

const HOMEOWNER_EMAIL = process.env.HOMEOWNER_EMAIL!;
const PASSWORD = process.env.TEST_PASSWORD!;

test.describe('Negative — Reschedule API gates', () => {
  let bookingId: string;

  test.beforeEach(async () => {
    await resetPolicy({ hours_before: 24, fee_percentage: 50, max_reschedules_per_booking: 1 });
    const clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);
    const tmw = new Date(Date.now() + 10 * 60 * 60 * 1000); // 10h ahead = inside window
    bookingId = await createTestBooking({
      clientId,
      scheduledDate: tmw.toISOString().split('T')[0],
      scheduledStart: `${String(tmw.getUTCHours()).padStart(2, '0')}:00:00`,
      status: 'scheduled',
      quotedPrice: 120,
    });
  });

  test.afterEach(async () => {
    if (bookingId) await deleteBooking(bookingId);
  });

  test('reschedule within 24h returns 409', async () => {
    const api = new ApiClient();
    await api.login(HOMEOWNER_EMAIL, PASSWORD);

    const futureDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    let caught: any;
    try {
      await api.post(`/my-bookings/${bookingId}/reschedule`, {
        new_date: futureDate,
        new_time: '11:00',
      });
    } catch (e) {
      caught = e;
    }
    expect(caught, 'should have thrown 409').toBeDefined();
    expect(caught.status).toBe(409);
  });

  test('reschedule at count=max returns 409', async () => {
    // Create another booking already at the limit
    const farDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    const clientId = await ensureHomeownerClientLink(HOMEOWNER_EMAIL);
    const maxedId = await createTestBooking({
      clientId,
      scheduledDate: farDate,
      scheduledStart: '10:00:00',
      status: 'scheduled',
      quotedPrice: 120,
      rescheduleCount: 1, // already at limit
    });

    const api = new ApiClient();
    await api.login(HOMEOWNER_EMAIL, PASSWORD);
    const otherDate = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

    let caught: any;
    try {
      await api.post(`/my-bookings/${maxedId}/reschedule`, {
        new_date: otherDate,
        new_time: '11:00',
      });
    } catch (e) {
      caught = e;
    }
    expect(caught.status).toBe(409);
    const detail = typeof caught.body?.detail === 'string' ? caught.body.detail : JSON.stringify(caught.body);
    expect(detail.toLowerCase()).toContain('limit reached');

    await deleteBooking(maxedId);
  });
});
