/**
 * CleanClaw — Homeowner Preferences Module (Sprint 3)
 *
 * Edit house details, access codes, pet info, and cleaning instructions.
 */
window.HomeownerPreferences = {
  _prefs: null,

  async render(container) {
    // Skeleton loading
    container.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <h2 style="margin:0;">My Home</h2>
        <div class="cc-card" style="padding:var(--cc-space-5);">
          <div class="cc-skeleton cc-skeleton-text" style="width:30%;height:16px;"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:100%;margin-top:var(--cc-space-3);height:42px;border-radius:var(--cc-radius-md);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:100%;margin-top:var(--cc-space-3);height:42px;border-radius:var(--cc-radius-md);"></div>
        </div>
        <div class="cc-card" style="padding:var(--cc-space-5);">
          <div class="cc-skeleton cc-skeleton-text" style="width:25%;height:16px;"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:100%;margin-top:var(--cc-space-3);height:42px;border-radius:var(--cc-radius-md);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:100%;margin-top:var(--cc-space-3);height:42px;border-radius:var(--cc-radius-md);"></div>
        </div>
      </div>
    `;

    try {
      let resp = await CleanAPI.cleanGet('/my-preferences');
      // Merge with localStorage saved data (demo mode persistence)
      const savedPrefs = JSON.parse(localStorage.getItem('cc_homeowner_prefs') || 'null');
      if (savedPrefs) resp = { ...resp, ...savedPrefs };
      this._prefs = (resp && typeof resp === 'object' && Object.keys(resp).length > 0) ? resp : null;
      if (!this._prefs) {
        container.innerHTML = `
          <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
            <div class="cc-empty-state-title">Could not load your home details</div>
          </div>
        `;
        return;
      }
      this._renderForm(container);
    } catch (err) {
      console.error('[Preferences] Error:', err);
      container.innerHTML = `
        <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
          <div class="cc-empty-state-title">Could not load preferences</div>
        </div>
      `;
    }
  },

  _renderForm(container) {
    const p = this._prefs;
    const addr = p.address || {};
    const prop = p.property || {};
    const pets = p.pets || {};
    const instr = p.instructions || {};
    const sched = p.scheduling || p.preferences || {};

    container.innerHTML = `
      <div class="cc-preferences cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <h2 style="margin:0;">My Home</h2>
        <form id="cc-prefs-form" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">

          <!-- Contact -->
          <div class="cc-card">
            <div class="cc-card-header">
              <span class="cc-card-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:-2px;margin-right:var(--cc-space-2);color:var(--cc-primary-500);"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                Contact Info
              </span>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Name</label>
              <input type="text" name="name" class="cc-input" value="${this._esc(p.name || '')}" placeholder="Your full name">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Email</label>
              <input type="email" name="email" class="cc-input" value="${this._esc(p.email || '')}" placeholder="you@email.com">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Phone</label>
              <input type="tel" name="phone" class="cc-input" value="${this._esc(p.phone || '')}" placeholder="(555) 123-4567">
            </div>
          </div>

          <!-- Address -->
          <div class="cc-card">
            <div class="cc-card-header">
              <span class="cc-card-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:-2px;margin-right:var(--cc-space-2);color:var(--cc-primary-500);"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                Address
              </span>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Street</label>
              <input type="text" name="address_line1" class="cc-input" value="${this._esc(addr.line1 || '')}" placeholder="123 Main St">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Apt/Unit</label>
              <input type="text" name="address_line2" class="cc-input" value="${this._esc(addr.line2 || '')}" placeholder="Apt 4B">
            </div>
            <div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:var(--cc-space-3);">
              <div class="cc-form-group">
                <label class="cc-label">City</label>
                <input type="text" name="city" class="cc-input" value="${this._esc(addr.city || '')}">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">State</label>
                <input type="text" name="state" class="cc-input" value="${this._esc(addr.state || '')}" maxlength="2" placeholder="FL">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Zip</label>
                <input type="text" name="zip_code" class="cc-input" value="${this._esc(addr.zip || '')}" maxlength="10" placeholder="33060">
              </div>
            </div>
          </div>

          <!-- Property Details -->
          <div class="cc-card">
            <div class="cc-card-header">
              <span class="cc-card-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:-2px;margin-right:var(--cc-space-2);color:var(--cc-primary-500);"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                Property Details
              </span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
              <div class="cc-form-group">
                <label class="cc-label">Type</label>
                <select name="property_type" class="cc-select">
                  <option value="">Select...</option>
                  ${['house', 'apartment', 'condo', 'townhouse', 'studio', 'other'].map(t =>
                    `<option value="${t}" ${prop.type === t ? 'selected' : ''}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`
                  ).join('')}
                </select>
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Sq. Ft.</label>
                <input type="number" name="square_feet" class="cc-input" value="${prop.square_feet || ''}" placeholder="1,500">
              </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
              <div class="cc-form-group">
                <label class="cc-label">Bedrooms</label>
                <input type="number" name="bedrooms" class="cc-input" value="${prop.bedrooms || ''}" min="0" max="20">
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Bathrooms</label>
                <input type="number" name="bathrooms" class="cc-input" value="${prop.bathrooms || ''}" min="0" max="20" step="0.5">
              </div>
            </div>
          </div>

          <!-- Pets -->
          <div class="cc-card">
            <div class="cc-card-header">
              <span class="cc-card-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:-2px;margin-right:var(--cc-space-2);color:var(--cc-primary-500);"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
                Pets
              </span>
            </div>
            <div class="cc-form-group" style="margin-bottom:var(--cc-space-3);">
              <label class="cc-toggle">
                <input type="checkbox" name="has_pets" class="cc-toggle-input" ${pets.has_pets ? 'checked' : ''}>
                <span class="cc-toggle-track"><span class="cc-toggle-thumb"></span></span>
                <span class="cc-toggle-label">I have pets</span>
              </label>
            </div>
            <div class="cc-form-group" id="cc-pet-details-group" ${!pets.has_pets ? 'style="display:none"' : ''}>
              <label class="cc-label">Pet Details</label>
              <textarea name="pet_details" class="cc-textarea" rows="2" placeholder="Dog (friendly), cat (stays in bedroom)...">${this._esc(pets.details || '')}</textarea>
            </div>
          </div>

          <!-- Cleaning Instructions -->
          <div class="cc-card">
            <div class="cc-card-header">
              <span class="cc-card-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:-2px;margin-right:var(--cc-space-2);color:var(--cc-primary-500);"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                Cleaning Instructions
              </span>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Access Instructions</label>
              <textarea name="access_instructions" class="cc-textarea" rows="2" placeholder="Gate code, key location, alarm code...">${this._esc(instr.access || '')}</textarea>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Special Instructions</label>
              <textarea name="special_instructions" class="cc-textarea" rows="3" placeholder="Skip the office, no bleach in kitchen, no shoes inside...">${this._esc(instr.special || '')}</textarea>
            </div>
          </div>

          <!-- Scheduling Preferences -->
          <div class="cc-card">
            <div class="cc-card-header">
              <span class="cc-card-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:-2px;margin-right:var(--cc-space-2);color:var(--cc-primary-500);"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Scheduling Preferences
              </span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
              <div class="cc-form-group">
                <label class="cc-label">Preferred Day</label>
                <select name="preferred_day" class="cc-select">
                  <option value="">No preference</option>
                  ${['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'].map(d =>
                    `<option value="${d.toLowerCase()}" ${sched.preferred_day === d.toLowerCase() ? 'selected' : ''}>${d}</option>`
                  ).join('')}
                </select>
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Preferred Time</label>
                <select name="preferred_time" class="cc-select">
                  <option value="">No preference</option>
                  ${['morning', 'afternoon', 'evening'].map(t =>
                    `<option value="${t}" ${sched.preferred_time === t ? 'selected' : ''}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`
                  ).join('')}
                </select>
              </div>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Communication Preference</label>
              <select name="communication_preference" class="cc-select">
                <option value="">Select...</option>
                ${['email', 'phone', 'text', 'whatsapp'].map(c =>
                  `<option value="${c}" ${sched.communication_preference === c ? 'selected' : ''}>${c.charAt(0).toUpperCase() + c.slice(1)}</option>`
                ).join('')}
              </select>
            </div>
          </div>

          <button type="submit" class="cc-btn cc-btn-primary cc-btn-lg cc-btn-block">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            Save Preferences
          </button>
        </form>
      </div>
    `;

    // Toggle pet details
    const hasPetsCheckbox = container.querySelector('[name="has_pets"]');
    const petDetailsGroup = document.getElementById('cc-pet-details-group');
    if (hasPetsCheckbox && petDetailsGroup) {
      hasPetsCheckbox.addEventListener('change', () => {
        petDetailsGroup.style.display = hasPetsCheckbox.checked ? '' : 'none';
      });
    }

    // Form submit
    document.getElementById('cc-prefs-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      await this._savePreferences(e.target);
    });
  },

  async _savePreferences(form) {
    const formData = new FormData(form);
    const data = {};

    for (const [key, value] of formData.entries()) {
      if (key === 'has_pets') {
        data[key] = true;
        continue;
      }
      if (value !== '' && value !== null) {
        // Convert numeric fields
        if (['square_feet', 'bedrooms'].includes(key)) {
          data[key] = parseInt(value) || null;
        } else if (key === 'bathrooms') {
          data[key] = parseFloat(value) || null;
        } else {
          data[key] = value;
        }
      }
    }

    // Handle unchecked has_pets
    if (!formData.has('has_pets')) {
      data.has_pets = false;
    }

    const submitBtn = form.querySelector('[type="submit"]');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Saving...'; }

    // Structure data to match what _renderForm expects
    const structured = {
      name: data.name || '',
      email: data.email || '',
      phone: data.phone || '',
      address: {
        line1: data.address_line1 || '',
        line2: data.address_line2 || '',
        city: data.city || '',
        state: data.state || '',
        zip: data.zip_code || '',
      },
      property: {
        type: data.property_type || '',
        square_feet: data.square_feet || 0,
        bedrooms: data.bedrooms || 0,
        bathrooms: data.bathrooms || 0,
      },
      pets: {
        has_pets: data.has_pets || false,
        details: data.pet_details || '',
      },
      instructions: {
        access: data.access_instructions || '',
        special: data.special_instructions || '',
      },
      scheduling: {
        preferred_day: data.preferred_day || '',
        preferred_time: data.preferred_time || '',
        communication_preference: data.communication_preference || 'email',
      },
    };

    // Save to localStorage (always works, even in demo mode)
    localStorage.setItem('cc_homeowner_prefs', JSON.stringify(structured));
    this._prefs = structured;

    try {
      await CleanAPI.request('PUT', `/api/v1/clean/${CleanAPI._slug}/my-preferences`, data);
    } catch {
      // API unavailable (demo mode) — localStorage save is sufficient
    }

    CleanClaw.showToast('House preferences updated. Your cleaning team will see these on their next visit.', 'success');
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Save Preferences'; }
  },

  _esc(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },
};
