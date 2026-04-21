import { Page, Locator } from '@playwright/test';

export class OwnerSchedulePage {
  readonly page: Page;
  readonly prevBtn: Locator;
  readonly todayBtn: Locator;
  readonly nextBtn: Locator;
  readonly generateScheduleBtn: Locator;
  readonly bookingBlocks: Locator;

  constructor(page: Page) {
    this.page = page;
    this.prevBtn = page.getByRole('button', { name: /prev/i });
    this.todayBtn = page.getByRole('button', { name: /^today$/i });
    this.nextBtn = page.getByRole('button', { name: /next/i });
    this.generateScheduleBtn = page.getByRole('button', { name: /generate schedule/i });
    this.bookingBlocks = page.locator('[data-testid="booking-block"], .cc-booking-block');
  }

  async goto(): Promise<void> {
    await this.page.goto('/schedule');
    await this.page.waitForLoadState('networkidle');
  }
}
