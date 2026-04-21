import { Page, Locator, expect } from '@playwright/test';

export class OwnerTeamsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly createTeamBtn: Locator;
  readonly inviteCleanerBtn: Locator;
  readonly teamCards: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole('heading', { name: /^teams$/i });
    this.createTeamBtn = page.getByRole('button', { name: /create team/i });
    this.inviteCleanerBtn = page.getByRole('button', { name: /invite cleaner/i });
    this.teamCards = page.locator('[data-testid="team-card"], .cc-card').filter({ hasText: /members?/i });
  }

  async goto(): Promise<void> {
    await this.page.goto('/teams');
    await this.heading.waitFor({ state: 'visible', timeout: 10_000 });
  }
}
