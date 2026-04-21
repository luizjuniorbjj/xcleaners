import { test, expect } from '../../fixtures/auth.fixture';
import { OwnerTeamsPage } from '../../pages/owner/OwnerTeamsPage';

test.describe('Regression — Owner Teams', () => {
  test('teams page renders action buttons', async ({ ownerPage }) => {
    const teams = new OwnerTeamsPage(ownerPage);
    await teams.goto();
    await expect(teams.heading).toBeVisible();
    await expect(teams.createTeamBtn).toBeVisible();
    await expect(teams.inviteCleanerBtn).toBeVisible();
  });
});
