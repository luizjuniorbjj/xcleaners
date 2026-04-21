/**
 * Policy Fixture — ensures a known cancellation_policy state per test.
 *
 * Usage:
 *   test.beforeEach(async () => { await resetPolicy(); });
 *
 * Or request a specific policy for a given test:
 *   await resetPolicy({ max_reschedules_per_booking: 3, fee_percentage: 25 });
 */
export { resetPolicy, readPolicy } from '../helpers/db-helpers';
