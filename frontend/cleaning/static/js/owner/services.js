/**
 * CleanClaw — Owner Services Management Module
 *
 * CRUD for cleaning service catalog. Lists services as cards with
 * name, category, price, duration, team size, and active toggle.
 * Create/edit via modal. Checklist editor per service.
 *
 * Route: #/owner/services
 * Global name: OwnerServices (loaded by router from owner/services.js)
 */

window.OwnerServices = {
  _container: null,
  _services: [],
  _editingId: null,

  // Categories for display (using design-system token references)
  _categories: {
    residential: { label: 'Residential', color: 'var(--cc-primary-500)', colorHex: '#3B82F6' },
    commercial: { label: 'Commercial', color: 'var(--cc-info-500)', colorHex: '#8B5CF6' },
    specialized: { label: 'Specialized', color: 'var(--cc-warning-500)', colorHex: '#F59E0B' },
    addon: { label: 'Add-on', color: 'var(--cc-neutral-500)', colorHex: '#6B7280' },
  },

  // ----- Render -----

  async render(container) {
    this._container = container;
    this._editingId = null;

    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading services...</span>
      </div>
    `;

    try {
      const resp = await CleanAPI.cleanGet('/services?include_inactive=true') || {};
      this._services = Array.isArray(resp.services) ? resp.services : (Array.isArray(resp) ? resp : []);
      this._renderPage();
    } catch (err) {
      container.innerHTML = `
        <div class="cc-empty-state">
          <div class="cc-empty-state-illustration">&#9888;</div>
          <div class="cc-empty-state-title">Could not load services</div>
          <div class="cc-empty-state-description">${err.detail || 'Something went wrong. Please try again.'}</div>
          <button class="cc-btn cc-btn-primary" onclick="OwnerServices.render(OwnerServices._container)">Retry</button>
        </div>
      `;
    }
  },

  _renderPage() {
    const c = this._container;
    c.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-6);">
        <!-- Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <h2 style="margin:0;">Services</h2>
          <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="OwnerServices._showCreateModal()">
            + Add Service
          </button>
        </div>

        ${this._services.length === 0 ? `
          <div class="cc-card">
            <div class="cc-empty-state">
              <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.cleaning : '&#128230;'}</div>
              <div class="cc-empty-state-title">Your schedule is empty</div>
              <div class="cc-empty-state-description">Add your cleaning service types to get started. You can set prices, durations, and team sizes for each service.</div>
              <button class="cc-btn cc-btn-primary" onclick="OwnerServices._showCreateModal()">+ Add Service</button>
            </div>
          </div>
        ` : `
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:var(--cc-space-4);">
            ${this._services.map(s => this._renderServiceCard(s)).join('')}
          </div>
        `}

        <!-- Modal container -->
        <div id="svc-modal-overlay" class="cc-modal-backdrop" onclick="OwnerServices._closeModal(event)">
          <div class="cc-modal" style="max-width:520px;" onclick="event.stopPropagation()">
            <div id="svc-modal-content"></div>
          </div>
        </div>
      </div>
    `;
  },

  _renderServiceCard(s) {
    const cat = this._categories[s.category] || this._categories.residential;
    const price = s.base_price != null ? `$${Number(s.base_price).toFixed(0)}` : '--';
    const duration = s.estimated_duration_minutes
      ? `${(s.estimated_duration_minutes / 60).toFixed(1)} hrs`
      : '--';

    return `
      <div class="cc-card" style="opacity:${s.is_active ? 1 : 0.6};border-left:4px solid ${cat.colorHex};">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--cc-space-3);">
          <div>
            <h4 style="margin:0 0 var(--cc-space-1);">${this._esc(s.name)}</h4>
            <span class="cc-badge cc-badge-sm" style="background:${cat.colorHex}20;color:${cat.colorHex};">
              ${cat.label}
            </span>
          </div>
          <label class="cc-toggle" title="${s.is_active ? 'Active' : 'Inactive'}">
            <input type="checkbox" ${s.is_active ? 'checked' : ''} onchange="OwnerServices._toggleActive('${s.id}', this.checked)">
            <span class="cc-toggle-slider"></span>
          </label>
        </div>
        ${s.description ? `<p class="cc-text-sm cc-text-muted" style="margin:0 0 var(--cc-space-3);">${this._esc(s.description)}</p>` : ''}
        <div class="cc-text-sm" style="display:flex;gap:var(--cc-space-5);color:var(--cc-neutral-700);">
          <span title="Base price"><strong>${price}</strong> ${s.price_unit}</span>
          <span title="Duration">${duration}</span>
          <span title="Min team size">${s.min_team_size} cleaner${s.min_team_size > 1 ? 's' : ''}</span>
        </div>
        <div style="display:flex;gap:var(--cc-space-2);margin-top:var(--cc-space-3);">
          <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="OwnerServices._showEditModal('${s.id}')">Edit</button>
          <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="OwnerServices._showChecklist('${s.id}')">Checklist</button>
          ${s.is_active ? `
            <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger" onclick="OwnerServices._deactivate('${s.id}')">Deactivate</button>
          ` : ''}
        </div>
      </div>
    `;
  },

  // ----- Create / Edit Modal -----

  _showCreateModal() {
    this._editingId = null;
    this._renderFormModal({});
  },

  _showEditModal(id) {
    const svc = this._services.find(s => s.id === id);
    if (!svc) return;
    this._editingId = id;
    this._renderFormModal(svc);
  },

  _renderFormModal(data) {
    const isEdit = !!this._editingId;
    const modal = document.getElementById('svc-modal-content');

    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">${isEdit ? 'Edit Service' : 'Add Service'}</h3>
        <button class="cc-modal-close" onclick="OwnerServices._closeModal()">&times;</button>
      </div>
      <form id="svc-form" onsubmit="OwnerServices._saveService(event)">
        <div class="cc-modal-body">
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Service Name</label>
            <input type="text" name="name" value="${this._esc(data.name || '')}" required maxlength="150" class="cc-input">
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Description</label>
            <textarea name="description" rows="2" class="cc-textarea">${this._esc(data.description || '')}</textarea>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">Category</label>
              <select name="category" class="cc-select">
                <option value="residential" ${data.category === 'residential' ? 'selected' : ''}>Residential</option>
                <option value="commercial" ${data.category === 'commercial' ? 'selected' : ''}>Commercial</option>
                <option value="specialized" ${data.category === 'specialized' ? 'selected' : ''}>Specialized</option>
                <option value="addon" ${data.category === 'addon' ? 'selected' : ''}>Add-on</option>
              </select>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Price Unit</label>
              <select name="price_unit" class="cc-select">
                <option value="flat" ${data.price_unit === 'flat' ? 'selected' : ''}>Flat Rate</option>
                <option value="hourly" ${data.price_unit === 'hourly' ? 'selected' : ''}>Hourly</option>
                <option value="per_sqft" ${data.price_unit === 'per_sqft' ? 'selected' : ''}>Per Sq Ft</option>
                <option value="per_room" ${data.price_unit === 'per_room' ? 'selected' : ''}>Per Room</option>
              </select>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">Base Price ($)</label>
              <input type="number" name="base_price" value="${data.base_price != null ? data.base_price : ''}" min="0" step="0.01" class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Duration (min)</label>
              <input type="number" name="estimated_duration_minutes" value="${data.estimated_duration_minutes || ''}" min="1" class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Min Team Size</label>
              <input type="number" name="min_team_size" value="${data.min_team_size || 1}" min="1" class="cc-input">
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">Sort Order</label>
              <input type="number" name="sort_order" value="${data.sort_order || 0}" min="0" class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Icon (emoji)</label>
              <input type="text" name="icon" value="${this._esc(data.icon || '')}" maxlength="50" class="cc-input" placeholder="e.g. 🧹">
            </div>
          </div>
          <div id="svc-form-error" style="display:none;padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);"></div>
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerServices._closeModal()">Cancel</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm" id="svc-save-btn">${isEdit ? 'Save Changes' : 'Create Service'}</button>
        </div>
      </form>
    `;

    document.getElementById('svc-modal-overlay').classList.add('cc-visible');
  },

  async _saveService(e) {
    e.preventDefault();
    const form = document.getElementById('svc-form');
    const btn = document.getElementById('svc-save-btn');
    const errEl = document.getElementById('svc-form-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Saving...';

    const fd = new FormData(form);
    const body = {};
    for (const [k, v] of fd.entries()) {
      if (v === '') continue;
      if (['base_price', 'estimated_duration_minutes', 'min_team_size', 'sort_order'].includes(k)) {
        body[k] = Number(v);
      } else {
        body[k] = v;
      }
    }

    try {
      if (this._editingId) {
        await CleanAPI.cleanPatch(`/services/${this._editingId}`, body);
        CleanClaw.showToast('Service updated successfully.', 'success');
      } else {
        await CleanAPI.cleanPost('/services', body);
        CleanClaw.showToast('Service created successfully.', 'success');
      }
      this._closeModal();
      await this.render(this._container);
    } catch (err) {
      errEl.textContent = err.detail || 'Could not save service. Please check the details and try again.';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = this._editingId ? 'Save Changes' : 'Create Service';
    }
  },

  // ----- Toggle Active / Deactivate -----

  async _toggleActive(id, active) {
    try {
      if (!active) {
        // Deactivate = soft delete
        await CleanAPI.cleanDel(`/services/${id}`);
        CleanClaw.showToast('Service deactivated. It will no longer appear in booking options.', 'success');
      } else {
        // Reactivate
        await CleanAPI.cleanPatch(`/services/${id}`, { is_active: true });
        CleanClaw.showToast('Service activated and available for booking.', 'success');
      }
      await this.render(this._container);
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Could not update service. Please try again.', 'error');
      await this.render(this._container);
    }
  },

  async _deactivate(id) {
    if (!confirm('Deactivate this service? It will no longer appear in booking options.')) return;
    await this._toggleActive(id, false);
  },

  // ----- Checklist -----

  async _showChecklist(serviceId) {
    const svc = this._services.find(s => s.id === serviceId);
    if (!svc) return;

    const modal = document.getElementById('svc-modal-content');

    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">Checklist: ${this._esc(svc.name)}</h3>
        <button class="cc-modal-close" onclick="OwnerServices._closeModal()">&times;</button>
      </div>
      <div class="cc-modal-body" style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-8);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading...</span>
      </div>
    `;
    document.getElementById('svc-modal-overlay').classList.add('cc-visible');

    try {
      const resp = await CleanAPI.cleanGet(`/services/${serviceId}/checklists`) || {};
      const items = Array.isArray(resp.items) ? resp.items : (Array.isArray(resp) ? resp : []);
      this._renderChecklistEditor(serviceId, svc.name, items);
    } catch (err) {
      modal.innerHTML = `
        <div class="cc-modal-header">
          <h3 class="cc-modal-title">Checklist: ${this._esc(svc.name)}</h3>
          <button class="cc-modal-close" onclick="OwnerServices._closeModal()">&times;</button>
        </div>
        <div class="cc-modal-body">
          <p class="cc-text-sm cc-text-danger">${err.detail || 'Failed to load checklist.'}</p>
        </div>
      `;
    }
  },

  _checklistItems: [],

  _renderChecklistEditor(serviceId, serviceName, items) {
    this._checklistItems = items.map((it, i) => ({
      name: it.task_description || it.name || '',
      room: it.room || '',
      is_required: it.is_required !== false,
      sort_order: it.sort_order || i,
    }));

    const modal = document.getElementById('svc-modal-content');
    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">Checklist: ${this._esc(serviceName)}</h3>
        <button class="cc-modal-close" onclick="OwnerServices._closeModal()">&times;</button>
      </div>
      <div class="cc-modal-body">
        <div id="checklist-list" style="max-height:400px;overflow-y:auto;"></div>
        <div style="margin-top:var(--cc-space-3);">
          <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="OwnerServices._addChecklistItem()">+ Add Item</button>
        </div>
        <div id="checklist-error" style="display:none;padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);margin-top:var(--cc-space-2);"></div>
      </div>
      <div class="cc-modal-footer">
        <button class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerServices._closeModal()">Cancel</button>
        <button class="cc-btn cc-btn-primary cc-btn-sm" id="checklist-save-btn" onclick="OwnerServices._saveChecklist('${serviceId}')">Save Checklist</button>
      </div>
    `;

    this._renderChecklistList();
  },

  _renderChecklistList() {
    const el = document.getElementById('checklist-list');
    if (!el) return;

    if (this._checklistItems.length === 0) {
      el.innerHTML = '<p class="cc-text-sm cc-text-muted" style="text-align:center;padding:var(--cc-space-6);">No items. Click "Add Item" to start.</p>';
      return;
    }

    el.innerHTML = this._checklistItems.map((item, i) => `
      <div style="display:flex;gap:var(--cc-space-2);align-items:center;padding:var(--cc-space-2) 0;border-bottom:1px solid var(--cc-neutral-100);">
        <span class="cc-text-xs cc-text-muted" style="width:24px;">${i + 1}.</span>
        <input type="text" value="${this._esc(item.name)}" placeholder="Task name *"
          onchange="OwnerServices._checklistItems[${i}].name=this.value"
          class="cc-input" style="flex:2;height:32px;font-size:var(--cc-text-sm);">
        <input type="text" value="${this._esc(item.room)}" placeholder="Room"
          onchange="OwnerServices._checklistItems[${i}].room=this.value"
          class="cc-input" style="flex:1;height:32px;font-size:var(--cc-text-sm);">
        <label class="cc-checkbox" style="white-space:nowrap;">
          <input type="checkbox" class="cc-checkbox-input" ${item.is_required ? 'checked' : ''}
            onchange="OwnerServices._checklistItems[${i}].is_required=this.checked">
          <span class="cc-text-xs">Req</span>
        </label>
        <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger" onclick="OwnerServices._removeChecklistItem(${i})">&times;</button>
      </div>
    `).join('');
  },

  _addChecklistItem() {
    this._checklistItems.push({ name: '', room: '', is_required: true, sort_order: this._checklistItems.length });
    this._renderChecklistList();
  },

  _removeChecklistItem(idx) {
    this._checklistItems.splice(idx, 1);
    this._renderChecklistList();
  },

  async _saveChecklist(serviceId) {
    const items = this._checklistItems.filter(it => it.name.trim());
    if (items.length === 0) {
      const errEl = document.getElementById('checklist-error');
      errEl.textContent = 'Add at least one checklist item.';
      errEl.style.display = 'block';
      return;
    }

    const btn = document.getElementById('checklist-save-btn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    try {
      await CleanAPI.cleanPost(`/services/${serviceId}/checklists`, {
        items: items.map((it, i) => ({
          name: it.name.trim(),
          room: it.room.trim() || null,
          is_required: it.is_required,
          sort_order: i,
        })),
      });
      CleanClaw.showToast('Checklist saved. Your team will see these tasks on every job.', 'success');
      this._closeModal();
    } catch (err) {
      const errEl = document.getElementById('checklist-error');
      errEl.textContent = err.detail || 'Could not save checklist. Please try again.';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Save Checklist';
    }
  },

  // ----- Modal Helpers -----

  _closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const overlay = document.getElementById('svc-modal-overlay');
    if (overlay) overlay.classList.remove('cc-visible');
  },

  _esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  },
};
