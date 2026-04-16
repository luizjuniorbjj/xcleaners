/**
 * Xcleaners — Owner Sales Taxes Manager Module (Story 1.1 Task 5b)
 *
 * CRUD for cleaning_sales_taxes with TEMPORAL semantics: changing tax
 * rate creates a NEW row with new effective_date (old row preserved
 * for historical bookings — F-001 correctness depends on this).
 *
 * Route: #/owner/taxes
 * Global: OwnerTaxesManager
 *
 * Endpoints (per docs/ux/story-1.1-ui-specs.md §7.5):
 *   GET    /locations                                (service areas)
 *   GET    /pricing/taxes?location_id={id}&include_archived=false
 *   POST   /pricing/taxes
 *   PATCH  /pricing/taxes/{id}      (archive via {is_archived:true}; edit only if 0 uses)
 *
 * Graceful 404 fallback when endpoints pending (Smith A2).
 */

window.OwnerTaxesManager = {
  _container: null,
  _locations: [],
  _taxes: [],                  // rates for the currently selected location
  _selectedLocationId: null,

  async render(container) {
    this._container = container;

    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading taxes…</span>
      </div>
    `;

    const locResp = await this._safeGet('/locations');
    this._locations = this._unwrap(locResp, 'locations');
    if (Array.isArray(this._locations) && this._locations.length > 0 && !this._selectedLocationId) {
      this._selectedLocationId = this._locations[0].id;
    }
    if (this._selectedLocationId) {
      await this._loadTaxes(this._selectedLocationId);
    } else {
      this._taxes = [];
      this._renderPage();
    }
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
    if (!resp || resp.__pending || resp.__error) return resp || [];
    if (Array.isArray(resp)) return resp;
    if (resp[key] && Array.isArray(resp[key])) return resp[key];
    return [];
  },

  async _loadTaxes(locationId) {
    const resp = await this._safeGet(`/pricing/taxes?location_id=${locationId}&include_archived=false`);
    this._taxes = this._unwrap(resp, 'taxes');
    this._renderPage();
  },

  _renderPage() {
    const locationsPending = this._locations && this._locations.__pending;
    const taxesPending = this._taxes && this._taxes.__pending;
    const locations = Array.isArray(this._locations) ? this._locations : [];
    const taxes = Array.isArray(this._taxes) ? this._taxes : [];

    // Identify "current" tax (most recent effective_date <= today, not archived)
    const today = new Date().toISOString().split('T')[0];
    const sorted = [...taxes].sort((a, b) => (b.effective_date || '').localeCompare(a.effective_date || ''));
    const currentId = sorted.find(t => !t.is_archived && (t.effective_date || '') <= today)?.id || null;

    // Identify locations without ANY tax config (UX hint card)
    const locationsWithoutTax = locations.filter(l => {
      if (l.id === this._selectedLocationId) return false;  // only known from loaded taxes
      return false;  // stub — requires aggregate data from backend; optional enhancement
    });

    this._container.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <h2 style="margin:0;">Sales Taxes</h2>
          ${!locationsPending && this._selectedLocationId ? `
            <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="OwnerTaxesManager._showCreateModal()">+ Add Rate</button>
          ` : ''}
        </div>

        ${locationsPending ? this._renderPendingNotice('/locations') : ''}
        ${!locationsPending && locations.length === 0 ? `
          <div class="cc-card">
            <div class="cc-text-sm cc-text-muted" style="padding:var(--cc-space-4);text-align:center;">
              No locations configured. Tax rates are per-location.
            </div>
          </div>
        ` : ''}

        ${!locationsPending && locations.length > 0 ? `
          <div class="cc-card" style="padding:var(--cc-space-3);">
            <div class="cc-form-group" style="margin:0;">
              <label class="cc-label">Location</label>
              <select class="cc-select" onchange="OwnerTaxesManager._selectLocation(this.value)">
                ${locations.map(l => `<option value="${l.id}" ${l.id === this._selectedLocationId ? 'selected' : ''}>${this._esc(l.name || l.id)}</option>`).join('')}
              </select>
            </div>
          </div>

          ${taxesPending ? this._renderPendingNotice('/pricing/taxes') : this._renderTimeline(sorted, currentId, today)}
        ` : ''}

        <div id="otm-modal-overlay" class="cc-modal-backdrop" onclick="OwnerTaxesManager._closeModal(event)">
          <div class="cc-modal" style="max-width:480px;" onclick="event.stopPropagation()">
            <div id="otm-modal-content"></div>
          </div>
        </div>
      </div>
    `;
  },

  _renderPendingNotice(endpoint) {
    return `
      <div class="cc-card" style="background:var(--cc-info-50);border-left:4px solid var(--cc-info-500);">
        <div style="display:flex;gap:var(--cc-space-3);">
          <div style="font-size:1.5rem;">ℹ</div>
          <div>
            <div style="font-weight:600;">Endpoint pending</div>
            <div class="cc-text-sm cc-text-muted"><code>${this._esc(endpoint)}</code> ships with Story 1.1 Task 5 backend.</div>
          </div>
        </div>
      </div>
    `;
  },

  _renderTimeline(sortedTaxes, currentId, today) {
    if (sortedTaxes.length === 0) {
      return `
        <div class="cc-card">
          <div class="cc-empty-state">
            <div class="cc-empty-state-title">No tax rates for this location</div>
            <div class="cc-empty-state-description">Bookings here default to 0% tax until a rate is configured.</div>
            <button class="cc-btn cc-btn-primary" onclick="OwnerTaxesManager._showCreateModal()">+ Add First Rate</button>
          </div>
        </div>
      `;
    }

    return `
      <div>
        <h3 style="margin:0 0 var(--cc-space-3);">Rate History (newest first)</h3>
        <div style="display:grid;gap:var(--cc-space-3);">
          ${sortedTaxes.map((t, idx) => this._renderTaxRow(t, idx, sortedTaxes, currentId, today)).join('')}
        </div>
      </div>
    `;
  },

  _renderTaxRow(t, idx, all, currentId, today) {
    const isCurrent = t.id === currentId;
    const pct = t.tax_pct != null ? `${Number(t.tax_pct).toFixed(2)}%` : '—%';
    const effective = t.effective_date || '—';
    // Range end: one day before next newer row's effective_date, else "current"
    const nextRow = all[idx - 1];  // array is sorted desc
    const rangeEnd = nextRow && nextRow.effective_date
      ? this._dayBefore(nextRow.effective_date)
      : (isCurrent ? 'current' : '—');
    const usage = t.usage_count != null ? t.usage_count : null;
    const canEdit = usage === 0 || usage == null;

    return `
      <div class="cc-card" style="border-left:4px solid ${isCurrent ? 'var(--cc-success-500)' : 'var(--cc-neutral-300)'};">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:var(--cc-space-3);">
          <div style="flex:1;min-width:200px;">
            <div style="display:flex;align-items:baseline;gap:var(--cc-space-2);">
              <span style="font-size:var(--cc-text-xl);font-weight:700;color:${isCurrent ? 'var(--cc-success-600)' : 'var(--cc-neutral-700)'};">${pct}</span>
              ${isCurrent ? `<span class="cc-badge cc-badge-success cc-badge-sm">current</span>` : ''}
            </div>
            <div class="cc-text-sm cc-text-muted" style="margin-top:var(--cc-space-1);">
              effective <strong>${effective}</strong> — <strong>${rangeEnd}</strong>
            </div>
            ${usage != null ? `<div class="cc-text-xs cc-text-muted" style="margin-top:var(--cc-space-1);">Used in ${usage} booking${usage !== 1 ? 's' : ''}</div>` : ''}
            ${t.created_by_name ? `<div class="cc-text-xs cc-text-muted">Added by ${this._esc(t.created_by_name)}${t.created_at ? ' · ' + new Date(t.created_at).toLocaleDateString() : ''}</div>` : ''}
          </div>
          <div style="display:flex;gap:var(--cc-space-2);">
            ${canEdit ? `<button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerTaxesManager._showEditModal('${t.id}')">Edit</button>` : `
              <span class="cc-text-xs cc-text-muted" style="align-self:center;" title="Cannot edit — referenced by ${usage} bookings. Archive + add new rate instead.">read-only</span>
            `}
            <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger" onclick="OwnerTaxesManager._archive('${t.id}')">Archive</button>
          </div>
        </div>
      </div>
    `;
  },

  _dayBefore(isoDate) {
    try {
      const d = new Date(isoDate + 'T00:00:00Z');
      d.setUTCDate(d.getUTCDate() - 1);
      return d.toISOString().split('T')[0];
    } catch { return isoDate; }
  },

  async _selectLocation(locationId) {
    this._selectedLocationId = locationId;
    await this._loadTaxes(locationId);
  },

  async _archive(id) {
    if (!confirm('Archive this tax rate? Historical bookings keep their snapshot; new bookings will use the rate effective on their scheduled_date.')) return;
    try {
      await CleanAPI.cleanPatch(`/pricing/taxes/${id}`, { is_archived: true });
      Xcleaners.showToast('Tax rate archived.', 'success');
      await this._loadTaxes(this._selectedLocationId);
    } catch (err) {
      if (err && err.status === 404) {
        Xcleaners.showToast('Endpoint pending.', 'warning');
      } else {
        Xcleaners.showToast(err.detail || 'Could not archive.', 'error');
      }
    }
  },

  _showCreateModal() {
    this._renderFormModal({});
  },

  _showEditModal(id) {
    const t = this._taxes.find(x => x.id === id);
    if (!t) return;
    this._renderFormModal(t, true);
  },

  _renderFormModal(data, isEdit = false) {
    const modal = document.getElementById('otm-modal-content');
    const todayISO = new Date().toISOString().split('T')[0];
    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">${isEdit ? 'Edit Rate' : 'Add Sales Tax Rate'}</h3>
        <button class="cc-modal-close" onclick="OwnerTaxesManager._closeModal()">&times;</button>
      </div>
      <form id="otm-form" onsubmit="OwnerTaxesManager._save(event, '${isEdit && data.id ? data.id : ''}')">
        <div class="cc-modal-body">
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Tax rate (%)</label>
            <input type="number" name="tax_pct" value="${data.tax_pct != null ? data.tax_pct : ''}" min="0" max="100" step="0.01" required class="cc-input">
          </div>
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Effective date</label>
            <input type="date" name="effective_date" value="${data.effective_date || todayISO}" required class="cc-input">
          </div>
          ${!isEdit ? `
            <div role="alert" style="padding:var(--cc-space-3);background:var(--cc-warning-50);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);color:var(--cc-warning-800);">
              ⚠ Changing the tax rate CREATES A NEW ROW with this effective date. Previous rates stay for bookings scheduled before this date (F-001 historical correctness). If a later rate exists, archive it first to supersede.
            </div>
          ` : ''}
          <div id="otm-form-error" style="display:none;padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);"></div>
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerTaxesManager._closeModal()">Cancel</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm" id="otm-save-btn">${isEdit ? 'Save Changes' : 'Create Rate'}</button>
        </div>
      </form>
    `;
    document.getElementById('otm-modal-overlay').classList.add('cc-visible');
  },

  async _save(e, editId) {
    e.preventDefault();
    const form = document.getElementById('otm-form');
    const btn = document.getElementById('otm-save-btn');
    const errEl = document.getElementById('otm-form-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Saving…';

    const fd = new FormData(form);
    const body = {
      location_id: this._selectedLocationId,
      tax_pct: Number(fd.get('tax_pct')),
      effective_date: fd.get('effective_date'),
    };

    try {
      if (editId) {
        await CleanAPI.cleanPatch(`/pricing/taxes/${editId}`, {
          tax_pct: body.tax_pct,
          effective_date: body.effective_date,
        });
      } else {
        await CleanAPI.cleanPost('/pricing/taxes', body);
      }
      Xcleaners.showToast('Tax rate saved.', 'success');
      this._closeModal();
      await this._loadTaxes(this._selectedLocationId);
    } catch (err) {
      if (err && (err.status === 404 || err.status === 405)) {
        errEl.textContent = 'Endpoint /pricing/taxes not yet implemented.';
      } else if (err && err.status === 409) {
        errEl.textContent = err.detail || 'A later rate exists. Archive it first to supersede.';
      } else {
        errEl.textContent = err.detail || 'Could not save tax rate.';
      }
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = editId ? 'Save Changes' : 'Create Rate';
    }
  },

  _closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const overlay = document.getElementById('otm-modal-overlay');
    if (overlay) overlay.classList.remove('cc-visible');
  },

  _esc(str) {
    if (str == null) return '';
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML;
  },
};
