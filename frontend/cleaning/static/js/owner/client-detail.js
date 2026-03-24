/**
 * CleanClaw v3 -- Owner Client Detail Module (S2.3)
 *
 * Client profile view with:
 * - Contact info, property details, access instructions
 * - Recurring schedules: list with add/edit/pause/cancel
 * - Booking history: past services with dates, teams, ratings
 * - Payment history: invoices with status
 * - Notes and preferences
 * - "Invite to app" button (sends homeowner invitation)
 */
window.OwnerClientDetail = {
  _client: null,
  _schedules: [],
  _editing: false,

  async render(container, params) {
    this._container = container;
    this._clientId = params?.id;
    this._editing = false;

    if (!this._clientId) {
      container.innerHTML = '<div class="cc-error"><p>No client ID provided.</p></div>';
      return;
    }

    container.innerHTML = '<div class="cc-loading">Loading client...</div>';
    await this._loadClient();
  },

  async _loadClient() {
    try {
      const slug = CleanAPI._slug;
      const [client, schedResp] = await Promise.all([
        CleanAPI.request('GET', `/api/v1/clean/${slug}/clients/${this._clientId}`),
        CleanAPI.request('GET', `/api/v1/clean/${slug}/clients/${this._clientId}/schedules`),
      ]);

      if (!client || (typeof client === 'object' && !client.id && Object.keys(client).length === 0)) {
        this._container.innerHTML = `
          <div class="cc-empty-state" style="padding:var(--cc-space-8);">
            <div class="cc-empty-state-illustration">?</div>
            <div class="cc-empty-state-title">Client not found</div>
            <a href="#/owner/clients" class="cc-btn cc-btn-secondary" style="margin-top:var(--cc-space-4);">Back to Clients</a>
          </div>`;
        return;
      }

      this._client = client;
      this._schedules = Array.isArray(schedResp) ? schedResp : ((schedResp && schedResp.schedules) ? schedResp.schedules : []);
      this._renderDetail();
    } catch (e) {
      this._container.innerHTML = `
        <div class="cc-error">
          <p>Failed to load client: ${e.detail || e.message || 'Unknown error'}</p>
          <a href="#/owner/clients">Back to Clients</a>
        </div>`;
    }
  },

  _renderDetail() {
    const c = this._client;
    if (!c) return;
    const name = `${c.first_name || ''} ${c.last_name || ''}`.trim() || 'Unnamed Client';
    const finRaw = c.financial_summary || {};
    const fin = { total_spent: finRaw.total_spent || 0, outstanding_balance: finRaw.outstanding_balance || 0, total_invoices: finRaw.total_invoices || 0, overdue_invoices: finRaw.overdue_invoices || 0 };
    const tags = (c.tags || []).map(t => `<span class="cc-tag">${this._esc(t)}</span>`).join('');

    this._container.innerHTML = `
      <div class="cc-client-detail">
        <div class="cc-detail-header">
          <a href="#/owner/clients" class="cc-back-link">&larr; Back to Clients</a>
          <div class="cc-detail-title">
            <h2>${this._esc(name)}</h2>
            <span class="cc-status cc-status-${(c.status || 'active') === 'active' ? 'active' : 'paused'}">${c.status || 'active'}</span>
          </div>
          <div class="cc-detail-actions">
            <button class="cc-btn cc-btn-sm" onclick="OwnerClientDetail._toggleEdit()">Edit</button>
            <button class="cc-btn cc-btn-sm cc-btn-outline" onclick="OwnerClientDetail._inviteClient()">Invite to App</button>
          </div>
        </div>

        <div class="cc-detail-grid">
          <!-- Contact Card -->
          <div class="cc-detail-card">
            <h4>Contact</h4>
            <div class="cc-detail-field"><label>Phone:</label> <span>${this._esc(c.phone || '--')}</span></div>
            <div class="cc-detail-field"><label>Email:</label> <span>${this._esc(c.email || '--')}</span></div>
            <div class="cc-detail-field"><label>Preferred:</label> <span>${this._esc(c.preferred_contact || '--')}</span></div>
            ${tags ? `<div class="cc-detail-field"><label>Tags:</label> <div>${tags}</div></div>` : ''}
            <div class="cc-detail-field"><label>Since:</label> <span>${c.created_at ? new Date(c.created_at).toLocaleDateString() : '--'}</span></div>
          </div>

          <!-- Property Card -->
          <div class="cc-detail-card">
            <h4>Property</h4>
            <div class="cc-detail-field">
              <span>${this._esc([c.address_line1, c.address_line2].filter(Boolean).join(', ') || '--')}</span>
            </div>
            <div class="cc-detail-field">
              <span>${this._esc([c.city, c.state, c.zip_code].filter(Boolean).join(', '))}</span>
            </div>
            <div class="cc-detail-field">
              <span>${[
                c.property_type ? c.property_type.charAt(0).toUpperCase() + c.property_type.slice(1) : null,
                c.bedrooms != null && c.bedrooms !== 0 ? `${c.bedrooms} bed` : null,
                c.bathrooms != null && c.bathrooms !== 0 ? `${c.bathrooms} bath` : null,
                c.square_feet ? `${Number(c.square_feet).toLocaleString()} sqft` : null,
              ].filter(Boolean).join(' | ') || '--'}</span>
            </div>
          </div>
        </div>

        <!-- Access & Preferences -->
        <div class="cc-detail-card cc-detail-full">
          <h4>Access &amp; Preferences</h4>
          <div class="cc-detail-grid cc-detail-grid-3">
            <div class="cc-detail-field"><label>Access:</label> <span>${this._esc(c.access_instructions || 'None specified')}</span></div>
            <div class="cc-detail-field"><label>Pets:</label> <span>${c.has_pets ? this._esc(c.pet_details || 'Yes') : 'No pets'}</span></div>
            <div class="cc-detail-field"><label>Notes:</label> <span>${this._esc(c.notes || c.internal_notes || '--')}</span></div>
          </div>
        </div>

        <!-- Schedule Section -->
        <div class="cc-detail-card cc-detail-full">
          <div class="cc-section-header">
            <h4>Recurring Schedules (${this._schedules.length})</h4>
            <button class="cc-btn cc-btn-sm cc-btn-primary" onclick="OwnerClientDetail._showAddSchedule()">+ Add Schedule</button>
          </div>
          ${this._renderSchedules()}
        </div>

        <!-- Financial Card -->
        <div class="cc-detail-card cc-detail-full">
          <h4>Financial Summary</h4>
          <div class="cc-kpi-row">
            <div class="cc-kpi">
              <div class="cc-kpi-value">$${Number(c.lifetime_value || 0).toLocaleString()}</div>
              <div class="cc-kpi-label">Lifetime Value</div>
            </div>
            <div class="cc-kpi">
              <div class="cc-kpi-value">${c.total_bookings || 0}</div>
              <div class="cc-kpi-label">Total Bookings</div>
            </div>
            <div class="cc-kpi">
              <div class="cc-kpi-value ${fin.outstanding_balance > 0 ? 'cc-text-danger' : ''}">$${fin.outstanding_balance.toLocaleString()}</div>
              <div class="cc-kpi-label">Outstanding</div>
            </div>
            <div class="cc-kpi">
              <div class="cc-kpi-value">${fin.total_invoices}</div>
              <div class="cc-kpi-label">Invoices</div>
            </div>
          </div>
          <div class="cc-detail-field">
            <label>Last Service:</label> <span>${c.last_service_date ? new Date(c.last_service_date).toLocaleDateString() : 'Never'}</span>
          </div>
        </div>
      </div>
    `;
  },

  _renderSchedules() {
    if (!this._schedules.length) {
      return '<p class="cc-muted">No recurring schedules. Click "+ Add Schedule" to create one.</p>';
    }

    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    return `
      <div class="cc-schedule-list">
        ${this._schedules.map(s => {
          const day = s.preferred_day_of_week != null ? dayNames[s.preferred_day_of_week] : '--';
          const time = s.preferred_time_start || '--';
          const isPaused = s.status === 'paused';

          return `
            <div class="cc-schedule-card ${isPaused ? 'cc-schedule-paused' : ''}">
              <div class="cc-schedule-info">
                <strong>${this._esc(s.frequency)}</strong>
                <span>${day} ${time}</span>
                ${s.agreed_price ? `<span>$${s.agreed_price}</span>` : ''}
                ${s.estimated_duration_minutes ? `<span>${s.estimated_duration_minutes} min</span>` : ''}
                ${s.next_occurrence ? `<span>Next: ${new Date(s.next_occurrence).toLocaleDateString()}</span>` : ''}
              </div>
              <div class="cc-schedule-actions">
                <span class="cc-status cc-status-${s.status === 'active' ? 'active' : 'paused'}">${s.status}</span>
                ${s.status === 'active' ? `
                  <button class="cc-btn cc-btn-xs" onclick="OwnerClientDetail._pauseSchedule('${s.id}')">Pause</button>
                ` : ''}
                ${s.status === 'paused' ? `
                  <button class="cc-btn cc-btn-xs cc-btn-primary" onclick="OwnerClientDetail._resumeSchedule('${s.id}')">Resume</button>
                ` : ''}
                <button class="cc-btn cc-btn-xs cc-btn-outline" onclick="OwnerClientDetail._editSchedule('${s.id}')">Edit</button>
                <button class="cc-btn cc-btn-xs cc-btn-danger" onclick="OwnerClientDetail._cancelSchedule('${s.id}')">Cancel</button>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  },

  // === SCHEDULE ACTIONS ===

  async _pauseSchedule(schedId) {
    if (!confirm('Pause this schedule? No new bookings will be generated until resumed.')) return;
    try {
      const slug = CleanAPI._slug;
      await CleanAPI.request('POST', `/api/v1/clean/${slug}/clients/${this._clientId}/schedules/${schedId}/pause`);
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast('Schedule paused. No new bookings will be generated.', 'success');
      await this._loadClient();
    } catch (e) {
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(e.detail || 'Could not pause schedule. Please try again.', 'error');
    }
  },

  async _resumeSchedule(schedId) {
    try {
      const slug = CleanAPI._slug;
      await CleanAPI.request('POST', `/api/v1/clean/${slug}/clients/${this._clientId}/schedules/${schedId}/resume`);
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast('Schedule resumed. New bookings will be generated.', 'success');
      await this._loadClient();
    } catch (e) {
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(e.detail || 'Could not resume schedule. Please try again.', 'error');
    }
  },

  async _cancelSchedule(schedId) {
    if (!confirm('Cancel this schedule? This cannot be undone.')) return;
    try {
      const slug = CleanAPI._slug;
      await CleanAPI.request('DELETE', `/api/v1/clean/${slug}/clients/${this._clientId}/schedules/${schedId}`);
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast('Schedule cancelled.', 'success');
      await this._loadClient();
    } catch (e) {
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(e.detail || 'Could not cancel schedule. Please try again.', 'error');
    }
  },

  _editSchedule(schedId) {
    const sched = this._schedules.find(s => s.id === schedId);
    if (!sched) return;
    this._showScheduleModal(sched);
  },

  _showAddSchedule() {
    this._showScheduleModal(null);
  },

  _showScheduleModal(existing) {
    const isEdit = !!existing;
    const title = isEdit ? 'Edit Schedule' : 'Add Recurring Schedule';
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

    const existing_m = document.getElementById('ccScheduleModal');
    if (existing_m) existing_m.remove();

    const modal = document.createElement('div');
    modal.id = 'ccScheduleModal';
    modal.className = 'cc-modal-overlay';
    modal.innerHTML = `
      <div class="cc-modal">
        <div class="cc-modal-header">
          <h3>${title}</h3>
          <button class="cc-modal-close" onclick="document.getElementById('ccScheduleModal').remove()">&times;</button>
        </div>
        <form id="ccScheduleForm" onsubmit="OwnerClientDetail._submitSchedule(event, ${isEdit ? `'${existing?.id}'` : 'null'})">
          <div class="cc-modal-body">
            ${!isEdit ? `
            <div class="cc-form-group">
              <label>Service *</label>
              <select name="service_id" required class="cc-select" id="ccSchedServiceId">
                <option value="">Select service...</option>
              </select>
            </div>` : ''}
            <div class="cc-form-row">
              <div class="cc-form-group">
                <label>Frequency *</label>
                <select name="frequency" required class="cc-select">
                  <option value="">Select...</option>
                  <option value="weekly" ${existing?.frequency === 'weekly' ? 'selected' : ''}>Weekly</option>
                  <option value="biweekly" ${existing?.frequency === 'biweekly' ? 'selected' : ''}>Biweekly</option>
                  <option value="monthly" ${existing?.frequency === 'monthly' ? 'selected' : ''}>Monthly</option>
                  <option value="sporadic" ${existing?.frequency === 'sporadic' ? 'selected' : ''}>Sporadic</option>
                </select>
              </div>
              <div class="cc-form-group">
                <label>Preferred Day</label>
                <select name="preferred_day_of_week" class="cc-select">
                  <option value="">Any</option>
                  ${dayNames.map((d, i) => `<option value="${i}" ${existing?.preferred_day_of_week === i ? 'selected' : ''}>${d}</option>`).join('')}
                </select>
              </div>
            </div>
            <div class="cc-form-row">
              <div class="cc-form-group">
                <label>Start Time</label>
                <input type="time" name="preferred_time_start" class="cc-input" value="${existing?.preferred_time_start?.substring(0, 5) || ''}">
              </div>
              <div class="cc-form-group">
                <label>End Time</label>
                <input type="time" name="preferred_time_end" class="cc-input" value="${existing?.preferred_time_end?.substring(0, 5) || ''}">
              </div>
            </div>
            <div class="cc-form-row">
              <div class="cc-form-group">
                <label>Price ($)</label>
                <input type="number" name="agreed_price" class="cc-input" min="0" step="0.01" value="${existing?.agreed_price || ''}">
              </div>
              <div class="cc-form-group">
                <label>Duration (min)</label>
                <input type="number" name="estimated_duration_minutes" class="cc-input" min="1" value="${existing?.estimated_duration_minutes || ''}">
              </div>
              <div class="cc-form-group">
                <label>Min Team Size</label>
                <input type="number" name="min_team_size" class="cc-input" min="1" value="${existing?.min_team_size || 1}">
              </div>
            </div>
            <div class="cc-form-group">
              <label>Notes</label>
              <textarea name="notes" class="cc-textarea" rows="2">${this._esc(existing?.notes || '')}</textarea>
            </div>
          </div>
          <div class="cc-modal-footer">
            <button type="button" class="cc-btn" onclick="document.getElementById('ccScheduleModal').remove()">Cancel</button>
            <button type="submit" class="cc-btn cc-btn-primary" id="ccSchedSubmitBtn">${isEdit ? 'Update' : 'Create'}</button>
          </div>
        </form>
      </div>
    `;
    document.body.appendChild(modal);

    // Load services for the dropdown
    if (!isEdit) this._loadServicesForDropdown();
  },

  async _loadServicesForDropdown() {
    try {
      const slug = CleanAPI._slug;
      const resp = await CleanAPI.request('GET', `/api/v1/clean/${slug}/services`);
      const select = document.getElementById('ccSchedServiceId');
      if (select && resp?.services) {
        resp.services.forEach(s => {
          if (!s.is_active) return;
          const opt = document.createElement('option');
          opt.value = s.id;
          opt.textContent = `${s.name} ($${s.base_price || 0})`;
          select.appendChild(opt);
        });
      }
    } catch { /* ignore */ }
  },

  async _submitSchedule(e, schedId) {
    e.preventDefault();
    const form = document.getElementById('ccScheduleForm');
    const btn = document.getElementById('ccSchedSubmitBtn');
    btn.disabled = true;

    const fd = new FormData(form);
    const data = {};

    for (const [key, val] of fd.entries()) {
      if (!val && val !== 0) continue;
      if (key === 'preferred_day_of_week' || key === 'min_team_size' || key === 'estimated_duration_minutes') {
        data[key] = parseInt(val, 10);
      } else if (key === 'agreed_price') {
        data[key] = parseFloat(val);
      } else {
        data[key] = val;
      }
    }

    try {
      const slug = CleanAPI._slug;
      if (schedId) {
        await CleanAPI.request('PATCH', `/api/v1/clean/${slug}/clients/${this._clientId}/schedules/${schedId}`, data);
        if (typeof CleanClaw !== 'undefined') CleanClaw.showToast('Schedule updated successfully.', 'success');
      } else {
        // client_id is set by the route, but we also send it in the body for the model
        data.client_id = this._clientId;
        await CleanAPI.request('POST', `/api/v1/clean/${slug}/clients/${this._clientId}/schedules`, data);
        if (typeof CleanClaw !== 'undefined') CleanClaw.showToast('Schedule created. Bookings will be generated automatically.', 'success');
      }
      document.getElementById('ccScheduleModal').remove();
      await this._loadClient();
    } catch (err) {
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(err.detail || 'Could not save schedule. Please check the details and try again.', 'error');
    } finally {
      btn.disabled = false;
    }
  },

  // === EDIT CLIENT ===

  _toggleEdit() {
    this._editing = !this._editing;
    if (this._editing) {
      this._renderEditForm();
    } else {
      this._renderDetail();
    }
  },

  _renderEditForm() {
    const c = this._client;
    this._container.innerHTML = `
      <div class="cc-client-detail">
        <div class="cc-detail-header">
          <a href="#/owner/clients" class="cc-back-link">&larr; Back to Clients</a>
          <h2>Edit Client</h2>
        </div>
        <form id="ccEditClientForm" onsubmit="OwnerClientDetail._submitEdit(event)">
          <div class="cc-detail-card cc-detail-full">
            <h4>Contact Information</h4>
            <div class="cc-form-row">
              <div class="cc-form-group"><label>First Name</label><input type="text" name="first_name" class="cc-input" value="${this._esc(c.first_name || '')}"></div>
              <div class="cc-form-group"><label>Last Name</label><input type="text" name="last_name" class="cc-input" value="${this._esc(c.last_name || '')}"></div>
            </div>
            <div class="cc-form-row">
              <div class="cc-form-group"><label>Phone</label><input type="tel" name="phone" class="cc-input" value="${this._esc(c.phone || '')}"></div>
              <div class="cc-form-group"><label>Email</label><input type="email" name="email" class="cc-input" value="${this._esc(c.email || '')}"></div>
            </div>
            <div class="cc-form-row">
              <div class="cc-form-group">
                <label>Status</label>
                <select name="status" class="cc-select">
                  <option value="active" ${c.status === 'active' ? 'selected' : ''}>Active</option>
                  <option value="paused" ${c.status === 'inactive' ? 'selected' : ''}>Paused</option>
                  <option value="former" ${c.status === 'former' ? 'selected' : ''}>Former</option>
                </select>
              </div>
              <div class="cc-form-group">
                <label>Tags</label>
                <input type="text" name="tags" class="cc-input" value="${(c.tags || []).join(', ')}">
              </div>
            </div>
          </div>

          <div class="cc-detail-card cc-detail-full">
            <h4>Property</h4>
            <div class="cc-form-group"><label>Address</label><input type="text" name="address_line1" class="cc-input" value="${this._esc(c.address_line1 || '')}"></div>
            <div class="cc-form-row">
              <div class="cc-form-group"><label>City</label><input type="text" name="city" class="cc-input" value="${this._esc(c.city || '')}"></div>
              <div class="cc-form-group"><label>State</label><input type="text" name="state" class="cc-input" value="${this._esc(c.state || '')}"></div>
              <div class="cc-form-group"><label>Zip</label><input type="text" name="zip_code" class="cc-input" value="${this._esc(c.zip_code || '')}"></div>
            </div>
            <div class="cc-form-row">
              <div class="cc-form-group"><label>Bedrooms</label><input type="number" name="bedrooms" class="cc-input" min="0" value="${c.bedrooms ?? ''}"></div>
              <div class="cc-form-group"><label>Bathrooms</label><input type="number" name="bathrooms" class="cc-input" min="0" step="0.5" value="${c.bathrooms ?? ''}"></div>
              <div class="cc-form-group"><label>Sqft</label><input type="number" name="square_feet" class="cc-input" min="0" value="${c.square_feet ?? ''}"></div>
            </div>
            <div class="cc-form-group">
              <label>Access Instructions</label>
              <textarea name="access_instructions" class="cc-textarea" rows="2">${this._esc(c.access_instructions || '')}</textarea>
            </div>
            <div class="cc-form-row">
              <div class="cc-form-group"><label><input type="checkbox" name="has_pets" ${c.has_pets ? 'checked' : ''}> Has Pets</label></div>
              <div class="cc-form-group"><label>Pet Details</label><input type="text" name="pet_details" class="cc-input" value="${this._esc(c.pet_details || '')}"></div>
            </div>
            <div class="cc-form-group">
              <label>Notes</label>
              <textarea name="notes" class="cc-textarea" rows="2">${this._esc(c.notes || c.internal_notes || '')}</textarea>
            </div>
          </div>

          <div class="cc-form-actions">
            <button type="button" class="cc-btn" onclick="OwnerClientDetail._toggleEdit()">Cancel</button>
            <button type="submit" class="cc-btn cc-btn-primary" id="ccEditBtn">Save Changes</button>
          </div>
        </form>
      </div>
    `;
  },

  async _submitEdit(e) {
    e.preventDefault();
    const form = document.getElementById('ccEditClientForm');
    const btn = document.getElementById('ccEditBtn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    const fd = new FormData(form);
    const data = {};

    for (const [key, val] of fd.entries()) {
      if (key === 'has_pets') { data[key] = true; continue; }
      if (key === 'tags') { data[key] = val ? val.split(',').map(t => t.trim()).filter(Boolean) : []; continue; }
      if (key === 'bedrooms' || key === 'square_feet') { if (val) data[key] = parseInt(val, 10); continue; }
      if (key === 'bathrooms') { if (val) data[key] = parseFloat(val); continue; }
      if (val) data[key] = val;
    }
    if (!fd.has('has_pets')) data['has_pets'] = false;

    try {
      const slug = CleanAPI._slug;
      const resp = await CleanAPI.request('PATCH', `/api/v1/clean/${slug}/clients/${this._clientId}`, data);
      if (resp) {
        this._client = resp;
        this._editing = false;
        if (typeof CleanClaw !== 'undefined') CleanClaw.showToast('Client details updated.', 'success');
        await this._loadClient();
      }
    } catch (err) {
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(err.detail || 'Could not update client. Please try again.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save Changes';
    }
  },

  // === INVITE CLIENT ===

  async _inviteClient() {
    if (!this._client?.email) {
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast('Add an email address first so we can send the invitation.', 'warning');
      return;
    }
    if (!confirm(`Invite ${this._client.first_name} (${this._client.email}) to access the app as a homeowner?`)) return;

    try {
      const slug = CleanAPI._slug;
      const resp = await CleanAPI.request('POST', `/api/v1/clean/${slug}/clients/${this._clientId}/invite`);
      if (resp) {
        if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(resp.message || 'Invitation sent. They\'ll receive an email to set up their account.', 'success');
      }
    } catch (err) {
      if (typeof CleanClaw !== 'undefined') CleanClaw.showToast(err.detail || 'Could not send invitation. Please try again.', 'error');
    }
  },

  _esc(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },
};
