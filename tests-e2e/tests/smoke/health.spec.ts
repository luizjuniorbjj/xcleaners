/**
 * Smoke — App health: /health endpoint + critical static assets.
 */
import { test, expect, request } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';

const envName = process.env.TEST_ENV || 'prod';
dotenv.config({ path: path.resolve(__dirname, `../../.env.${envName}`) });

test.describe('Smoke — App health', () => {
  test('/health returns 200', async () => {
    const ctx = await request.newContext({ baseURL: process.env.BASE_URL });
    const res = await ctx.get('/health');
    expect(res.status()).toBe(200);
    await ctx.dispose();
  });

  test('my-bookings.js serves latest version (has Wave 2 markers)', async () => {
    const ctx = await request.newContext({ baseURL: process.env.BASE_URL });
    const res = await ctx.get('/cleaning/static/js/homeowner/my-bookings.js', {
      headers: { 'Cache-Control': 'no-cache' },
    });
    expect(res.status()).toBe(200);
    const body = await res.text();
    expect(body, 'expect Wave 2 "Already rescheduled" string').toContain('Already rescheduled');
    expect(body, 'expect Wave 2 "late_cancellation_fee"').toContain('late_cancellation_fee');
    await ctx.dispose();
  });

  test('settings.js owner has Wave 3 contract (max_reschedules_per_booking)', async () => {
    const ctx = await request.newContext({ baseURL: process.env.BASE_URL });
    const res = await ctx.get('/cleaning/static/js/owner/settings.js?v=20', {
      headers: { 'Cache-Control': 'no-cache' },
    });
    expect(res.status()).toBe(200);
    const body = await res.text();
    expect(body).toContain('max_reschedules_per_booking');
    // Ghost legacy must be absent from the input name
    expect(body).not.toMatch(/name="max_reschedules"\s/);
    await ctx.dispose();
  });
});
