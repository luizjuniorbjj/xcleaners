import { test, expect } from '../../fixtures/auth.fixture';
import { OwnerInvoicesPage } from '../../pages/owner/OwnerInvoicesPage';

test.describe('Regression — Owner Invoices', () => {
  test('invoices page renders heading and actions', async ({ ownerPage }) => {
    const invoices = new OwnerInvoicesPage(ownerPage);
    await invoices.goto();
    await expect(invoices.heading).toBeVisible();
    await expect(invoices.batchInvoiceBtn).toBeVisible();
  });
});
