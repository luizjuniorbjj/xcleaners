/**
 * CleanClaw — Owner Settings Module
 *
 * Tabbed layout: General, Services, Areas, Pricing, Notifications, Plan.
 * Each tab loads its own data and renders inline.
 * Explicit "Save Changes" button with unsaved-changes warning.
 */

window.OwnerSettings = {
  _settings: null,
  _areas: null,
  _pricing: null,
  _services: null,
  _activeTab: 'general',
  _dirty: false,
  _container: null,

  async render(container) {
    this._container = container;
    this._dirty = false;
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;

    container.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-5);">
        <h2 style="margin:0;">${t('settings.title')}</h2>

        <!-- Tabs -->
        <div id="settings-tabs" style="display:flex;gap:var(--cc-space-1);border-bottom:1px solid var(--cc-neutral-200);">
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="general" style="border-bottom:2px solid var(--cc-primary-500);border-radius:0;color:var(--cc-primary-600);font-weight:var(--cc-font-semibold);">${t('settings.tab_general')}</button>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="areas" style="border-bottom:2px solid transparent;border-radius:0;">${t('settings.tab_areas')}</button>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="pricing" style="border-bottom:2px solid transparent;border-radius:0;">${t('settings.tab_pricing')}</button>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="notifications" style="border-bottom:2px solid transparent;border-radius:0;">${t('settings.tab_notifications')}</button>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" data-tab="plan" style="border-bottom:2px solid transparent;border-radius:0;">${t('settings.tab_plan')}</button>
        </div>

        <!-- Tab Content -->
        <div id="settings-content">
          <div style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
            <div class="cc-skeleton" style="height:42px;width:100%;"></div>
            <div class="cc-skeleton" style="height:42px;width:80%;"></div>
            <div class="cc-skeleton" style="height:42px;width:60%;"></div>
          </div>
        </div>
      </div>
    `;

    // Bind tab events
    container.querySelectorAll('#settings-tabs button[data-tab]').forEach(tab => {
      tab.addEventListener('click', (e) => {
        if (this._dirty) {
          if (!confirm(t('settings.unsaved_warning'))) return;
          this._dirty = false;
        }
        container.querySelectorAll('#settings-tabs button[data-tab]').forEach(t => {
          t.style.borderBottomColor = 'transparent';
          t.style.color = '';
          t.style.fontWeight = '';
        });
        e.target.style.borderBottomColor = 'var(--cc-primary-500)';
        e.target.style.color = 'var(--cc-primary-600)';
        e.target.style.fontWeight = 'var(--cc-font-semibold)';
        this._activeTab = e.target.dataset.tab;
        this._renderTab();
      });
    });

    // Warn on navigation
    this._navHandler = () => {
      if (this._dirty) {
        const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
        // Can't truly prevent hash change, but we can warn
      }
    };
    window.addEventListener('hashchange', this._navHandler);

    // Load data
    await this._loadSettings();
    this._renderTab();
  },

  destroy() {
    if (this._navHandler) {
      window.removeEventListener('hashchange', this._navHandler);
    }
  },

  // ---- Data Loading ----

  async _loadSettings() {
    try {
      const resp = await CleanAPI.cleanGet('/settings');
      // Guard against empty object from demo mode
      if (resp && typeof resp === 'object' && Object.keys(resp).length > 0) {
        this._settings = resp;
        // Ensure nested structures exist
        if (!this._settings.business_profile) this._settings.business_profile = {};
        if (!this._settings.settings) this._settings.settings = {};
      } else {
        // Provide sensible defaults for demo/empty state
        this._settings = {
          business_profile: {},
          settings: { business_hours: {}, cancellation_policy: {} },
        };
      }
    } catch (err) {
      console.error('[Settings] Failed to load:', err);
      this._settings = {
        business_profile: {},
        settings: { business_hours: {}, cancellation_policy: {} },
      };
    }
  },

  async _loadAreas() {
    try {
      const resp = await CleanAPI.cleanGet('/settings/areas') || {};
      this._areas = Array.isArray(resp) ? resp : (resp.areas || []);
    } catch (err) {
      console.error('[Settings] Failed to load areas:', err);
      this._areas = [];
    }
  },

  async _loadPricing() {
    try {
      const resp = await CleanAPI.cleanGet('/settings/pricing') || {};
      this._pricing = Array.isArray(resp) ? resp : (resp.pricing || resp.rules || []);
    } catch (err) {
      console.error('[Settings] Failed to load pricing:', err);
      this._pricing = [];
    }
  },

  async _loadServices() {
    try {
      const resp = await CleanAPI.cleanGet('/services') || {};
      this._services = Array.isArray(resp) ? resp : (resp.services || []);
    } catch (err) {
      console.error('[Settings] Failed to load services:', err);
      this._services = [];
    }
  },

  // ---- Tab Rendering ----

  async _renderTab() {
    const el = document.getElementById('settings-content');
    this._dirty = false;

    switch (this._activeTab) {
      case 'general':
        this._renderGeneral(el);
        break;
      case 'areas':
        await this._loadAreas();
        this._renderAreas(el);
        break;
      case 'pricing':
        await this._loadPricing();
        if (!this._services) await this._loadServices();
        this._renderPricing(el);
        break;
      case 'notifications':
        this._renderNotifications(el);
        break;
      case 'plan':
        this._renderPlan(el);
        break;
    }
  },

  // ---- General Tab ----

  _renderGeneral(el) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    if (!this._settings) {
      el.innerHTML = '<p class="cc-text-sm cc-text-muted">Failed to load settings.</p>';
      return;
    }

    const p = this._settings.business_profile || {};
    const s = this._settings.settings || {};
    const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

    el.innerHTML = `
      <form id="general-form" style="display:flex;flex-direction:column;gap:var(--cc-space-6);">
        <!-- Business Profile -->
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">${t('settings.business_profile')}</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.business_name')}</label>
              <input type="text" name="name" value="${this._esc(p.name || '')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.phone')}</label>
              <input type="tel" name="phone" value="${this._esc(p.phone || '')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.email')}</label>
              <input type="email" name="email" value="${this._esc(p.email || '')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.address')}</label>
              <input type="text" name="address" value="${this._esc(p.address || '')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.city')}</label>
              <input type="text" name="city" value="${this._esc(p.city || '')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.state')}</label>
              <input type="text" name="state" value="${this._esc(p.state || '')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.zip_code')}</label>
              <input type="text" name="zip_code" value="${this._esc(p.zip_code || '')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.timezone')}</label>
              <input type="text" name="timezone" value="${this._esc(p.timezone || 'America/New_York')}" class="cc-input" />
            </div>
          </div>
        </div>

        <!-- Business Hours -->
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">${t('settings.business_hours')}</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:var(--cc-space-2);">
            ${days.map(day => {
              const h = s.business_hours?.[day] || { start: '08:00', end: '17:00', enabled: true };
              const dayLabel = t(`days.${day}`);
              return `
                <div style="display:flex;align-items:center;gap:var(--cc-space-3);padding:var(--cc-space-2) 0;border-bottom:1px solid var(--cc-neutral-100);">
                  <label class="cc-toggle" style="min-width:140px;">
                    <input type="checkbox" name="hours_${day}_enabled" ${h.enabled ? 'checked' : ''} class="cc-toggle-input" />
                    <span class="cc-toggle-track"><span class="cc-toggle-thumb"></span></span>
                    <span class="cc-toggle-label">${dayLabel}</span>
                  </label>
                  <input type="time" name="hours_${day}_start" value="${h.start}" ${h.enabled ? '' : 'disabled'} class="cc-input" style="width:120px;height:36px;" />
                  <span class="cc-text-muted">-</span>
                  <input type="time" name="hours_${day}_end" value="${h.end}" ${h.enabled ? '' : 'disabled'} class="cc-input" style="width:120px;height:36px;" />
                </div>
              `;
            }).join('')}
          </div>
        </div>

        <!-- Cancellation Policy -->
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">${t('settings.cancellation_policy')}</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.hours_before')}</label>
              <input type="number" name="cancel_hours" value="${s.cancellation_policy?.hours_before || 24}" min="0" max="168" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.fee_percentage')}</label>
              <input type="number" name="cancel_fee" value="${s.cancellation_policy?.fee_percentage || 50}" min="0" max="100" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.max_reschedules')}</label>
              <input type="number" name="max_reschedules" value="${s.cancellation_policy?.max_reschedules_per_month || 2}" min="0" max="10" class="cc-input" />
            </div>
          </div>
        </div>

        <!-- Auto Schedule -->
        <div class="cc-card">
          <div class="cc-card-header">
            <span class="cc-card-title">${t('settings.auto_schedule')}</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.travel_buffer')}</label>
              <input type="number" name="travel_buffer" value="${s.travel_buffer_minutes || 30}" min="0" max="120" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.default_duration')}</label>
              <input type="number" name="default_duration" value="${s.default_service_duration || 120}" min="30" max="600" step="15" class="cc-input" />
            </div>
            <div class="cc-form-group" style="display:flex;align-items:flex-end;">
              <label class="cc-toggle">
                <input type="checkbox" name="auto_gen" ${s.auto_generate_schedule ? 'checked' : ''} class="cc-toggle-input" />
                <span class="cc-toggle-track"><span class="cc-toggle-thumb"></span></span>
                <span class="cc-toggle-label">${t('settings.auto_schedule')}</span>
              </label>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.auto_schedule_time')}</label>
              <input type="time" name="auto_gen_time" value="${s.auto_generate_time || '06:00'}" class="cc-input" />
            </div>
          </div>
        </div>

        <!-- Save Button -->
        <div style="display:flex;justify-content:flex-end;">
          <button type="submit" class="cc-btn cc-btn-primary">${t('common.save')}</button>
        </div>
      </form>
    `;

    // Track dirty state
    el.querySelectorAll('input, select').forEach(input => {
      input.addEventListener('change', () => { this._dirty = true; });
    });

    // Toggle time inputs with day checkboxes
    el.querySelectorAll('.cc-toggle-input[name$="_enabled"]').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const day = e.target.name.replace('hours_', '').replace('_enabled', '');
        const startEl = el.querySelector(`[name="hours_${day}_start"]`);
        const endEl = el.querySelector(`[name="hours_${day}_end"]`);
        if (startEl) startEl.disabled = !e.target.checked;
        if (endEl) endEl.disabled = !e.target.checked;
      });
    });

    // Save
    el.querySelector('#general-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      await this._saveGeneral(e.target);
    });
  },

  async _saveGeneral(form) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    const fd = new FormData(form);
    const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

    const businessHours = {};
    for (const day of days) {
      businessHours[day] = {
        start: fd.get(`hours_${day}_start`) || '08:00',
        end: fd.get(`hours_${day}_end`) || '17:00',
        enabled: !!fd.get(`hours_${day}_enabled`),
      };
    }

    const payload = {
      name: fd.get('name'),
      phone: fd.get('phone'),
      email: fd.get('email'),
      address: fd.get('address'),
      city: fd.get('city'),
      state: fd.get('state'),
      zip_code: fd.get('zip_code'),
      timezone: fd.get('timezone'),
      business_hours: businessHours,
      cancellation_policy: {
        hours_before: parseInt(fd.get('cancel_hours')) || 24,
        fee_percentage: parseInt(fd.get('cancel_fee')) || 50,
        max_reschedules_per_month: parseInt(fd.get('max_reschedules')) || 2,
      },
      travel_buffer_minutes: parseInt(fd.get('travel_buffer')) || 30,
      default_service_duration: parseInt(fd.get('default_duration')) || 120,
      auto_generate_schedule: !!fd.get('auto_gen'),
      auto_generate_time: fd.get('auto_gen_time') || '06:00',
    };

    try {
      this._settings = await CleanAPI.cleanPut('/settings', payload);
      this._dirty = false;
      CleanClaw.showToast(t('settings.saved'), 'success');
      // Update sidebar business name if changed
      if (payload.name) {
        const sidebarName = document.getElementById('sidebar-business-name') || document.querySelector('.cc-sidebar-business-name, .cc-sidebar-header h3, [data-business-name]');
        if (sidebarName) sidebarName.textContent = payload.name;
      }
    } catch (err) {
      CleanClaw.showToast(err.detail || t('settings.save_error'), 'error');
    }
  },

  // ---- Areas Tab ----

  _renderAreas(el) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;

    let html = `
      <div class="cc-card">
        <div class="cc-card-header">
          <span class="cc-card-title">${t('settings.service_areas')}</span>
          <button class="cc-btn cc-btn-primary cc-btn-xs" id="btn-add-area">${t('settings.add_area')}</button>
        </div>
    `;

    if (!this._areas || this._areas.length === 0) {
      html += `
        <div class="cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:64px;height:64px;font-size:1.5rem;">&#127758;</div>
          <div class="cc-empty-state-title cc-text-sm">No service areas</div>
          <div class="cc-empty-state-description">${t('common.no_data')}</div>
        </div>
      `;
    } else {
      html += `
        <div class="cc-table-wrapper">
          <table class="cc-table">
            <thead>
              <tr>
                <th>${t('settings.area_name')}</th>
                <th>${t('settings.zip_codes')}</th>
                <th>${t('settings.city')}</th>
                <th>${t('settings.travel_fee')}</th>
                <th>${t('common.active')}</th>
                <th class="cc-text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
      `;

      for (const area of this._areas) {
        html += `
          <tr data-id="${area.id}">
            <td class="cc-font-medium">${this._esc(area.name)}</td>
            <td class="cc-text-sm">${(area.zip_codes || []).join(', ')}</td>
            <td class="cc-text-sm">${this._esc(area.city || '')}</td>
            <td class="cc-text-sm">$${(area.travel_fee || 0).toFixed(2)}</td>
            <td><span class="cc-badge cc-badge-sm ${area.is_active ? 'cc-badge-success' : 'cc-badge-neutral'}">${area.is_active ? t('common.yes') : t('common.no')}</span></td>
            <td class="cc-text-right">
              <button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerSettings._editArea('${area.id}')" title="${t('common.edit')}">Edit</button>
              <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger" onclick="OwnerSettings._deleteArea('${area.id}')" title="${t('common.delete')}">Delete</button>
            </td>
          </tr>
        `;
      }

      html += '</tbody></table></div>';
    }

    html += '<div id="area-form-container" style="margin-top:var(--cc-space-4);"></div></div>';
    el.innerHTML = html;

    el.querySelector('#btn-add-area').addEventListener('click', () => {
      this._showAreaForm();
    });
  },

  _showAreaForm(area) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    const isEdit = !!area;
    const container = document.getElementById('area-form-container');

    container.innerHTML = `
      <div class="cc-card" style="border:1px solid var(--cc-primary-200);background:var(--cc-primary-50);">
        <form id="area-form" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
          <h5 style="margin:0;">${isEdit ? t('common.edit') : t('settings.add_area')}</h5>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.area_name')}</label>
              <input type="text" name="name" value="${this._esc(area?.name || '')}" required class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.zip_codes')} (comma separated)</label>
              <input type="text" name="zip_codes" value="${(area?.zip_codes || []).join(', ')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.city')}</label>
              <input type="text" name="city" value="${this._esc(area?.city || '')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.state')}</label>
              <input type="text" name="state" value="${this._esc(area?.state || '')}" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.travel_fee')}</label>
              <input type="number" name="travel_fee" value="${area?.travel_fee || 0}" min="0" step="0.01" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.priority')}</label>
              <input type="number" name="priority" value="${area?.priority || 0}" min="0" class="cc-input" />
            </div>
          </div>
          <div style="display:flex;gap:var(--cc-space-2);justify-content:flex-end;">
            <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="document.getElementById('area-form-container').innerHTML=''">${t('common.cancel')}</button>
            <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm">${t('common.save')}</button>
          </div>
          ${isEdit ? `<input type="hidden" name="area_id" value="${area.id}" />` : ''}
        </form>
      </div>
    `;

    container.querySelector('#area-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const data = {
        name: fd.get('name'),
        zip_codes: fd.get('zip_codes') ? fd.get('zip_codes').split(',').map(z => z.trim()).filter(Boolean) : [],
        city: fd.get('city') || null,
        state: fd.get('state') || null,
        travel_fee: parseFloat(fd.get('travel_fee')) || 0,
        priority: parseInt(fd.get('priority')) || 0,
      };
      const areaId = fd.get('area_id');

      try {
        if (areaId) {
          await CleanAPI.cleanPut(`/settings/areas/${areaId}`, data);
          CleanClaw.showToast(t('settings.area_updated'), 'success');
        } else {
          await CleanAPI.cleanPost('/settings/areas', data);
          CleanClaw.showToast(t('settings.area_added'), 'success');
        }
        await this._loadAreas();
        this._renderAreas(document.getElementById('settings-content'));
      } catch (err) {
        CleanClaw.showToast(err.detail || t('settings.save_error'), 'error');
      }
    });
  },

  async _editArea(id) {
    const area = (this._areas || []).find(a => a.id === id);
    if (area) this._showAreaForm(area);
  },

  async _deleteArea(id) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    if (!confirm(t('settings.confirm_delete_area'))) return;
    try {
      await CleanAPI.cleanDel(`/settings/areas/${id}`);
      CleanClaw.showToast(t('settings.area_deleted'), 'success');
      await this._loadAreas();
      this._renderAreas(document.getElementById('settings-content'));
    } catch (err) {
      CleanClaw.showToast(err.detail || t('settings.save_error'), 'error');
    }
  },

  // ---- Pricing Tab ----

  _renderPricing(el) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;

    let html = `
      <div class="cc-card">
        <div class="cc-card-header">
          <span class="cc-card-title">${t('settings.pricing_rules')}</span>
          <button class="cc-btn cc-btn-primary cc-btn-xs" id="btn-add-rule">${t('settings.add_rule')}</button>
        </div>
    `;

    if (!this._pricing || this._pricing.length === 0) {
      html += `
        <div class="cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:64px;height:64px;font-size:1.5rem;">&#128176;</div>
          <div class="cc-empty-state-title cc-text-sm">No pricing rules</div>
          <div class="cc-empty-state-description">${t('common.no_data')}</div>
        </div>
      `;
    } else {
      html += `
        <div class="cc-table-wrapper">
          <table class="cc-table">
            <thead>
              <tr>
                <th>${t('settings.rule_name')}</th>
                <th>${t('settings.rule_type')}</th>
                <th>${t('settings.service')}</th>
                <th>${t('settings.amount')}/${t('settings.percentage')}</th>
                <th>${t('common.active')}</th>
                <th class="cc-text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
      `;

      for (const rule of this._pricing) {
        const typeLabel = t(`pricing_types.${rule.rule_type}`) || rule.rule_type;
        const valDisplay = rule.amount != null ? `$${rule.amount.toFixed(2)}` : rule.percentage != null ? `${rule.percentage}%` : '-';

        html += `
          <tr data-id="${rule.id}">
            <td class="cc-font-medium">${this._esc(rule.name)}</td>
            <td><span class="cc-badge cc-badge-sm cc-badge-info">${typeLabel}</span></td>
            <td class="cc-text-sm">${this._esc(rule.service_name || t('settings.all_services'))}</td>
            <td class="cc-font-medium">${valDisplay}</td>
            <td><span class="cc-badge cc-badge-sm ${rule.is_active ? 'cc-badge-success' : 'cc-badge-neutral'}">${rule.is_active ? t('common.yes') : t('common.no')}</span></td>
            <td class="cc-text-right">
              <button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerSettings._editRule('${rule.id}')" title="${t('common.edit')}">Edit</button>
              <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger" onclick="OwnerSettings._deleteRule('${rule.id}')" title="${t('common.delete')}">Delete</button>
            </td>
          </tr>
        `;
      }

      html += '</tbody></table></div>';
    }

    html += '<div id="rule-form-container" style="margin-top:var(--cc-space-4);"></div></div>';
    el.innerHTML = html;

    el.querySelector('#btn-add-rule').addEventListener('click', () => {
      this._showRuleForm();
    });
  },

  _showRuleForm(rule) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    const isEdit = !!rule;
    const container = document.getElementById('rule-form-container');
    const types = ['base_price', 'addon', 'multiplier', 'surcharge', 'discount', 'minimum'];

    const serviceOptions = (this._services || []).map(s =>
      `<option value="${s.id}" ${rule?.service_id === s.id ? 'selected' : ''}>${this._esc(s.name)}</option>`
    ).join('');

    container.innerHTML = `
      <div class="cc-card" style="border:1px solid var(--cc-primary-200);background:var(--cc-primary-50);">
        <form id="rule-form" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
          <h5 style="margin:0;">${isEdit ? t('common.edit') : t('settings.add_rule')}</h5>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.rule_name')}</label>
              <input type="text" name="name" value="${this._esc(rule?.name || '')}" required class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.rule_type')}</label>
              <select name="rule_type" required class="cc-select">
                ${types.map(tp => `<option value="${tp}" ${rule?.rule_type === tp ? 'selected' : ''}>${t(`pricing_types.${tp}`)}</option>`).join('')}
              </select>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.service')}</label>
              <select name="service_id" class="cc-select">
                <option value="">${t('settings.all_services')}</option>
                ${serviceOptions}
              </select>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.amount')} ($)</label>
              <input type="number" name="amount" value="${rule?.amount ?? ''}" min="0" step="0.01" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.percentage')} (%)</label>
              <input type="number" name="percentage" value="${rule?.percentage ?? ''}" min="0" max="999" step="0.1" class="cc-input" />
            </div>
            <div class="cc-form-group">
              <label class="cc-label">${t('settings.priority')}</label>
              <input type="number" name="priority" value="${rule?.priority || 0}" min="0" class="cc-input" />
            </div>
          </div>
          <div style="display:flex;gap:var(--cc-space-2);justify-content:flex-end;">
            <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="document.getElementById('rule-form-container').innerHTML=''">${t('common.cancel')}</button>
            <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm">${t('common.save')}</button>
          </div>
          ${isEdit ? `<input type="hidden" name="rule_id" value="${rule.id}" />` : ''}
        </form>
      </div>
    `;

    container.querySelector('#rule-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const data = {
        name: fd.get('name'),
        rule_type: fd.get('rule_type'),
        service_id: fd.get('service_id') || null,
        amount: fd.get('amount') ? parseFloat(fd.get('amount')) : null,
        percentage: fd.get('percentage') ? parseFloat(fd.get('percentage')) : null,
        priority: parseInt(fd.get('priority')) || 0,
        is_active: true,
      };
      const ruleId = fd.get('rule_id');

      try {
        if (ruleId) {
          await CleanAPI.cleanPut(`/settings/pricing/${ruleId}`, data);
          CleanClaw.showToast(t('settings.rule_updated'), 'success');
        } else {
          await CleanAPI.cleanPost('/settings/pricing', data);
          CleanClaw.showToast(t('settings.rule_added'), 'success');
        }
        await this._loadPricing();
        this._renderPricing(document.getElementById('settings-content'));
      } catch (err) {
        CleanClaw.showToast(err.detail || t('settings.save_error'), 'error');
      }
    });
  },

  async _editRule(id) {
    const rule = (this._pricing || []).find(r => r.id === id);
    if (rule) this._showRuleForm(rule);
  },

  async _deleteRule(id) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    if (!confirm(t('settings.confirm_delete_rule'))) return;
    try {
      await CleanAPI.cleanDel(`/settings/pricing/${id}`);
      CleanClaw.showToast(t('settings.rule_deleted'), 'success');
      await this._loadPricing();
      this._renderPricing(document.getElementById('settings-content'));
    } catch (err) {
      CleanClaw.showToast(err.detail || t('settings.save_error'), 'error');
    }
  },

  // ---- Notifications Tab ----

  _renderNotifications(el) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    if (!this._settings) {
      el.innerHTML = '<p class="cc-text-sm cc-text-muted">Failed to load settings.</p>';
      return;
    }

    const prefs = this._settings.settings.notification_preferences || {};
    const notifKeys = [
      { key: 'booking_confirmation', label: t('settings.notif_booking_confirm') },
      { key: 'booking_reminder_24h', label: t('settings.notif_reminder_24h') },
      { key: 'booking_reminder_1h', label: t('settings.notif_reminder_1h') },
      { key: 'schedule_change', label: t('settings.notif_schedule_change') },
      { key: 'payment_received', label: t('settings.notif_payment_received') },
      { key: 'invoice_sent', label: t('settings.notif_invoice_sent') },
      { key: 'team_checkin', label: t('settings.notif_team_checkin') },
    ];

    el.innerHTML = `
      <div class="cc-card">
        <form id="notif-form" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
          <div class="cc-card-header" style="margin-bottom:0;">
            <span class="cc-card-title">${t('settings.notifications')}</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:var(--cc-space-1);">
            ${notifKeys.map(({ key, label }) => `
              <label class="cc-toggle" style="padding:var(--cc-space-3);border-bottom:1px solid var(--cc-neutral-100);">
                <input type="checkbox" name="notif_${key}" ${prefs[key] !== false ? 'checked' : ''} class="cc-toggle-input" />
                <span class="cc-toggle-track"><span class="cc-toggle-thumb"></span></span>
                <span class="cc-toggle-label">${label}</span>
              </label>
            `).join('')}
          </div>
          <div style="display:flex;justify-content:flex-end;">
            <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm">${t('common.save')}</button>
          </div>
        </form>
      </div>
    `;

    el.querySelector('#notif-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = {
        notification_preferences: {},
      };
      for (const { key } of notifKeys) {
        payload.notification_preferences[key] = !!fd.get(`notif_${key}`);
      }
      try {
        this._settings = await CleanAPI.cleanPut('/settings', payload);
        CleanClaw.showToast(t('settings.saved'), 'success');
      } catch (err) {
        CleanClaw.showToast(err.detail || t('settings.save_error'), 'error');
      }
    });
  },

  // ---- Plan Tab ----

  _renderPlan(el) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    const plan = this._settings?.plan || 'basic';

    const plans = [
      { id: 'basic', name: 'Basic', price: '$29/mo', features: ['Manual scheduling', '1 team (3 cleaners)', '50 clients', 'Basic dashboard'] },
      { id: 'intermediate', name: 'Intermediate', price: '$49/mo', features: ['AI scheduling', 'Unlimited teams (15 cleaners)', '200 clients', 'Full analytics', 'AI Chat Monitor'] },
      { id: 'maximum', name: 'Maximum', price: '$99/mo', features: ['Everything in Intermediate', 'Unlimited cleaners & clients', 'Website + AI Chat', 'CRM / Lead capture', 'Export & reports'] },
    ];

    el.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:var(--cc-space-6);">
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:var(--cc-space-4);">
          ${plans.map(p => `
            <div class="cc-card ${p.id === plan ? '' : 'cc-card-interactive'}" style="${p.id === plan ? 'border:2px solid var(--cc-primary-500);' : ''}">
              <div style="text-align:center;padding:var(--cc-space-4) 0;">
                <h4 style="margin:0 0 var(--cc-space-2);">${p.name}</h4>
                <div style="font-size:var(--cc-text-2xl);font-weight:var(--cc-font-bold);color:var(--cc-primary-600);">${p.price}</div>
              </div>
              <div style="display:flex;flex-direction:column;gap:var(--cc-space-2);padding:var(--cc-space-4) 0;border-top:1px solid var(--cc-neutral-200);">
                ${p.features.map(f => `
                  <div style="display:flex;align-items:center;gap:var(--cc-space-2);" class="cc-text-sm">
                    <span style="color:var(--cc-success-500);">&#10003;</span> ${f}
                  </div>
                `).join('')}
              </div>
              <div style="padding-top:var(--cc-space-3);text-align:center;">
                ${p.id === plan
                  ? `<span class="cc-badge cc-badge-success">${t('settings.current_plan')}</span>`
                  : `<button class="cc-btn cc-btn-outline cc-btn-sm cc-btn-block" onclick="OwnerSettings._handleUpgrade('${p.id}')">${t('settings.upgrade')}</button>`
                }
              </div>
            </div>
          `).join('')}
        </div>
        <div style="text-align:center;">
          <button class="cc-btn cc-btn-secondary" onclick="OwnerSettings._handleManageBilling()">
            ${t('settings.manage_billing')}
          </button>
        </div>
      </div>
    `;
  },

  _handleUpgrade(plan) {
    // Redirect to Stripe checkout for the new plan
    CleanClaw.showToast('Redirecting to checkout...', 'info');
    // In production, this would create a Stripe checkout session
    CleanAPI.cleanPost('/billing/checkout', { plan }).then(data => {
      if (data?.url) window.location.href = data.url;
    }).catch(err => {
      CleanClaw.showToast(err.detail || 'Failed to start checkout.', 'error');
    });
  },

  _handleManageBilling() {
    CleanAPI.cleanPost('/billing/portal').then(data => {
      if (data?.url) window.location.href = data.url;
    }).catch(err => {
      CleanClaw.showToast(err.detail || 'Failed to open billing portal.', 'error');
    });
  },

  // ---- Helpers ----

  _esc(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },
};
