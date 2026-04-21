/**
 * Custom assertions — readable domain-specific matchers.
 *
 * Keep specs declarative:
 *   expectLateCancelFeeEquals(result, 103.50)
 *   expectReschedulesRemaining(result, 0)
 *
 * instead of:
 *   expect(result.fee_amount).toBeCloseTo(103.50, 2)
 */
import { expect } from '@playwright/test';

export function expectLateCancelFeeEquals(response: any, expected: number): void {
  expect(response.late_cancellation, 'late_cancellation should be true').toBe(true);
  expect(response.fee_amount, 'fee_amount should match policy calc').toBeCloseTo(expected, 2);
}

export function expectReschedulesRemaining(response: any, expected: number): void {
  expect(response.reschedules_remaining, 'reschedules_remaining mismatch').toBe(expected);
}

export function expectLimitReachedError(err: any): void {
  expect(err.status, 'expected 409 Conflict').toBe(409);
  // Backend currently serializes detail as string (see homeowner_routes.py).
  // Once contract fix propagates dict, this can read err.body.detail.reason.
  const detail = typeof err.body?.detail === 'string' ? err.body.detail : JSON.stringify(err.body);
  expect(detail.toLowerCase(), 'message should mention reschedule limit').toContain('limit reached');
}

export function expectWindowViolationError(err: any): void {
  expect(err.status).toBe(409);
  const detail = typeof err.body?.detail === 'string' ? err.body.detail : JSON.stringify(err.body);
  expect(detail.toLowerCase()).toMatch(/hours? before|window|cannot be rescheduled/);
}

export function expectPolicyShape(policy: any): void {
  expect(policy).toHaveProperty('hours_before');
  expect(policy).toHaveProperty('fee_percentage');
  expect(policy).toHaveProperty('max_reschedules_per_booking');
  expect(typeof policy.hours_before).toBe('number');
  expect(typeof policy.fee_percentage).toBe('number');
  expect(typeof policy.max_reschedules_per_booking).toBe('number');
}
