import { Page, Locator } from '@playwright/test';

export class CleanerTodayPage {
  readonly page: Page;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /today/i }).first();
  }

  async goto(): Promise<void> {
    await this.page.goto('/today');
    await this.page.waitForLoadState('networkidle');
  }
}
