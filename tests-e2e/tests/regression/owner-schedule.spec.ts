import { test, expect } from '../../fixtures/auth.fixture';
import { OwnerSchedulePage } from '../../pages/owner/OwnerSchedulePage';

test.describe('Regression — Owner Schedule/Calendar', () => {
  test('schedule page has navigation controls', async ({ ownerPage }) => {
    const schedule = new OwnerSchedulePage(ownerPage);
    await schedule.goto();
    await expect(schedule.prevBtn).toBeVisible();
    await expect(schedule.todayBtn).toBeVisible();
    await expect(schedule.nextBtn).toBeVisible();
  });
});
