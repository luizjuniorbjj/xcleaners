import { Page, expect, Locator } from '@playwright/test';

/**
 * CancelModal — Wave 2 core visual.
 *
 * Shows a red banner with exact fee amount when the booking is inside the
 * late cancellation window, amber if late but draft/no-price.
 */
export class CancelModal {
  readonly page: Page;
  readonly modal: Locator;
  readonly title: Locator;
  readonly lateBanner: Locator;
  readonly amberBanner: Locator;
  readonly reasonSelect: Locator;
  readonly keepBookingBtn: Locator;
  readonly yesCancelBtn: Locator;

  constructor(page: Page) {
    this.page = page;
    this.modal = page.locator('#cancel-modal');
    this.title = this.modal.getByRole('heading', { name: /cancel cleaning/i });
    // Banner identification by their unique text — more stable than hex color selectors
    this.lateBanner = this.modal.getByText(/late cancellation.*fee of \$/i);
    this.amberBanner = this.modal.getByText(/this is a late cancellation/i);
    this.reasonSelect = this.modal.locator('#cancel-reason');
    this.keepBookingBtn = this.modal.getByRole('button', { name: /keep booking/i });
    this.yesCancelBtn = this.modal.getByRole('button', { name: /yes, cancel/i });
  }

  async waitForOpen(): Promise<void> {
    await this.modal.waitFor({ state: 'visible', timeout: 5_000 });
    await this.title.waitFor({ state: 'visible' });
  }

  async getLateFeeDisplayed(): Promise<number | null> {
    if (!(await this.lateBanner.isVisible().catch(() => false))) return null;
    const text = (await this.lateBanner.textContent()) || '';
    const match = text.match(/\$([\d,]+\.\d{2})/);
    return match ? Number(match[1].replace(/,/g, '')) : null;
  }

  async expectLateFee(expected: number): Promise<void> {
    await expect(this.lateBanner).toBeVisible();
    const shown = await this.getLateFeeDisplayed();
    expect(shown, `displayed fee ${shown} should equal ${expected}`).toBeCloseTo(expected, 2);
  }

  async expectNoLateWarning(): Promise<void> {
    await expect(this.lateBanner).toHaveCount(0);
    await expect(this.amberBanner).toHaveCount(0);
  }

  async expectAmberWarning(): Promise<void> {
    await expect(this.amberBanner).toBeVisible();
    await expect(this.lateBanner).toHaveCount(0);
  }

  async confirmCancel(reason?: string): Promise<void> {
    if (reason) await this.reasonSelect.selectOption(reason);
    await this.yesCancelBtn.click();
    // Wait for modal to close
    await this.modal.waitFor({ state: 'hidden', timeout: 10_000 });
  }

  async close(): Promise<void> {
    await this.keepBookingBtn.click();
    await this.modal.waitFor({ state: 'hidden' });
  }
}
