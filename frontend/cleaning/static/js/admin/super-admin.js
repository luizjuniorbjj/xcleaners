/**
 * Xcleaners — Super Admin Dashboard
 *
 * Platform-level admin panel for managing ALL businesses.
 * Role: super_admin
 * Route: /admin
 *
 * Backend endpoints:
 *   GET /api/v1/admin/businesses  — list all businesses + per-business stats
 *   GET /api/v1/admin/stats       — platform-wide KPIs
 */

window.AdminSuperAdmin = {
  _businesses: [],
  _stats: null,
  _expandedBiz: null,

  async render(container) {
    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading platform data…</span>
      </div>
    `;

    try {
      const [bizResp, statsResp] = await Promise.all([
        CleanAPI.get('/api/v1/admin/businesses'),
        CleanAPI.get('/api/v1/admin/stats'),
      ]);
      this._businesses = (bizResp && bizResp.items) || [];
      this._stats = statsResp || {};
    } catch (err) {
      container.innerHTML = `
        <div class="cc-card" style="margin:var(--cc-space-4);">
          <h2>Could not load platform data</h2>
          <p class="cc-text-sm cc-text-muted">${this._esc((err && err.detail) || String(err))}</p>
          <button class="cc-btn cc-btn-primary" onclick="AdminSuperAdmin.render(document.getElementById('content-view'))">Retry</button>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div class="cc-super-admin">
        <div class="cc-sa-kpis">
          <div class="cc-sa-kpi-card">
            <div class="cc-sa-kpi-value">${this._stats.total_businesses ?? 0}</div>
            <div class="cc-sa-kpi-label">Total Businesses</div>
          </div>
          <div class="cc-sa-kpi-card">
            <div class="cc-sa-kpi-value">${this._stats.active_users ?? 0}</div>
            <div class="cc-sa-kpi-label">Active Users</div>
          </div>
          <div class="cc-sa-kpi-card">
            <div class="cc-sa-kpi-value">${this._stats.active_cleaners ?? 0}</div>
            <div class="cc-sa-kpi-label">Active Cleaners</div>
          </div>
          <div class="cc-sa-kpi-card">
            <div class="cc-sa-kpi-value">${this._stats.bookings_last_30d ?? 0}</div>
            <div class="cc-sa-kpi-label">Bookings (30d)</div>
          </div>
          <div class="cc-sa-kpi-card">
            <div class="cc-sa-kpi-value">${this._stats.businesses_with_stripe ?? 0}</div>
            <div class="cc-sa-kpi-label">Stripe Connected</div>
          </div>
          <div class="cc-sa-kpi-card">
            <div class="cc-sa-kpi-value">${this._stats.total_clients ?? 0}</div>
            <div class="cc-sa-kpi-label">Total Clients</div>
          </div>
        </div>

        <div class="cc-sa-actions-bar">
          <h2 class="cc-text-xl" style="margin:0;">Businesses</h2>
          <button class="cc-btn cc-btn-primary" onclick="AdminSuperAdmin._notImplemented('Create Business')">
            + Create Business
          </button>
        </div>

        <div class="cc-card" style="overflow-x:auto;">
          <table class="cc-sa-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Owner Email</th>
                <th>Clients</th>
                <th>Cleaners</th>
                <th>Bookings</th>
                <th>Stripe</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody id="sa-businesses-tbody">
              ${this._renderRows()}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  _renderRows() {
    if (!this._businesses.length) {
      return '<tr><td colspan="8" style="text-align:center;padding:var(--cc-space-8);color:var(--cc-neutral-400);">No businesses yet.</td></tr>';
    }

    return this._businesses.map((b) => {
      const stripeBadge = b.stripe_charges_enabled
        ? '<span class="cc-badge cc-badge-success">Active</span>'
        : b.stripe_account_id
          ? '<span class="cc-badge cc-badge-warning">Pending</span>'
          : '<span class="cc-badge cc-badge-muted">None</span>';
      const statusText = b.status || 'active';
      const statusBadge = statusText === 'active' || !statusText || statusText === 'null'
        ? `<span class="cc-badge cc-badge-success">${this._esc(statusText || 'active')}</span>`
        : `<span class="cc-badge cc-badge-muted">${this._esc(statusText)}</span>`;

      return `
        <tr class="cc-sa-row" data-biz-id="${this._esc(b.id)}">
          <td>
            <strong>${this._esc(b.name || b.slug)}</strong>
            <span class="cc-text-xs cc-text-muted" style="display:block;">${this._esc(b.slug)}</span>
          </td>
          <td>${this._esc(b.owner_email || '—')}</td>
          <td style="text-align:center;">${b.clients_count ?? 0}</td>
          <td style="text-align:center;">${b.cleaners_count ?? 0}</td>
          <td style="text-align:center;">${b.bookings_completed ?? 0}<span class="cc-text-xs cc-text-muted"> / ${b.bookings_total ?? 0}</span></td>
          <td>${stripeBadge}</td>
          <td>${statusBadge}</td>
          <td class="cc-text-sm cc-text-muted">${this._fmtDate(b.created_at)}</td>
        </tr>
      `;
    }).join('');
  },

  _notImplemented(feature) {
    alert(`${feature}: in next sprint. For now use SQL direct on the database.`);
  },

  _esc(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  },

  _fmtDate(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch { return iso; }
  },
};
