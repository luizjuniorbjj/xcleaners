/**
 * Auth Fixture — provides authenticated pages per role.
 *
 * Uses Playwright's `storageState` pattern: login once per role in the
 * setup project, persist cookies/localStorage to disk, then reuse that
 * state in every test. Makes the suite ~10x faster vs logging each test.
 *
 * Usage in specs:
 *
 *   test('owner can see settings', async ({ ownerPage }) => { ... });
 *   test('homeowner sees bookings', async ({ homeownerPage }) => { ... });
 *   test('cleaner sees today', async ({ cleanerPage }) => { ... });
 */
import { test as base, Page } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';

const STORAGE_DIR = path.resolve(__dirname, '../.storage');
if (!fs.existsSync(STORAGE_DIR)) fs.mkdirSync(STORAGE_DIR, { recursive: true });

export const OWNER_STORAGE = path.join(STORAGE_DIR, 'owner.json');
export const HOMEOWNER_STORAGE = path.join(STORAGE_DIR, 'homeowner.json');
export const CLEANER_STORAGE = path.join(STORAGE_DIR, 'cleaner.json');

type Fixtures = {
  ownerPage: Page;
  homeownerPage: Page;
  cleanerPage: Page;
};

export const test = base.extend<Fixtures>({
  ownerPage: async ({ browser }, use) => {
    const context = await browser.newContext({ storageState: OWNER_STORAGE });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },

  homeownerPage: async ({ browser }, use) => {
    const context = await browser.newContext({ storageState: HOMEOWNER_STORAGE });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },

  cleanerPage: async ({ browser }, use) => {
    const context = await browser.newContext({ storageState: CLEANER_STORAGE });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

export const expect = test.expect;

/**
 * Helper used by the auth.setup.ts project: performs the UI login and
 * saves the storageState to disk so subsequent tests skip the flow.
 */
export async function performLogin(
  page: Page,
  email: string,
  password: string,
  storagePath: string
): Promise<void> {
  await page.goto('/cleaning/app#/login');
  await page.waitForLoadState('domcontentloaded');
  // Login page uses hash route — wait a tick for the client router to render
  await page.waitForTimeout(500);

  // Form fields — use accessible role selectors when possible, fallback to attribute
  const emailInput = page.locator('input[type="email"], input[name="email"]').first();
  const passwordInput = page.locator('input[type="password"]').first();
  await emailInput.fill(email);
  await passwordInput.fill(password);

  const signIn = page.getByRole('button', { name: /sign in/i }).first();
  await signIn.click();

  // Wait for redirect away from /login — any post-auth route counts as success
  await page.waitForURL(
    (url) => !url.pathname.includes('/login'),
    { timeout: 15_000 }
  );

  await page.context().storageState({ path: storagePath });
}
