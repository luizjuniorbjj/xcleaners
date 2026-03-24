/**
 * CleanClaw — Owner Bookings List Module
 *
 * ZenMaid-style "All Bookings" page: filterable list of ALL bookings.
 * Separate from the calendar view — table-based, searchable, tabbed.
 *
 * Route: #/owner/bookings
 * Global name: OwnerBookings (loaded by router from owner/bookings.js)
 */

window.OwnerBookings = {
  _container: null,
  _bookings: [],
  _allBookings: [],
  _currentTab: 'upcoming',
  _filters: { status: 'all', dateFrom: '', dateTo: '', search: '' },
  _sortCol: 'date',
  _sortAsc: true,

  // ----- Render -----

  async render(container) {
    this._container = container;

    container.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-top:var(--cc-space-3);">Loading bookings...</span>
      </div>
    `;

    try {
      // Use DemoData directly for bookings
      if (typeof DemoData !== 'undefined') {
        this._allBookings = DemoData._generateBookings().slice();
      } else {
        const resp = await CleanAPI.cleanGet('/bookings');
        this._allBookings = (resp && resp.bookings) ? resp.bookings : (Array.isArray(resp) ? resp : []);
      }
      this._applyFilters();
      this._renderPage();
    } catch (err) {
      container.innerHTML = `
        <div class="cc-empty-state">
          <div class="cc-empty-state-illustration">&#9888;</div>
          <div class="cc-empty-state-title">Could not load bookings</div>
          <div class="cc-empty-state-description">${err.detail || 'Something went wrong. Please try again.'}</div>
          <button class="cc-btn cc-btn-primary" onclick="OwnerBookings.render(OwnerBookings._container)">Retry</button>
        </div>
      `;
    }
  },

  _applyFilters() {
    const today = new Date().toISOString().split('T')[0];
    let list = this._allBookings.slice();

    // Status filter
    if (this._filters.status !== 'all') {
      list = list.filter(b => b.status === this._filters.status);
    }

    // Date from
    if (this._filters.dateFrom) {
      list = list.filter(b => b.scheduled_date >= this._filters.dateFrom);
    }

    // Date to
    if (this._filters.dateTo) {
      list = list.filter(b => b.scheduled_date <= this._filters.dateTo);
    }

    // Search (client name, service, address)
    if (this._filters.search) {
      const q = this._filters.search.toLowerCase();
      list = list.filter(b =>
        (b.client_name || '').toLowerCase().includes(q) ||
        (b.service || '').toLowerCase().includes(q) ||
        (b.address || '').toLowerCase().includes(q) ||
        (b.team_name || '').toLowerCase().includes(q)
      );
    }

    // Tab filter
    if (this._currentTab === 'upcoming') {
      list = list.filter(b => b.scheduled_date >= today && b.status !== 'cancelled');
    } else if (this._currentTab === 'past') {
      list = list.filter(b => b.scheduled_date < today || b.status === 'completed');
    } else if (this._currentTab === 'cancelled') {
      list = list.filter(b => b.status === 'cancelled');
    }

    // Sort
    list.sort((a, b) => {
      let va, vb;
      switch (this._sortCol) {
        case 'date': va = a.scheduled_date + a.scheduled_start; vb = b.scheduled_date + b.scheduled_start; break;
        case 'client': va = a.client_name || ''; vb = b.client_name || ''; break;
        case 'service': va = a.service || ''; vb = b.service || ''; break;
        case 'team': va = a.team_name || ''; vb = b.team_name || ''; break;
        case 'status': va = a.status || ''; vb = b.status || ''; break;
        default: va = a.scheduled_date; vb = b.scheduled_date;
      }
      const cmp = va < vb ? -1 : va > vb ? 1 : 0;
      return this._sortAsc ? cmp : -cmp;
    });

    this._bookings = list;
  },

  _getCounts() {
    const today = new Date().toISOString().split('T')[0];
    const all = this._allBookings;
    return {
      upcoming: all.filter(b => b.scheduled_date >= today && b.status !== 'cancelled').length,
      past: all.filter(b => b.scheduled_date < today || b.status === 'completed').length,
      cancelled: all.filter(b => b.status === 'cancelled').length,
    };
  },

  _renderPage() {
    const c = this._container;
    const counts = this._getCounts();

    c.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <!-- Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <h2 style="margin:0;">All Bookings</h2>
          <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="CleanRouter.navigate('#/owner/schedule')">
            + New Booking
          </button>
        </div>

        <!-- Filters Bar -->
        <div class="cc-card" style="padding:var(--cc-space-3);display:flex;flex-wrap:wrap;gap:var(--cc-space-3);align-items:flex-end;">
          <div class="cc-form-group" style="margin:0;min-width:140px;">
            <label class="cc-label cc-text-xs">Status</label>
            <select class="cc-select cc-select-sm" id="ob-filter-status" onchange="OwnerBookings._onFilterChange()">
              <option value="all"${this._filters.status === 'all' ? ' selected' : ''}>All Statuses</option>
              <option value="scheduled"${this._filters.status === 'scheduled' ? ' selected' : ''}>Scheduled</option>
              <option value="in_progress"${this._filters.status === 'in_progress' ? ' selected' : ''}>In Progress</option>
              <option value="completed"${this._filters.status === 'completed' ? ' selected' : ''}>Completed</option>
              <option value="cancelled"${this._filters.status === 'cancelled' ? ' selected' : ''}>Cancelled</option>
            </select>
          </div>
          <div class="cc-form-group" style="margin:0;min-width:140px;">
            <label class="cc-label cc-text-xs">Date From</label>
            <input type="date" class="cc-input cc-input-sm" id="ob-filter-from" value="${this._filters.dateFrom}" onchange="OwnerBookings._onFilterChange()">
          </div>
          <div class="cc-form-group" style="margin:0;min-width:140px;">
            <label class="cc-label cc-text-xs">Date To</label>
            <input type="date" class="cc-input cc-input-sm" id="ob-filter-to" value="${this._filters.dateTo}" onchange="OwnerBookings._onFilterChange()">
          </div>
          <div class="cc-form-group" style="margin:0;flex:1;min-width:180px;">
            <label class="cc-label cc-text-xs">Search</label>
            <input type="text" class="cc-input cc-input-sm" id="ob-filter-search" placeholder="Client, service, address..." value="${this._esc(this._filters.search)}" oninput="OwnerBookings._onFilterChange()">
          </div>
          <button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerBookings._clearFilters()" style="margin-bottom:2px;">Clear</button>
        </div>

        <!-- Tabs -->
        <div style="display:flex;gap:var(--cc-space-1);border-bottom:1px solid var(--cc-neutral-200);">
          ${['upcoming', 'past', 'cancelled'].map(tab => `
            <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="${tab}"
              style="border-bottom:2px solid ${this._currentTab === tab ? 'var(--cc-primary-500)' : 'transparent'};border-radius:0;${this._currentTab === tab ? 'color:var(--cc-primary-600);font-weight:var(--cc-font-semibold);' : ''}"
              onclick="OwnerBookings._switchTab('${tab}')">
              ${tab.charAt(0).toUpperCase() + tab.slice(1)} (${counts[tab]})
            </button>
          `).join('')}
        </div>

        <!-- Table -->
        ${this._bookings.length === 0 ? `
          <div class="cc-card" style="padding:var(--cc-space-8);text-align:center;">
            <p class="cc-text-muted">No bookings match your filters.</p>
          </div>
        ` : `
          <div class="cc-table-wrapper">
            <table class="cc-table">
              <thead>
                <tr>
                  ${this._renderSortHeader('date', 'Date')}
                  <th>Time</th>
                  ${this._renderSortHeader('client', 'Client')}
                  ${this._renderSortHeader('service', 'Service')}
                  ${this._renderSortHeader('team', 'Team')}
                  ${this._renderSortHeader('status', 'Status')}
                  <th style="text-align:right;">Actions</th>
                </tr>
              </thead>
              <tbody>
                ${this._bookings.map(b => this._renderRow(b)).join('')}
              </tbody>
            </table>
          </div>
        `}

        <!-- Modal container -->
        <div id="ob-modal-overlay" class="cc-modal-backdrop" onclick="OwnerBookings._closeModal(event)">
          <div class="cc-modal" style="max-width:560px;" onclick="event.stopPropagation()">
            <div id="ob-modal-content"></div>
          </div>
        </div>
      </div>
    `;
  },

  _renderSortHeader(col, label) {
    const isActive = this._sortCol === col;
    const arrow = isActive ? (this._sortAsc ? ' &#9650;' : ' &#9660;') : '';
    return `<th style="cursor:pointer;user-select:none;white-space:nowrap;" onclick="OwnerBookings._toggleSort('${col}')">${label}${arrow}</th>`;
  },

  _renderRow(b) {
    const dateObj = new Date(b.scheduled_date + 'T12:00:00');
    const dateStr = dateObj.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    const statusBadge = this._statusBadge(b.status);

    return `
      <tr style="cursor:pointer;" onclick="OwnerBookings._showDetail('${b.id}')">
        <td class="cc-text-sm cc-font-medium">${dateStr}</td>
        <td class="cc-text-sm">${b.scheduled_start} - ${b.scheduled_end}</td>
        <td>
          <div class="cc-text-sm cc-font-medium">${this._esc(b.client_name)}</div>
        </td>
        <td class="cc-text-sm">${this._esc(b.service)}</td>
        <td>
          <div style="display:flex;align-items:center;gap:var(--cc-space-1);">
            <span style="width:8px;height:8px;border-radius:50%;background:${b.team_color || 'var(--cc-neutral-300)'};flex-shrink:0;"></span>
            <span class="cc-text-sm">${this._esc(b.team_name)}</span>
          </div>
        </td>
        <td>${statusBadge}</td>
        <td style="text-align:right;">
          <div style="display:flex;gap:var(--cc-space-1);justify-content:flex-end;" onclick="event.stopPropagation();">
            ${b.status === 'scheduled' ? `
              <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger" onclick="OwnerBookings._cancelBooking('${b.id}')">Cancel</button>
            ` : ''}
            <button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerBookings._showDetail('${b.id}')">View</button>
          </div>
        </td>
      </tr>
    `;
  },

  _statusBadge(status) {
    const map = {
      scheduled: '<span class="cc-badge cc-badge-info cc-badge-sm">Scheduled</span>',
      in_progress: '<span class="cc-badge cc-badge-warning cc-badge-sm">In Progress</span>',
      completed: '<span class="cc-badge cc-badge-success cc-badge-sm">Completed</span>',
      cancelled: '<span class="cc-badge cc-badge-danger cc-badge-sm">Cancelled</span>',
    };
    return map[status] || `<span class="cc-badge cc-badge-neutral cc-badge-sm">${status}</span>`;
  },

  // ----- Filters & Sorting -----

  _onFilterChange() {
    this._filters.status = document.getElementById('ob-filter-status').value;
    this._filters.dateFrom = document.getElementById('ob-filter-from').value;
    this._filters.dateTo = document.getElementById('ob-filter-to').value;
    this._filters.search = document.getElementById('ob-filter-search').value;
    this._applyFilters();
    this._renderPage();
  },

  _clearFilters() {
    this._filters = { status: 'all', dateFrom: '', dateTo: '', search: '' };
    this._applyFilters();
    this._renderPage();
  },

  _switchTab(tab) {
    this._currentTab = tab;
    this._applyFilters();
    this._renderPage();
  },

  _toggleSort(col) {
    if (this._sortCol === col) {
      this._sortAsc = !this._sortAsc;
    } else {
      this._sortCol = col;
      this._sortAsc = true;
    }
    this._applyFilters();
    this._renderPage();
  },

  // ----- Booking Detail Modal -----

  _showDetail(bookingId) {
    const b = this._allBookings.find(x => x.id === bookingId);
    if (!b) return;

    const dateObj = new Date(b.scheduled_date + 'T12:00:00');
    const dateStr = dateObj.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    const modal = document.getElementById('ob-modal-content');

    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">Booking Detail</h3>
        <button class="cc-modal-close" onclick="OwnerBookings._closeModal()">&times;</button>
      </div>
      <div class="cc-modal-body" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <div class="cc-text-lg cc-font-semibold">${this._esc(b.client_name)}</div>
            <div class="cc-text-sm cc-text-muted">${this._esc(b.service)}</div>
          </div>
          ${this._statusBadge(b.status)}
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
          <div>
            <div class="cc-text-xs cc-text-muted">Date</div>
            <div class="cc-text-sm cc-font-medium">${dateStr}</div>
          </div>
          <div>
            <div class="cc-text-xs cc-text-muted">Time</div>
            <div class="cc-text-sm cc-font-medium">${b.scheduled_start} - ${b.scheduled_end}</div>
          </div>
          <div>
            <div class="cc-text-xs cc-text-muted">Team</div>
            <div class="cc-text-sm cc-font-medium" style="display:flex;align-items:center;gap:var(--cc-space-1);">
              <span style="width:8px;height:8px;border-radius:50%;background:${b.team_color || 'var(--cc-neutral-300)'};"></span>
              ${this._esc(b.team_name)}
            </div>
          </div>
          <div>
            <div class="cc-text-xs cc-text-muted">Address</div>
            <div class="cc-text-sm">${this._esc(b.address)}</div>
          </div>
        </div>

        ${b.notes ? `
          <div>
            <div class="cc-text-xs cc-text-muted">Notes</div>
            <div class="cc-text-sm">${this._esc(b.notes)}</div>
          </div>
        ` : ''}

        ${b.checkin_at ? `<div class="cc-text-xs cc-text-muted">Checked in: ${new Date(b.checkin_at).toLocaleString()}</div>` : ''}
        ${b.checkout_at ? `<div class="cc-text-xs cc-text-muted">Checked out: ${new Date(b.checkout_at).toLocaleString()}</div>` : ''}
      </div>
      <div class="cc-modal-footer">
        ${b.status === 'scheduled' ? `<button class="cc-btn cc-btn-danger cc-btn-sm" onclick="OwnerBookings._cancelBooking('${b.id}');OwnerBookings._closeModal();">Cancel Booking</button>` : ''}
        <button class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerBookings._closeModal()">Close</button>
      </div>
    `;

    document.getElementById('ob-modal-overlay').classList.add('cc-visible');
  },

  // ----- Actions -----

  async _cancelBooking(bookingId) {
    if (!confirm('Cancel this booking?')) return;
    try {
      await CleanAPI.cleanPatch(`/bookings/${bookingId}`, { status: 'cancelled' });
      // Also update local data
      const idx = this._allBookings.findIndex(b => b.id === bookingId);
      if (idx >= 0) this._allBookings[idx].status = 'cancelled';
      CleanClaw.showToast('Booking cancelled.', 'success');
      this._applyFilters();
      this._renderPage();
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Could not cancel booking.', 'error');
    }
  },

  // ----- Modal Helpers -----

  _closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const overlay = document.getElementById('ob-modal-overlay');
    if (overlay) overlay.classList.remove('cc-visible');
  },

  _esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  },
};
