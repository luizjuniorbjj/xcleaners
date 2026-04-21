import { Page, expect, Locator } from '@playwright/test';
import { CancelModal } from './CancelModal';
import { RescheduleModal } from './RescheduleModal';

/**
 * MyBookingsPage — POM for homeowner /my-bookings route.
 *
 * Core consumer of Wave 1 (backend) + Wave 2 (frontend) + Wave 3 (owner config).
 * This is where the policy actually affects the end-user experience.
 */
export class MyBookingsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly tabUpcoming: Locator;
  readonly tabPast: Locator;
  readonly bookingCards: Locator;
  readonly alreadyRescheduledBadge: Locator;
  readonly rescheduleButtons: Locator;
  readonly cancelButtons: Locator;
  readonly requestCleaningBtn: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /my bookings/i });
    this.tabUpcoming = page.getByRole('button', { name: /upcoming/i });
    this.tabPast = page.getByRole('button', { name: /past/i });
    this.bookingCards = page.locator('.cc-card.cc-card-interactive');
    this.alreadyRescheduledBadge = page.getByText(/already rescheduled/i);
    this.rescheduleButtons = page.getByRole('button', { name: /^reschedule$/i });
    this.cancelButtons = page.getByRole('button', { name: /^cancel$/i });
    this.requestCleaningBtn = page.getByRole('button', { name: /request cleaning/i });
  }

  async goto(): Promise<void> {
    await this.page.goto('/my-bookings');
    await this.hydrate();
  }

  /**
   * Wait until the bookings list is hydrated (skeleton gone, cards or
   * empty-state visible). Call after any action that refetches the list.
   */
  async hydrate(): Promise<void> {
    await this.heading.waitFor({ state: 'visible', timeout: 10_000 });
    await this.page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});
    // Wait until either at least one card is rendered OR empty-state appears
    // — this is the real signal that CleanAPI fetch resolved.
    await this.page
      .waitForFunction(
        () =>
          document.querySelectorAll('.cc-card.cc-card-interactive').length > 0 ||
          !!document.querySelector('.cc-empty-state'),
        undefined,
        { timeout: 10_000 },
      )
      .catch(() => {});
    await this.page.waitForTimeout(300);
  }

  async reloadAndHydrate(): Promise<void> {
    await this.page.reload();
    await this.hydrate();
  }

  /** Open the cancel modal for the Nth upcoming booking (0-indexed). */
  async openCancelModal(index = 0): Promise<CancelModal> {
    const buttons = await this.cancelButtons.all();
    if (!buttons[index]) throw new Error(`No Cancel button at index ${index}`);
    await buttons[index].click();
    const modal = new CancelModal(this.page);
    await modal.waitForOpen();
    return modal;
  }

  async openRescheduleModal(index = 0): Promise<RescheduleModal> {
    const buttons = await this.rescheduleButtons.all();
    if (!buttons[index]) throw new Error(`No Reschedule button at index ${index}`);
    await buttons[index].click();
    const modal = new RescheduleModal(this.page);
    await modal.waitForOpen();
    return modal;
  }

  async expectRescheduleButtonHiddenAt(index: number): Promise<void> {
    // When limit reached, the Reschedule button is replaced by a badge
    const all = await this.bookingCards.all();
    if (!all[index]) throw new Error(`No booking at ${index}`);
    const card = all[index];
    const resch = card.getByRole('button', { name: /reschedule/i });
    await expect(resch).toHaveCount(0);
    // And the badge should be present in THAT card
    await expect(card.getByText(/already rescheduled/i)).toBeVisible();
  }

  async countUpcoming(): Promise<number> {
    return this.bookingCards.count();
  }
}
