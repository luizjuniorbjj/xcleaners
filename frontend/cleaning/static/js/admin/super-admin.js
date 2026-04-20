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
          <button class="cc-btn cc-btn-primary" onclick="AdminSuperAdmin._openCreateModal()">
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

        <!-- Create Business Modal -->
        <div class="cc-modal-backdrop" id="sa-create-modal" onclick="AdminSuperAdmin._closeCreateModal(event)">
          <div class="cc-modal" style="max-width:520px;" onclick="event.stopPropagation()">
            <div class="cc-modal-header">
              <h3 style="margin:0;">Create Business</h3>
              <button class="cc-modal-close" onclick="AdminSuperAdmin._hideCreateModal()" type="button">&times;</button>
            </div>
            <form id="sa-create-form" onsubmit="return AdminSuperAdmin._handleCreateBusiness(event)">
              <div class="cc-modal-body" style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
                <div>
                  <label class="cc-label">Business Name *</label>
                  <input type="text" class="cc-input" id="sa-biz-name" required minlength="2" maxlength="100" placeholder="e.g. Sparkle Miami">
                </div>
                <div>
                  <label class="cc-label">Owner Email *</label>
                  <input type="email" class="cc-input" id="sa-biz-email" required placeholder="owner@example.com">
                </div>
                <div>
                  <label class="cc-label">Owner Password *</label>
                  <input type="password" class="cc-input" id="sa-biz-password" required minlength="6" placeholder="Min 6 characters (ignored if email already exists)">
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
                  <div>
                    <label class="cc-label">Plan</label>
                    <select class="cc-input" id="sa-biz-plan">
                      <option value="basic" selected>Basic</option>
                      <option value="intermediate">Intermediate</option>
                      <option value="maximum">Maximum</option>
                    </select>
                  </div>
                  <div>
                    <label class="cc-label">Status</label>
                    <select class="cc-input" id="sa-biz-status">
                      <option value="active" selected>Active</option>
                      <option value="trial">Trial</option>
                    </select>
                  </div>
                </div>
                <div style="display:grid;grid-template-columns:2fr 1fr;gap:var(--cc-space-3);">
                  <div>
                    <label class="cc-label">City</label>
                    <input type="text" class="cc-input" id="sa-biz-city" maxlength="100" placeholder="New York">
                  </div>
                  <div>
                    <label class="cc-label">State</label>
                    <input type="text" class="cc-input" id="sa-biz-state" maxlength="2" placeholder="NY" style="text-transform:uppercase;">
                  </div>
                </div>
                <div id="sa-create-error" style="display:none;color:var(--cc-danger, #d33);font-size:0.875rem;"></div>
              </div>
              <div class="cc-modal-footer" style="display:flex;gap:var(--cc-space-3);justify-content:flex-end;">
                <button type="button" class="cc-btn cc-btn-secondary" onclick="AdminSuperAdmin._hideCreateModal()">Cancel</button>
                <button type="submit" class="cc-btn cc-btn-primary" id="sa-create-submit">Create</button>
              </div>
            </form>
          </div>
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

  // ----- Create Business Modal -----

  _openCreateModal() {
    const modal = document.getElementById('sa-create-modal');
    if (modal) {
      modal.classList.add('cc-visible');
      const nameInput = document.getElementById('sa-biz-name');
      if (nameInput) setTimeout(() => nameInput.focus(), 50);
    }
  },

  _hideCreateModal() {
    const modal = document.getElementById('sa-create-modal');
    if (modal) modal.classList.remove('cc-visible');
    const form = document.getElementById('sa-create-form');
    if (form) form.reset();
    const err = document.getElementById('sa-create-error');
    if (err) { err.style.display = 'none'; err.textContent = ''; }
  },

  _closeCreateModal(event) {
    // Triggered by backdrop click only (event stopped on modal body)
    if (event && event.target && event.target.id === 'sa-create-modal') {
      this._hideCreateModal();
    }
  },

  async _handleCreateBusiness(event) {
    event.preventDefault();
    const submitBtn = document.getElementById('sa-create-submit');
    const errEl = document.getElementById('sa-create-error');
    if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }

    const payload = {
      name: document.getElementById('sa-biz-name').value.trim(),
      owner_email: document.getElementById('sa-biz-email').value.trim(),
      owner_password: document.getElementById('sa-biz-password').value,
      plan: document.getElementById('sa-biz-plan').value,
      status: document.getElementById('sa-biz-status').value,
      city: document.getElementById('sa-biz-city').value.trim() || undefined,
      state: (document.getElementById('sa-biz-state').value.trim() || '').toUpperCase() || undefined,
    };

    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Creating…'; }
    try {
      const token = (window.CleanAuth && CleanAuth.getToken && CleanAuth.getToken()) || localStorage.getItem('token') || '';
      const resp = await fetch('/api/v1/admin/businesses', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try { const j = await resp.json(); msg = j.detail || j.message || msg; } catch (_) {}
        throw new Error(msg);
      }
      this._hideCreateModal();
      // Reload businesses list so the new row shows up with real stats
      if (typeof this.render === 'function' && this._container) {
        await this.render(this._container);
      } else if (typeof window.location !== 'undefined') {
        window.location.reload();
      }
    } catch (err) {
      if (errEl) {
        errEl.style.display = 'block';
        errEl.textContent = err.message || 'Failed to create business.';
      }
    } finally {
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Create'; }
    }
    return false;
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
