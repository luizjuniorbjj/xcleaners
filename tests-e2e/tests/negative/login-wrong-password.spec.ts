/**
 * Negative — login fails with wrong password.
 * Does NOT use auth fixture because we're testing the failure path.
 */
import { test, expect } from '@playwright/test';
import { LoginPage } from '../../pages/LoginPage';
import * as dotenv from 'dotenv';
import * as path from 'path';

const envName = process.env.TEST_ENV || 'prod';
dotenv.config({ path: path.resolve(__dirname, `../../.env.${envName}`) });

test.describe('Negative — Auth failure paths', () => {
  test('wrong password keeps user on /login', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.loginAs(process.env.OWNER_EMAIL!, 'DefinitelyWrongPassword');
    await page.waitForTimeout(2000);
    await login.expectLoginFailed();
  });

  test('nonexistent email keeps user on /login', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.loginAs('noone@nowhere.invalid', 'Whatever123');
    await page.waitForTimeout(2000);
    await login.expectLoginFailed();
  });
});
