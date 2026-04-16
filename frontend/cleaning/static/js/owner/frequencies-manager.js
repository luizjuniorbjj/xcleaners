/**
 * Xcleaners — Owner Frequencies Manager Module (Story 1.1 Task 5b)
 *
 * CRUD for cleaning_frequencies (recurring cadence + discount %).
 * Exactly one frequency may be is_default=TRUE per business.
 *
 * Route: #/owner/frequencies
 * Global: OwnerFrequenciesManager
 *
 * Endpoints (per docs/ux/story-1.1-ui-specs.md §6.5):
 *   GET    /pricing/frequencies?include_archived=false
 *   POST   /pricing/frequencies
 *   PATCH  /pricing/frequencies/{id}       (edit, archive via {is_archived:true})
 *   POST   /pricing/frequencies/{id}/set-default   (atomic unset-old + set-new)
 *
 * Graceful 404 fallback when endpoints pending (Smith A2).
 */

window.OwnerFrequenciesManager = {
  _container: null,
  _frequencies: [],
  _showArchived: false,
  _editingId: null,

  async render(container) {
    this._container = container;
    this._editingId = null;

    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading frequencies…</span>
      </div>
    `;

    const resp = await this._safeGet(`/pricing/frequencies?include_archived=${this._showArchived}`);
    this._frequencies = this._unwrap(resp, 'frequencies');
    this._renderPage();
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

  _renderPage() {
    const pending = this._frequencies && this._frequencies.__pending;
    const list = Array.isArray(this._frequencies) ? this._frequencies : [];
    const active = list.filter(f => !f.is_archived);
    const archived = list.filter(f => f.is_archived);

    this._container.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <h2 style="margin:0;">Frequencies</h2>
          <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="OwnerFrequenciesManager._showCreateModal()">+ Add Frequency</button>
        </div>

        ${pending ? this._renderPendingNotice('/pricing/frequencies') : this._renderList(active)}

        ${!pending && archived.length > 0 ? `
          <div style="margin-top:var(--cc-space-4);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <h3 style="margin:0;color:var(--cc-neutral-600);">Archived (${archived.length})</h3>
              <button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerFrequenciesManager._toggleArchivedView()">
                ${this._showArchived ? 'Hide' : 'Show'}
              </button>
            </div>
            ${this._showArchived ? this._renderList(archived, true) : ''}
          </div>
        ` : ''}

        <div id="ofm-modal-overlay" class="cc-modal-backdrop" onclick="OwnerFrequenciesManager._closeModal(event)">
          <div class="cc-modal" style="max-width:480px;" onclick="event.stopPropagation()">
            <div id="ofm-modal-content"></div>
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

  _renderList(list, isArchivedList = false) {
    if (!list.length) {
      return `
        <div class="cc-card">
          <div class="cc-empty-state">
            <div class="cc-empty-state-title">${isArchivedList ? 'No archived frequencies' : 'No frequencies configured'}</div>
            ${!isArchivedList ? `
              <div class="cc-empty-state-description">Add cadences like One Time, Weekly, Biweekly, Monthly with their discount %.</div>
              <button class="cc-btn cc-btn-primary" onclick="OwnerFrequenciesManager._showCreateModal()">+ Add First Frequency</button>
            ` : ''}
          </div>
        </div>
      `;
    }
    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:var(--cc-space-4);">
        ${list.map(f => this._renderCard(f)).join('')}
      </div>
    `;
  },

  _renderCard(f) {
    const discount = f.discount_pct != null ? `${Number(f.discount_pct).toFixed(0)}%` : '0%';
    const intervalStr = f.interval_weeks ? `${f.interval_weeks} week${f.interval_weeks > 1 ? 's' : ''}` : '—';
    const usage = f.usage_count != null ? f.usage_count : null;
    const isDefault = !!f.is_default;

    return `
      <div class="cc-card" style="opacity:${f.is_archived ? 0.6 : 1};border-left:4px solid ${isDefault ? 'var(--cc-success-500)' : 'var(--cc-neutral-300)'};">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div>
            <h4 style="margin:0;">${this._esc(f.name || 'Frequency')}</h4>
            <div style="display:flex;gap:var(--cc-space-2);margin-top:var(--cc-space-1);flex-wrap:wrap;">
              ${isDefault ? `<span class="cc-badge cc-badge-sm" style="background:var(--cc-success-50);color:var(--cc-success-700);">default</span>` : ''}
              ${f.is_archived ? `<span class="cc-badge cc-badge-neutral cc-badge-sm">archived</span>` : ''}
            </div>
          </div>
          <div style="font-size:var(--cc-text-xl);font-weight:700;color:${isDefault ? 'var(--cc-success-600)' : 'var(--cc-primary-600)'};">
            −${discount}
          </div>
        </div>
        <div class="cc-text-sm cc-text-muted" style="margin-top:var(--cc-space-2);">
          Interval: <strong>${intervalStr}</strong>
          ${usage != null ? ` · Used in ${usage} active schedule${usage !== 1 ? 's' : ''}` : ''}
        </div>
        <div style="display:flex;gap:var(--cc-space-2);margin-top:var(--cc-space-3);flex-wrap:wrap;">
          <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="OwnerFrequenciesManager._showEditModal('${f.id}')">Edit</button>
          ${!isDefault && !f.is_archived ? `
            <button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerFrequenciesManager._setDefault('${f.id}')">Set as Default</button>
          ` : ''}
          ${!isDefault && !f.is_archived ? `
            <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger" onclick="OwnerFrequenciesManager._archive('${f.id}')" ${usage > 0 ? '' : ''}>Archive</button>
          ` : ''}
          ${isDefault ? `
            <span class="cc-text-xs cc-text-muted" style="align-self:center;" title="Set another frequency as default first">cannot archive default</span>
          ` : ''}
        </div>
      </div>
    `;
  },

  _toggleArchivedView() {
    this._showArchived = !this._showArchived;
    this.render(this._container);
  },

  async _setDefault(id) {
    const cur = this._frequencies.find(f => f.is_default);
    const next = this._frequencies.find(f => f.id === id);
    if (!next) return;
    const msg = cur
      ? `This will unmark '${cur.name}' as default and set '${next.name}' instead. Continue?`
      : `Set '${next.name}' as the default frequency?`;
    if (!confirm(msg)) return;

    try {
      await CleanAPI.cleanPost(`/pricing/frequencies/${id}/set-default`, {});
      Xcleaners.showToast(`'${next.name}' is now the default frequency.`, 'success');
      await this.render(this._container);
    } catch (err) {
      // Fallback — try two-step (unset prev, set new) if atomic endpoint absent
      if (err && (err.status === 404 || err.status === 405)) {
        try {
          if (cur) await CleanAPI.cleanPatch(`/pricing/frequencies/${cur.id}`, { is_default: false });
          await CleanAPI.cleanPatch(`/pricing/frequencies/${id}`, { is_default: true });
          Xcleaners.showToast('Default updated (non-atomic).', 'success');
          await this.render(this._container);
          return;
        } catch (e2) {
          if (e2 && (e2.status === 404 || e2.status === 405)) {
            Xcleaners.showToast('set-default endpoint not yet available.', 'warning');
            return;
          }
        }
      }
      Xcleaners.showToast(err.detail || 'Could not set default.', 'error');
    }
  },

  async _archive(id) {
    const f = this._frequencies.find(x => x.id === id);
    if (!f) return;
    if (f.usage_count > 0) {
      if (!confirm(`'${f.name}' is used in ${f.usage_count} active schedule${f.usage_count > 1 ? 's' : ''}. Archive preserves historical bookings. Continue?`)) return;
    } else if (!confirm(`Archive '${f.name}'?`)) return;

    try {
      await CleanAPI.cleanPatch(`/pricing/frequencies/${id}`, { is_archived: true });
      Xcleaners.showToast('Frequency archived.', 'success');
      await this.render(this._container);
    } catch (err) {
      if (err && err.status === 404) {
        Xcleaners.showToast('Endpoint pending.', 'warning');
      } else {
        Xcleaners.showToast(err.detail || 'Could not archive.', 'error');
      }
    }
  },

  _showCreateModal() {
    this._editingId = null;
    this._renderFormModal({});
  },

  _showEditModal(id) {
    const f = this._frequencies.find(x => x.id === id);
    if (!f) return;
    this._editingId = id;
    this._renderFormModal(f);
  },

  _renderFormModal(data) {
    const isEdit = !!this._editingId;
    const modal = document.getElementById('ofm-modal-content');
    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">${isEdit ? 'Edit Frequency' : 'Add Frequency'}</h3>
        <button class="cc-modal-close" onclick="OwnerFrequenciesManager._closeModal()">&times;</button>
      </div>
      <form id="ofm-form" onsubmit="OwnerFrequenciesManager._save(event)">
        <div class="cc-modal-body">
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Name</label>
            <input type="text" name="name" value="${this._esc(data.name || '')}" required maxlength="50" class="cc-input" placeholder="e.g. Weekly">
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">Interval (weeks)</label>
              <input type="number" name="interval_weeks" value="${data.interval_weeks != null ? data.interval_weeks : ''}" min="1" max="52" class="cc-input" placeholder="blank = once">
              <small class="cc-text-muted">blank = One Time</small>
            </div>
            <div class="cc-form-group">
              <label class="cc-label cc-label-required">Discount %</label>
              <input type="number" name="discount_pct" value="${data.discount_pct != null ? data.discount_pct : 0}" min="0" max="100" step="0.01" required class="cc-input">
            </div>
          </div>
          <div class="cc-form-group">
            <label style="display:flex;align-items:center;gap:var(--cc-space-2);cursor:pointer;">
              <input type="checkbox" name="is_default" ${data.is_default ? 'checked' : ''}>
              <span>Set as default (will unmark previous default)</span>
            </label>
          </div>
          <div id="ofm-form-error" style="display:none;padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);"></div>
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerFrequenciesManager._closeModal()">Cancel</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm" id="ofm-save-btn">${isEdit ? 'Save Changes' : 'Create'}</button>
        </div>
      </form>
    `;
    document.getElementById('ofm-modal-overlay').classList.add('cc-visible');
  },

  async _save(e) {
    e.preventDefault();
    const form = document.getElementById('ofm-form');
    const btn = document.getElementById('ofm-save-btn');
    const errEl = document.getElementById('ofm-form-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Saving…';

    const fd = new FormData(form);
    const interval = fd.get('interval_weeks');
    const body = {
      name: fd.get('name'),
      interval_weeks: interval === '' || interval == null ? null : Number(interval),
      discount_pct: Number(fd.get('discount_pct') || 0),
      is_default: !!fd.get('is_default'),
    };

    try {
      if (this._editingId) {
        await CleanAPI.cleanPatch(`/pricing/frequencies/${this._editingId}`, body);
      } else {
        await CleanAPI.cleanPost('/pricing/frequencies', body);
      }
      Xcleaners.showToast('Frequency saved.', 'success');
      this._closeModal();
      await this.render(this._container);
    } catch (err) {
      if (err && (err.status === 404 || err.status === 405)) {
        errEl.textContent = 'Endpoint /pricing/frequencies not yet implemented.';
      } else {
        errEl.textContent = err.detail || 'Could not save frequency.';
      }
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = this._editingId ? 'Save Changes' : 'Create';
    }
  },

  _closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const overlay = document.getElementById('ofm-modal-overlay');
    if (overlay) overlay.classList.remove('cc-visible');
  },

  _esc(str) {
    if (str == null) return '';
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML;
  },
};
