import { Page, Locator } from '@playwright/test';

export class OwnerBookingsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly tabPending: Locator;
  readonly tabUpcoming: Locator;
  readonly tabPast: Locator;
  readonly tabCancelled: Locator;
  readonly newBookingBtn: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /all bookings/i });
    this.tabPending = page.getByRole('button', { name: /pending \(/i });
    this.tabUpcoming = page.getByRole('button', { name: /upcoming \(/i });
    this.tabPast = page.getByRole('button', { name: /past \(/i });
    this.tabCancelled = page.getByRole('button', { name: /cancelled \(/i });
    this.newBookingBtn = page.getByRole('button', { name: /new booking/i });
  }

  async goto(): Promise<void> {
    await this.page.goto('/bookings');
    await this.heading.waitFor({ state: 'visible', timeout: 10_000 });
  }

  /** Extract the count from tab labels e.g. "Upcoming (7)" -> 7 */
  async getTabCount(tab: 'pending' | 'upcoming' | 'past' | 'cancelled'): Promise<number> {
    const locator = this[`tab${tab.charAt(0).toUpperCase()}${tab.slice(1)}` as 'tabPending' | 'tabUpcoming' | 'tabPast' | 'tabCancelled'];
    const text = (await locator.textContent()) || '';
    const match = text.match(/\((\d+)\)/);
    return match ? Number(match[1]) : 0;
  }
}
