/**
 * CleanClaw v3 -- Owner Client Manager Module (S2.3)
 *
 * Client list view with:
 * - Table with search, filters (frequency, status, team), pagination
 * - Client cards showing: name, address, frequency, preferred team, LTV, last service, payment status
 * - Add client modal (name, email, phone, address, property details)
 * - Bulk actions (send reminders, export)
 */
window.OwnerClientManager = {
  _page: 1,
  _perPage: 25,
  _total: 0,
  _search: '',
  _filters: { status: '', frequency: '', team_id: '', tag: '' },
  _sortBy: 'last_name',
  _sortOrder: 'asc',
  _selected: new Set(),
  _teams: [],
  _clients: [],

  async render(container, params) {
    this._container = container;
    this._page = 1;
    this._selected.clear();
    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading clients...</span>
      </div>
    `;
    await this._loadTeams();
    await this._loadAndRender();
  },

  async _loadTeams() {
    try {
      const slug = CleanAPI._slug;
      const resp = await CleanAPI.request('GET', `/api/v1/clean/${slug}/clients?per_page=1`);
      // Load teams for filter dropdown
      // Teams endpoint may exist from S2.2
      try {
        const tResp = await CleanAPI.request('GET', `/api/v1/clean/${slug}/teams`);
        this._teams = (tResp && tResp.teams) ? tResp.teams : (Array.isArray(tResp) ? tResp : []);
      } catch { this._teams = []; }
    } catch { /* ignore */ }
  },

  async _loadAndRender() {
    try {
      const slug = CleanAPI._slug;
      const qs = new URLSearchParams({
        page: this._page,
        per_page: this._perPage,
        sort_by: this._sortBy,
        sort_order: this._sortOrder,
      });
      if (this._search) qs.set('search', this._search);
      if (this._filters.status) qs.set('status', this._filters.status);
      if (this._filters.frequency) qs.set('frequency', this._filters.frequency);
      if (this._filters.team_id) qs.set('team_id', this._filters.team_id);
      if (this._filters.tag) qs.set('tag', this._filters.tag);

      const resp = await CleanAPI.request('GET', `/api/v1/clean/${slug}/clients?${qs.toString()}`);
      if (!resp || (typeof resp === 'object' && Object.keys(resp).length === 0)) {
        this._clients = [];
        this._total = 0;
        this._renderPage();
        return;
      }

      this._clients = Array.isArray(resp.clients) ? resp.clients : [];
      this._total = resp.total || 0;
      this._renderPage();
    } catch (e) {
      this._container.innerHTML = `
        <div class="cc-empty-state">
          <div class="cc-empty-state-illustration">&#9888;</div>
          <div class="cc-empty-state-title">Could not load clients</div>
          <div class="cc-empty-state-description">${e.detail || e.message || 'Unknown error'}</div>
          <button class="cc-btn cc-btn-primary" onclick="OwnerClientManager._loadAndRender()">Retry</button>
        </div>`;
    }
  },

  _renderPage() {
    const totalPages = Math.ceil(this._total / this._perPage) || 1;
    const isMobile = window.innerWidth < 768;

    this._container.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <!-- Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <div style="display:flex;align-items:baseline;gap:var(--cc-space-2);">
            <h2 style="margin:0;">Clients</h2>
            <span class="cc-badge cc-badge-neutral">${this._total}</span>
          </div>
          <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="OwnerClientManager._showAddModal()">+ Add Client</button>
        </div>

        <!-- Filters Bar -->
        <div class="cc-card" style="padding:var(--cc-space-3) var(--cc-space-4);display:flex;flex-wrap:wrap;align-items:center;gap:var(--cc-space-3);">
          <div style="flex:1;min-width:200px;">
            <input type="text" id="ccClientSearch" class="cc-input"
                   placeholder="Search name, phone, email, address..."
                   value="${this._escHtml(this._search)}"
                   oninput="OwnerClientManager._onSearchDebounced(this.value)"
                   style="height:36px;font-size:var(--cc-text-sm);">
          </div>
          <select id="ccFilterStatus" class="cc-select"
                  onchange="OwnerClientManager._onFilter('status', this.value)"
                  style="width:auto;min-width:120px;height:36px;font-size:var(--cc-text-sm);">
            <option value="">All Status</option>
            <option value="active" ${this._filters.status === 'active' ? 'selected' : ''}>Active</option>
            <option value="paused" ${this._filters.status === 'paused' ? 'selected' : ''}>Paused</option>
            <option value="former" ${this._filters.status === 'former' ? 'selected' : ''}>Former</option>
          </select>
          <select id="ccFilterFreq" class="cc-select"
                  onchange="OwnerClientManager._onFilter('frequency', this.value)"
                  style="width:auto;min-width:140px;height:36px;font-size:var(--cc-text-sm);">
            <option value="">All Frequencies</option>
            <option value="weekly" ${this._filters.frequency === 'weekly' ? 'selected' : ''}>Weekly</option>
            <option value="biweekly" ${this._filters.frequency === 'biweekly' ? 'selected' : ''}>Biweekly</option>
            <option value="monthly" ${this._filters.frequency === 'monthly' ? 'selected' : ''}>Monthly</option>
            <option value="sporadic" ${this._filters.frequency === 'sporadic' ? 'selected' : ''}>Sporadic</option>
          </select>
          ${this._teams.length ? `
          <select id="ccFilterTeam" class="cc-select"
                  onchange="OwnerClientManager._onFilter('team_id', this.value)"
                  style="width:auto;min-width:120px;height:36px;font-size:var(--cc-text-sm);">
            <option value="">All Teams</option>
            ${this._teams.map(t => `<option value="${t.id}" ${this._filters.team_id === t.id ? 'selected' : ''}>${this._escHtml(t.name)}</option>`).join('')}
          </select>` : ''}
        </div>

        <!-- Content -->
        ${isMobile ? this._renderCards() : this._renderTable()}

        <!-- Pagination -->
        ${this._total > this._perPage ? this._renderPagination(totalPages) : ''}

        <!-- Bulk Actions -->
        ${this._selected.size > 0 ? `
        <div style="position:fixed;bottom:calc(var(--cc-bottombar-height) + var(--cc-space-4));left:50%;transform:translateX(-50%);background:var(--cc-neutral-800);color:#fff;padding:var(--cc-space-3) var(--cc-space-5);border-radius:var(--cc-radius-lg);box-shadow:var(--cc-shadow-lg);display:flex;align-items:center;gap:var(--cc-space-3);z-index:var(--cc-z-toast);">
          <span class="cc-text-sm">Selected (${this._selected.size}):</span>
          <button class="cc-btn cc-btn-xs" style="background:rgba(255,255,255,0.2);color:#fff;border:1px solid rgba(255,255,255,0.3);" onclick="OwnerClientManager._exportSelected()">Export CSV</button>
        </div>` : ''}
      </div>
    `;
  },

  _renderTable() {
    if (!this._clients.length) {
      return `
        <div class="cc-card">
          <div class="cc-empty-state">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? (this._search || Object.values(this._filters).some(v => v) ? CleanClawIllustrations.search : CleanClawIllustrations.clients) : '&#128100;'}</div>
            <div class="cc-empty-state-title">${this._search || Object.values(this._filters).some(v => v) ? 'No results found' : 'No clients yet'}</div>
            <div class="cc-empty-state-description">${this._search || Object.values(this._filters).some(v => v) ? 'Try different keywords or check the spelling.' : 'Add your clients and their house details. They\'ll be able to see their bookings and pay online.'}</div>
          </div>
        </div>`;
    }

    const sortIcon = (col) => {
      const isActive = this._sortBy === col;
      const arrow = isActive
        ? (this._sortOrder === 'asc' ? '&#9650;' : '&#9660;')
        : '&#8693;'; // up-down arrow for inactive sortable columns
      const color = isActive ? 'color:var(--cc-primary-500);' : 'color:var(--cc-neutral-400);font-size:0.7em;';
      return ` <span style="${color}vertical-align:middle;">${arrow}</span>`;
    };

    return `
      <div class="cc-table-wrapper">
        <table class="cc-table">
          <thead>
            <tr>
              <th style="width:32px;"><input type="checkbox" onchange="OwnerClientManager._toggleAll(this.checked)"></th>
              <th style="cursor:pointer;user-select:none;" onclick="OwnerClientManager._onSort('last_name')">Client${sortIcon('last_name')}</th>
              <th>Frequency</th>
              <th>Team</th>
              <th style="cursor:pointer;user-select:none;text-align:right;" onclick="OwnerClientManager._onSort('lifetime_value')">LTV${sortIcon('lifetime_value')}</th>
              <th style="cursor:pointer;user-select:none;" onclick="OwnerClientManager._onSort('last_service_date')">Last Service${sortIcon('last_service_date')}</th>
              <th>Status</th>
              <th style="width:60px;text-align:center;">Actions</th>
            </tr>
          </thead>
          <tbody>
            ${this._clients.map(c => this._renderRow(c)).join('')}
          </tbody>
        </table>
      </div>
    `;
  },

  _renderRow(c) {
    const name = `${c.last_name || ''}, ${c.first_name}`.replace(/^, /, '');
    const addr = [c.address_line1, c.city].filter(Boolean).join(', ') || '--';
    const tags = (c.tags || []).map(t => `<span class="cc-tag cc-tag-primary" style="padding:1px var(--cc-space-2);font-size:10px;">${this._escHtml(t)}</span>`).join(' ');
    const checked = this._selected.has(c.id) ? 'checked' : '';

    const statusMap = {
      active: 'cc-badge-success',
      inactive: 'cc-badge-neutral',
      paused: 'cc-badge-warning',
      former: 'cc-badge-neutral',
    };
    const badgeClass = statusMap[c.status] || 'cc-badge-neutral';

    return `
      <tr style="cursor:pointer;" data-id="${c.id}">
        <td><input type="checkbox" ${checked} onchange="OwnerClientManager._toggleSelect('${c.id}', this.checked)" onclick="event.stopPropagation()"></td>
        <td onclick="OwnerClientManager._goToDetail('${c.id}')">
          <div style="display:flex;align-items:center;gap:var(--cc-space-3);">
            <div class="cc-avatar cc-avatar-sm" style="background:var(--cc-primary-100);color:var(--cc-primary-600);">
              ${(c.first_name || '?')[0]}${(c.last_name || '')[0] || ''}
            </div>
            <div>
              <div class="cc-text-sm cc-font-medium">${this._escHtml(name)}</div>
              <div class="cc-text-xs cc-text-muted cc-truncate" style="max-width:200px;">${this._escHtml(addr)}</div>
              ${tags ? `<div style="margin-top:2px;display:flex;gap:var(--cc-space-1);flex-wrap:wrap;">${tags}</div>` : ''}
            </div>
          </div>
        </td>
        <td class="cc-text-sm">${c.active_schedules_count > 0 ? (c.preferred_day || '--') : '--'}</td>
        <td class="cc-text-sm">--</td>
        <td class="cc-text-sm cc-text-right cc-font-medium">$${(c.lifetime_value || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})}</td>
        <td class="cc-text-sm">${c.last_service_date ? new Date(c.last_service_date).toLocaleDateString() : '--'}</td>
        <td><span class="cc-badge cc-badge-sm ${badgeClass}">${c.status}</span></td>
        <td style="text-align:center;" onclick="event.stopPropagation()">
          <button class="cc-btn cc-btn-xs cc-btn-outline" onclick="OwnerClientManager._goToDetail('${c.id}')" title="Edit client" style="padding:4px 8px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
        </td>
      </tr>
    `;
  },

  _renderCards() {
    if (!this._clients.length) {
      return `
        <div class="cc-card">
          <div class="cc-empty-state">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.clients : '&#128100;'}</div>
            <div class="cc-empty-state-title">No clients yet</div>
            <div class="cc-empty-state-description">Add your clients and their house details to get started.</div>
          </div>
        </div>`;
    }

    return `
      <div style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
        ${this._clients.map(c => {
          const name = `${c.first_name} ${c.last_name || ''}`.trim();
          const addr = [c.address_line1, c.city].filter(Boolean).join(', ') || '';
          const statusMap = { active: 'cc-badge-success', paused: 'cc-badge-warning', former: 'cc-badge-neutral' };
          const badgeClass = statusMap[c.status] || 'cc-badge-neutral';

          return `
            <div class="cc-card cc-card-interactive cc-client-card" onclick="OwnerClientManager._goToDetail('${c.id}')">
              <div class="cc-avatar cc-avatar-md" style="background:var(--cc-primary-100);color:var(--cc-primary-600);">
                ${(c.first_name || '?')[0]}${(c.last_name || '')[0] || ''}
              </div>
              <div class="cc-client-card-info">
                <div class="cc-client-card-name">${this._escHtml(name)}</div>
                ${addr ? `<div class="cc-client-card-detail">${this._escHtml(addr)}</div>` : ''}
                <div style="display:flex;gap:var(--cc-space-3);margin-top:var(--cc-space-1);" class="cc-text-xs cc-text-muted">
                  <span>LTV: $${(c.lifetime_value || 0).toLocaleString()}</span>
                  <span>Bookings: ${c.total_bookings || 0}</span>
                </div>
              </div>
              <div class="cc-client-card-actions" style="display:flex;flex-direction:column;align-items:flex-end;gap:var(--cc-space-2);">
                <span class="cc-badge cc-badge-sm ${badgeClass}">${c.status}</span>
                <button class="cc-btn cc-btn-xs cc-btn-outline" onclick="event.stopPropagation();OwnerClientManager._goToDetail('${c.id}')" style="padding:4px 8px;font-size:11px;">Edit</button>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  },

  _renderPagination(totalPages) {
    let pages = '';
    const start = Math.max(1, this._page - 2);
    const end = Math.min(totalPages, start + 4);
    for (let i = start; i <= end; i++) {
      pages += `<button class="cc-btn cc-btn-xs ${i === this._page ? 'cc-btn-primary' : 'cc-btn-secondary'}"
                        onclick="OwnerClientManager._goToPage(${i})">${i}</button>`;
    }
    return `
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-2);">
        <span class="cc-text-sm cc-text-muted">Showing ${(this._page - 1) * this._perPage + 1}-${Math.min(this._page * this._perPage, this._total)} of ${this._total}</span>
        <div style="display:flex;gap:var(--cc-space-1);">
          <button class="cc-btn cc-btn-xs cc-btn-secondary" ${this._page <= 1 ? 'disabled' : ''} onclick="OwnerClientManager._goToPage(${this._page - 1})">&lt;</button>
          ${pages}
          <button class="cc-btn cc-btn-xs cc-btn-secondary" ${this._page >= totalPages ? 'disabled' : ''} onclick="OwnerClientManager._goToPage(${this._page + 1})">&gt;</button>
        </div>
      </div>
    `;
  },

  // === INTERACTIONS ===

  _searchTimer: null,
  _onSearchDebounced(val) {
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this._search = val.trim();
      this._page = 1;
      this._loadAndRender();
    }, 300);
  },

  _onFilter(key, val) {
    this._filters[key] = val;
    this._page = 1;
    this._loadAndRender();
  },

  _onSort(col) {
    if (this._sortBy === col) {
      this._sortOrder = this._sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      this._sortBy = col;
      this._sortOrder = 'asc';
    }
    this._loadAndRender();
  },

  _goToPage(p) {
    this._page = p;
    this._loadAndRender();
  },

  _goToDetail(clientId) {
    window.location.hash = `#/owner/clients/${clientId}`;
  },

  _toggleAll(checked) {
    if (checked) {
      this._clients.forEach(c => this._selected.add(c.id));
    } else {
      this._selected.clear();
    }
    this._renderPage();
  },

  _toggleSelect(id, checked) {
    if (checked) this._selected.add(id);
    else this._selected.delete(id);
    this._renderPage();
  },

  _exportSelected() {
    const clients = this._clients.filter(c => this._selected.has(c.id));
    if (!clients.length) return;

    const headers = ['First Name', 'Last Name', 'Email', 'Phone', 'Address', 'City', 'State', 'Zip', 'Status', 'LTV'];
    const rows = clients.map(c => [
      c.first_name, c.last_name || '', c.email || '', c.phone || '',
      c.address_line1 || '', c.city || '', c.state || '', c.zip_code || '',
      c.status, c.lifetime_value || 0,
    ]);

    let csv = headers.join(',') + '\n';
    rows.forEach(r => {
      csv += r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',') + '\n';
    });

    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'clients-export.csv';
    a.click();
    URL.revokeObjectURL(a.href);
    if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(`${clients.length} clients exported to CSV.`, 'success');
  },

  // === ADD CLIENT MODAL ===

  _showAddModal() {
    const existing = document.getElementById('ccAddClientModal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'ccAddClientModal';
    modal.className = 'cc-modal-backdrop cc-visible';
    modal.innerHTML = `
      <div class="cc-modal" style="max-width:600px;">
        <div class="cc-modal-header">
          <h3 class="cc-modal-title">Add Client</h3>
          <button class="cc-modal-close" onclick="OwnerClientManager._closeAddModal()">&times;</button>
        </div>
        <form id="ccAddClientForm" onsubmit="OwnerClientManager._submitAddClient(event)">
          <div class="cc-modal-body" style="max-height:60vh;overflow-y:auto;">
            <!-- Contact Information -->
            <h5 style="margin:0 0 var(--cc-space-3);color:var(--cc-neutral-600);">Contact Information</h5>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
              <div class="cc-form-group">
                <label class="cc-label cc-label-required">First Name</label>
                <input type="text" name="first_name" required class="cc-input" placeholder="First name">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Last Name</label>
                <input type="text" name="last_name" class="cc-input" placeholder="Last name">
              </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
              <div class="cc-form-group">
                <label class="cc-label">Phone</label>
                <input type="tel" name="phone" class="cc-input" placeholder="(303) 555-1234">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Email</label>
                <input type="email" name="email" class="cc-input" placeholder="client@email.com">
              </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
              <div class="cc-form-group">
                <label class="cc-label">Preferred Contact</label>
                <select name="preferred_contact" class="cc-select">
                  <option value="">--</option>
                  <option value="phone">Phone</option>
                  <option value="email">Email</option>
                  <option value="text">Text</option>
                  <option value="whatsapp">WhatsApp</option>
                </select>
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Tags</label>
                <input type="text" name="tags" class="cc-input" placeholder="VIP, Weekly (comma-separated)">
              </div>
            </div>

            <!-- Property Address -->
            <h5 style="margin:var(--cc-space-4) 0 var(--cc-space-3);color:var(--cc-neutral-600);">Property Address</h5>
            <div class="cc-form-group">
              <label class="cc-label">Address</label>
              <input type="text" name="address_line1" class="cc-input" placeholder="1234 Oak Street">
            </div>
            <div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:var(--cc-space-3);">
              <div class="cc-form-group">
                <label class="cc-label">City</label>
                <input type="text" name="city" class="cc-input" placeholder="Denver">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">State</label>
                <input type="text" name="state" class="cc-input" placeholder="CO" maxlength="2">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Zip</label>
                <input type="text" name="zip_code" class="cc-input" placeholder="80202">
              </div>
            </div>

            <!-- Property Details (collapsible) -->
            <details style="margin-top:var(--cc-space-2);">
              <summary class="cc-text-sm cc-font-medium cc-text-primary" style="cursor:pointer;padding:var(--cc-space-2) 0;">Property Details (optional)</summary>
              <div style="padding-top:var(--cc-space-3);">
                <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:var(--cc-space-3);">
                  <div class="cc-form-group">
                    <label class="cc-label">Property Type</label>
                    <select name="property_type" class="cc-select">
                      <option value="">--</option>
                      <option value="house">House</option>
                      <option value="apartment">Apartment</option>
                      <option value="condo">Condo</option>
                      <option value="townhouse">Townhouse</option>
                      <option value="office">Office</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div class="cc-form-group">
                    <label class="cc-label">Bedrooms</label>
                    <input type="number" name="bedrooms" class="cc-input" min="0" placeholder="3">
                  </div>
                  <div class="cc-form-group">
                    <label class="cc-label">Bathrooms</label>
                    <input type="number" name="bathrooms" class="cc-input" min="0" step="0.5" placeholder="2.5">
                  </div>
                  <div class="cc-form-group">
                    <label class="cc-label">Sqft</label>
                    <input type="number" name="square_feet" class="cc-input" min="0" placeholder="2800">
                  </div>
                </div>
                <div class="cc-form-group">
                  <label class="cc-label">Access Instructions</label>
                  <textarea name="access_instructions" class="cc-textarea" rows="2" placeholder="Key under mat, alarm code 4521..."></textarea>
                </div>
                <div style="display:grid;grid-template-columns:auto 1fr;gap:var(--cc-space-3);align-items:center;">
                  <label class="cc-checkbox">
                    <input type="checkbox" name="has_pets" class="cc-checkbox-input">
                    <span class="cc-text-sm">Has Pets</span>
                  </label>
                  <div class="cc-form-group" style="margin-bottom:0;">
                    <input type="text" name="pet_details" class="cc-input" placeholder="Golden Retriever, friendly">
                  </div>
                </div>
                <div class="cc-form-group" style="margin-top:var(--cc-space-3);">
                  <label class="cc-label">Internal Notes</label>
                  <textarea name="notes" class="cc-textarea" rows="2" placeholder="Any notes about this client..."></textarea>
                </div>
              </div>
            </details>
          </div>

          <div class="cc-modal-footer">
            <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerClientManager._closeAddModal()">Cancel</button>
            <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm" id="ccAddClientBtn">Add Client</button>
          </div>
        </form>
      </div>
    `;
    document.body.appendChild(modal);
  },

  _closeAddModal() {
    const modal = document.getElementById('ccAddClientModal');
    if (modal) modal.remove();
  },

  async _submitAddClient(e) {
    e.preventDefault();
    const form = document.getElementById('ccAddClientForm');
    const btn = document.getElementById('ccAddClientBtn');
    btn.disabled = true;
    btn.textContent = 'Adding...';

    const fd = new FormData(form);
    const data = {};

    for (const [key, val] of fd.entries()) {
      if (key === 'has_pets') {
        data[key] = true;
        continue;
      }
      if (key === 'tags') {
        data[key] = val ? val.split(',').map(t => t.trim()).filter(Boolean) : [];
        continue;
      }
      if (key === 'bedrooms' || key === 'square_feet') {
        if (val) data[key] = parseInt(val, 10);
        continue;
      }
      if (key === 'bathrooms') {
        if (val) data[key] = parseFloat(val);
        continue;
      }
      if (val) data[key] = val;
    }

    if (!fd.has('has_pets')) data['has_pets'] = false;

    try {
      const slug = CleanAPI._slug;
      const resp = await CleanAPI.request('POST', `/api/v1/clean/${slug}/clients`, data);

      // Note: In demo mode, DemoData.handleWrite already adds the client to _clients
      // and emits a dataChanged event. No need to duplicate that here.

      if (resp || CleanClaw._user?.id?.startsWith('demo-')) {
        this._closeAddModal();
        if (typeof CleanClaw !== 'undefined') CleanClaw.showToast('Client added. They can now sign in to see their bookings.', 'success');
        this._page = 1;
        await this._loadAndRender();
      }
    } catch (err) {
      if (err.status === 409) {
        const detail = typeof err.detail === 'string' ? err.detail : (err.detail?.message || 'Duplicate client detected');
        if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(detail, 'warning');
      } else if (err.status === 403) {
        if (typeof CleanClaw !== 'undefined') CleanClaw.showToast('You\'ve reached the client limit on your current plan. Upgrade to add more clients.', 'warning');
      } else {
        if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(err.detail || 'Could not add client. Please check the details and try again.', 'error');
      }
    } finally {
      btn.disabled = false;
      btn.textContent = 'Add Client';
    }
  },

  _escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },
};
