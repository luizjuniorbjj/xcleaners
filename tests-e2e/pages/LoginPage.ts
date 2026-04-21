import { Page, expect, Locator } from '@playwright/test';

/**
 * LoginPage — Page Object Model for the auth entry point.
 *
 * Routes:
 *   - /cleaning/app#/login  (hash-based SPA route)
 */
export class LoginPage {
  readonly page: Page;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly signInBtn: Locator;
  readonly forgotPasswordLink: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.emailInput = page.locator('input[type="email"], input[name="email"]').first();
    this.passwordInput = page.locator('input[type="password"]').first();
    this.signInBtn = page.getByRole('button', { name: /sign in/i }).first();
    this.forgotPasswordLink = page.getByRole('link', { name: /forgot password/i });
    this.errorMessage = page.locator('[role="alert"], .cc-toast-error, .error-message');
  }

  async goto(): Promise<void> {
    await this.page.goto('/cleaning/app#/login');
    await this.page.waitForLoadState('domcontentloaded');
    await this.page.waitForTimeout(500);
  }

  async loginAs(email: string, password: string): Promise<void> {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.signInBtn.click();
  }

  async expectLoginFailed(): Promise<void> {
    // Stays on /login after failed attempt
    await expect(this.page).toHaveURL(/\/login/);
  }

  async waitForSuccessfulLogin(): Promise<void> {
    await this.page.waitForURL((url) => !url.pathname.includes('/login'), {
      timeout: 15_000,
    });
  }
}
