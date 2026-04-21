import { test, expect } from '../../fixtures/auth.fixture';
import { OwnerClientsPage } from '../../pages/owner/OwnerClientsPage';

test.describe('Regression — Owner Clients', () => {
  test('clients page renders with add/import buttons + search', async ({ ownerPage }) => {
    const clients = new OwnerClientsPage(ownerPage);
    await clients.goto();
    await expect(clients.heading).toBeVisible();
    await expect(clients.addClientBtn).toBeVisible();
    await expect(clients.importCsvBtn).toBeVisible();
    await expect(clients.searchInput).toBeVisible();
  });
});
