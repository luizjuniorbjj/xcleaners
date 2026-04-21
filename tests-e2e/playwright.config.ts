import { defineConfig, devices } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';

// Load env based on TEST_ENV (prod | staging | dev). Default: prod.
const envName = process.env.TEST_ENV || 'prod';
dotenv.config({ path: path.resolve(__dirname, `.env.${envName}`) });

/**
 * Xcleaners E2E — Playwright Config
 *
 * Multi-environment via TEST_ENV=prod|staging|dev
 * Run:
 *   npm test                    → all tests
 *   npm run test:smoke          → smoke only (~90s)
 *   npm run test:policy         → policy MVP suite (core value)
 *   npm run test:regression     → full regression
 *   npm run test:negative       → negative/failure paths
 *   TEST_ENV=staging npm test   → against staging env
 *
 * Reports: reports/html/index.html (open with `npm run report`)
 */
export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // sequential by default — some tests mutate shared DB state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 2 : 1,

  reporter: [
    ['html', { outputFolder: 'reports/html', open: 'never' }],
    ['list'],
    ['json', { outputFile: 'reports/results.json' }],
    ...(process.env.CI ? [['github'] as const] : []),
  ],

  use: {
    baseURL: process.env.BASE_URL || 'https://app.xcleaners.app',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
  },

  outputDir: 'reports/test-artifacts',

  projects: [
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium',
      testIgnore: /.*\.setup\.ts/,
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        storageState: undefined, // each test uses auth fixture
      },
    },
    // Enable when needed — kept off by default to keep runs fast
    // {
    //   name: 'firefox',
    //   testIgnore: /.*\.setup\.ts/,
    //   dependencies: ['setup'],
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'mobile-safari',
    //   testIgnore: /.*\.setup\.ts/,
    //   dependencies: ['setup'],
    //   use: { ...devices['iPhone 14'] },
    // },
  ],
});
