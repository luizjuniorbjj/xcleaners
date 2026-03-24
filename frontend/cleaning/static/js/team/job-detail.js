/**
 * CleanClaw — Team Job Detail Module (Sprint 3)
 *
 * Job execution view: client info, timer, room-by-room checklist,
 * photo capture, notes, report issue, check-out.
 */
window.TeamJobDetail = {
  _job: null,
  _timerInterval: null,
  _container: null,

  async render(container, params) {
    this._container = container;
    const bookingId = params?.id;
    if (!bookingId) {
      container.innerHTML = `
        <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
          <div class="cc-empty-state-title">No job ID specified</div>
        </div>
      `;
      return;
    }

    // Skeleton loading
    container.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <div style="display:flex;align-items:center;gap:var(--cc-space-3);">
          <div class="cc-skeleton" style="width:34px;height:34px;border-radius:var(--cc-radius-md);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:50%;height:20px;"></div>
        </div>
        <div class="cc-card" style="padding:var(--cc-space-5);">
          <div class="cc-skeleton cc-skeleton-text" style="width:30%;height:16px;"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:80%;margin-top:var(--cc-space-3);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:60%;margin-top:var(--cc-space-2);"></div>
        </div>
        <div class="cc-card" style="padding:var(--cc-space-5);">
          <div class="cc-skeleton cc-skeleton-text" style="width:25%;height:16px;"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:90%;margin-top:var(--cc-space-3);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:75%;margin-top:var(--cc-space-2);"></div>
        </div>
      </div>
    `;

    try {
      const resp = await CleanAPI.cleanGet(`/my-jobs/${bookingId}`);
      this._job = (resp && typeof resp === 'object' && resp.id) ? resp : null;
      if (!this._job) {
        container.innerHTML = `
          <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '?'}</div>
            <div class="cc-empty-state-title">Job not found</div>
            <button onclick="window.location.hash='#/team/today'" class="cc-btn cc-btn-secondary" style="margin-top:var(--cc-space-4);">Back to Today</button>
          </div>
        `;
        return;
      }
      this._renderJob(container);
    } catch (err) {
      console.error('[JobDetail] Error:', err);
      container.innerHTML = `
        <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
          <div class="cc-empty-state-title">Could not load job details</div>
          <button onclick="window.location.hash='#/team/today'" class="cc-btn cc-btn-secondary" style="margin-top:var(--cc-space-4);">Back to Today</button>
        </div>
      `;
    }
  },

  _renderJob(container) {
    const job = this._job;
    const isInProgress = job.status === 'in_progress';
    const isCompleted = job.status === 'completed';
    const isUpcoming = !isInProgress && !isCompleted;

    const statusMap = {
      'in_progress': 'cc-badge-success',
      'completed': 'cc-badge-neutral',
      'confirmed': 'cc-badge-primary',
      'scheduled': 'cc-badge-primary',
      'pending': 'cc-badge-warning',
    };
    const badgeClass = statusMap[job.status] || 'cc-badge-primary';

    container.innerHTML = `
      <div class="cc-job-detail cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <!-- Header -->
        <div style="display:flex;align-items:center;gap:var(--cc-space-3);">
          <button class="cc-btn cc-btn-ghost cc-btn-sm" onclick="window.location.hash='#/team/today'" style="padding:var(--cc-space-2);">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <h2 style="flex:1;margin:0;font-size:var(--cc-text-2xl);">${this._esc(job.client?.name || 'Client')}</h2>
          <span class="cc-badge ${badgeClass}">${(job.status || 'scheduled').replace('_', ' ')}</span>
        </div>

        <!-- Timer (visible when in_progress) -->
        ${isInProgress ? `
        <div class="cc-card" id="cc-job-timer" style="background:var(--cc-success-50);border:1px solid var(--cc-success-200);text-align:center;padding:var(--cc-space-4);">
          <div class="cc-text-xs cc-font-semibold" style="color:var(--cc-success-600);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:var(--cc-space-1);">Time on site</div>
          <div id="cc-timer-display" style="font-size:var(--cc-text-3xl);font-weight:var(--cc-font-bold);color:var(--cc-success-700);font-family:var(--cc-font-mono);">00:00:00</div>
        </div>
        ` : ''}

        <!-- Client Info Hero -->
        <div class="cc-card" style="padding:var(--cc-space-5);">
          <div class="cc-card-header">
            <span class="cc-card-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:-2px;margin-right:var(--cc-space-2);color:var(--cc-primary-500);"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              Client Info
            </span>
          </div>
          <div style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
            <div style="display:flex;align-items:flex-start;gap:var(--cc-space-3);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cc-neutral-400)" stroke-width="2" style="flex-shrink:0;margin-top:2px;"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
              <span class="cc-text-sm" style="color:var(--cc-neutral-700);">${this._esc(job.location?.address || 'No address')}</span>
            </div>
            ${job.client?.phone ? `
            <div style="display:flex;align-items:center;gap:var(--cc-space-3);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cc-neutral-400)" stroke-width="2" style="flex-shrink:0;"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72"/></svg>
              <a href="tel:${job.client.phone}" class="cc-text-sm" style="color:var(--cc-primary-500);text-decoration:none;">${this._esc(job.client.phone)}</a>
            </div>
            ` : ''}
            ${job.location?.access_instructions ? `
            <div style="background:var(--cc-warning-50);border:1px solid var(--cc-warning-200);border-radius:var(--cc-radius-md);padding:var(--cc-space-3);display:flex;align-items:flex-start;gap:var(--cc-space-2);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cc-warning-600)" stroke-width="2" style="flex-shrink:0;margin-top:1px;"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              <span class="cc-text-sm" style="color:var(--cc-warning-700);">${this._esc(job.location.access_instructions)}</span>
            </div>
            ` : ''}
            ${job.special_instructions ? `
            <div style="display:flex;align-items:flex-start;gap:var(--cc-space-3);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cc-neutral-400)" stroke-width="2" style="flex-shrink:0;margin-top:2px;"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              <span class="cc-text-sm" style="color:var(--cc-neutral-600);">${this._esc(job.special_instructions)}</span>
            </div>
            ` : ''}
            ${job.client?.has_pets ? `
            <div style="background:var(--cc-danger-50);border:1px solid var(--cc-danger-200);border-radius:var(--cc-radius-md);padding:var(--cc-space-3);display:flex;align-items:center;gap:var(--cc-space-2);">
              <span class="cc-badge cc-badge-danger">Pets</span>
              <span class="cc-text-sm" style="color:var(--cc-danger-700);">${this._esc(job.client.pet_details || 'Yes')}</span>
            </div>
            ` : ''}
            <div style="display:flex;align-items:center;gap:var(--cc-space-3);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cc-neutral-400)" stroke-width="2" style="flex-shrink:0;"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              <span class="cc-text-sm" style="color:var(--cc-neutral-700);">${this._esc(job.service?.name || 'Cleaning')} (${job.service?.estimated_duration || '?'}min)</span>
            </div>
          </div>
        </div>

        <!-- Navigate Button -->
        ${!isCompleted && job.location?.address ? `
        <button class="cc-btn cc-btn-secondary cc-btn-lg cc-btn-block" id="cc-btn-navigate">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="3 11 22 2 13 21 11 13 3 11"/></svg>
          Navigate to Address
        </button>
        ` : ''}

        <!-- Checklist -->
        ${job.checklist && job.checklist.length > 0 ? `
        <div class="cc-card" style="padding:var(--cc-space-5);">
          <div class="cc-card-header">
            <span class="cc-card-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:-2px;margin-right:var(--cc-space-2);color:var(--cc-primary-500);"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              Checklist
            </span>
            <span class="cc-text-sm cc-text-muted" id="cc-checklist-text">${this._checklistDoneCount()}/${job.checklist.length}</span>
          </div>
          <!-- Progress bar -->
          <div style="height:6px;background:var(--cc-neutral-200);border-radius:var(--cc-radius-full);overflow:hidden;margin-bottom:var(--cc-space-4);">
            <div id="cc-checklist-progress" style="height:100%;background:var(--cc-success-500);border-radius:var(--cc-radius-full);transition:width var(--cc-duration-normal) var(--cc-ease-default);width:${this._checklistProgress()}%;"></div>
          </div>
          <div id="cc-checklist-items">
            ${this._renderChecklist(job.checklist)}
          </div>
        </div>
        ` : ''}

        <!-- Notes Section -->
        <div class="cc-card" style="padding:var(--cc-space-5);">
          <div class="cc-card-header">
            <span class="cc-card-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline;vertical-align:-2px;margin-right:var(--cc-space-2);color:var(--cc-primary-500);"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="3"/></svg>
              Notes & Photos
            </span>
          </div>
          <div id="cc-job-notes-list" style="margin-bottom:var(--cc-space-3);">
            ${this._renderNotes(job.logs || [])}
          </div>
          ${!isCompleted ? `
          <div style="display:flex;flex-direction:column;gap:var(--cc-space-2);padding-top:var(--cc-space-3);border-top:1px solid var(--cc-neutral-100);">
            <textarea id="cc-note-input" class="cc-textarea" placeholder="Add a note..." rows="2" maxlength="2000" style="min-height:60px;"></textarea>
            <div style="display:flex;gap:var(--cc-space-2);">
              <button class="cc-btn cc-btn-secondary cc-btn-sm" id="cc-btn-photo">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="3"/></svg>
                Photo
              </button>
              <button class="cc-btn cc-btn-primary cc-btn-sm" id="cc-btn-add-note" style="margin-left:auto;">Add Note</button>
            </div>
            <input type="file" id="cc-photo-input" accept="image/*" capture="environment" style="display:none">
          </div>
          ` : ''}
        </div>

        <!-- Action Buttons -->
        <div style="display:flex;flex-direction:column;gap:var(--cc-space-3);margin-top:var(--cc-space-2);">
          ${isUpcoming ? `
            <button class="cc-btn cc-btn-primary cc-btn-lg cc-btn-block" id="cc-btn-checkin">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              Check In
            </button>
          ` : ''}
          ${isInProgress ? `
            <button class="cc-btn cc-btn-outline cc-btn-lg cc-btn-block" id="cc-btn-issue">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              Report Issue
            </button>
            <button class="cc-btn cc-btn-primary cc-btn-lg cc-btn-block" id="cc-btn-checkout">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
              Check Out
            </button>
          ` : ''}
        </div>
      </div>
    `;

    this._attachListeners();

    // Start timer if in_progress
    const timerStart = job.checkin_at || job.scheduling?.actual_start;
    if (isInProgress && timerStart) {
      this._startTimer(new Date(timerStart));
    } else if (isInProgress) {
      // No checkin_at yet, start from now
      this._startTimer(new Date());
    }
  },

  _renderChecklist(items) {
    // Group by room
    const rooms = {};
    items.forEach(item => {
      const room = item.room || 'General';
      if (!rooms[room]) rooms[room] = [];
      rooms[room].push(item);
    });

    let html = '';
    for (const [room, roomItems] of Object.entries(rooms)) {
      html += `<div style="margin-bottom:var(--cc-space-3);"><h4 class="cc-text-sm cc-font-semibold" style="color:var(--cc-neutral-600);margin-bottom:var(--cc-space-2);">${this._esc(room)}</h4>`;
      roomItems.forEach(item => {
        html += `
          <label class="cc-checkbox cc-checklist-item ${item.completed ? 'cc-completed' : ''}" data-item-id="${item.id}"
            style="display:flex;align-items:center;gap:var(--cc-space-3);padding:var(--cc-space-2) 0;${item.completed ? 'opacity:0.6;' : ''}">
            <input type="checkbox" ${item.completed ? 'checked disabled' : ''} class="cc-checkbox-input cc-checklist-checkbox">
            <span class="cc-text-sm" style="${item.completed ? 'text-decoration:line-through;' : ''}color:var(--cc-neutral-700);">${this._esc(item.task)}</span>
            ${item.is_required ? '<span class="cc-badge cc-badge-danger cc-badge-sm" style="margin-left:auto;">Required</span>' : ''}
          </label>
        `;
      });
      html += '</div>';
    }
    return html;
  },

  _renderNotes(logs) {
    const noteLogs = logs.filter(l => l.log_type === 'note' || l.log_type === 'photo' || l.log_type === 'issue');
    if (noteLogs.length === 0) return '<p class="cc-text-sm cc-text-muted">No notes yet.</p>';

    return noteLogs.map(log => {
      const time = log.timestamp ? new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
      const isIssue = log.log_type === 'issue';
      return `
        <div style="display:flex;gap:var(--cc-space-3);padding:var(--cc-space-3);border-radius:var(--cc-radius-md);${isIssue ? 'background:var(--cc-danger-50);border:1px solid var(--cc-danger-200);' : 'background:var(--cc-neutral-50);'}margin-bottom:var(--cc-space-2);">
          <div style="flex-shrink:0;">
            <span class="cc-badge ${isIssue ? 'cc-badge-danger' : log.log_type === 'photo' ? 'cc-badge-info' : 'cc-badge-neutral'} cc-badge-sm">${log.log_type}</span>
          </div>
          <div style="flex:1;min-width:0;">
            ${log.note ? `<p class="cc-text-sm" style="color:var(--cc-neutral-700);margin-bottom:var(--cc-space-1);">${this._esc(log.note)}</p>` : ''}
            ${log.photo_url ? `<img src="${log.photo_url}" style="max-width:100%;border-radius:var(--cc-radius-md);margin-bottom:var(--cc-space-1);" alt="Job photo">` : ''}
            <span class="cc-text-xs cc-text-muted">${time}</span>
          </div>
        </div>
      `;
    }).join('');
  },

  _attachListeners() {
    const job = this._job;
    const bookingId = job.id;

    // Navigate
    const navBtn = document.getElementById('cc-btn-navigate');
    if (navBtn) {
      navBtn.addEventListener('click', () => {
        if (job.location?.latitude && job.location?.longitude) {
          window.open(`https://www.google.com/maps/dir/?api=1&destination=${job.location.latitude},${job.location.longitude}`, '_blank');
        } else if (job.location?.address) {
          window.open(`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(job.location.address)}`, '_blank');
        }
      });
    }

    // Check-in
    const checkinBtn = document.getElementById('cc-btn-checkin');
    if (checkinBtn) {
      checkinBtn.addEventListener('click', () => this._doCheckIn(bookingId));
    }

    // Check-out
    const checkoutBtn = document.getElementById('cc-btn-checkout');
    if (checkoutBtn) {
      checkoutBtn.addEventListener('click', () => this._doCheckOut(bookingId));
    }

    // Report issue
    const issueBtn = document.getElementById('cc-btn-issue');
    if (issueBtn) {
      issueBtn.addEventListener('click', () => this._showIssueModal(bookingId));
    }

    // Add note
    const addNoteBtn = document.getElementById('cc-btn-add-note');
    if (addNoteBtn) {
      addNoteBtn.addEventListener('click', () => this._addNote(bookingId));
    }

    // Photo
    const photoBtn = document.getElementById('cc-btn-photo');
    const photoInput = document.getElementById('cc-photo-input');
    if (photoBtn && photoInput) {
      photoBtn.addEventListener('click', () => photoInput.click());
      photoInput.addEventListener('change', (e) => this._handlePhoto(bookingId, e));
    }

    // Checklist items
    document.querySelectorAll('.cc-checklist-checkbox:not(:checked)').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const itemId = e.target.closest('.cc-checklist-item').dataset.itemId;
        this._completeChecklistItem(bookingId, itemId, e.target);
      });
    });
  },

  async _doCheckIn(bookingId) {
    const btn = document.getElementById('cc-btn-checkin');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="cc-loading-overlay-spinner" style="width:16px;height:16px;display:inline-block;"></span> Getting location...'; }

    try {
      let lat = null, lng = null, accuracy = null;
      let gpsNote = null;
      try {
        const pos = await this._getPosition();
        lat = pos.coords.latitude;
        lng = pos.coords.longitude;
        accuracy = pos.coords.accuracy;

        // Proximity check against job address
        const jobLat = this._job?.location?.latitude;
        const jobLng = this._job?.location?.longitude;
        if (jobLat && jobLng && lat && lng) {
          const distance = this._haversineDistance(lat, lng, jobLat, jobLng);
          if (distance > 1000) {
            // >1km: Red warning, require note
            const proceed = await this._showProximityWarning(distance, accuracy, true);
            if (!proceed) { if (btn) { btn.disabled = false; btn.textContent = 'Check In'; } return; }
            gpsNote = proceed.note || `GPS override: ${(distance / 1000).toFixed(1)} km away`;
          } else if (distance > 200) {
            // 200m-1km: Yellow warning, allow override
            const proceed = await this._showProximityWarning(distance, accuracy, false);
            if (!proceed) { if (btn) { btn.disabled = false; btn.textContent = 'Check In'; } return; }
          }
          // <200m: proceed silently
        }
      } catch (e) {
        // GPS unavailable — allow check-in with warning
        const proceed = await this._showGpsUnavailableWarning();
        if (!proceed) { if (btn) { btn.disabled = false; btn.textContent = 'Check In'; } return; }
        gpsNote = 'Checked in without GPS verification';
      }

      if (btn) { btn.textContent = 'Checking in...'; }
      const payload = { lat, lng };
      if (gpsNote) payload.gps_note = gpsNote;
      const result = await CleanAPI.cleanPost(`/my-jobs/${bookingId}/checkin`, payload);
      if (result && (result.success || result.status === 'in_progress' || result.checkin_at)) {
        CleanClaw.showToast('Checked in. Have a great cleaning!', 'success');
        // Update local job data so timer starts
        if (this._job) {
          this._job.status = 'in_progress';
          this._job.checkin_at = result.checkin_at || new Date().toISOString();
        }
        this.render(this._container, { id: bookingId });
      }
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Check-in failed. Please try again.', 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Check In'; }
    }
  },

  /** Calculate distance between two lat/lng points in meters (Haversine formula) */
  _haversineDistance(lat1, lon1, lat2, lon2) {
    const R = 6371000; // Earth radius in meters
    const toRad = (d) => d * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  },

  /** Show proximity warning modal. Returns promise: false if cancelled, {note} if confirmed */
  _showProximityWarning(distanceMeters, accuracy, requireNote) {
    return new Promise((resolve) => {
      const distLabel = distanceMeters >= 1000 ? `${(distanceMeters / 1000).toFixed(1)} km` : `${Math.round(distanceMeters)}m`;
      const accLabel = accuracy ? `GPS accuracy: ~${Math.round(accuracy)}m` : '';
      const isFar = distanceMeters > 1000;
      const borderColor = isFar ? 'var(--cc-danger-200)' : 'var(--cc-warning-200)';
      const bgColor = isFar ? 'var(--cc-danger-50)' : 'var(--cc-warning-50)';
      const iconColor = isFar ? 'var(--cc-danger-500)' : 'var(--cc-warning-500)';

      const modal = document.createElement('div');
      modal.className = 'cc-modal-overlay';
      modal.innerHTML = `
        <div class="cc-modal" style="max-width:380px;">
          <div style="text-align:center;padding:var(--cc-space-4) 0;">
            <div style="width:56px;height:56px;border-radius:50%;background:${bgColor};border:2px solid ${borderColor};display:inline-flex;align-items:center;justify-content:center;margin-bottom:var(--cc-space-3);">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="${iconColor}" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            </div>
            <h3 style="margin:0 0 var(--cc-space-2);">${isFar ? 'Far from job location' : 'Distance notice'}</h3>
            <p class="cc-text-sm" style="color:var(--cc-neutral-600);margin:0;">You appear to be <strong>${distLabel}</strong> from the job address.</p>
            ${accLabel ? `<p class="cc-text-xs cc-text-muted" style="margin:var(--cc-space-1) 0 0;">${accLabel}</p>` : ''}
          </div>
          ${requireNote ? `
          <div class="cc-form-group" style="margin-top:var(--cc-space-3);">
            <label class="cc-label">Reason (required)</label>
            <textarea id="cc-proximity-note" class="cc-textarea" rows="2" placeholder="e.g. I'm inside the building, GPS is inaccurate..." required></textarea>
          </div>
          ` : ''}
          <div class="cc-modal-actions" style="margin-top:var(--cc-space-4);">
            <button class="cc-btn cc-btn-secondary" id="cc-prox-cancel">Cancel</button>
            <button class="cc-btn ${isFar ? 'cc-btn-danger' : 'cc-btn-primary'}" id="cc-prox-confirm">Check In Anyway</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      document.getElementById('cc-prox-cancel').addEventListener('click', () => { modal.remove(); resolve(false); });
      document.getElementById('cc-prox-confirm').addEventListener('click', () => {
        if (requireNote) {
          const note = document.getElementById('cc-proximity-note').value.trim();
          if (!note) { CleanClaw.showToast('Please provide a reason.', 'warning'); return; }
          modal.remove();
          resolve({ note });
        } else {
          modal.remove();
          resolve(true);
        }
      });
    });
  },

  /** Show GPS unavailable warning. Returns promise: true to proceed, false to cancel */
  _showGpsUnavailableWarning() {
    return new Promise((resolve) => {
      const modal = document.createElement('div');
      modal.className = 'cc-modal-overlay';
      modal.innerHTML = `
        <div class="cc-modal" style="max-width:360px;">
          <div style="text-align:center;padding:var(--cc-space-4) 0;">
            <div style="width:56px;height:56px;border-radius:50%;background:var(--cc-warning-50);border:2px solid var(--cc-warning-200);display:inline-flex;align-items:center;justify-content:center;margin-bottom:var(--cc-space-3);">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--cc-warning-500)" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
            <h3 style="margin:0 0 var(--cc-space-2);">GPS Unavailable</h3>
            <p class="cc-text-sm" style="color:var(--cc-neutral-600);margin:0;">CleanClaw needs your location to verify check-in. Your check-in will be recorded without GPS.</p>
            <div class="cc-text-xs cc-text-muted" style="margin-top:var(--cc-space-3);text-align:left;">
              <p style="margin:0 0 var(--cc-space-1);">Tips:</p>
              <ul style="margin:0;padding-left:var(--cc-space-4);">
                <li>Go outside briefly</li>
                <li>Turn on Wi-Fi (helps GPS accuracy)</li>
              </ul>
            </div>
          </div>
          <div class="cc-modal-actions" style="margin-top:var(--cc-space-4);">
            <button class="cc-btn cc-btn-secondary" id="cc-gps-retry">Retry</button>
            <button class="cc-btn cc-btn-primary" id="cc-gps-proceed">Check In Without GPS</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      document.getElementById('cc-gps-retry').addEventListener('click', () => { modal.remove(); resolve('retry'); });
      document.getElementById('cc-gps-proceed').addEventListener('click', () => { modal.remove(); resolve(true); });
    });
  },

  async _doCheckOut(bookingId) {
    if (!confirm('Are you sure you want to check out?')) return;

    const btn = document.getElementById('cc-btn-checkout');
    if (btn) { btn.disabled = true; btn.textContent = 'Checking out...'; }

    try {
      let lat = null, lng = null;
      try {
        const pos = await this._getPosition();
        lat = pos.coords.latitude;
        lng = pos.coords.longitude;
      } catch (e) { /* GPS unavailable */ }

      const noteInput = document.getElementById('cc-note-input');
      const notes = noteInput ? noteInput.value.trim() : null;

      const result = await CleanAPI.cleanPost(`/my-jobs/${bookingId}/checkout`, { lat, lng, notes: notes || null });
      if (result && (result.success || result.status === 'completed' || result.checkout_at)) {
        this._stopTimer();
        // Calculate duration
        const checkinTime = this._job?.checkin_at ? new Date(this._job.checkin_at) : null;
        const duration = checkinTime ? Math.round((Date.now() - checkinTime.getTime()) / 60000) : 0;
        CleanClaw.showToast(`Checked out. Job completed in ${duration || result.actual_duration_minutes || '?'} minutes.`, 'success');
        if (this._job) {
          this._job.status = 'completed';
          this._job.checkout_at = result.checkout_at || new Date().toISOString();
        }
        this.render(this._container, { id: bookingId });
      }
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Check-out failed. Please try again.', 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Check Out'; }
    }
  },

  async _completeChecklistItem(bookingId, itemId, checkbox) {
    try {
      const result = await CleanAPI.cleanPost(`/my-jobs/${bookingId}/checklist/${itemId}/complete`, {});
      if (result && result.success) {
        checkbox.disabled = true;
        const label = checkbox.closest('.cc-checklist-item');
        label.classList.add('cc-completed');
        label.style.opacity = '0.6';
        const textSpan = label.querySelector('span');
        if (textSpan) textSpan.style.textDecoration = 'line-through';
        // Bounce animation
        checkbox.style.animation = 'cc-bounce-in var(--cc-duration-normal) var(--cc-ease-bounce)';
        this._updateChecklistProgress();
      }
    } catch (err) {
      checkbox.checked = false;
      CleanClaw.showToast(err.detail || 'Could not complete checklist item. Please try again.', 'error');
    }
  },

  async _addNote(bookingId) {
    const input = document.getElementById('cc-note-input');
    const note = input ? input.value.trim() : '';
    if (!note) {
      CleanClaw.showToast('Please enter a note.', 'warning');
      return;
    }

    try {
      const result = await CleanAPI.cleanPost(`/my-jobs/${bookingId}/note`, { note });
      if (result && result.success) {
        input.value = '';
        CleanClaw.showToast('Note added to this job.', 'success');
        // Refresh notes list
        this.render(this._container, { id: bookingId });
      }
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Could not add note. Please try again.', 'error');
    }
  },

  async _handlePhoto(bookingId, event) {
    const file = event.target.files?.[0];
    if (!file) return;

    // For now, create a data URL (in production, upload to storage)
    const reader = new FileReader();
    reader.onload = async (e) => {
      const photoUrl = e.target.result;
      try {
        const result = await CleanAPI.cleanPost(`/my-jobs/${bookingId}/note`, { photo_url: photoUrl });
        if (result && result.success) {
          CleanClaw.showToast('Photo added to this job.', 'success');
          this.render(this._container, { id: bookingId });
        }
      } catch (err) {
        CleanClaw.showToast('Could not upload photo. Please try again.', 'error');
      }
    };
    reader.readAsDataURL(file);
  },

  _showIssueModal(bookingId) {
    const types = [
      { value: 'locked_out', label: 'Locked Out' },
      { value: 'client_not_home', label: 'Client Not Home' },
      { value: 'pet_problem', label: 'Pet Problem' },
      { value: 'damage_found', label: 'Damage Found' },
      { value: 'supplies_needed', label: 'Supplies Needed' },
      { value: 'other', label: 'Other' },
    ];

    const modal = document.createElement('div');
    modal.className = 'cc-modal-overlay';
    modal.innerHTML = `
      <div class="cc-modal">
        <h3>Report Issue</h3>
        <div class="cc-form-group">
          <label class="cc-label">Issue Type</label>
          <select id="cc-issue-type" class="cc-select">
            ${types.map(t => `<option value="${t.value}">${t.label}</option>`).join('')}
          </select>
        </div>
        <div class="cc-form-group">
          <label class="cc-label">Description</label>
          <textarea id="cc-issue-desc" class="cc-textarea" rows="3" placeholder="Describe the issue..." required></textarea>
        </div>
        <div class="cc-modal-actions">
          <button class="cc-btn cc-btn-secondary" id="cc-issue-cancel">Cancel</button>
          <button class="cc-btn cc-btn-primary" id="cc-issue-submit">Report</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    document.getElementById('cc-issue-cancel').addEventListener('click', () => modal.remove());
    document.getElementById('cc-issue-submit').addEventListener('click', async () => {
      const issueType = document.getElementById('cc-issue-type').value;
      const description = document.getElementById('cc-issue-desc').value.trim();
      if (!description) {
        CleanClaw.showToast('Please describe the issue.', 'warning');
        return;
      }
      try {
        const result = await CleanAPI.cleanPost(`/my-jobs/${bookingId}/issue`, {
          issue_type: issueType,
          description,
        });
        if (result && result.success) {
          CleanClaw.showToast('Issue reported. Your manager has been notified.', 'success');
          modal.remove();
        }
      } catch (err) {
        CleanClaw.showToast(err.detail || 'Could not report issue. Please try again.', 'error');
      }
    });
  },

  // Timer
  _startTimer(startTime) {
    this._stopTimer();
    const display = document.getElementById('cc-timer-display');
    if (!display) return;

    this._timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime.getTime()) / 1000);
      const h = Math.floor(elapsed / 3600);
      const m = Math.floor((elapsed % 3600) / 60);
      const s = elapsed % 60;
      display.textContent = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }, 1000);
  },

  _stopTimer() {
    if (this._timerInterval) {
      clearInterval(this._timerInterval);
      this._timerInterval = null;
    }
  },

  _checklistProgress() {
    if (!this._job?.checklist?.length) return 0;
    const done = this._job.checklist.filter(i => i.completed).length;
    return Math.round((done / this._job.checklist.length) * 100);
  },

  _checklistDoneCount() {
    if (!this._job?.checklist) return 0;
    return this._job.checklist.filter(i => i.completed).length;
  },

  _updateChecklistProgress() {
    const items = document.querySelectorAll('.cc-checklist-item');
    const total = items.length;
    const done = document.querySelectorAll('.cc-checklist-item.cc-completed').length;
    const bar = document.getElementById('cc-checklist-progress');
    const text = document.getElementById('cc-checklist-text');
    if (bar) bar.style.width = `${Math.round((done / total) * 100)}%`;
    if (text) text.textContent = `${done}/${total}`;
  },

  _getPosition() {
    return new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 10000,
      });
    });
  },

  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },
};
