import { Page, Locator, expect } from '@playwright/test';

export class OwnerDashboardPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly revenueKpi: Locator;
  readonly bookingsTodayKpi: Locator;
  readonly activeClientsKpi: Locator;
  readonly overdueInvoicesKpi: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /business overview/i });
    // KPIs identified by their label text (not brittle CSS)
    this.revenueKpi = page.locator('text=Revenue This Month').locator('xpath=..').locator('.cc-kpi-value, div').first();
    this.bookingsTodayKpi = page.locator('text=Bookings Today').locator('xpath=..').first();
    this.activeClientsKpi = page.locator('text=Active Clients').locator('xpath=..').first();
    this.overdueInvoicesKpi = page.locator('text=Overdue Invoices').locator('xpath=..').first();
  }

  async goto(): Promise<void> {
    await this.page.goto('/dashboard');
    await this.heading.waitFor({ state: 'visible', timeout: 10_000 });
  }

  async getKpiValues(): Promise<{ revenue: string; bookings: string; clients: string; overdue: string }> {
    return {
      revenue: (await this.revenueKpi.textContent()) || '',
      bookings: (await this.bookingsTodayKpi.textContent()) || '',
      clients: (await this.activeClientsKpi.textContent()) || '',
      overdue: (await this.overdueInvoicesKpi.textContent()) || '',
    };
  }
}
