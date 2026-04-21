/**
 * Regression — Owner Settings (Wave 3 focus).
 *
 * Validates the contract fix persists: max_reschedules_per_booking
 * (NOT max_reschedules_per_month) is what gets written to JSONB.
 */
import { test, expect } from '../../fixtures/auth.fixture';
import { OwnerSettingsPage } from '../../pages/owner/OwnerSettingsPage';
import { resetPolicy, readPolicy } from '../../helpers/db-helpers';

test.describe('Regression — Owner Settings / Cancellation Policy', () => {
  test.beforeEach(async () => {
    await resetPolicy({ hours_before: 24, fee_percentage: 50, max_reschedules_per_booking: 1 });
  });

  test('renders 3 policy inputs with defaults and help texts', async ({ ownerPage }) => {
    const settings = new OwnerSettingsPage(ownerPage);
    await settings.goto();
    await settings.openGeneralTab();

    const { hours, fee, max } = await settings.readPolicy();
    expect(hours).toBe(24);
    expect(fee).toBe(50);
    expect(max).toBe(1);

    await settings.expectAllHelpTextsVisible();
    await settings.expectLegacyGhostFieldAbsent();
  });

  test('save persists max_reschedules_per_booking in JSONB', async ({ ownerPage }) => {
    const settings = new OwnerSettingsPage(ownerPage);
    await settings.goto();
    await settings.openGeneralTab();

    await settings.setPolicy({ max: 3, fee: 25, hours: 48 });
    await settings.savePolicy();

    // DB-level verification (avoids UI cache quirks)
    const stored = await readPolicy();
    expect(stored.max_reschedules_per_booking).toBe(3);
    expect(stored.fee_percentage).toBe(25);
    expect(stored.hours_before).toBe(48);
  });

  test('fee=0 persists as 0 (not falls back to default 50) — ?? operator fix', async ({ ownerPage }) => {
    const settings = new OwnerSettingsPage(ownerPage);
    await settings.goto();
    await settings.openGeneralTab();
    await settings.setPolicy({ fee: 0 });
    await settings.savePolicy();

    const stored = await readPolicy();
    expect(stored.fee_percentage).toBe(0);
  });
});
