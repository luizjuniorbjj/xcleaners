import { Page, Locator } from '@playwright/test';

export class HomeownerInvoicesPage {
  readonly page: Page;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /my invoices/i });
  }

  async goto(): Promise<void> {
    await this.page.goto('/my-invoices');
    await this.heading.waitFor({ state: 'visible', timeout: 10_000 });
  }
}
