/**
 * CleanClaw — Owner Onboarding Wizard (5-Step Setup)
 *
 * Guides new cleaning business owners through initial configuration:
 *   Step 1: Business Info
 *   Step 2: Services (from templates)
 *   Step 3: Service Area
 *   Step 4: Pricing
 *   Step 5: Team
 *
 * Saves progress per step. Resumes from last completed step.
 */

window.OwnerOnboarding = {
  _container: null,
  _currentStep: 1,
  _completedSteps: [],
  _completed: false,
  _skipped: false,
  _templates: [],
  _selectedServices: [],
  _stepData: {},

  // ----- Render Entry Point -----

  async render(container) {
    this._container = container;
    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:80px 20px;">
        <div style="text-align:center;">
          <div class="cc-spinner" style="margin:0 auto var(--cc-space-4);"></div>
          <p class="cc-text-sm cc-text-muted">Loading setup wizard...</p>
        </div>
      </div>
    `;

    try {
      // Fetch status
      const status = await CleanAPI.cleanGet('/onboarding/status') || {};
      this._completedSteps = Array.isArray(status.completed_steps) ? status.completed_steps : [];
      this._currentStep = status.current_step || 1;
      this._completed = status.completed || false;
      this._skipped = status.skipped || false;

      // If already completed, redirect to dashboard
      if (this._completed || this._skipped) {
        CleanRouter.navigate('#/owner/dashboard');
        return;
      }

      // Fetch templates for step 2
      const tmplResp = await CleanAPI.cleanGet('/onboarding/templates') || {};
      const tmplList = Array.isArray(tmplResp.templates) ? tmplResp.templates : (Array.isArray(tmplResp) ? tmplResp : []);
      if (tmplList.length > 0) {
        this._templates = tmplList;
        // Pre-select standard-clean
        this._selectedServices = this._templates.map(t => ({
          ...t,
          is_selected: t.slug === 'standard-clean',
          template_slug: t.slug,
          base_price: t.suggested_base_price,
        }));
      }

      this._renderWizard();
    } catch (err) {
      console.error('[Onboarding] Init error:', err);
      container.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:center;padding:80px 20px;">
          <div class="cc-card" style="max-width:420px;width:100%;text-align:center;padding:var(--cc-space-8);">
            <div style="display:inline-flex;align-items:center;justify-content:center;width:56px;height:56px;border-radius:50%;background:var(--cc-danger-50);margin-bottom:var(--cc-space-4);">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--cc-danger-500)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
            </div>
            <h3 style="margin-bottom:var(--cc-space-2);">Setup Error</h3>
            <p class="cc-text-sm cc-text-muted" style="margin-bottom:var(--cc-space-5);">${err.detail || 'Failed to load onboarding wizard. Please try again.'}</p>
            <button class="cc-btn cc-btn-primary" onclick="OwnerOnboarding.render(OwnerOnboarding._container)">Retry</button>
          </div>
        </div>
      `;
    }
  },

  // ----- Wizard Shell -----

  _renderWizard() {
    const stepNames = ['Business Info', 'Services', 'Service Area', 'Pricing', 'Team'];
    const totalSteps = stepNames.length;
    const progressPct = Math.round(((this._currentStep - 1) / totalSteps) * 100);

    this._container.innerHTML = `
      <div style="max-width:720px;margin:0 auto;padding:var(--cc-space-8) var(--cc-space-4);" class="cc-animate-fade-in">
        <!-- Header -->
        <div style="text-align:center;margin-bottom:var(--cc-space-6);">
          <h2 style="color:var(--cc-neutral-900);margin-bottom:var(--cc-space-2);">Set Up Your Cleaning Business</h2>
          <p class="cc-text-sm cc-text-muted">Complete these steps to get started. It takes under 5 minutes.</p>
        </div>

        <!-- Step Indicator -->
        <div style="display:flex;align-items:center;justify-content:center;margin-bottom:var(--cc-space-8);padding:0 var(--cc-space-4);">
          ${stepNames.map((name, i) => {
            const num = i + 1;
            const done = this._completedSteps.includes(num);
            const active = num === this._currentStep;
            const clickable = done || num <= Math.max(...this._completedSteps, 0) + 1;
            return `
              ${i > 0 ? `<div style="flex:1;height:2px;background:${done || (active && i < this._currentStep) ? 'var(--cc-primary-500)' : 'var(--cc-neutral-200)'};margin:0 -2px;transition:background 0.3s ease;"></div>` : ''}
              <div style="display:flex;flex-direction:column;align-items:center;${clickable ? 'cursor:pointer;' : ''}" onclick="${clickable ? `OwnerOnboarding._goToStep(${num})` : ''}">
                <div style="width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:var(--cc-text-sm);font-weight:var(--cc-font-semibold);transition:all 0.3s ease;flex-shrink:0;
                  ${done ? 'background:var(--cc-success-500);color:#fff;' :
                    active ? 'background:var(--cc-primary-500);color:#fff;box-shadow:0 0 0 4px var(--cc-primary-100);' :
                    'background:var(--cc-neutral-100);color:var(--cc-neutral-400);border:2px solid var(--cc-neutral-200);'}">
                  ${done ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>' : num}
                </div>
                <span class="cc-text-xs" style="margin-top:var(--cc-space-2);white-space:nowrap;color:${active ? 'var(--cc-primary-600)' : done ? 'var(--cc-success-600)' : 'var(--cc-neutral-400)'};font-weight:${active ? 'var(--cc-font-semibold)' : 'var(--cc-font-regular)'};">${name}</span>
              </div>
            `;
          }).join('')}
        </div>

        <!-- Progress bar (thin) -->
        <div style="height:3px;background:var(--cc-neutral-100);border-radius:var(--cc-radius-full);margin-bottom:var(--cc-space-6);overflow:hidden;">
          <div style="height:100%;width:${progressPct}%;background:var(--cc-primary-500);border-radius:var(--cc-radius-full);transition:width 0.5s ease;"></div>
        </div>

        <!-- Step Content Card -->
        <div class="cc-card" style="padding:var(--cc-space-6);margin-bottom:var(--cc-space-4);">
          <div id="onboarding-step-content"></div>
        </div>

        <!-- Navigation -->
        <div style="display:flex;align-items:center;justify-content:space-between;gap:var(--cc-space-3);">
          <div>
            ${this._currentStep > 1 ? `
              <button class="cc-btn cc-btn-secondary" onclick="OwnerOnboarding._prevStep()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                Back
              </button>
            ` : ''}
          </div>
          <div style="display:flex;align-items:center;gap:var(--cc-space-2);">
            <span class="cc-text-xs cc-text-muted">Step ${this._currentStep} of ${totalSteps}</span>
            ${this._currentStep >= 3 ? `
              <button class="cc-btn cc-btn-ghost cc-btn-sm" onclick="OwnerOnboarding._skipStep()">Skip</button>
            ` : ''}
            <button class="cc-btn cc-btn-primary" id="onboarding-next-btn" onclick="OwnerOnboarding._nextStep()">
              ${this._currentStep === 5 ? 'Finish Setup' : 'Next'}
              ${this._currentStep < 5 ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>' : ''}
            </button>
          </div>
        </div>

        <!-- Skip All -->
        <div style="text-align:center;margin-top:var(--cc-space-6);">
          <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-muted" onclick="OwnerOnboarding._skipAll()" style="font-size:var(--cc-text-xs);">
            Skip setup — go to dashboard
          </button>
        </div>
      </div>
    `;

    this._renderStepContent();
  },

  // ----- Step Content Renderers -----

  _renderStepContent() {
    const content = document.getElementById('onboarding-step-content');
    if (!content) return;

    switch (this._currentStep) {
      case 1: this._renderStep1(content); break;
      case 2: this._renderStep2(content); break;
      case 3: this._renderStep3(content); break;
      case 4: this._renderStep4(content); break;
      case 5: this._renderStep5(content); break;
    }
  },

  _renderStep1(el) {
    const data = this._stepData[1] || {};
    const tz = data.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York';
    const email = data.contact_email || CleanAPI.getUser()?.email || '';

    el.innerHTML = `
      <div>
        <div style="display:flex;align-items:center;gap:var(--cc-space-3);margin-bottom:var(--cc-space-5);">
          <div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:var(--cc-radius-lg);background:var(--cc-primary-50);flex-shrink:0;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--cc-primary-500)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
          </div>
          <div>
            <h3 style="margin-bottom:2px;">Business Information</h3>
            <p class="cc-text-sm cc-text-muted">Tell us about your cleaning business.</p>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr;gap:0;">
          <div class="cc-form-group">
            <label class="cc-label cc-label-required" for="ob-name">Business Name</label>
            <input type="text" id="ob-name" class="cc-input" placeholder="e.g., Sparkle Clean Services" maxlength="255"
                   value="${this._esc(data.business_name || '')}" required>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 var(--cc-space-4);">
            <div class="cc-form-group">
              <label class="cc-label cc-label-required" for="ob-phone">Phone</label>
              <input type="tel" id="ob-phone" class="cc-input" placeholder="(555) 123-4567"
                     value="${this._esc(data.phone || '')}">
            </div>
            <div class="cc-form-group">
              <label class="cc-label" for="ob-email">Contact Email</label>
              <input type="email" id="ob-email" class="cc-input" placeholder="you@example.com"
                     value="${this._esc(email)}">
            </div>
          </div>

          <div class="cc-form-group">
            <label class="cc-label cc-label-required" for="ob-address">Address</label>
            <input type="text" id="ob-address" class="cc-input" placeholder="123 Main St"
                   value="${this._esc(data.address_line1 || '')}">
          </div>

          <div style="display:grid;grid-template-columns:1fr 80px 100px;gap:0 var(--cc-space-4);">
            <div class="cc-form-group">
              <label class="cc-label" for="ob-city">City</label>
              <input type="text" id="ob-city" class="cc-input" placeholder="Denver"
                     value="${this._esc(data.city || '')}">
            </div>
            <div class="cc-form-group">
              <label class="cc-label" for="ob-state">State</label>
              <input type="text" id="ob-state" class="cc-input" placeholder="CO" maxlength="50"
                     value="${this._esc(data.state || '')}">
            </div>
            <div class="cc-form-group">
              <label class="cc-label" for="ob-zip">ZIP Code</label>
              <input type="text" id="ob-zip" class="cc-input" placeholder="80202" maxlength="20"
                     value="${this._esc(data.zip_code || '')}">
            </div>
          </div>

          <div class="cc-form-group">
            <label class="cc-label" for="ob-tz">Timezone</label>
            <select id="ob-tz" class="cc-select">
              ${this._timezoneOptions(tz)}
            </select>
          </div>
        </div>
      </div>
    `;
  },

  _renderStep2(el) {
    el.innerHTML = `
      <div>
        <div style="display:flex;align-items:center;gap:var(--cc-space-3);margin-bottom:var(--cc-space-5);">
          <div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:var(--cc-radius-lg);background:var(--cc-success-50);flex-shrink:0;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--cc-success-500)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          </div>
          <div>
            <h3 style="margin-bottom:2px;">Services You Offer</h3>
            <p class="cc-text-sm cc-text-muted">Select the cleaning services your business provides.</p>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr;gap:var(--cc-space-3);" id="ob-services-list">
          ${this._selectedServices.map((svc, i) => `
            <div class="cc-card cc-card-interactive" data-idx="${i}" onclick="OwnerOnboarding._toggleServiceCard(${i})" style="padding:var(--cc-space-4);border:2px solid ${svc.is_selected ? 'var(--cc-primary-500)' : 'transparent'};${svc.is_selected ? 'background:var(--cc-primary-50);' : ''}transition:all 0.2s ease;">
              <div style="display:flex;align-items:flex-start;gap:var(--cc-space-3);">
                <div style="display:flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:var(--cc-radius-sm);border:2px solid ${svc.is_selected ? 'var(--cc-primary-500)' : 'var(--cc-neutral-300)'};background:${svc.is_selected ? 'var(--cc-primary-500)' : '#fff'};flex-shrink:0;margin-top:2px;transition:all 0.2s ease;">
                  ${svc.is_selected ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>' : ''}
                </div>
                <input type="checkbox" data-svc-idx="${i}" ${svc.is_selected ? 'checked' : ''} style="display:none;"
                       onchange="OwnerOnboarding._toggleService(${i}, this.checked)">
                <div style="flex:1;min-width:0;">
                  <div style="display:flex;align-items:center;justify-content:space-between;gap:var(--cc-space-2);">
                    <strong style="color:var(--cc-neutral-900);">${this._esc(svc.name)}</strong>
                    <span class="cc-text-sm cc-font-semibold" style="color:var(--cc-primary-600);white-space:nowrap;">$${(svc.base_price || 0).toFixed(2)}</span>
                  </div>
                  <p class="cc-text-sm cc-text-muted" style="margin-top:var(--cc-space-1);">${this._esc(svc.description || '')}</p>
                  <div style="display:flex;gap:var(--cc-space-3);margin-top:var(--cc-space-2);flex-wrap:wrap;">
                    <span class="cc-text-xs" style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:var(--cc-radius-full);background:var(--cc-neutral-100);color:var(--cc-neutral-600);">${svc.price_unit}</span>
                    ${svc.estimated_duration_minutes ? `<span class="cc-text-xs" style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:var(--cc-radius-full);background:var(--cc-neutral-100);color:var(--cc-neutral-600);">${svc.estimated_duration_minutes} min</span>` : ''}
                    <span class="cc-text-xs" style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:var(--cc-radius-full);background:var(--cc-neutral-100);color:var(--cc-neutral-600);">${svc.category}</span>
                  </div>
                </div>
              </div>
            </div>
          `).join('')}
        </div>

        <!-- Add Custom Service -->
        <div style="margin-top:var(--cc-space-4);">
          <button class="cc-btn cc-btn-outline cc-btn-sm" onclick="OwnerOnboarding._showCustomServiceForm()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Add Custom Service
          </button>
          <div id="ob-custom-service-form" style="display:none;margin-top:var(--cc-space-4);padding:var(--cc-space-4);border-radius:var(--cc-radius-lg);border:1px solid var(--cc-neutral-200);background:var(--cc-neutral-50);">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 var(--cc-space-4);">
              <div class="cc-form-group">
                <label class="cc-label">Service Name</label>
                <input type="text" id="ob-custom-name" class="cc-input" placeholder="e.g., Eco-Friendly Clean">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Base Price ($)</label>
                <input type="number" id="ob-custom-price" class="cc-input" placeholder="0.00" min="0" step="0.01">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Duration (min)</label>
                <input type="number" id="ob-custom-duration" class="cc-input" placeholder="120" min="1">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Category</label>
                <select id="ob-custom-category" class="cc-select">
                  <option value="residential">Residential</option>
                  <option value="commercial">Commercial</option>
                  <option value="specialized">Specialized</option>
                  <option value="addon">Add-on</option>
                </select>
              </div>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Description</label>
              <textarea id="ob-custom-desc" class="cc-textarea" rows="2" placeholder="Brief description..." style="min-height:60px;"></textarea>
            </div>
            <div style="display:flex;gap:var(--cc-space-2);justify-content:flex-end;">
              <button class="cc-btn cc-btn-ghost cc-btn-sm" onclick="document.getElementById('ob-custom-service-form').style.display='none'">Cancel</button>
              <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="OwnerOnboarding._addCustomService()">Add Service</button>
            </div>
          </div>
        </div>

        <div id="ob-step2-error" style="display:none;margin-top:var(--cc-space-3);padding:var(--cc-space-3);border-radius:var(--cc-radius-md);background:var(--cc-danger-50);color:var(--cc-danger-600);font-size:var(--cc-text-sm);border:1px solid var(--cc-danger-200);"></div>
      </div>
    `;
  },

  _renderStep3(el) {
    const data = this._stepData[3] || {};
    const serveAll = data.serve_all_areas || false;
    const areas = data.areas || [];

    el.innerHTML = `
      <div>
        <div style="display:flex;align-items:center;gap:var(--cc-space-3);margin-bottom:var(--cc-space-5);">
          <div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:var(--cc-radius-lg);background:var(--cc-info-50);flex-shrink:0;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--cc-info-500)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
          </div>
          <div>
            <h3 style="margin-bottom:2px;">Service Area</h3>
            <p class="cc-text-sm cc-text-muted">Where does your business operate?</p>
          </div>
        </div>

        <div class="cc-form-group">
          <label class="cc-toggle">
            <input type="checkbox" class="cc-toggle-input" id="ob-serve-all" ${serveAll ? 'checked' : ''}
                   onchange="OwnerOnboarding._toggleServeAll(this.checked)">
            <div class="cc-toggle-track"><div class="cc-toggle-thumb"></div></div>
            <span class="cc-toggle-label">I serve all areas (no geographic restriction)</span>
          </label>
        </div>

        <div id="ob-areas-container" style="${serveAll ? 'display:none;' : ''}">
          <div id="ob-areas-list" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
            ${areas.length > 0 ? areas.map((a, i) => this._renderAreaRow(a, i)).join('') : this._renderAreaRow({}, 0)}
          </div>

          <button class="cc-btn cc-btn-outline cc-btn-sm" style="margin-top:var(--cc-space-4);"
                  onclick="OwnerOnboarding._addAreaRow()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Add Another Area
          </button>
        </div>
      </div>
    `;
  },

  _renderAreaRow(area, idx) {
    return `
      <div class="cc-area-row" data-idx="${idx}" style="padding:var(--cc-space-4);border-radius:var(--cc-radius-lg);border:1px solid var(--cc-neutral-200);background:var(--cc-neutral-50);position:relative;">
        ${idx > 0 ? `<button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="this.closest('.cc-area-row').remove()" style="position:absolute;top:var(--cc-space-2);right:var(--cc-space-2);color:var(--cc-neutral-400);" title="Remove area">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>` : ''}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 var(--cc-space-4);">
          <div class="cc-form-group">
            <label class="cc-label">Area Name</label>
            <input type="text" class="cc-input ob-area-name" placeholder="e.g., Downtown Denver"
                   value="${this._esc(area.name || '')}">
          </div>
          <div class="cc-form-group">
            <label class="cc-label">ZIP Codes (comma-separated)</label>
            <input type="text" class="cc-input ob-area-zips" placeholder="80202, 80203, 80204"
                   value="${this._esc((area.zip_codes || []).join(', '))}">
          </div>
          <div class="cc-form-group" style="margin-bottom:0;">
            <label class="cc-label">City</label>
            <input type="text" class="cc-input ob-area-city" placeholder="Denver"
                   value="${this._esc(area.city || '')}">
          </div>
          <div class="cc-form-group" style="margin-bottom:0;">
            <label class="cc-label">State</label>
            <input type="text" class="cc-input ob-area-state" placeholder="CO"
                   value="${this._esc(area.state || '')}">
          </div>
        </div>
      </div>
    `;
  },

  _renderStep4(el) {
    const data = this._stepData[4] || {};
    const selected = this._selectedServices.filter(s => s.is_selected);

    el.innerHTML = `
      <div>
        <div style="display:flex;align-items:center;gap:var(--cc-space-3);margin-bottom:var(--cc-space-5);">
          <div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:var(--cc-radius-lg);background:var(--cc-warning-50);flex-shrink:0;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--cc-warning-500)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          </div>
          <div>
            <h3 style="margin-bottom:2px;">Pricing</h3>
            <p class="cc-text-sm cc-text-muted">Adjust prices for your services. Template defaults are pre-filled.</p>
          </div>
        </div>

        <div style="margin-bottom:var(--cc-space-4);">
          <button class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerOnboarding._useDefaultPrices()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
            Use Default Prices
          </button>
        </div>

        <div style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
          ${selected.map(svc => `
            <div class="cc-pricing-row" data-slug="${svc.template_slug || svc.slug}" style="display:flex;align-items:center;gap:var(--cc-space-4);padding:var(--cc-space-4);border-radius:var(--cc-radius-lg);border:1px solid var(--cc-neutral-200);background:var(--cc-neutral-50);">
              <div style="flex:1;min-width:0;">
                <strong class="cc-text-sm" style="color:var(--cc-neutral-900);">${this._esc(svc.name)}</strong>
              </div>
              <div style="display:flex;align-items:center;gap:var(--cc-space-3);flex-shrink:0;">
                <div style="width:100px;">
                  <input type="number" class="cc-input ob-price-value" step="0.01" min="0"
                         value="${svc.base_price || ''}" style="text-align:right;height:36px;font-size:var(--cc-text-sm);">
                </div>
                <div style="width:120px;">
                  <select class="cc-select ob-price-unit" style="height:36px;font-size:var(--cc-text-sm);">
                    <option value="flat" ${svc.price_unit === 'flat' ? 'selected' : ''}>Flat Rate</option>
                    <option value="hourly" ${svc.price_unit === 'hourly' ? 'selected' : ''}>Hourly</option>
                    <option value="per_sqft" ${svc.price_unit === 'per_sqft' ? 'selected' : ''}>Per Sq Ft</option>
                    <option value="per_room" ${svc.price_unit === 'per_room' ? 'selected' : ''}>Per Room</option>
                  </select>
                </div>
              </div>
            </div>
          `).join('')}
        </div>

        <div style="margin-top:var(--cc-space-8);">
          <h4 style="margin-bottom:var(--cc-space-2);">Extras & Surcharges</h4>
          <p class="cc-text-sm cc-text-muted" style="margin-bottom:var(--cc-space-4);">Add extra charges or discounts (optional).</p>

          <div id="ob-extras-list" style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
            ${(data.extras || []).map((e, i) => this._renderExtraRow(e, i)).join('')}
          </div>

          <button class="cc-btn cc-btn-outline cc-btn-sm" style="margin-top:var(--cc-space-3);"
                  onclick="OwnerOnboarding._addExtraRow()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Add Extra
          </button>
        </div>
      </div>
    `;
  },

  _renderExtraRow(extra, idx) {
    extra = extra || {};
    return `
      <div class="cc-extra-row" data-idx="${idx}" style="display:flex;align-items:flex-end;gap:var(--cc-space-3);padding:var(--cc-space-4);border-radius:var(--cc-radius-lg);border:1px solid var(--cc-neutral-200);background:var(--cc-neutral-50);position:relative;">
        <div style="flex:1;min-width:0;">
          <label class="cc-label">Name</label>
          <input type="text" class="cc-input ob-extra-name" placeholder="e.g., Pet Surcharge"
                 value="${this._esc(extra.name || '')}" style="height:36px;font-size:var(--cc-text-sm);">
        </div>
        <div style="width:130px;">
          <label class="cc-label">Type</label>
          <select class="cc-select ob-extra-type" style="height:36px;font-size:var(--cc-text-sm);">
            <option value="surcharge" ${extra.rule_type === 'surcharge' ? 'selected' : ''}>Surcharge ($)</option>
            <option value="multiplier" ${extra.rule_type === 'multiplier' ? 'selected' : ''}>Multiplier (x)</option>
            <option value="discount_percent" ${extra.rule_type === 'discount_percent' ? 'selected' : ''}>Discount (%)</option>
            <option value="discount_fixed" ${extra.rule_type === 'discount_fixed' ? 'selected' : ''}>Discount ($)</option>
          </select>
        </div>
        <div style="width:90px;">
          <label class="cc-label">Value</label>
          <input type="number" class="cc-input ob-extra-value" step="0.01"
                 value="${extra.value || ''}" placeholder="0.00" style="height:36px;font-size:var(--cc-text-sm);">
        </div>
        <button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="this.closest('.cc-extra-row').remove()" style="color:var(--cc-neutral-400);margin-bottom:2px;" title="Remove">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    `;
  },

  _renderStep5(el) {
    const data = this._stepData[5] || {};

    el.innerHTML = `
      <div>
        <div style="display:flex;align-items:center;gap:var(--cc-space-3);margin-bottom:var(--cc-space-5);">
          <div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:var(--cc-radius-lg);background:var(--cc-purple-50);flex-shrink:0;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--cc-purple-500)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <div>
            <h3 style="margin-bottom:2px;">Create Your First Team</h3>
            <p class="cc-text-sm cc-text-muted">Set up a team and invite your cleaners. You can add more later.</p>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr auto;gap:0 var(--cc-space-4);align-items:end;">
          <div class="cc-form-group">
            <label class="cc-label" for="ob-team-name">Team Name</label>
            <input type="text" id="ob-team-name" class="cc-input" placeholder="e.g., Team Alpha"
                   value="${this._esc(data.team_name || '')}">
          </div>
          <div class="cc-form-group">
            <label class="cc-label" for="ob-team-color">Color</label>
            <div style="display:flex;align-items:center;gap:var(--cc-space-2);">
              <input type="color" id="ob-team-color" value="${data.team_color || '#3B82F6'}"
                     style="height:42px;width:60px;padding:4px;cursor:pointer;border:1px solid var(--cc-neutral-300);border-radius:var(--cc-radius-md);background:#fff;">
            </div>
          </div>
        </div>

        <div class="cc-form-group" style="margin-top:var(--cc-space-2);">
          <label class="cc-label" for="ob-invite-emails">Invite Cleaners by Email</label>
          <textarea id="ob-invite-emails" class="cc-textarea" rows="4"
                    placeholder="Enter email addresses, one per line:&#10;jane@example.com&#10;carlos@example.com"
          >${this._esc((data.invite_emails || []).join('\n'))}</textarea>
          <p class="cc-input-help">Invitations will be sent when you finish setup. They can accept and join your team.</p>
        </div>

        <div style="padding:var(--cc-space-3) var(--cc-space-4);border-radius:var(--cc-radius-md);background:var(--cc-neutral-50);border:1px solid var(--cc-neutral-200);">
          <p class="cc-text-sm cc-text-muted">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cc-neutral-400)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:text-bottom;margin-right:4px;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            You can skip this step and add teams later from the Teams page.
          </p>
        </div>
      </div>
    `;
  },

  // ----- Completion Screen -----

  _renderComplete() {
    this._container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;min-height:60vh;padding:var(--cc-space-8) var(--cc-space-4);">
        <div class="cc-card cc-animate-scale-in" style="max-width:480px;width:100%;text-align:center;padding:var(--cc-space-10);">
          <div style="display:inline-flex;align-items:center;justify-content:center;width:72px;height:72px;border-radius:50%;background:var(--cc-success-50);margin-bottom:var(--cc-space-5);">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--cc-success-500)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="cc-animate-bounce-in"><polyline points="20 6 9 17 4 12"/></svg>
          </div>
          <h2 style="margin-bottom:var(--cc-space-3);color:var(--cc-neutral-900);">You're All Set!</h2>
          <p class="cc-text-muted" style="margin-bottom:var(--cc-space-6);">Your cleaning business is ready. Start building your schedule and managing clients.</p>
          <button class="cc-btn cc-btn-primary cc-btn-lg" onclick="CleanRouter.navigate('#/owner/dashboard')">
            Go to Dashboard
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </button>
        </div>
      </div>
    `;
  },

  // ----- Navigation -----

  async _nextStep() {
    const btn = document.getElementById('onboarding-next-btn');
    if (btn) btn.disabled = true;

    try {
      // Collect step data
      const data = this._collectStepData(this._currentStep);
      if (!data) return; // validation failed

      // Save to backend
      const result = await CleanAPI.cleanPost(`/onboarding/step/${this._currentStep}`, {
        step: this._currentStep,
        data: data,
      });

      if (result && result.success) {
        // Store data locally
        this._stepData[this._currentStep] = data;

        if (!this._completedSteps.includes(this._currentStep)) {
          this._completedSteps.push(this._currentStep);
        }

        if (this._currentStep === 5) {
          // Complete onboarding
          await CleanAPI.cleanPost('/onboarding/complete', {});
          this._completed = true;
          this._renderComplete();
          return;
        }

        this._currentStep++;
        this._renderWizard();
      }
    } catch (err) {
      console.error('[Onboarding] Save error:', err);
      const detail = err.detail;
      const errors = typeof detail === 'object' && detail.errors
        ? detail.errors.join(', ')
        : (typeof detail === 'string' ? detail : 'Failed to save. Please try again.');
      CleanClaw.showToast(errors, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  _prevStep() {
    if (this._currentStep > 1) {
      // Save current step data locally (no backend save on back)
      const data = this._collectStepData(this._currentStep, true);
      if (data) this._stepData[this._currentStep] = data;

      this._currentStep--;
      this._renderWizard();
    }
  },

  _goToStep(step) {
    // Can only go to completed steps or next uncompleted
    if (this._completedSteps.includes(step) || step === Math.max(...this._completedSteps, 0) + 1) {
      // Save current data locally
      const data = this._collectStepData(this._currentStep, true);
      if (data) this._stepData[this._currentStep] = data;

      this._currentStep = step;
      this._renderWizard();
    }
  },

  async _skipStep() {
    // Save current data locally
    const data = this._collectStepData(this._currentStep, true);
    if (data) this._stepData[this._currentStep] = data;

    if (this._currentStep === 5) {
      // Skip = finish without this step
      try {
        await CleanAPI.cleanPost('/onboarding/complete', {});
        this._completed = true;
        this._renderComplete();
      } catch (err) {
        CleanClaw.showToast('Could not complete setup. Please try again.', 'error');
      }
      return;
    }

    this._currentStep++;
    this._renderWizard();
  },

  async _skipAll() {
    if (!confirm('Skip setup? You can complete it later from Settings.')) return;

    try {
      await CleanAPI.cleanPost('/onboarding/skip', {});
      CleanRouter.navigate('#/owner/dashboard');
    } catch (err) {
      CleanClaw.showToast('Could not skip setup. Please try again.', 'error');
    }
  },

  // ----- Data Collection -----

  _collectStepData(step, silent) {
    switch (step) {
      case 1: return this._collectStep1(silent);
      case 2: return this._collectStep2(silent);
      case 3: return this._collectStep3(silent);
      case 4: return this._collectStep4(silent);
      case 5: return this._collectStep5(silent);
      default: return {};
    }
  },

  _collectStep1(silent) {
    const name = (document.getElementById('ob-name')?.value || '').trim();
    const phone = (document.getElementById('ob-phone')?.value || '').trim();
    const address = (document.getElementById('ob-address')?.value || '').trim();

    if (!silent) {
      if (!name) { CleanClaw.showToast('Business name is required.', 'error'); return null; }
      if (!phone) { CleanClaw.showToast('Phone number is required.', 'error'); return null; }
      if (!address) { CleanClaw.showToast('Address is required.', 'error'); return null; }
    }

    return {
      business_name: name,
      phone: phone,
      contact_email: (document.getElementById('ob-email')?.value || '').trim(),
      address_line1: address,
      city: (document.getElementById('ob-city')?.value || '').trim(),
      state: (document.getElementById('ob-state')?.value || '').trim(),
      zip_code: (document.getElementById('ob-zip')?.value || '').trim(),
      timezone: document.getElementById('ob-tz')?.value || 'America/New_York',
    };
  },

  _collectStep2(silent) {
    const selected = this._selectedServices.filter(s => s.is_selected);

    if (!silent && selected.length === 0) {
      CleanClaw.showToast('Select at least one service.', 'error');
      const errEl = document.getElementById('ob-step2-error');
      if (errEl) {
        errEl.textContent = 'Select at least one service.';
        errEl.style.display = 'block';
      }
      return null;
    }

    return {
      services: selected.map(s => ({
        template_slug: s.template_slug || null,
        name: s.name,
        description: s.description,
        category: s.category,
        base_price: s.base_price,
        price_unit: s.price_unit,
        estimated_duration_minutes: s.estimated_duration_minutes,
        is_selected: true,
      })),
    };
  },

  _collectStep3(silent) {
    const serveAll = document.getElementById('ob-serve-all')?.checked || false;
    const areas = [];

    if (!serveAll) {
      const rows = document.querySelectorAll('.cc-area-row');
      rows.forEach(row => {
        const name = row.querySelector('.ob-area-name')?.value?.trim();
        const zips = row.querySelector('.ob-area-zips')?.value?.trim();
        const city = row.querySelector('.ob-area-city')?.value?.trim();
        const state = row.querySelector('.ob-area-state')?.value?.trim();

        if (name || zips || city) {
          areas.push({
            name: name || city || 'Area',
            zip_codes: zips ? zips.split(',').map(z => z.trim()).filter(z => z) : [],
            city: city || null,
            state: state || null,
          });
        }
      });
    }

    return { serve_all_areas: serveAll, areas };
  },

  _collectStep4(silent) {
    const adjustments = [];
    const extras = [];

    // Collect price adjustments
    document.querySelectorAll('.cc-pricing-row').forEach(row => {
      const slug = row.dataset.slug;
      const price = parseFloat(row.querySelector('.ob-price-value')?.value);
      const unit = row.querySelector('.ob-price-unit')?.value;

      if (slug && !isNaN(price)) {
        adjustments.push({
          service_slug: slug,
          base_price: price,
          price_unit: unit || 'flat',
        });
      }
    });

    // Collect extras
    document.querySelectorAll('.cc-extra-row').forEach(row => {
      const name = row.querySelector('.ob-extra-name')?.value?.trim();
      const type = row.querySelector('.ob-extra-type')?.value;
      const value = parseFloat(row.querySelector('.ob-extra-value')?.value);

      if (name && !isNaN(value)) {
        extras.push({ name, rule_type: type || 'surcharge', value });
      }
    });

    return { use_defaults: false, adjustments, extras };
  },

  _collectStep5(silent) {
    const teamName = (document.getElementById('ob-team-name')?.value || '').trim();
    const teamColor = document.getElementById('ob-team-color')?.value || '#3B82F6';
    const emailsRaw = (document.getElementById('ob-invite-emails')?.value || '').trim();

    const emails = emailsRaw
      ? emailsRaw.split(/[\n,;]+/).map(e => e.trim()).filter(e => e)
      : [];

    // Validate emails if not silent
    if (!silent && emails.length > 0) {
      const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      const invalid = emails.filter(e => !emailRe.test(e));
      if (invalid.length > 0) {
        CleanClaw.showToast(`Invalid email(s): ${invalid.join(', ')}`, 'error');
        return null;
      }
    }

    return { team_name: teamName, team_color: teamColor, invite_emails: emails };
  },

  // ----- Service Selection Helpers -----

  _toggleServiceCard(idx) {
    if (this._selectedServices[idx]) {
      const newState = !this._selectedServices[idx].is_selected;
      this._selectedServices[idx].is_selected = newState;
      // Re-render step 2 to update UI
      this._renderStep2(document.getElementById('onboarding-step-content'));
    }
  },

  _toggleService(idx, checked) {
    if (this._selectedServices[idx]) {
      this._selectedServices[idx].is_selected = checked;
      const card = document.querySelector(`.cc-card-interactive[data-idx="${idx}"]`);
      if (card) {
        card.style.borderColor = checked ? 'var(--cc-primary-500)' : 'transparent';
        card.style.background = checked ? 'var(--cc-primary-50)' : '';
      }
    }
  },

  _showCustomServiceForm() {
    const form = document.getElementById('ob-custom-service-form');
    if (form) form.style.display = 'block';
  },

  _addCustomService() {
    const name = document.getElementById('ob-custom-name')?.value?.trim();
    const price = parseFloat(document.getElementById('ob-custom-price')?.value);
    const duration = parseInt(document.getElementById('ob-custom-duration')?.value);
    const category = document.getElementById('ob-custom-category')?.value || 'residential';
    const desc = document.getElementById('ob-custom-desc')?.value?.trim();

    if (!name) {
      CleanClaw.showToast('Service name is required.', 'error');
      return;
    }

    this._selectedServices.push({
      name,
      description: desc,
      category,
      base_price: isNaN(price) ? 0 : price,
      price_unit: 'flat',
      estimated_duration_minutes: isNaN(duration) ? null : duration,
      is_selected: true,
      template_slug: null,
      slug: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    });

    // Re-render step 2
    this._renderStep2(document.getElementById('onboarding-step-content'));
    CleanClaw.showToast(`"${name}" added.`, 'success');
  },

  // ----- Area Helpers -----

  _toggleServeAll(checked) {
    const container = document.getElementById('ob-areas-container');
    if (container) container.style.display = checked ? 'none' : '';
  },

  _addAreaRow() {
    const list = document.getElementById('ob-areas-list');
    if (!list) return;
    const idx = list.querySelectorAll('.cc-area-row').length;
    list.insertAdjacentHTML('beforeend', this._renderAreaRow({}, idx));
  },

  // ----- Pricing Helpers -----

  _useDefaultPrices() {
    document.querySelectorAll('.cc-pricing-row').forEach(row => {
      const slug = row.dataset.slug;
      const svc = this._selectedServices.find(s => (s.template_slug || s.slug) === slug);
      if (svc) {
        const priceInput = row.querySelector('.ob-price-value');
        const unitSelect = row.querySelector('.ob-price-unit');
        if (priceInput) priceInput.value = svc.base_price || '';
        if (unitSelect) unitSelect.value = svc.price_unit || 'flat';
      }
    });
    CleanClaw.showToast('Default prices restored.', 'info');
  },

  _addExtraRow() {
    const list = document.getElementById('ob-extras-list');
    if (!list) return;
    const idx = list.querySelectorAll('.cc-extra-row').length;
    list.insertAdjacentHTML('beforeend', this._renderExtraRow({}, idx));
  },

  // ----- Utilities -----

  _esc(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  },

  _timezoneOptions(selected) {
    const zones = [
      'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
      'America/Phoenix', 'America/Anchorage', 'Pacific/Honolulu',
      'America/Sao_Paulo', 'America/Argentina/Buenos_Aires', 'America/Mexico_City',
      'Europe/London', 'Europe/Paris', 'Europe/Berlin',
      'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Kolkata',
      'Australia/Sydney', 'Pacific/Auckland',
    ];

    return zones.map(tz => {
      const label = tz.replace(/_/g, ' ').replace(/\//g, ' / ');
      return `<option value="${tz}" ${tz === selected ? 'selected' : ''}>${label}</option>`;
    }).join('');
  },
};
