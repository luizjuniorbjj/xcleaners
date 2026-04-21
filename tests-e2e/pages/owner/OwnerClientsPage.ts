import { Page, Locator } from '@playwright/test';

export class OwnerClientsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly addClientBtn: Locator;
  readonly importCsvBtn: Locator;
  readonly searchInput: Locator;
  readonly clientRows: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /^clients/i });
    this.addClientBtn = page.getByRole('button', { name: /add client/i });
    this.importCsvBtn = page.getByRole('button', { name: /import csv/i });
    this.searchInput = page.locator('input[placeholder*="Search name"]');
    this.clientRows = page.locator('table tr, .cc-table tr').filter({ hasNot: page.locator('th') });
  }

  async goto(): Promise<void> {
    await this.page.goto('/clients');
    await this.heading.waitFor({ state: 'visible', timeout: 10_000 });
  }
}
