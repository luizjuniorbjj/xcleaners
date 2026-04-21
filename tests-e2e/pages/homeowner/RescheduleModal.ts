import { Page, Locator, expect } from '@playwright/test';

export class RescheduleModal {
  readonly page: Page;
  readonly modal: Locator;
  readonly dateInput: Locator;
  readonly timeSelect: Locator;
  readonly reasonInput: Locator;
  readonly submitBtn: Locator;
  readonly cancelBtn: Locator;

  constructor(page: Page) {
    this.page = page;
    this.modal = page.locator('#reschedule-modal');
    this.dateInput = this.modal.locator('#resched-date');
    this.timeSelect = this.modal.locator('#resched-time');
    this.reasonInput = this.modal.locator('#resched-reason');
    this.submitBtn = this.modal.getByRole('button', { name: /^reschedule$/i });
    this.cancelBtn = this.modal.getByRole('button', { name: /cancel/i });
  }

  async waitForOpen(): Promise<void> {
    await this.modal.waitFor({ state: 'visible', timeout: 5_000 });
  }

  async fill(newDate: string, newTime?: string, reason?: string): Promise<void> {
    await this.dateInput.fill(newDate);
    if (newTime) await this.timeSelect.selectOption(newTime);
    if (reason) await this.reasonInput.fill(reason);
  }

  async submit(): Promise<void> {
    await this.submitBtn.click();
  }

  async close(): Promise<void> {
    await this.cancelBtn.click();
    await this.modal.waitFor({ state: 'hidden' });
  }
}
