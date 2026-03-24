/**
 * CleanClaw — Homeowner My Invoices Module (Sprint 3)
 *
 * Invoice list with status badges and pay button.
 */
window.HomeownerMyInvoices = {
  async render(container) {
    container.innerHTML = `
      <div class="cc-my-invoices" style="display:flex;flex-direction:column;gap:var(--cc-space-5);">
        <!-- Page Header -->
        <h2 style="margin:0;">My Invoices</h2>

        <!-- Total Due (skeleton) -->
        <div id="cc-invoices-summary"></div>

        <!-- Invoice List (skeleton) -->
        <div id="cc-invoices-list" style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
          <div class="cc-card" style="padding:var(--cc-space-4);">
            <div class="cc-skeleton cc-skeleton-text" style="width:50%;"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:30%;margin-top:var(--cc-space-2);"></div>
          </div>
          <div class="cc-card" style="padding:var(--cc-space-4);">
            <div class="cc-skeleton cc-skeleton-text" style="width:60%;"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:25%;margin-top:var(--cc-space-2);"></div>
          </div>
          <div class="cc-card" style="padding:var(--cc-space-4);">
            <div class="cc-skeleton cc-skeleton-text" style="width:45%;"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:35%;margin-top:var(--cc-space-2);"></div>
          </div>
        </div>
      </div>
    `;

    try {
      const rawData = await CleanAPI.cleanGet('/my-invoices');
      const data = (rawData && typeof rawData === 'object' && Object.keys(rawData).length > 0) ? rawData : { total_due: 0, invoices: [] };

      const summaryEl = document.getElementById('cc-invoices-summary');
      const listEl = document.getElementById('cc-invoices-list');

      // Total Due stat card
      if ((data.total_due || 0) > 0) {
        summaryEl.innerHTML = `
          <div class="cc-card cc-stat-card cc-stat-warning cc-animate-fade-in" style="border-left-width:4px;">
            <div>
              <div class="cc-stat-card-value" style="color:var(--cc-warning-600);">$${(data.total_due || 0).toFixed(2)}</div>
              <div class="cc-stat-card-label">Total Due</div>
            </div>
            <div class="cc-stat-card-icon" style="background:var(--cc-warning-50);color:var(--cc-warning-500);">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
            </div>
          </div>
        `;
      } else {
        summaryEl.innerHTML = `
          <div class="cc-card cc-stat-card cc-stat-success cc-animate-fade-in" style="border-left-width:4px;">
            <div>
              <div class="cc-stat-card-value" style="color:var(--cc-success-600);">$0.00</div>
              <div class="cc-stat-card-label">All Paid Up</div>
            </div>
            <div class="cc-stat-card-icon" style="background:var(--cc-success-50);color:var(--cc-success-500);">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            </div>
          </div>
        `;
      }

      const invoices = Array.isArray(data.invoices) ? data.invoices : [];
      if (invoices.length === 0) {
        listEl.innerHTML = `
          <div class="cc-card cc-empty-state cc-animate-fade-in" style="padding:var(--cc-space-8);">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.invoice : '&#128196;'}</div>
            <div class="cc-empty-state-title" style="font-size:var(--cc-text-lg);">No invoices yet</div>
            <div class="cc-empty-state-description">Invoices from your cleaning service will appear here. When they do, you can pay online securely.</div>
          </div>
        `;
        return;
      }

      // Invoice table
      listEl.innerHTML = `
        <div class="cc-table-wrapper cc-animate-fade-in">
          <table class="cc-table">
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Date</th>
                <th>Amount</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${invoices.map(inv => {
                const dateStr = new Date(inv.issue_date + 'T00:00:00').toLocaleDateString('en-US', {
                  month: 'short', day: 'numeric', year: 'numeric',
                });
                const statusBadge = {
                  paid: 'cc-badge-success',
                  partial: 'cc-badge-warning',
                  overdue: 'cc-badge-danger',
                  sent: 'cc-badge-primary',
                  viewed: 'cc-badge-primary',
                  draft: 'cc-badge-neutral',
                  void: 'cc-badge-neutral',
                  refunded: 'cc-badge-neutral',
                };
                const badgeClass = statusBadge[inv.status] || 'cc-badge-neutral';
                const showPay = ['sent', 'viewed', 'partial', 'overdue'].includes(inv.status);

                return `
                  <tr>
                    <td>
                      <div class="cc-font-medium" style="color:var(--cc-neutral-900);">${this._esc(inv.number)}</div>
                      ${inv.service_name ? `<div class="cc-text-xs cc-text-muted">${this._esc(inv.service_name)}</div>` : ''}
                    </td>
                    <td class="cc-text-sm">${dateStr}</td>
                    <td>
                      <span class="cc-font-semibold" style="color:var(--cc-neutral-900);">$${(inv.total || 0).toFixed(2)}</span>
                      ${(inv.balance_due || 0) > 0 ? `<div class="cc-text-xs cc-text-warning">Due: $${(inv.balance_due || 0).toFixed(2)}</div>` : ''}
                    </td>
                    <td><span class="cc-badge ${badgeClass}">${inv.status}</span></td>
                    <td style="text-align:right;">
                      ${showPay ? `<button class="cc-btn cc-btn-primary cc-btn-xs cc-btn-pay" data-invoice-id="${inv.id}">Pay Now</button>` : ''}
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;

      // Pay button listeners
      listEl.querySelectorAll('.cc-btn-pay').forEach(btn => {
        btn.addEventListener('click', () => {
          // In production, this would open a Stripe payment link
          CleanClaw.showToast('Online payment coming soon. Contact your cleaning service for payment options.', 'info');
        });
      });

    } catch (err) {
      console.error('[MyInvoices] Error:', err);
      document.getElementById('cc-invoices-list').innerHTML = `
        <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
          <div class="cc-empty-state-title">Could not load invoices</div>
          <div class="cc-empty-state-description">Please check your connection and try again.</div>
        </div>
      `;
    }
  },

  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },
};
