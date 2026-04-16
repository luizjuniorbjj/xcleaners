/**
 * Xcleaners — Owner Payroll Manager Module (Sprint D Track B)
 *
 * Lists cleaner earnings (pending + paid) with filters and bulk mark-as-paid.
 * Route: #/owner/payroll
 * Global: OwnerPayrollManager
 *
 * Endpoints:
 *   GET  /payroll/earnings?cleaner_id&status&from_date&to_date
 *   GET  /payroll/summary?from_date&to_date
 *   POST /payroll/mark-paid   { earnings_ids[], payout_ref }
 *
 * Graceful 404 fallback when endpoints pending (matches other managers' pattern).
 */

window.OwnerPayrollManager = {
  _container: null,
  _summary: [],
  _earnings: [],
  _selected: new Set(),
  _filter: { status: 'pending', from_date: '', to_date: '', cleaner_id: '' },

  async render(container) {
    this._container = container;
    this._selected.clear();

    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading payroll…</span>
      </div>
    `;

    await this._reload();
  },

  async _reload() {
    const [sumResp, earnResp] = await Promise.all([
      this._safeGet(this._buildQS('/payroll/summary', ['from_date', 'to_date'])),
      this._safeGet(this._buildQS('/payroll/earnings', ['status', 'from_date', 'to_date', 'cleaner_id'])),
    ]);
    this._summary = this._unwrap(sumResp, 'items');
    this._earnings = this._unwrap(earnResp, 'items');
    this._renderPage();
  },

  _buildQS(base, keys) {
    const qs = keys
      .map((k) => (this._filter[k] ? `${k}=${encodeURIComponent(this._filter[k])}` : null))
      .filter(Boolean)
      .join('&');
    return qs ? `${base}?${qs}` : base;
  },

  async _safeGet(endpoint) {
    try {
      return await CleanAPI.cleanGet(endpoint);
    } catch (err) {
      if (err && (err.status === 404 || err.status === 405)) {
        return { __pending: true, __endpoint: endpoint };
      }
      return { __error: true, __detail: err && err.detail };
    }
  },

  _unwrap(resp, key) {
    if (!resp || resp.__pending || resp.__error) return [];
    if (Array.isArray(resp)) return resp;
    if (resp[key] && Array.isArray(resp[key])) return resp[key];
    return [];
  },

  _fmt(v) {
    if (v === null || v === undefined || v === '') return '$—';
    const n = parseFloat(v);
    if (Number.isNaN(n)) return '$—';
    const sign = n < 0 ? '-' : '';
    return `${sign}$${Math.abs(n).toFixed(2)}`;
  },

  _escape(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  },

  _renderPage() {
    const total = this._summary.reduce((a, r) => a + parseFloat(r.net_total || 0), 0);
    const pending = this._summary.reduce((a, r) => a + parseFloat(r.pending_net || 0), 0);
    const paid = this._summary.reduce((a, r) => a + parseFloat(r.paid_net || 0), 0);

    const selectedCount = this._selected.size;
    const selectedSum = [...this._selected].reduce((a, id) => {
      const row = this._earnings.find((e) => e.id === id);
      return a + (row ? parseFloat(row.net_amount || 0) : 0);
    }, 0);

    this._container.innerHTML = `
      <div class="cc-stack" style="gap:var(--cc-space-6);">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:var(--cc-space-3);">
          <h1 class="cc-text-2xl" style="margin:0;">Payroll</h1>
          <div class="cc-stack cc-stack-horizontal" style="gap:var(--cc-space-2);">
            <input type="date" id="payroll-from" value="${this._escape(this._filter.from_date)}" class="cc-input" style="max-width:160px;" placeholder="From">
            <input type="date" id="payroll-to" value="${this._escape(this._filter.to_date)}" class="cc-input" style="max-width:160px;" placeholder="To">
            <select id="payroll-status" class="cc-input" style="max-width:140px;">
              <option value="">All</option>
              <option value="pending" ${this._filter.status === 'pending' ? 'selected' : ''}>Pending</option>
              <option value="paid" ${this._filter.status === 'paid' ? 'selected' : ''}>Paid</option>
              <option value="void" ${this._filter.status === 'void' ? 'selected' : ''}>Void</option>
            </select>
            <button id="payroll-apply" class="cc-btn cc-btn-secondary">Apply</button>
          </div>
        </div>

        <div class="cc-grid" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:var(--cc-space-4);">
          <div class="cc-card"><div class="cc-text-sm cc-text-muted">Total net</div><div class="cc-text-xl" style="margin-top:var(--cc-space-1);">${this._fmt(total)}</div></div>
          <div class="cc-card"><div class="cc-text-sm cc-text-muted">Pending</div><div class="cc-text-xl" style="margin-top:var(--cc-space-1);color:var(--cc-color-warning,#b45309);">${this._fmt(pending)}</div></div>
          <div class="cc-card"><div class="cc-text-sm cc-text-muted">Paid</div><div class="cc-text-xl" style="margin-top:var(--cc-space-1);color:var(--cc-color-success,#15803d);">${this._fmt(paid)}</div></div>
        </div>

        <div class="cc-card">
          <h2 class="cc-text-lg" style="margin:0 0 var(--cc-space-3) 0;">By cleaner</h2>
          ${this._renderSummaryTable()}
        </div>

        <div class="cc-card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--cc-space-3);">
            <h2 class="cc-text-lg" style="margin:0;">Earnings</h2>
            <div class="cc-stack cc-stack-horizontal" style="gap:var(--cc-space-2);align-items:center;">
              <span class="cc-text-sm cc-text-muted">${selectedCount} selected · ${this._fmt(selectedSum)}</span>
              <button id="payroll-mark-paid" class="cc-btn cc-btn-primary" ${selectedCount === 0 ? 'disabled' : ''}>Mark as paid…</button>
            </div>
          </div>
          ${this._renderEarningsTable()}
        </div>
      </div>
    `;

    this._wireEvents();
  },

  _renderSummaryTable() {
    if (!this._summary.length) {
      return `<div class="cc-text-sm cc-text-muted" style="padding:var(--cc-space-3);">No earnings in this period.</div>`;
    }
    const rows = this._summary.map((r) => `
      <tr>
        <td>${this._escape(r.cleaner_name || r.cleaner_id)}</td>
        <td style="text-align:right;">${r.bookings_count}</td>
        <td style="text-align:right;">${this._fmt(r.gross_total)}</td>
        <td style="text-align:right;"><strong>${this._fmt(r.net_total)}</strong></td>
        <td style="text-align:right;color:var(--cc-color-warning,#b45309);">${this._fmt(r.pending_net)}</td>
        <td style="text-align:right;color:var(--cc-color-success,#15803d);">${this._fmt(r.paid_net)}</td>
      </tr>
    `).join('');
    return `
      <table class="cc-table" style="width:100%;">
        <thead><tr>
          <th>Cleaner</th><th style="text-align:right;">Bookings</th>
          <th style="text-align:right;">Gross</th><th style="text-align:right;">Net</th>
          <th style="text-align:right;">Pending</th><th style="text-align:right;">Paid</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  },

  _renderEarningsTable() {
    if (!this._earnings.length) {
      return `<div class="cc-text-sm cc-text-muted" style="padding:var(--cc-space-3);">No earnings match the filters.</div>`;
    }
    const rows = this._earnings.map((e) => {
      const canSelect = e.status === 'pending';
      const checked = this._selected.has(e.id) ? 'checked' : '';
      const statusBadge = {
        pending: '<span class="cc-badge cc-badge-warning">Pending</span>',
        paid: '<span class="cc-badge cc-badge-success">Paid</span>',
        void: '<span class="cc-badge cc-badge-muted">Void</span>',
      }[e.status] || e.status;
      const date = e.scheduled_date ? new Date(e.scheduled_date).toISOString().slice(0, 10) : '—';
      return `
        <tr>
          <td><input type="checkbox" class="payroll-check" data-id="${e.id}" ${checked} ${canSelect ? '' : 'disabled'}></td>
          <td>${date}</td>
          <td>${this._escape(e.cleaner_name || e.cleaner_id)}</td>
          <td style="text-align:right;">${this._fmt(e.gross_amount)}</td>
          <td style="text-align:right;">${parseFloat(e.commission_pct).toFixed(0)}%</td>
          <td style="text-align:right;"><strong>${this._fmt(e.net_amount)}</strong></td>
          <td>${statusBadge}</td>
          <td class="cc-text-sm cc-text-muted" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${this._escape(e.payout_ref || '')}">${this._escape(e.payout_ref || '')}</td>
        </tr>
      `;
    }).join('');
    return `
      <table class="cc-table" style="width:100%;">
        <thead><tr>
          <th style="width:32px;"></th><th>Date</th><th>Cleaner</th>
          <th style="text-align:right;">Gross</th><th style="text-align:right;">Commission</th>
          <th style="text-align:right;">Net</th><th>Status</th><th>Payout ref</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  },

  _wireEvents() {
    document.getElementById('payroll-apply')?.addEventListener('click', () => {
      this._filter.from_date = document.getElementById('payroll-from').value || '';
      this._filter.to_date = document.getElementById('payroll-to').value || '';
      this._filter.status = document.getElementById('payroll-status').value || '';
      this._selected.clear();
      this._reload();
    });

    this._container.querySelectorAll('.payroll-check').forEach((cb) => {
      cb.addEventListener('change', (e) => {
        const id = e.target.dataset.id;
        if (e.target.checked) this._selected.add(id);
        else this._selected.delete(id);
        this._renderPage();
      });
    });

    document.getElementById('payroll-mark-paid')?.addEventListener('click', () => this._promptMarkPaid());
  },

  async _promptMarkPaid() {
    if (!this._selected.size) return;
    const ref = window.prompt('Enter payout reference (check #, Stripe transfer id, Zelle confirm, etc.):');
    if (ref === null) return;
    if (!ref.trim()) {
      alert('Payout reference is required.');
      return;
    }
    try {
      const result = await CleanAPI.cleanPost('/payroll/mark-paid', {
        earnings_ids: [...this._selected],
        payout_ref: ref.trim(),
      });
      alert(`Updated: ${result.updated} · Skipped (already paid): ${result.skipped_already_paid}`);
      this._selected.clear();
      this._reload();
    } catch (err) {
      alert(`Failed: ${(err && err.detail) || err}`);
    }
  },
};
