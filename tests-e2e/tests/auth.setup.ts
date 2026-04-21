/**
 * Auth Setup — runs ONCE before the entire suite.
 * Located in tests/ so playwright's testDir picks it up.
 *
 * Logs in each of the 3 personas, saves storageState to .storage/*.json.
 * Every subsequent test reuses these states via the auth fixture.
 */
import { test as setup } from '@playwright/test';
import { performLogin, OWNER_STORAGE, HOMEOWNER_STORAGE, CLEANER_STORAGE } from '../fixtures/auth.fixture';
import * as dotenv from 'dotenv';
import * as path from 'path';

const envName = process.env.TEST_ENV || 'prod';
dotenv.config({ path: path.resolve(__dirname, `../.env.${envName}`) });

const OWNER_EMAIL = process.env.OWNER_EMAIL!;
const HOMEOWNER_EMAIL = process.env.HOMEOWNER_EMAIL!;
const CLEANER_EMAIL = process.env.CLEANER_EMAIL!;
const PASSWORD = process.env.TEST_PASSWORD!;

setup('authenticate owner', async ({ page }) => {
  await performLogin(page, OWNER_EMAIL, PASSWORD, OWNER_STORAGE);
});

setup('authenticate homeowner', async ({ page }) => {
  await performLogin(page, HOMEOWNER_EMAIL, PASSWORD, HOMEOWNER_STORAGE);
});

setup('authenticate cleaner', async ({ page }) => {
  await performLogin(page, CLEANER_EMAIL, PASSWORD, CLEANER_STORAGE);
});
