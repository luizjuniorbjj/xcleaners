/**
 * CleanClaw — Owner Invoice Manager Module (Sprint 4)
 *
 * Full invoice management:
 * - Invoice list with status tabs (All/Draft/Sent/Paid/Overdue)
 * - Summary cards: total revenue, outstanding, overdue amount
 * - Batch generate button
 * - Send/remind actions
 * - Mark paid modal (cash/check/Zelle/other)
 * - Invoice detail with line items
 * - Payment link copy button
 */
window.OwnerInvoiceManager = {
  _currentTab: 'all',
  _invoices: [],
  _dashboard: null,
  _page: 1,
  _total: 0,
  _selectedIds: new Set(),
  _detailInvoice: null,

  async render(container, params) {
    this._container = container;
    this._selectedIds.clear();
    this._detailInvoice = null;

    container.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <!-- Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <h2 style="margin:0;">Invoices</h2>
          <div style="display:flex;gap:var(--cc-space-2);">
            <button class="cc-btn cc-btn-secondary cc-btn-sm" id="cc-batch-invoice-btn">
              Batch Invoice
            </button>
            <button class="cc-btn cc-btn-primary cc-btn-sm" id="cc-remind-overdue-btn">
              Remind Overdue
            </button>
          </div>
        </div>

        <!-- KPI Summary Cards -->
        <div id="cc-invoice-kpis" style="display:grid;grid-template-columns:repeat(3,1fr);gap:var(--cc-space-4);">
          <div class="cc-card cc-stat-card cc-stat-success">
            <div>
              <div class="cc-stat-card-value" id="kpi-month-revenue">
                <div class="cc-skeleton" style="width:80px;height:28px;"></div>
              </div>
              <div class="cc-stat-card-label">Revenue This Month</div>
            </div>
            <div class="cc-stat-card-icon" style="background:var(--cc-success-50);color:var(--cc-success-500);">$</div>
          </div>
          <div class="cc-card cc-stat-card">
            <div>
              <div class="cc-stat-card-value" id="kpi-outstanding">
                <div class="cc-skeleton" style="width:80px;height:28px;"></div>
              </div>
              <div class="cc-stat-card-label">Outstanding</div>
            </div>
            <div class="cc-stat-card-icon">&#9201;</div>
          </div>
          <div class="cc-card cc-stat-card cc-stat-danger">
            <div>
              <div class="cc-stat-card-value" id="kpi-overdue">
                <div class="cc-skeleton" style="width:80px;height:28px;"></div>
              </div>
              <div class="cc-stat-card-label">Overdue (<span id="kpi-overdue-count">0</span>)</div>
            </div>
            <div class="cc-stat-card-icon" style="background:var(--cc-danger-50);color:var(--cc-danger-500);">&#9888;</div>
          </div>
        </div>

        <!-- Status Tabs -->
        <div id="cc-invoice-tabs" style="display:flex;gap:var(--cc-space-1);border-bottom:1px solid var(--cc-neutral-200);padding-bottom:0;">
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="all" style="border-bottom:2px solid var(--cc-primary-500);border-radius:0;color:var(--cc-primary-600);font-weight:var(--cc-font-semibold);">All</button>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="draft" style="border-bottom:2px solid transparent;border-radius:0;">Draft</button>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="sent" style="border-bottom:2px solid transparent;border-radius:0;">Sent</button>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="paid" style="border-bottom:2px solid transparent;border-radius:0;">Paid</button>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="overdue" style="border-bottom:2px solid transparent;border-radius:0;">Overdue</button>
        </div>

        <!-- Search -->
        <div>
          <input type="text" id="cc-invoice-search" class="cc-input"
                 placeholder="Search client name or invoice #..."
                 style="height:36px;font-size:var(--cc-text-sm);" />
        </div>

        <!-- Invoice List -->
        <div id="cc-invoice-list">
          <div style="display:flex;flex-direction:column;gap:var(--cc-space-2);">
            <div class="cc-skeleton" style="height:40px;width:100%;"></div>
            <div class="cc-skeleton" style="height:40px;width:100%;"></div>
            <div class="cc-skeleton" style="height:40px;width:100%;"></div>
          </div>
        </div>

        <!-- Batch Actions (shown when items selected) -->
        <div id="cc-batch-actions" style="display:none;position:fixed;bottom:calc(var(--cc-bottombar-height) + var(--cc-space-4));left:50%;transform:translateX(-50%);background:var(--cc-neutral-800);color:#fff;padding:var(--cc-space-3) var(--cc-space-5);border-radius:var(--cc-radius-lg);box-shadow:var(--cc-shadow-lg);align-items:center;gap:var(--cc-space-3);z-index:var(--cc-z-toast);">
          <span id="cc-selected-count" class="cc-text-sm">0</span> <span class="cc-text-sm">selected:</span>
          <button class="cc-btn cc-btn-xs" id="cc-batch-send-reminder" style="background:rgba(255,255,255,0.2);color:#fff;border:1px solid rgba(255,255,255,0.3);">Send Reminder</button>
          <button class="cc-btn cc-btn-xs" id="cc-batch-mark-paid" style="background:rgba(255,255,255,0.2);color:#fff;border:1px solid rgba(255,255,255,0.3);">Mark Paid</button>
        </div>

        <!-- Invoice Detail Panel -->
        <div id="cc-invoice-detail" style="display:none;position:fixed;top:0;right:0;bottom:0;width:420px;max-width:90vw;background:#fff;box-shadow:var(--cc-shadow-xl);z-index:var(--cc-z-modal);overflow-y:auto;"></div>

        <!-- Mark Paid Modal -->
        <div class="cc-modal-backdrop" id="cc-mark-paid-modal">
          <div class="cc-modal" style="max-width:420px;" onclick="event.stopPropagation()">
            <div class="cc-modal-header">
              <h3 class="cc-modal-title">Record Manual Payment</h3>
              <button class="cc-modal-close" id="cc-mark-paid-close">&times;</button>
            </div>
            <div class="cc-modal-body">
              <div class="cc-form-group">
                <label class="cc-label">Payment Method</label>
                <select id="cc-pay-method" class="cc-select">
                  <option value="cash">Cash</option>
                  <option value="check">Check</option>
                  <option value="zelle">Zelle</option>
                  <option value="venmo">Venmo</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Amount ($)</label>
                <input type="number" id="cc-pay-amount" class="cc-input" step="0.01" min="0.01" />
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Reference (optional)</label>
                <input type="text" id="cc-pay-reference" class="cc-input"
                       placeholder="Check #, transaction ID..." />
              </div>
            </div>
            <div class="cc-modal-footer">
              <button class="cc-btn cc-btn-secondary cc-btn-sm" id="cc-mark-paid-cancel">Cancel</button>
              <button class="cc-btn cc-btn-primary cc-btn-sm" id="cc-mark-paid-confirm">Record Payment</button>
            </div>
          </div>
        </div>

        <!-- Batch Invoice Modal -->
        <div class="cc-modal-backdrop" id="cc-batch-modal">
          <div class="cc-modal" style="max-width:480px;" onclick="event.stopPropagation()">
            <div class="cc-modal-header">
              <h3 class="cc-modal-title">Batch Generate Invoices</h3>
              <button class="cc-modal-close" id="cc-batch-close">&times;</button>
            </div>
            <div class="cc-modal-body">
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
                <div class="cc-form-group">
                  <label class="cc-label">From Date</label>
                  <input type="date" id="cc-batch-from" class="cc-input" />
                </div>
                <div class="cc-form-group">
                  <label class="cc-label">To Date</label>
                  <input type="date" id="cc-batch-to" class="cc-input" />
                </div>
              </div>
              <p class="cc-text-sm cc-text-muted">
                Generates invoices for all completed jobs in this date range
                that don't already have an invoice.
              </p>
              <div id="cc-batch-result"></div>
            </div>
            <div class="cc-modal-footer">
              <button class="cc-btn cc-btn-secondary cc-btn-sm" id="cc-batch-cancel">Cancel</button>
              <button class="cc-btn cc-btn-primary cc-btn-sm" id="cc-batch-generate">Generate Invoices</button>
            </div>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
    await this._loadDashboard();
    await this._loadInvoices();
  },

  // ============================================
  // EVENT BINDING
  // ============================================

  _bindEvents() {
    // Tab clicks
    document.querySelectorAll('#cc-invoice-tabs button[data-tab]').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('#cc-invoice-tabs button[data-tab]').forEach(t => {
          t.style.borderBottomColor = 'transparent';
          t.style.color = '';
          t.style.fontWeight = '';
        });
        tab.style.borderBottomColor = 'var(--cc-primary-500)';
        tab.style.color = 'var(--cc-primary-600)';
        tab.style.fontWeight = 'var(--cc-font-semibold)';
        this._currentTab = tab.dataset.tab;
        this._page = 1;
        this._loadInvoices();
      });
    });

    // Search
    let searchTimeout;
    document.getElementById('cc-invoice-search')?.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        this._page = 1;
        this._loadInvoices();
      }, 400);
    });

    // Batch Invoice button
    document.getElementById('cc-batch-invoice-btn')?.addEventListener('click', () => {
      this._openBatchModal();
    });

    // Remind overdue
    document.getElementById('cc-remind-overdue-btn')?.addEventListener('click', () => {
      this._remindOverdue();
    });

    // Batch modal
    document.getElementById('cc-batch-close')?.addEventListener('click', () => this._closeBatchModal());
    document.getElementById('cc-batch-cancel')?.addEventListener('click', () => this._closeBatchModal());
    document.getElementById('cc-batch-generate')?.addEventListener('click', () => this._doBatchGenerate());

    // Mark Paid modal
    document.getElementById('cc-mark-paid-close')?.addEventListener('click', () => this._closeMarkPaidModal());
    document.getElementById('cc-mark-paid-cancel')?.addEventListener('click', () => this._closeMarkPaidModal());
    document.getElementById('cc-mark-paid-confirm')?.addEventListener('click', () => this._doMarkPaid());
  },

  // ============================================
  // DATA LOADING
  // ============================================

  async _loadDashboard() {
    try {
      const slug = CleanAPI._slug;
      const dashResp = await CleanAPI.request('GET', `/api/v1/clean/${slug}/payments/dashboard`);
      this._dashboard = (dashResp && typeof dashResp === 'object' && Object.keys(dashResp).length > 0) ? dashResp : {
        revenue_this_month: 0, outstanding: 0, overdue_amount: 0, overdue_count: 0
      };
      this._renderKPIs();
    } catch (err) {
      console.error('[INVOICES] Dashboard load error:', err);
      this._dashboard = { revenue_this_month: 0, outstanding: 0, overdue_amount: 0, overdue_count: 0 };
      this._renderKPIs();
    }
  },

  async _loadInvoices() {
    const slug = CleanAPI._slug;
    const search = document.getElementById('cc-invoice-search')?.value || '';
    const status = this._currentTab === 'all' ? '' : this._currentTab;

    let url = `/api/v1/clean/${slug}/invoices?page=${this._page}&page_size=50`;
    if (status) url += `&status=${status}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    try {
      const data = await CleanAPI.request('GET', url) || {};
      this._invoices = Array.isArray(data.invoices) ? data.invoices : (Array.isArray(data) ? data : []);
      this._total = data.total || this._invoices.length;
      this._renderInvoiceTable();
    } catch (err) {
      console.error('[INVOICES] Load error:', err);
      document.getElementById('cc-invoice-list').innerHTML =
        '<div class="cc-card" style="padding:var(--cc-space-6);text-align:center;"><p class="cc-text-sm cc-text-danger">Could not load invoices. Please check your connection and try again.</p></div>';
    }
  },

  // ============================================
  // RENDERING
  // ============================================

  _renderKPIs() {
    const d = this._dashboard || {};

    const fmt = (n) => `$${(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;

    const monthEl = document.getElementById('kpi-month-revenue');
    const outEl = document.getElementById('kpi-outstanding');
    const overdueEl = document.getElementById('kpi-overdue');
    const overdueCountEl = document.getElementById('kpi-overdue-count');

    if (monthEl) monthEl.textContent = fmt(d.month_revenue || d.revenue_this_month);
    if (outEl) outEl.textContent = fmt(d.outstanding);
    if (overdueEl) overdueEl.textContent = fmt(d.overdue_amount);
    if (overdueCountEl) overdueCountEl.textContent = d.overdue_count || 0;
  },

  _renderInvoiceTable() {
    const listEl = document.getElementById('cc-invoice-list');
    if (!listEl) return;

    if (this._invoices.length === 0) {
      const emptyMsg = this._currentTab === 'all'
        ? 'Invoices are created when jobs are completed. Complete your first job and an invoice will appear here.'
        : `No ${this._currentTab} invoices found.`;
      listEl.innerHTML = `
        <div class="cc-card">
          <div class="cc-empty-state">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.invoice : '&#128196;'}</div>
            <div class="cc-empty-state-title">No invoices yet</div>
            <div class="cc-empty-state-description">${emptyMsg}</div>
          </div>
        </div>`;
      return;
    }

    const statusBadge = (s) => {
      const map = {
        draft: 'cc-badge-neutral',
        sent: 'cc-badge-primary',
        viewed: 'cc-badge-info',
        paid: 'cc-badge-success',
        partial: 'cc-badge-warning',
        overdue: 'cc-badge-danger',
        void: 'cc-badge-neutral',
        refunded: 'cc-badge-neutral',
      };
      return `<span class="cc-badge cc-badge-sm ${map[s] || 'cc-badge-neutral'}">${s}</span>`;
    };

    const fmt = (n) => `$${(n || 0).toFixed(2)}`;

    let rows = this._invoices.map(inv => `
      <tr style="cursor:pointer;" data-id="${inv.id}">
        <td><input type="checkbox" class="cc-inv-check" data-id="${inv.id}" onclick="event.stopPropagation();" /></td>
        <td class="cc-font-medium">${inv.invoice_number || '--'}</td>
        <td>${inv.client_name || '--'}</td>
        <td class="cc-text-right cc-font-medium">${fmt(inv.total)}</td>
        <td>${statusBadge(inv.status)}</td>
        <td>${inv.due_date || '--'}${inv.days_overdue ? ` <span class="cc-text-danger cc-text-xs">(${inv.days_overdue}d)</span>` : ''}</td>
        <td>
          <div style="display:flex;gap:var(--cc-space-1);justify-content:flex-end;">
            <button class="cc-btn cc-btn-ghost cc-btn-xs cc-inv-view" data-id="${inv.id}">View</button>
            ${inv.status === 'draft' ? `<button class="cc-btn cc-btn-primary cc-btn-xs cc-inv-send" data-id="${inv.id}">Send</button>` : ''}
            ${['sent', 'overdue', 'partial'].includes(inv.status) ? `<button class="cc-btn cc-btn-ghost cc-btn-xs cc-inv-mark-paid" data-id="${inv.id}">Paid</button>` : ''}
          </div>
        </td>
      </tr>
    `).join('');

    listEl.innerHTML = `
      <div class="cc-table-wrapper">
        <table class="cc-table">
          <thead>
            <tr>
              <th style="width:32px;"><input type="checkbox" id="cc-inv-check-all" /></th>
              <th>Invoice #</th>
              <th>Client</th>
              <th class="cc-text-right">Amount</th>
              <th>Status</th>
              <th>Due</th>
              <th class="cc-text-right">Actions</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${this._total > 50 ? `<div class="cc-text-sm cc-text-muted" style="text-align:center;padding:var(--cc-space-3);">Page ${this._page} of ${Math.ceil(this._total / 50)}</div>` : ''}
    `;

    // Bind row events
    listEl.querySelectorAll('.cc-inv-view').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._showDetail(btn.dataset.id);
      });
    });

    listEl.querySelectorAll('.cc-inv-send').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._sendInvoice(btn.dataset.id);
      });
    });

    listEl.querySelectorAll('.cc-inv-mark-paid').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._openMarkPaidModal(btn.dataset.id);
      });
    });

    // Checkboxes
    document.getElementById('cc-inv-check-all')?.addEventListener('change', (e) => {
      listEl.querySelectorAll('.cc-inv-check').forEach(cb => {
        cb.checked = e.target.checked;
        if (e.target.checked) {
          this._selectedIds.add(cb.dataset.id);
        } else {
          this._selectedIds.delete(cb.dataset.id);
        }
      });
      this._updateBatchActions();
    });

    listEl.querySelectorAll('.cc-inv-check').forEach(cb => {
      cb.addEventListener('change', () => {
        if (cb.checked) this._selectedIds.add(cb.dataset.id);
        else this._selectedIds.delete(cb.dataset.id);
        this._updateBatchActions();
      });
    });

    // Row click -> detail
    listEl.querySelectorAll('tbody tr[data-id]').forEach(row => {
      row.addEventListener('click', (e) => {
        if (e.target.closest('button') || e.target.closest('input')) return;
        this._showDetail(row.dataset.id);
      });
    });
  },

  _updateBatchActions() {
    const bar = document.getElementById('cc-batch-actions');
    const countEl = document.getElementById('cc-selected-count');
    if (this._selectedIds.size > 0) {
      bar.style.display = 'flex';
      countEl.textContent = this._selectedIds.size;
    } else {
      bar.style.display = 'none';
    }
  },

  // ============================================
  // INVOICE DETAIL
  // ============================================

  async _showDetail(invoiceId) {
    const slug = CleanAPI._slug;
    const panel = document.getElementById('cc-invoice-detail');
    if (!panel) return;

    panel.style.display = 'block';
    panel.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
      </div>
    `;

    try {
      const inv = await CleanAPI.request('GET', `/api/v1/clean/${slug}/invoices/${invoiceId}`);
      if (!inv) {
        panel.innerHTML = '<div style="padding:var(--cc-space-6);text-align:center;" class="cc-text-danger">Invoice not found</div>';
        return;
      }

      this._detailInvoice = inv;
      const fmt = (n) => `$${(n || 0).toFixed(2)}`;
      const statusMap = {
        draft: 'cc-badge-neutral', sent: 'cc-badge-primary', viewed: 'cc-badge-info',
        paid: 'cc-badge-success', partial: 'cc-badge-warning', overdue: 'cc-badge-danger',
      };

      const itemsHtml = (inv.items || []).map(item => `
        <tr>
          <td class="cc-text-sm">${item.description}</td>
          <td class="cc-text-right cc-text-sm">${item.quantity}</td>
          <td class="cc-text-right cc-text-sm">${fmt(item.unit_price)}</td>
          <td class="cc-text-right cc-text-sm cc-font-medium">${fmt(item.total)}</td>
        </tr>
      `).join('') || '<tr><td colspan="4" class="cc-text-sm cc-text-muted">No line items</td></tr>';

      panel.innerHTML = `
        <div style="display:flex;flex-direction:column;height:100%;">
          <!-- Header -->
          <div style="display:flex;align-items:center;justify-content:space-between;padding:var(--cc-space-5);border-bottom:1px solid var(--cc-neutral-200);">
            <h3 style="margin:0;">${inv.invoice_number}</h3>
            <button class="cc-btn cc-btn-ghost cc-btn-sm cc-detail-close" style="font-size:1.25rem;">&times;</button>
          </div>

          <!-- Body -->
          <div style="flex:1;padding:var(--cc-space-5);overflow-y:auto;display:flex;flex-direction:column;gap:var(--cc-space-4);">
            <!-- Meta -->
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
              <div class="cc-text-sm"><span class="cc-text-muted">Client:</span> <strong>${inv.client_name || '--'}</strong></div>
              <div class="cc-text-sm"><span class="cc-text-muted">Status:</span> <span class="cc-badge cc-badge-sm ${statusMap[inv.status] || 'cc-badge-neutral'}">${inv.status}</span></div>
              <div class="cc-text-sm"><span class="cc-text-muted">Issued:</span> ${inv.issue_date}</div>
              <div class="cc-text-sm"><span class="cc-text-muted">Due:</span> ${inv.due_date}</div>
              <div class="cc-text-sm"><span class="cc-text-muted">Total:</span> <strong>${fmt(inv.total)}</strong></div>
              <div class="cc-text-sm"><span class="cc-text-muted">Paid:</span> ${fmt(inv.amount_paid)}</div>
              <div class="cc-text-sm"><span class="cc-text-muted">Balance:</span> <strong class="${inv.balance_due > 0 ? 'cc-text-danger' : ''}">${fmt(inv.balance_due)}</strong></div>
              ${inv.payment_method ? `<div class="cc-text-sm"><span class="cc-text-muted">Method:</span> ${inv.payment_method}</div>` : ''}
            </div>

            <!-- Line Items -->
            <div>
              <h5 style="margin:0 0 var(--cc-space-2);">Line Items</h5>
              <div class="cc-table-wrapper">
                <table class="cc-table">
                  <thead>
                    <tr><th>Description</th><th class="cc-text-right">Qty</th><th class="cc-text-right">Price</th><th class="cc-text-right">Total</th></tr>
                  </thead>
                  <tbody>${itemsHtml}</tbody>
                </table>
              </div>
            </div>

            ${inv.notes ? `<div class="cc-text-sm"><span class="cc-text-muted">Notes:</span> ${inv.notes}</div>` : ''}
          </div>

          <!-- Footer Actions -->
          <div style="padding:var(--cc-space-4) var(--cc-space-5);border-top:1px solid var(--cc-neutral-200);display:flex;gap:var(--cc-space-2);justify-content:flex-end;">
            ${inv.status === 'draft' ? `<button class="cc-btn cc-btn-primary cc-btn-sm" id="cc-detail-send">Send Invoice</button>` : ''}
            ${inv.balance_due > 0 && inv.status !== 'draft' ? `
              <button class="cc-btn cc-btn-secondary cc-btn-sm" id="cc-detail-payment-link">Copy Payment Link</button>
              <button class="cc-btn cc-btn-primary cc-btn-sm" id="cc-detail-mark-paid">Mark Paid</button>
            ` : ''}
          </div>
        </div>
      `;

      // Bind detail events
      panel.querySelector('.cc-detail-close')?.addEventListener('click', () => {
        panel.style.display = 'none';
      });

      document.getElementById('cc-detail-send')?.addEventListener('click', () => {
        this._sendInvoice(invoiceId);
      });

      document.getElementById('cc-detail-payment-link')?.addEventListener('click', () => {
        this._copyPaymentLink(invoiceId);
      });

      document.getElementById('cc-detail-mark-paid')?.addEventListener('click', () => {
        this._openMarkPaidModal(invoiceId);
      });

    } catch (err) {
      console.error('[INVOICES] Detail load error:', err);
      panel.innerHTML = '<div style="padding:var(--cc-space-6);text-align:center;" class="cc-text-danger">Failed to load invoice details</div>';
    }
  },

  // ============================================
  // ACTIONS
  // ============================================

  async _sendInvoice(invoiceId) {
    const slug = CleanAPI._slug;
    try {
      const result = await CleanAPI.request('POST', `/api/v1/clean/${slug}/invoices/${invoiceId}/send`);
      if (result) {
        CleanClaw.showToast(`Invoice sent. ${result.payment_url ? 'The client will receive an email with a payment link.' : ''}`, 'success');
        await this._loadInvoices();
        await this._loadDashboard();
      }
    } catch (err) {
      CleanClaw.showToast('Could not send invoice. ' + (err.message || 'Please check the client\'s email address and try again.'), 'error');
    }
  },

  async _copyPaymentLink(invoiceId) {
    const slug = CleanAPI._slug;
    try {
      const result = await CleanAPI.request('POST', `/api/v1/clean/${slug}/invoices/${invoiceId}/payment-link`);
      if (result?.payment_url) {
        await navigator.clipboard.writeText(result.payment_url);
        CleanClaw.showToast('Payment link copied to clipboard.', 'success');
      } else {
        CleanClaw.showToast('Could not create payment link. Please try again.', 'error');
      }
    } catch (err) {
      CleanClaw.showToast('Error: ' + (err.message || 'Unknown error'), 'error');
    }
  },

  _markPaidInvoiceId: null,

  _openMarkPaidModal(invoiceId) {
    this._markPaidInvoiceId = invoiceId;
    const inv = this._invoices.find(i => i.id === invoiceId) || this._detailInvoice;
    if (inv) {
      document.getElementById('cc-pay-amount').value = (inv.balance_due || inv.total || 0).toFixed(2);
    }
    document.getElementById('cc-mark-paid-modal').classList.add('cc-visible');
  },

  _closeMarkPaidModal() {
    document.getElementById('cc-mark-paid-modal').classList.remove('cc-visible');
    this._markPaidInvoiceId = null;
  },

  async _doMarkPaid() {
    const invoiceId = this._markPaidInvoiceId;
    if (!invoiceId) return;

    const method = document.getElementById('cc-pay-method')?.value;
    const amount = parseFloat(document.getElementById('cc-pay-amount')?.value || '0');
    const reference = document.getElementById('cc-pay-reference')?.value || '';

    if (!amount || amount <= 0) {
      CleanClaw.showToast('Please enter a valid amount', 'warning');
      return;
    }

    const slug = CleanAPI._slug;
    try {
      const result = await CleanAPI.request('POST',
        `/api/v1/clean/${slug}/invoices/${invoiceId}/mark-paid`,
        { method, amount, reference: reference || null }
      );
      if (result) {
        this._closeMarkPaidModal();
        CleanClaw.showToast('Payment recorded successfully.', 'success');
        await this._loadInvoices();
        await this._loadDashboard();
        // Refresh detail if open
        const panel = document.getElementById('cc-invoice-detail');
        if (panel?.style.display !== 'none') {
          this._showDetail(invoiceId);
        }
      }
    } catch (err) {
      CleanClaw.showToast('Error: ' + (err.message || 'Unknown error'), 'error');
    }
  },

  // ============================================
  // BATCH INVOICE
  // ============================================

  _openBatchModal() {
    const today = new Date();
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);

    document.getElementById('cc-batch-from').value = weekAgo.toISOString().split('T')[0];
    document.getElementById('cc-batch-to').value = today.toISOString().split('T')[0];
    document.getElementById('cc-batch-result').innerHTML = '';
    document.getElementById('cc-batch-modal').classList.add('cc-visible');
  },

  _closeBatchModal() {
    document.getElementById('cc-batch-modal').classList.remove('cc-visible');
  },

  async _doBatchGenerate() {
    const dateFrom = document.getElementById('cc-batch-from')?.value;
    const dateTo = document.getElementById('cc-batch-to')?.value;
    if (!dateFrom || !dateTo) {
      CleanClaw.showToast('Please select both dates', 'warning');
      return;
    }

    const slug = CleanAPI._slug;
    const resultEl = document.getElementById('cc-batch-result');
    resultEl.innerHTML = `
      <div style="display:flex;align-items:center;gap:var(--cc-space-2);padding:var(--cc-space-3);">
        <div class="cc-loading-overlay-spinner" style="width:20px;height:20px;border-width:2px;"></div>
        <span class="cc-text-sm">Generating invoices...</span>
      </div>
    `;

    try {
      const result = await CleanAPI.request('POST',
        `/api/v1/clean/${slug}/invoices/batch`,
        { date_from: dateFrom, date_to: dateTo }
      );
      if (result) {
        resultEl.innerHTML = `
          <div style="padding:var(--cc-space-3);background:var(--cc-success-50);color:var(--cc-success-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);">
            <strong>${result.created} invoices generated.</strong>
            ${result.errors ? `<br>${result.errors} errors.` : ''}
          </div>
        `;
        await this._loadInvoices();
        await this._loadDashboard();
      }
    } catch (err) {
      resultEl.innerHTML = `<div style="padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);">Error: ${err.message || 'Unknown error'}</div>`;
    }
  },

  // ============================================
  // REMIND OVERDUE
  // ============================================

  async _remindOverdue() {
    if (!confirm('Send payment reminders to all clients with overdue invoices?')) return;

    const slug = CleanAPI._slug;
    try {
      const result = await CleanAPI.request('POST', `/api/v1/clean/${slug}/invoices/remind-overdue`);
      if (result) {
        CleanClaw.showToast(`Payment reminders sent to ${result.reminded} clients with overdue invoices.`, 'success');
      }
    } catch (err) {
      CleanClaw.showToast('Error: ' + (err.message || 'Unknown error'), 'error');
    }
  },
};
