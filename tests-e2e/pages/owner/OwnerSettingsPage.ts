import { Page, expect, Locator } from '@playwright/test';

/**
 * OwnerSettingsPage — POM for /settings tabbed layout.
 *
 * Core focus: Cancellation Policy section (Wave 3 of Policy MVP).
 * This is where the backend contract `max_reschedules_per_booking`
 * must match the UI input name (the Wave 3 fix).
 */
export class OwnerSettingsPage {
  readonly page: Page;

  // Cancellation Policy inputs (Wave 3 contract fix lives here)
  readonly hoursBeforeInput: Locator;
  readonly feePercentageInput: Locator;
  readonly maxReschedulesPerBookingInput: Locator;

  // Save + toast
  readonly saveBtn: Locator;
  readonly successToast: Locator;

  // Tab navigation
  readonly tabGeneral: Locator;
  readonly tabAreas: Locator;
  readonly tabPricing: Locator;
  readonly tabNotifications: Locator;
  readonly tabAppearance: Locator;
  readonly tabPlan: Locator;

  constructor(page: Page) {
    this.page = page;
    this.hoursBeforeInput = page.locator('input[name="cancel_hours"]');
    this.feePercentageInput = page.locator('input[name="cancel_fee"]');
    this.maxReschedulesPerBookingInput = page.locator(
      'input[name="max_reschedules_per_booking"]'
    );
    this.saveBtn = page
      .getByRole('button', { name: /^save/i })
      .last(); // the General tab save button is at bottom
    this.successToast = page.locator('.cc-toast-success, [role="status"]');

    this.tabGeneral = page.getByRole('button', { name: /general/i });
    this.tabAreas = page.getByRole('button', { name: /^areas/i });
    this.tabPricing = page.getByRole('button', { name: /^pricing/i });
    this.tabNotifications = page.getByRole('button', { name: /notifications/i });
    this.tabAppearance = page.getByRole('button', { name: /appearance/i });
    this.tabPlan = page.getByRole('button', { name: /plan/i });
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings');
    await this.page.waitForLoadState('networkidle');
  }

  async openGeneralTab(): Promise<void> {
    await this.tabGeneral.click();
    await expect(this.hoursBeforeInput).toBeVisible({ timeout: 5_000 });
  }

  async readPolicy(): Promise<{ hours: number; fee: number; max: number }> {
    return {
      hours: Number(await this.hoursBeforeInput.inputValue()),
      fee: Number(await this.feePercentageInput.inputValue()),
      max: Number(await this.maxReschedulesPerBookingInput.inputValue()),
    };
  }

  async setPolicy(policy: { hours?: number; fee?: number; max?: number }): Promise<void> {
    if (policy.hours !== undefined) await this.hoursBeforeInput.fill(String(policy.hours));
    if (policy.fee !== undefined) await this.feePercentageInput.fill(String(policy.fee));
    if (policy.max !== undefined)
      await this.maxReschedulesPerBookingInput.fill(String(policy.max));
  }

  async savePolicy(): Promise<void> {
    await this.saveBtn.click();
    // Wait for toast or URL stable — the form POSTs to /settings
    await this.page.waitForLoadState('networkidle', { timeout: 10_000 });
  }

  async expectLegacyGhostFieldAbsent(): Promise<void> {
    // Wave 3 contract fix: old name must NOT exist in the form
    const legacy = this.page.locator('input[name="max_reschedules"]');
    await expect(legacy).toHaveCount(0);
  }

  async expectAllHelpTextsVisible(): Promise<void> {
    await expect(
      this.page.getByText(/clients must cancel or reschedule at least/i)
    ).toBeVisible();
    await expect(
      this.page.getByText(/percentage of booking price charged/i)
    ).toBeVisible();
    await expect(
      this.page.getByText(/how many times a client can reschedule/i)
    ).toBeVisible();
  }
}
