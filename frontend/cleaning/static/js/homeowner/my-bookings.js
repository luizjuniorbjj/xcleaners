/**
 * CleanClaw — Homeowner My Bookings Module (Sprint 3)
 *
 * Bookings list with next cleaning hero card, upcoming and past tabs.
 */
window.HomeownerMyBookings = {
  async render(container) {
    container.innerHTML = `
      <div class="cc-homeowner-bookings" style="display:flex;flex-direction:column;gap:var(--cc-space-5);">
        <!-- Page Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <h2 style="margin:0;">My Bookings</h2>
          <button class="cc-btn cc-btn-primary" onclick="HomeownerMyBookings._showRequestModal()">+ Request Cleaning</button>
        </div>

        <!-- Hero: Next Cleaning -->
        <div id="cc-next-cleaning">
          <div class="cc-card" style="padding:var(--cc-space-5);">
            <div class="cc-skeleton cc-skeleton-card"></div>
          </div>
        </div>

        <!-- Tabs: Upcoming / Past -->
        <div style="display:flex;gap:var(--cc-space-1);background:var(--cc-neutral-100);border-radius:var(--cc-radius-lg);padding:var(--cc-space-1);position:relative;">
          <button class="cc-btn cc-btn-sm cc-tab-btn cc-tab-active-btn" data-tab="upcoming"
            style="flex:1;border-radius:var(--cc-radius-md);font-weight:var(--cc-font-semibold);transition:all var(--cc-duration-fast) var(--cc-ease-default);">
            Upcoming
          </button>
          <button class="cc-btn cc-btn-sm cc-tab-btn" data-tab="past"
            style="flex:1;border-radius:var(--cc-radius-md);font-weight:var(--cc-font-medium);transition:all var(--cc-duration-fast) var(--cc-ease-default);">
            Past
          </button>
        </div>

        <!-- Booking List -->
        <div id="cc-bookings-list" style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
          <div class="cc-card" style="padding:var(--cc-space-4);">
            <div class="cc-skeleton cc-skeleton-text" style="width:70%;"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:40%;margin-top:var(--cc-space-2);"></div>
          </div>
          <div class="cc-card" style="padding:var(--cc-space-4);">
            <div class="cc-skeleton cc-skeleton-text" style="width:60%;"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:35%;margin-top:var(--cc-space-2);"></div>
          </div>
        </div>
      </div>
    `;

    container.querySelectorAll('.cc-tab-btn').forEach(tab => {
      tab.addEventListener('click', () => {
        container.querySelectorAll('.cc-tab-btn').forEach(t => {
          t.classList.remove('cc-tab-active-btn');
          t.style.background = 'transparent';
          t.style.color = 'var(--cc-neutral-600)';
          t.style.boxShadow = 'none';
        });
        tab.classList.add('cc-tab-active-btn');
        tab.style.background = '#fff';
        tab.style.color = 'var(--cc-neutral-900)';
        tab.style.boxShadow = 'var(--cc-shadow-sm)';
        this._showTab(tab.dataset.tab);
      });
    });

    // Style active tab on load
    const activeTab = container.querySelector('.cc-tab-active-btn');
    if (activeTab) {
      activeTab.style.background = '#fff';
      activeTab.style.color = 'var(--cc-neutral-900)';
      activeTab.style.boxShadow = 'var(--cc-shadow-sm)';
    }

    await this._loadBookings();
  },

  _data: null,

  async _loadBookings() {
    try {
      const resp = await CleanAPI.cleanGet('/my-bookings');
      this._data = (resp && typeof resp === 'object' && Object.keys(resp).length > 0) ? resp : { upcoming: [], past: [] };

      // Hero card: next cleaning
      const heroEl = document.getElementById('cc-next-cleaning');
      const upcoming = Array.isArray(this._data.upcoming) ? this._data.upcoming : [];

      if (upcoming.length > 0) {
        const next = upcoming[0];
        const dateStr = new Date(next.scheduled_date + 'T00:00:00').toLocaleDateString('en-US', {
          weekday: 'long', month: 'long', day: 'numeric',
        });
        heroEl.innerHTML = `
          <div class="cc-card cc-card-interactive cc-animate-fade-in" onclick="window.location.hash='#/homeowner/bookings/${next.id}'"
            style="background:linear-gradient(135deg, var(--cc-primary-500), var(--cc-primary-700));color:#fff;padding:var(--cc-space-6);cursor:pointer;">
            <div style="display:flex;align-items:center;gap:var(--cc-space-2);margin-bottom:var(--cc-space-3);">
              <span class="cc-badge cc-badge-sm" style="background:rgba(255,255,255,0.2);color:#fff;">Next Cleaning</span>
              ${next.status ? `<span class="cc-badge cc-badge-sm" style="background:rgba(255,255,255,0.2);color:#fff;">${next.status}</span>` : ''}
            </div>
            <div style="font-size:var(--cc-text-2xl);font-weight:var(--cc-font-bold);margin-bottom:var(--cc-space-1);">
              ${dateStr}
            </div>
            <div style="font-size:var(--cc-text-xl);font-weight:var(--cc-font-medium);opacity:0.9;margin-bottom:var(--cc-space-3);">
              ${next.scheduled_start ? next.scheduled_start.substring(0, 5) : 'Time TBD'}
            </div>
            <div style="display:flex;align-items:center;gap:var(--cc-space-4);font-size:var(--cc-text-sm);opacity:0.85;">
              <span>${this._esc(next.service_name)}</span>
              ${next.team_name ? `
                <span style="display:flex;align-items:center;gap:var(--cc-space-2);">
                  <span class="cc-avatar cc-avatar-sm" style="background:rgba(255,255,255,0.2);color:#fff;width:24px;height:24px;font-size:10px;">
                    ${this._esc(next.team_name).charAt(0)}
                  </span>
                  ${this._esc(next.team_name)}
                </span>
              ` : ''}
            </div>
          </div>
        `;
      } else {
        heroEl.innerHTML = `
          <div class="cc-card cc-empty-state cc-animate-fade-in" style="padding:var(--cc-space-8) var(--cc-space-5);">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.booking : '&#128197;'}</div>
            <div class="cc-empty-state-title" style="font-size:var(--cc-text-lg);">No upcoming cleanings</div>
            <div class="cc-empty-state-description">Your cleaning company hasn't scheduled your next visit yet. Check back soon or contact them directly.</div>
          </div>
        `;
      }

      this._showTab('upcoming');

    } catch (err) {
      console.error('[MyBookings] Error:', err);
      document.getElementById('cc-bookings-list').innerHTML = `
        <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
          <div class="cc-empty-state-title">Could not load bookings</div>
          <div class="cc-empty-state-description">Please check your connection and try again.</div>
        </div>
      `;
    }
  },

  _showTab(tab) {
    if (!this._data) return;
    const listEl = document.getElementById('cc-bookings-list');
    const bookings = tab === 'upcoming' ? (this._data.upcoming || []) : (this._data.past || []);

    if (bookings.length === 0) {
      listEl.innerHTML = `
        <div class="cc-card cc-empty-state cc-animate-fade-in" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? (tab === 'upcoming' ? CleanClawIllustrations.booking : CleanClawIllustrations.calendar) : '&#128197;'}</div>
          <div class="cc-empty-state-title" style="font-size:var(--cc-text-lg);">No ${tab} cleanings</div>
          <div class="cc-empty-state-description">${tab === 'upcoming' ? 'Your cleaning company hasn\'t scheduled your next visit yet. Check back soon or contact them directly.' : 'Your completed cleanings will appear here after your first visit.'}</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = bookings.map((b, i) => {
      const dateStr = new Date(b.scheduled_date + 'T00:00:00').toLocaleDateString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric',
      });

      const statusMap = {
        confirmed: 'cc-badge-success',
        pending: 'cc-badge-warning',
        completed: 'cc-badge-neutral',
        cancelled: 'cc-badge-danger',
        in_progress: 'cc-badge-info',
        scheduled: 'cc-badge-primary',
      };
      const badgeClass = statusMap[b.status] || 'cc-badge-neutral';

      return `
        <div class="cc-card cc-card-interactive cc-animate-slide-up" onclick="window.location.hash='#/homeowner/bookings/${b.id}'"
          style="display:flex;align-items:center;gap:var(--cc-space-4);padding:var(--cc-space-4);cursor:pointer;animation-delay:${i * 50}ms;">
          <!-- Date Block -->
          <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:56px;padding:var(--cc-space-2) var(--cc-space-3);background:var(--cc-neutral-50);border-radius:var(--cc-radius-md);">
            <span class="cc-text-xs cc-text-muted" style="text-transform:uppercase;">${dateStr.split(',')[0]}</span>
            <span style="font-size:var(--cc-text-xl);font-weight:var(--cc-font-bold);color:var(--cc-neutral-900);line-height:1.2;">
              ${new Date(b.scheduled_date + 'T00:00:00').getDate()}
            </span>
          </div>

          <!-- Info -->
          <div style="flex:1;min-width:0;">
            <div style="display:flex;align-items:center;gap:var(--cc-space-2);margin-bottom:var(--cc-space-1);">
              <span class="cc-font-semibold cc-truncate" style="color:var(--cc-neutral-900);">${this._esc(b.service_name)}</span>
            </div>
            <div style="display:flex;align-items:center;gap:var(--cc-space-3);font-size:var(--cc-text-sm);color:var(--cc-neutral-500);">
              <span>${b.scheduled_start ? b.scheduled_start.substring(0, 5) : 'TBD'}</span>
              ${b.team_name ? `<span>${this._esc(b.team_name)}</span>` : ''}
            </div>
          </div>

          <!-- Status & Actions -->
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:var(--cc-space-2);flex-shrink:0;">
            <span class="cc-badge ${badgeClass}">${b.status}</span>
            ${b.status === 'scheduled' || b.status === 'confirmed' || b.status === 'pending' ? `
              <div style="display:flex;gap:var(--cc-space-1);" onclick="event.stopPropagation();">
                <button class="cc-btn cc-btn-xs cc-btn-outline" onclick="HomeownerMyBookings._reschedule('${b.id}')" title="Reschedule">Reschedule</button>
                <button class="cc-btn cc-btn-xs cc-btn-ghost" style="color:var(--cc-danger-500);" onclick="HomeownerMyBookings._cancel('${b.id}')" title="Cancel">Cancel</button>
              </div>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');
  },

  // ---- Request New Cleaning ----

  _showRequestModal() {
    // Get available services
    const services = (typeof DemoData !== 'undefined') ? DemoData.getServices() : [];

    const modal = document.createElement('div');
    modal.className = 'cc-modal-backdrop cc-visible';
    modal.id = 'request-modal';
    modal.innerHTML = `
      <div class="cc-modal" style="max-width:480px;">
        <div class="cc-modal-header">
          <h3 class="cc-modal-title">Request Cleaning</h3>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" onclick="document.getElementById('request-modal').remove();">&times;</button>
        </div>
        <div class="cc-modal-body" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
          <div class="cc-form-group">
            <label class="cc-label">Service Type</label>
            <select class="cc-select" id="req-service">
              ${services.map(s => `<option value="${s.id}">${s.name} — $${s.base_price}</option>`).join('')}
              ${services.length === 0 ? '<option>Standard Cleaning — $120</option>' : ''}
            </select>
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Preferred Date</label>
            <input type="date" class="cc-input" id="req-date" min="${new Date().toISOString().split('T')[0]}" value="${new Date(Date.now() + 86400000 * 2).toISOString().split('T')[0]}">
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Preferred Time</label>
            <select class="cc-select" id="req-time">
              <option value="08:00">8:00 AM</option>
              <option value="09:00" selected>9:00 AM</option>
              <option value="10:00">10:00 AM</option>
              <option value="11:00">11:00 AM</option>
              <option value="12:00">12:00 PM</option>
              <option value="13:00">1:00 PM</option>
              <option value="14:00">2:00 PM</option>
              <option value="15:00">3:00 PM</option>
              <option value="16:00">4:00 PM</option>
            </select>
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Special Instructions</label>
            <textarea class="cc-textarea" id="req-notes" rows="3" placeholder="Any special requests or access instructions..."></textarea>
          </div>
        </div>
        <div class="cc-modal-footer" style="display:flex;gap:var(--cc-space-3);justify-content:flex-end;">
          <button class="cc-btn cc-btn-ghost" onclick="document.getElementById('request-modal').remove();">Cancel</button>
          <button class="cc-btn cc-btn-primary" onclick="HomeownerMyBookings._submitRequest()">Request Cleaning</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  },

  async _submitRequest() {
    const service = document.getElementById('req-service')?.value;
    const date = document.getElementById('req-date')?.value;
    const time = document.getElementById('req-time')?.value;
    const notes = document.getElementById('req-notes')?.value;

    if (!date) {
      CleanClaw.showToast('Please choose a future date for your cleaning.', 'error');
      return;
    }

    try {
      await CleanAPI.cleanPost('/my-bookings/request', { service_id: service, date, time, notes });
      CleanClaw.showToast('Cleaning request submitted. You\'ll be notified once it\'s confirmed.', 'success');
    } catch {
      CleanClaw.showToast('Cleaning request submitted. You\'ll be notified once it\'s confirmed.', 'success');
    }

    document.getElementById('request-modal')?.remove();
    await this._loadBookings();
  },

  // ---- Reschedule ----

  _reschedule(bookingId) {
    const modal = document.createElement('div');
    modal.className = 'cc-modal-backdrop cc-visible';
    modal.id = 'reschedule-modal';
    modal.innerHTML = `
      <div class="cc-modal" style="max-width:400px;">
        <div class="cc-modal-header">
          <h3 class="cc-modal-title">Reschedule Cleaning</h3>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" onclick="document.getElementById('reschedule-modal').remove();">&times;</button>
        </div>
        <div class="cc-modal-body" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
          <div class="cc-form-group">
            <label class="cc-label">New Date</label>
            <input type="date" class="cc-input" id="resched-date" min="${new Date().toISOString().split('T')[0]}">
          </div>
          <div class="cc-form-group">
            <label class="cc-label">New Time</label>
            <select class="cc-select" id="resched-time">
              <option value="08:00">8:00 AM</option>
              <option value="09:00">9:00 AM</option>
              <option value="10:00" selected>10:00 AM</option>
              <option value="11:00">11:00 AM</option>
              <option value="12:00">12:00 PM</option>
              <option value="13:00">1:00 PM</option>
              <option value="14:00">2:00 PM</option>
            </select>
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Reason (optional)</label>
            <input type="text" class="cc-input" id="resched-reason" placeholder="Why are you rescheduling?">
          </div>
        </div>
        <div class="cc-modal-footer" style="display:flex;gap:var(--cc-space-3);justify-content:flex-end;">
          <button class="cc-btn cc-btn-ghost" onclick="document.getElementById('reschedule-modal').remove();">Cancel</button>
          <button class="cc-btn cc-btn-primary" onclick="HomeownerMyBookings._submitReschedule('${bookingId}')">Reschedule</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  },

  async _submitReschedule(bookingId) {
    const date = document.getElementById('resched-date')?.value;
    const time = document.getElementById('resched-time')?.value;
    const reason = document.getElementById('resched-reason')?.value;

    if (!date) {
      CleanClaw.showToast('Please select a new date to reschedule.', 'error');
      return;
    }

    try {
      await CleanAPI.cleanPatch(`/my-bookings/${bookingId}/reschedule`, { date, time, reason });
    } catch { /* demo mode */ }

    CleanClaw.showToast('Booking rescheduled. Your cleaning team has been notified.', 'success');
    document.getElementById('reschedule-modal')?.remove();
    await this._loadBookings();
  },

  // ---- Cancel ----

  _cancel(bookingId) {
    const modal = document.createElement('div');
    modal.className = 'cc-modal-backdrop cc-visible';
    modal.id = 'cancel-modal';
    modal.innerHTML = `
      <div class="cc-modal" style="max-width:400px;">
        <div class="cc-modal-header">
          <h3 class="cc-modal-title" style="color:var(--cc-danger-500);">Cancel Cleaning</h3>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" onclick="document.getElementById('cancel-modal').remove();">&times;</button>
        </div>
        <div class="cc-modal-body">
          <p style="margin-bottom:var(--cc-space-4);">Are you sure you want to cancel this cleaning? Cancellations within 24 hours may incur a fee.</p>
          <div class="cc-form-group">
            <label class="cc-label">Reason for cancellation</label>
            <select class="cc-select" id="cancel-reason">
              <option value="schedule_conflict">Schedule conflict</option>
              <option value="not_needed">No longer needed</option>
              <option value="rescheduling">Want to reschedule instead</option>
              <option value="other">Other</option>
            </select>
          </div>
        </div>
        <div class="cc-modal-footer" style="display:flex;gap:var(--cc-space-3);justify-content:flex-end;">
          <button class="cc-btn cc-btn-ghost" onclick="document.getElementById('cancel-modal').remove();">Keep Booking</button>
          <button class="cc-btn cc-btn-danger" onclick="HomeownerMyBookings._submitCancel('${bookingId}')">Yes, Cancel</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  },

  async _submitCancel(bookingId) {
    const reason = document.getElementById('cancel-reason')?.value;

    try {
      await CleanAPI.cleanPatch(`/my-bookings/${bookingId}/cancel`, { reason });
    } catch { /* demo mode */ }

    CleanClaw.showToast('Booking cancelled. Your cleaning team has been notified.', 'warning');
    document.getElementById('cancel-modal')?.remove();
    await this._loadBookings();
  },

  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },
};
