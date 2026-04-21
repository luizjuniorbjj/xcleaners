import { Page, Locator } from '@playwright/test';

export class OwnerReportsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly thisMonthRevenueKpi: Locator;
  readonly lastMonthRevenueKpi: Locator;
  readonly topClientsTable: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /^reports/i });
    this.thisMonthRevenueKpi = page.locator('text=This Month Revenue').locator('xpath=..').first();
    this.lastMonthRevenueKpi = page.locator('text=Last Month Revenue').locator('xpath=..').first();
    this.topClientsTable = page.locator('text=Top Clients by Revenue').locator('xpath=..').first();
  }

  async goto(): Promise<void> {
    await this.page.goto('/reports');
    await this.heading.waitFor({ state: 'visible', timeout: 10_000 });
  }
}
