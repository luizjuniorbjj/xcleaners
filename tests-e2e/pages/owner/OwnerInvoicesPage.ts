import { Page, Locator } from '@playwright/test';

export class OwnerInvoicesPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly outstandingKpi: Locator;
  readonly overdueKpi: Locator;
  readonly batchInvoiceBtn: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /^invoices/i });
    this.outstandingKpi = page.locator('text=Outstanding').locator('xpath=..').first();
    this.overdueKpi = page.locator('text=Overdue').locator('xpath=..').first();
    this.batchInvoiceBtn = page.getByRole('button', { name: /batch invoice/i });
  }

  async goto(): Promise<void> {
    await this.page.goto('/invoices');
    await this.heading.waitFor({ state: 'visible', timeout: 10_000 });
  }
}
