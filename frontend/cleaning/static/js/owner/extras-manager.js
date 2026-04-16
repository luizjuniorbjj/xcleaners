/**
 * Xcleaners — Owner Extras Manager Module (Story 1.1 Task 5a)
 *
 * Two tabs:
 *   1. Catalog — CRUD cleaning_extras (name, price, sort_order, is_active)
 *   2. Whitelist — per-service selection of allowed extras
 *
 * Route: #/owner/extras
 * Global: OwnerExtrasManager
 *
 * Endpoints (per docs/ux/story-1.1-ui-specs.md §5.4):
 *   GET    /pricing/extras?include_inactive=true
 *   POST   /pricing/extras
 *   PATCH  /pricing/extras/{id}
 *   GET    /services/{service_id}/extras
 *   PUT    /services/{service_id}/extras    { extra_ids: [uuid...] }
 *
 * Graceful 404 fallback when endpoints pending (Smith A2).
 */

window.OwnerExtrasManager = {
  _container: null,
  _extras: [],
  _services: [],
  _activeTab: 'catalog',   // 'catalog' | 'whitelist'
  _selectedServiceId: null,
  _serviceWhitelist: [],   // extras allowed for selected service
  _editingId: null,

  async render(container) {
    this._container = container;
    this._editingId = null;

    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading extras…</span>
      </div>
    `;

    const [eResp, sResp] = await Promise.all([
      this._safeGet('/pricing/extras?include_inactive=true'),
      this._safeGet('/services?include_inactive=false'),
    ]);
    this._extras = this._unwrap(eResp, 'extras');
    this._services = this._unwrap(sResp, 'services');
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
    const extrasPending = this._extras && this._extras.__pending;

    this._container.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <h2 style="margin:0;">Extras</h2>
          ${this._activeTab === 'catalog' && !extrasPending ? `
            <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="OwnerExtrasManager._showCreateModal()">+ Add Extra</button>
          ` : ''}
        </div>

        <div role="tablist" style="display:flex;gap:var(--cc-space-1);border-bottom:1px solid var(--cc-neutral-200);">
          ${['catalog', 'whitelist'].map(tab => `
            <button role="tab" aria-selected="${this._activeTab === tab}"
              class="cc-btn cc-btn-ghost cc-btn-sm"
              style="border-bottom:2px solid ${this._activeTab === tab ? 'var(--cc-primary-500)' : 'transparent'};border-radius:0;${this._activeTab === tab ? 'color:var(--cc-primary-600);font-weight:600;' : ''}"
              onclick="OwnerExtrasManager._switchTab('${tab}')">
              ${tab === 'catalog' ? 'Catalog' : 'Whitelist'}
            </button>
          `).join('')}
        </div>

        ${extrasPending ? this._renderPendingNotice('/pricing/extras') : (
          this._activeTab === 'catalog' ? this._renderCatalog() : this._renderWhitelist()
        )}

        <div id="oem-modal-overlay" class="cc-modal-backdrop" onclick="OwnerExtrasManager._closeModal(event)">
          <div class="cc-modal" style="max-width:480px;" onclick="event.stopPropagation()">
            <div id="oem-modal-content"></div>
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
            <div class="cc-text-sm cc-text-muted"><code>${this._esc(endpoint)}</code> ships with Story 1.1 Task 5 backend. UI renders automatically once available.</div>
          </div>
        </div>
      </div>
    `;
  },

  _switchTab(tab) {
    this._activeTab = tab;
    this._renderPage();
  },

  _renderCatalog() {
    const list = Array.isArray(this._extras) ? this._extras : [];
    if (list.length === 0) {
      return `
        <div class="cc-card">
          <div class="cc-empty-state">
            <div class="cc-empty-state-title">No extras yet</div>
            <div class="cc-empty-state-description">Add-ons like Stairs, Windows, Oven — priced flat and attachable per service.</div>
            <button class="cc-btn cc-btn-primary" onclick="OwnerExtrasManager._showCreateModal()">+ Add First Extra</button>
          </div>
        </div>
      `;
    }
    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:var(--cc-space-4);">
        ${list.map(e => this._renderExtraCard(e)).join('')}
      </div>
    `;
  },

  _renderExtraCard(e) {
    const price = e.price != null ? `$${Number(e.price).toFixed(2)}` : '—';
    return `
      <div class="cc-card" style="opacity:${e.is_active === false ? 0.6 : 1};">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div>
            <h4 style="margin:0;">${this._esc(e.name)}</h4>
            <div class="cc-text-sm cc-text-muted" style="margin-top:var(--cc-space-1);">
              Order: ${e.sort_order != null ? e.sort_order : 0}
              ${e.allowed_in_count != null ? ` · Allowed in ${e.allowed_in_count} services` : ''}
            </div>
          </div>
          <div style="font-size:var(--cc-text-xl);font-weight:700;color:var(--cc-primary-600);">${price}</div>
        </div>
        <div style="display:flex;gap:var(--cc-space-2);margin-top:var(--cc-space-3);">
          <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="OwnerExtrasManager._showEditModal('${e.id}')">Edit</button>
          ${e.is_active !== false
            ? `<button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger" onclick="OwnerExtrasManager._toggleActive('${e.id}', false)">Archive</button>`
            : `<button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerExtrasManager._toggleActive('${e.id}', true)">Activate</button>`}
        </div>
      </div>
    `;
  },

  _renderWhitelist() {
    const services = Array.isArray(this._services) ? this._services : [];
    const extras = Array.isArray(this._extras) ? this._extras.filter(e => e.is_active !== false) : [];

    if (services.length === 0) {
      return `<div class="cc-card"><div class="cc-text-sm cc-text-muted" style="padding:var(--cc-space-4);text-align:center;">No services configured. Add services first.</div></div>`;
    }

    const selected = this._selectedServiceId || (services[0] && services[0].id);
    const allowedSet = new Set(this._serviceWhitelist || []);
    const totalCatalog = extras.length;
    const selectedCount = extras.filter(e => allowedSet.has(e.id)).length;

    return `
      <div class="cc-card" style="padding:var(--cc-space-4);">
        <div class="cc-form-group">
          <label class="cc-label">Service</label>
          <select class="cc-select" onchange="OwnerExtrasManager._selectService(this.value)">
            ${services.map(s => `<option value="${s.id}" ${s.id === selected ? 'selected' : ''}>${this._esc(s.name)}</option>`).join('')}
          </select>
        </div>
        <div class="cc-text-sm cc-text-muted" style="margin-bottom:var(--cc-space-3);">
          Allowed extras (${selectedCount} / ${totalCatalog} in catalog):
        </div>
        <div style="display:grid;gap:var(--cc-space-2);max-height:400px;overflow-y:auto;">
          ${extras.length === 0
            ? `<div class="cc-text-sm cc-text-muted">No extras in catalog to allow.</div>`
            : extras.map(e => `
                <label style="display:flex;align-items:center;gap:var(--cc-space-3);cursor:pointer;padding:var(--cc-space-2);border-radius:var(--cc-radius-md);">
                  <input type="checkbox" ${allowedSet.has(e.id) ? 'checked' : ''} data-extra-id="${e.id}" onchange="OwnerExtrasManager._toggleWhitelistItem('${e.id}', this.checked)">
                  <span style="flex:1;">${this._esc(e.name)}</span>
                  <span class="cc-text-sm" style="color:var(--cc-neutral-600);">$${e.price != null ? Number(e.price).toFixed(2) : '—'}</span>
                </label>
              `).join('')}
        </div>
        <div style="display:flex;justify-content:flex-end;gap:var(--cc-space-2);margin-top:var(--cc-space-4);">
          <button class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerExtrasManager._loadWhitelist('${selected}')">Reset</button>
          <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="OwnerExtrasManager._saveWhitelist('${selected}')">Save Whitelist</button>
        </div>
      </div>
    `;
  },

  async _selectService(serviceId) {
    this._selectedServiceId = serviceId;
    await this._loadWhitelist(serviceId);
  },

  async _loadWhitelist(serviceId) {
    try {
      const resp = await CleanAPI.cleanGet(`/services/${serviceId}/extras`);
      const ids = Array.isArray(resp) ? resp.map(r => r.extra_id || r.id) :
                  resp && Array.isArray(resp.extras) ? resp.extras.map(r => r.extra_id || r.id) : [];
      this._serviceWhitelist = ids;
    } catch (err) {
      if (err && err.status === 404) {
        this._serviceWhitelist = [];  // endpoint pending, start empty
      } else {
        Xcleaners.showToast(err.detail || 'Could not load whitelist.', 'error');
        this._serviceWhitelist = [];
      }
    }
    this._renderPage();
  },

  _toggleWhitelistItem(extraId, checked) {
    if (!Array.isArray(this._serviceWhitelist)) this._serviceWhitelist = [];
    if (checked && !this._serviceWhitelist.includes(extraId)) {
      this._serviceWhitelist.push(extraId);
    } else if (!checked) {
      this._serviceWhitelist = this._serviceWhitelist.filter(id => id !== extraId);
    }
  },

  async _saveWhitelist(serviceId) {
    try {
      await CleanAPI.cleanPut(`/services/${serviceId}/extras`, {
        extra_ids: this._serviceWhitelist || [],
      });
      Xcleaners.showToast('Whitelist updated.', 'success');
    } catch (err) {
      if (err && (err.status === 404 || err.status === 405)) {
        Xcleaners.showToast('Endpoint /services/{id}/extras not yet available. Saved locally only.', 'warning');
      } else {
        Xcleaners.showToast(err.detail || 'Could not save whitelist.', 'error');
      }
    }
  },

  // ----- Create / Edit Modal -----

  _showCreateModal() {
    this._editingId = null;
    this._renderFormModal({});
  },

  _showEditModal(id) {
    const e = this._extras.find(x => x.id === id);
    if (!e) return;
    this._editingId = id;
    this._renderFormModal(e);
  },

  _renderFormModal(data) {
    const isEdit = !!this._editingId;
    const modal = document.getElementById('oem-modal-content');
    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">${isEdit ? 'Edit Extra' : 'Add Extra'}</h3>
        <button class="cc-modal-close" onclick="OwnerExtrasManager._closeModal()">&times;</button>
      </div>
      <form id="oem-form" onsubmit="OwnerExtrasManager._save(event)">
        <div class="cc-modal-body">
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Name</label>
            <input type="text" name="name" value="${this._esc(data.name || '')}" required maxlength="100" class="cc-input">
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label cc-label-required">Price ($)</label>
              <input type="number" name="price" value="${data.price != null ? data.price : ''}" min="0" step="0.01" required class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Sort order</label>
              <input type="number" name="sort_order" value="${data.sort_order != null ? data.sort_order : 0}" min="0" class="cc-input">
            </div>
          </div>
          <div class="cc-form-group">
            <label style="display:flex;align-items:center;gap:var(--cc-space-2);cursor:pointer;">
              <input type="checkbox" name="is_active" ${data.is_active !== false ? 'checked' : ''}>
              <span>Active</span>
            </label>
          </div>
          <div id="oem-form-error" style="display:none;padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);"></div>
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerExtrasManager._closeModal()">Cancel</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm" id="oem-save-btn">${isEdit ? 'Save Changes' : 'Create Extra'}</button>
        </div>
      </form>
    `;
    document.getElementById('oem-modal-overlay').classList.add('cc-visible');
  },

  async _save(e) {
    e.preventDefault();
    const form = document.getElementById('oem-form');
    const btn = document.getElementById('oem-save-btn');
    const errEl = document.getElementById('oem-form-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Saving…';

    const fd = new FormData(form);
    const body = {
      name: fd.get('name'),
      price: Number(fd.get('price')),
      sort_order: Number(fd.get('sort_order') || 0),
      is_active: !!fd.get('is_active'),
    };

    try {
      if (this._editingId) {
        await CleanAPI.cleanPatch(`/pricing/extras/${this._editingId}`, body);
      } else {
        await CleanAPI.cleanPost('/pricing/extras', body);
      }
      Xcleaners.showToast('Extra saved.', 'success');
      this._closeModal();
      await this.render(this._container);
    } catch (err) {
      if (err && (err.status === 404 || err.status === 405)) {
        errEl.textContent = 'Endpoint /pricing/extras not yet implemented. Form valid; retry after backend deploy.';
      } else {
        errEl.textContent = err.detail || 'Could not save extra.';
      }
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = this._editingId ? 'Save Changes' : 'Create Extra';
    }
  },

  async _toggleActive(id, active) {
    try {
      await CleanAPI.cleanPatch(`/pricing/extras/${id}`, { is_active: active });
      Xcleaners.showToast(active ? 'Extra activated.' : 'Extra archived.', 'success');
      await this.render(this._container);
    } catch (err) {
      if (err && err.status === 404) {
        Xcleaners.showToast('Endpoint pending.', 'warning');
      } else {
        Xcleaners.showToast(err.detail || 'Could not update extra.', 'error');
      }
    }
  },

  _closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const overlay = document.getElementById('oem-modal-overlay');
    if (overlay) overlay.classList.remove('cc-visible');
  },

  _esc(str) {
    if (str == null) return '';
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML;
  },
};
