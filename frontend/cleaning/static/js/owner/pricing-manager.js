/**
 * Xcleaners — Owner Pricing Manager Module (Story 1.1 Task 5a)
 *
 * CRUD for cleaning_pricing_formulas (default + location-specific) plus
 * visualization/revert of active cleaning_service_overrides.
 *
 * Route: #/owner/pricing
 * Global: OwnerPricingManager
 *
 * Endpoints (per docs/ux/story-1.1-ui-specs.md §4.5):
 *   GET    /pricing/formulas
 *   POST   /pricing/formulas
 *   PATCH  /pricing/formulas/{id}
 *   GET    /pricing/overrides?is_active=true
 *   DELETE /pricing/overrides/{id}
 *   POST   /pricing/preview             ← exists (C2)
 *
 * Graceful: if a CRUD endpoint returns 404/405 (not yet implemented —
 * Smith Wave 1 finding A2), UI shows "endpoint pending" hint instead
 * of crashing.
 */

window.OwnerPricingManager = {
  _container: null,
  _formulas: [],
  _overrides: [],
  _editingId: null,

  async render(container) {
    this._container = container;
    this._editingId = null;

    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading pricing…</span>
      </div>
    `;

    // Load in parallel; both may 404 if endpoints pending
    const [fResp, oResp] = await Promise.all([
      this._safeGet('/pricing/formulas'),
      this._safeGet('/pricing/overrides?is_active=true'),
    ]);
    this._formulas = this._unwrap(fResp, 'formulas');
    this._overrides = this._unwrap(oResp, 'overrides');
    this._renderPage();
  },

  async _safeGet(endpoint) {
    try {
      return await CleanAPI.cleanGet(endpoint);
    } catch (err) {
      if (err && (err.status === 404 || err.status === 405)) {
        return { __pending: true, __endpoint: endpoint };
      }
      console.warn('[pricing-manager] GET failed:', endpoint, err);
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
    const formulasPending = this._formulas && this._formulas.__pending;
    const overridesPending = this._overrides && this._overrides.__pending;

    this._container.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-6);">
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <h2 style="margin:0;">Pricing Formulas</h2>
          <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="OwnerPricingManager._showCreateModal()">
            + Add Formula
          </button>
        </div>

        ${formulasPending ? this._renderPendingNotice('/pricing/formulas') : this._renderFormulas()}

        <div>
          <h3 style="margin:0 0 var(--cc-space-3);">Active Overrides ${!overridesPending && Array.isArray(this._overrides) ? `(${this._overrides.length})` : ''}</h3>
          ${overridesPending ? this._renderPendingNotice('/pricing/overrides') : this._renderOverrides()}
        </div>

        <div id="opm-modal-overlay" class="cc-modal-backdrop" onclick="OwnerPricingManager._closeModal(event)">
          <div class="cc-modal" style="max-width:560px;" onclick="event.stopPropagation()">
            <div id="opm-modal-content"></div>
          </div>
        </div>
      </div>
    `;
  },

  _renderPendingNotice(endpoint) {
    return `
      <div class="cc-card" style="background:var(--cc-info-50, #EFF6FF);border-left:4px solid var(--cc-info-500, #3B82F6);">
        <div style="display:flex;align-items:start;gap:var(--cc-space-3);">
          <div style="font-size:1.5rem;">ℹ</div>
          <div>
            <div style="font-weight:600;margin-bottom:var(--cc-space-1);">Endpoint pending</div>
            <div class="cc-text-sm cc-text-muted">
              <code>${this._esc(endpoint)}</code> is part of Story 1.1 Task 5 backend work.
              This UI will populate automatically once the endpoint ships. No action needed.
            </div>
          </div>
        </div>
      </div>
    `;
  },

  _renderFormulas() {
    if (!Array.isArray(this._formulas) || this._formulas.length === 0) {
      return `
        <div class="cc-card">
          <div class="cc-empty-state">
            <div class="cc-empty-state-title">No pricing formulas configured</div>
            <div class="cc-empty-state-description">
              Start with a business-wide default formula. You can add location-specific ones later.
            </div>
            <button class="cc-btn cc-btn-primary" onclick="OwnerPricingManager._showCreateModal()">+ Add First Formula</button>
          </div>
        </div>
      `;
    }
    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:var(--cc-space-4);">
        ${this._formulas.map(f => this._renderFormulaCard(f)).join('')}
      </div>
    `;
  },

  _renderFormulaCard(f) {
    const isDefault = !f.location_id;
    const base = f.base_amount != null ? `$${Number(f.base_amount).toFixed(2)}` : '—';
    const brDelta = f.bedroom_delta != null ? `$${Number(f.bedroom_delta).toFixed(2)}` : '—';
    const baDelta = f.bathroom_delta != null ? `$${Number(f.bathroom_delta).toFixed(2)}` : '—';
    const mult = this._parseTierMultipliers(f.tier_multipliers);
    const updated = f.updated_at ? new Date(f.updated_at).toLocaleDateString() : '—';
    const staleCount = this._countStaleOverrides(f);

    return `
      <div class="cc-card" style="border-left:4px solid ${f.is_active ? 'var(--cc-success-500)' : 'var(--cc-neutral-300)'};">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:var(--cc-space-2);">
          <div>
            <h4 style="margin:0;">${this._esc(f.name || 'Standard')}</h4>
            <div style="display:flex;gap:var(--cc-space-2);margin-top:var(--cc-space-1);flex-wrap:wrap;">
              ${isDefault
                ? `<span class="cc-badge cc-badge-sm" style="background:var(--cc-primary-50);color:var(--cc-primary-700);">default</span>`
                : `<span class="cc-badge cc-badge-sm">Location: ${this._esc(f.location_name || f.location_id || '—')}</span>`}
              ${f.is_active
                ? `<span class="cc-badge cc-badge-success cc-badge-sm">active</span>`
                : `<span class="cc-badge cc-badge-neutral cc-badge-sm">inactive</span>`}
            </div>
          </div>
          <button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerPricingManager._showEditModal('${f.id}')">Edit</button>
        </div>
        <div class="cc-text-sm" style="display:grid;gap:var(--cc-space-1);color:var(--cc-neutral-700);margin-bottom:var(--cc-space-2);">
          <div>Base: <strong>${base}</strong>   + BR: <strong>${brDelta}</strong>   + BA: <strong>${baDelta}</strong></div>
          <div>Tiers: Basic ×${mult.basic}  ·  Deep ×${mult.deep}  ·  Premium ×${mult.premium}</div>
        </div>
        <div class="cc-text-xs cc-text-muted">Last updated: ${updated}</div>
        ${staleCount > 0 ? `
          <div role="alert" style="margin-top:var(--cc-space-3);padding:var(--cc-space-2) var(--cc-space-3);background:var(--cc-warning-50);border-radius:var(--cc-radius-md);">
            <div class="cc-text-sm" style="color:var(--cc-warning-700);">
              ⚠ ${staleCount} override${staleCount > 1 ? 's' : ''} created BEFORE last update — may be stale
            </div>
          </div>
        ` : ''}
      </div>
    `;
  },

  _parseTierMultipliers(raw) {
    const defaults = { basic: '1.0', deep: '1.8', premium: '2.8' };
    if (!raw) return defaults;
    const data = typeof raw === 'string' ? (() => { try { return JSON.parse(raw); } catch { return {}; } })() : raw;
    return {
      basic: data.basic != null ? String(data.basic) : defaults.basic,
      deep: data.deep != null ? String(data.deep) : defaults.deep,
      premium: data.premium != null ? String(data.premium) : defaults.premium,
    };
  },

  _countStaleOverrides(formula) {
    if (!Array.isArray(this._overrides) || !formula.updated_at) return 0;
    const fTime = new Date(formula.updated_at).getTime();
    return this._overrides.filter(o => {
      if (!o.created_at) return false;
      return new Date(o.created_at).getTime() < fTime;
    }).length;
  },

  _renderOverrides() {
    if (!Array.isArray(this._overrides) || this._overrides.length === 0) {
      return `
        <div class="cc-card">
          <div class="cc-text-sm cc-text-muted" style="padding:var(--cc-space-4);text-align:center;">
            No active overrides. Services use formula-computed prices.
          </div>
        </div>
      `;
    }
    return `
      <div style="display:grid;gap:var(--cc-space-3);">
        ${this._overrides.map(o => this._renderOverrideCard(o)).join('')}
      </div>
    `;
  },

  _renderOverrideCard(o) {
    const override = o.price_override != null ? `$${Number(o.price_override).toFixed(2)}` : '—';
    const formula = o.formula_price != null ? `$${Number(o.formula_price).toFixed(2)}` : '—';
    const diff = (o.price_override != null && o.formula_price != null)
      ? Number(o.price_override) - Number(o.formula_price)
      : null;
    const diffStr = diff != null ? `${diff >= 0 ? '+' : ''}$${diff.toFixed(2)}` : '';
    return `
      <div class="cc-card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:var(--cc-space-3);flex-wrap:wrap;">
          <div style="flex:1;min-width:200px;">
            <div style="font-weight:600;">${this._esc(o.service_name || 'Service')} (${this._esc(o.tier || 'basic')})</div>
            <div class="cc-text-sm cc-text-muted" style="margin-top:var(--cc-space-1);">
              Formula: ${formula} → Override: <strong>${override}</strong> ${diffStr ? `(${diffStr})` : ''}
            </div>
            ${o.reason ? `<div class="cc-text-xs cc-text-muted" style="margin-top:var(--cc-space-1);">Reason: ${this._esc(o.reason)}</div>` : ''}
          </div>
          <button class="cc-btn cc-btn-outline cc-btn-xs cc-text-danger" onclick="OwnerPricingManager._revertOverride('${o.id}')">
            ↩ Revert
          </button>
        </div>
      </div>
    `;
  },

  async _revertOverride(overrideId) {
    if (!confirm('Revert this override? Service will use formula price.')) return;
    try {
      await CleanAPI.cleanDel(`/pricing/overrides/${overrideId}`);
      Xcleaners.showToast('Override reverted.', 'success');
      await this.render(this._container);
    } catch (err) {
      if (err && err.status === 404) {
        Xcleaners.showToast('Revert endpoint not yet available.', 'warning');
      } else {
        Xcleaners.showToast(err.detail || 'Could not revert override.', 'error');
      }
    }
  },

  // ----- Create / Edit Modal -----

  _showCreateModal() {
    this._editingId = null;
    this._renderFormModal({});
  },

  _showEditModal(id) {
    const f = this._formulas.find(x => x.id === id);
    if (!f) return;
    this._editingId = id;
    this._renderFormModal(f);
  },

  _renderFormModal(data) {
    const isEdit = !!this._editingId;
    const mult = this._parseTierMultipliers(data.tier_multipliers);
    const modal = document.getElementById('opm-modal-content');

    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">${isEdit ? 'Edit Formula' : 'Add Formula'}</h3>
        <button class="cc-modal-close" onclick="OwnerPricingManager._closeModal()">&times;</button>
      </div>
      <form id="opm-form" onsubmit="OwnerPricingManager._save(event)">
        <div class="cc-modal-body">
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Name</label>
            <input type="text" name="name" value="${this._esc(data.name || '')}" required maxlength="100" class="cc-input">
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label cc-label-required">Base ($)</label>
              <input type="number" name="base_amount" value="${data.base_amount != null ? data.base_amount : 115}" min="0" step="0.01" required class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label cc-label-required">+ Bedroom ($)</label>
              <input type="number" name="bedroom_delta" value="${data.bedroom_delta != null ? data.bedroom_delta : 20}" min="0" step="0.01" required class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label cc-label-required">+ Bathroom ($)</label>
              <input type="number" name="bathroom_delta" value="${data.bathroom_delta != null ? data.bathroom_delta : 15}" min="0" step="0.01" required class="cc-input">
            </div>
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Tier multipliers (applied to base + BR + BA)</label>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--cc-space-3);">
              <div><label class="cc-text-xs">Basic ×</label><input type="number" name="mult_basic" value="${mult.basic}" step="0.1" min="0" class="cc-input cc-input-sm"></div>
              <div><label class="cc-text-xs">Deep ×</label><input type="number" name="mult_deep" value="${mult.deep}" step="0.1" min="0" class="cc-input cc-input-sm"></div>
              <div><label class="cc-text-xs">Premium ×</label><input type="number" name="mult_premium" value="${mult.premium}" step="0.1" min="0" class="cc-input cc-input-sm"></div>
            </div>
          </div>
          <div class="cc-form-group">
            <label style="display:flex;align-items:center;gap:var(--cc-space-2);cursor:pointer;">
              <input type="checkbox" name="is_active" ${data.is_active !== false ? 'checked' : ''}>
              <span>Active (inactive = fallback to default formula)</span>
            </label>
          </div>
          <div id="opm-form-error" style="display:none;padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);"></div>
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerPricingManager._closeModal()">Cancel</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm" id="opm-save-btn">${isEdit ? 'Save Changes' : 'Create Formula'}</button>
        </div>
      </form>
    `;
    document.getElementById('opm-modal-overlay').classList.add('cc-visible');
  },

  async _save(e) {
    e.preventDefault();
    const form = document.getElementById('opm-form');
    const btn = document.getElementById('opm-save-btn');
    const errEl = document.getElementById('opm-form-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Saving…';

    const fd = new FormData(form);
    const body = {
      name: fd.get('name'),
      base_amount: Number(fd.get('base_amount')),
      bedroom_delta: Number(fd.get('bedroom_delta')),
      bathroom_delta: Number(fd.get('bathroom_delta')),
      tier_multipliers: {
        basic: Number(fd.get('mult_basic') || 1.0),
        deep: Number(fd.get('mult_deep') || 1.8),
        premium: Number(fd.get('mult_premium') || 2.8),
      },
      is_active: !!fd.get('is_active'),
    };

    try {
      if (this._editingId) {
        await CleanAPI.cleanPatch(`/pricing/formulas/${this._editingId}`, body);
      } else {
        await CleanAPI.cleanPost('/pricing/formulas', body);
      }
      Xcleaners.showToast('Formula saved.', 'success');
      this._closeModal();
      await this.render(this._container);
    } catch (err) {
      if (err && (err.status === 404 || err.status === 405)) {
        errEl.textContent = 'Endpoint /pricing/formulas not yet implemented. Your form input was valid; please retry after backend deploy.';
      } else {
        errEl.textContent = err.detail || 'Could not save formula.';
      }
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = this._editingId ? 'Save Changes' : 'Create Formula';
    }
  },

  _closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const overlay = document.getElementById('opm-modal-overlay');
    if (overlay) overlay.classList.remove('cc-visible');
  },

  _esc(str) {
    if (str == null) return '';
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML;
  },
};
