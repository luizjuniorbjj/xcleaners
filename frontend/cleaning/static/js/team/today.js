/**
 * CleanClaw — Team Today Module (Sprint 3)
 *
 * Today's jobs for the cleaner's team, ordered by time.
 * Features: job cards with status, navigate button, check-in/out, pull-to-refresh.
 */
window.TeamToday = {
  _jobs: [],
  _container: null,
  _refreshing: false,

  async render(container) {
    this._container = container;
    container.innerHTML = `
      <div class="cc-team-today" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <!-- Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <h2 style="margin:0;">Today's Jobs</h2>
          <button id="cc-today-refresh" class="cc-btn cc-btn-ghost cc-btn-sm" title="Refresh">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 4v6h6M23 20v-6h-6"/>
              <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
            </svg>
          </button>
        </div>

        <!-- Summary Stats (skeleton) -->
        <div id="cc-today-summary" style="display:grid;grid-template-columns:repeat(3,1fr);gap:var(--cc-space-3);">
          <div class="cc-card" style="padding:var(--cc-space-3);text-align:center;">
            <div class="cc-skeleton" style="width:32px;height:24px;margin:0 auto var(--cc-space-1);"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:50%;margin:0 auto;"></div>
          </div>
          <div class="cc-card" style="padding:var(--cc-space-3);text-align:center;">
            <div class="cc-skeleton" style="width:32px;height:24px;margin:0 auto var(--cc-space-1);"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:50%;margin:0 auto;"></div>
          </div>
          <div class="cc-card" style="padding:var(--cc-space-3);text-align:center;">
            <div class="cc-skeleton" style="width:32px;height:24px;margin:0 auto var(--cc-space-1);"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:50%;margin:0 auto;"></div>
          </div>
        </div>

        <!-- Job List (skeleton) -->
        <div id="cc-today-list" style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
          <div class="cc-card cc-job-card" style="border-left-color:var(--cc-neutral-200);">
            <div class="cc-skeleton cc-skeleton-text" style="width:30%;height:16px;"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:60%;margin-top:var(--cc-space-2);"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:80%;margin-top:var(--cc-space-2);"></div>
          </div>
          <div class="cc-card cc-job-card" style="border-left-color:var(--cc-neutral-200);">
            <div class="cc-skeleton cc-skeleton-text" style="width:25%;height:16px;"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:55%;margin-top:var(--cc-space-2);"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:70%;margin-top:var(--cc-space-2);"></div>
          </div>
        </div>
      </div>
    `;

    document.getElementById('cc-today-refresh').addEventListener('click', () => this.loadJobs());

    // Pull-to-refresh via touch
    this._setupPullToRefresh(container);

    await this.loadJobs();
  },

  async loadJobs() {
    if (this._refreshing) return;
    this._refreshing = true;

    const listEl = document.getElementById('cc-today-list');
    const summaryEl = document.getElementById('cc-today-summary');

    try {
      const rawData = await CleanAPI.cleanGet('/my-jobs/today');
      const data = (rawData && typeof rawData === 'object' && Object.keys(rawData).length > 0) ? rawData : { jobs: [], summary: { total: 0, completed: 0, active: 0 } };

      this._jobs = Array.isArray(data.jobs) ? data.jobs : [];
      const s = data.summary || { total: data.total || this._jobs.length, completed: data.completed || this._jobs.filter(j => j.status === 'completed').length, active: data.active || data.in_progress || this._jobs.filter(j => j.status === 'in_progress').length };

      // Summary stats
      summaryEl.innerHTML = `
        <div class="cc-card cc-animate-fade-in" style="padding:var(--cc-space-3);text-align:center;">
          <div style="font-size:var(--cc-text-2xl);font-weight:var(--cc-font-bold);color:var(--cc-neutral-900);">${s.total || this._jobs.length}</div>
          <div class="cc-text-xs cc-text-muted">Total</div>
        </div>
        <div class="cc-card cc-animate-fade-in" style="padding:var(--cc-space-3);text-align:center;animation-delay:50ms;">
          <div style="font-size:var(--cc-text-2xl);font-weight:var(--cc-font-bold);color:var(--cc-success-500);">${s.completed || 0}</div>
          <div class="cc-text-xs cc-text-muted">Done</div>
        </div>
        <div class="cc-card cc-animate-fade-in" style="padding:var(--cc-space-3);text-align:center;animation-delay:100ms;">
          <div style="font-size:var(--cc-text-2xl);font-weight:var(--cc-font-bold);color:var(--cc-primary-500);">${s.active || 0}</div>
          <div class="cc-text-xs cc-text-muted">Active</div>
        </div>
      `;

      if (this._jobs.length === 0) {
        listEl.innerHTML = `
          <div class="cc-card cc-empty-state cc-animate-fade-in" style="padding:var(--cc-space-8);">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.noJobs : '&#128197;'}</div>
            <div class="cc-empty-state-title" style="font-size:var(--cc-text-lg);">No jobs today</div>
            <div class="cc-empty-state-description">You don't have any jobs scheduled for today. Enjoy your day off.</div>
          </div>
        `;
        return;
      }

      listEl.innerHTML = this._jobs.map((job, i) => this._renderJobCard(job, i)).join('');

      // Attach event listeners
      this._jobs.forEach((job) => {
        const card = document.getElementById(`job-card-${job.id}`);
        if (!card) return;

        // Navigate button
        const navBtn = card.querySelector('.cc-btn-navigate');
        if (navBtn) {
          navBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this._navigate(job);
          });
        }

        // Check-in button
        const checkinBtn = card.querySelector('.cc-btn-checkin');
        if (checkinBtn) {
          checkinBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this._checkIn(job.id);
          });
        }

        // Card tap -> job detail
        card.addEventListener('click', () => {
          window.location.hash = `#/team/job/${job.id}`;
        });
      });

      // Cache for offline
      if (typeof OfflineStore !== 'undefined') OfflineStore.saveForOffline(this._jobs);

    } catch (err) {
      console.error('[TeamToday] Error loading jobs:', err);
      // Try offline cache
      const cached = (typeof OfflineStore !== 'undefined') ? await OfflineStore.getCachedJobs() : null;
      if (cached && cached.length > 0) {
        this._jobs = cached;
        listEl.innerHTML = `
          <div class="cc-card cc-animate-fade-in" style="padding:var(--cc-space-3);background:var(--cc-warning-50);border:1px solid var(--cc-warning-200);text-align:center;">
            <span class="cc-text-sm cc-text-warning">Showing cached data. Pull to refresh when online.</span>
          </div>
          ${cached.map((job, i) => this._renderJobCard(job, i)).join('')}
        `;
      } else {
        listEl.innerHTML = `
          <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
            <div class="cc-empty-state-title">Could not load today's jobs</div>
            <div class="cc-empty-state-description">Please check your connection and try again.</div>
            <button onclick="TeamToday.loadJobs()" class="cc-btn cc-btn-primary" style="margin-top:var(--cc-space-4);">Retry</button>
          </div>
        `;
      }
    } finally {
      this._refreshing = false;
    }
  },

  _renderJobCard(job, index) {
    const statusColors = {
      'upcoming': { border: 'var(--cc-primary-500)', bg: 'var(--cc-primary-50)', badge: 'cc-badge-primary' },
      'in-progress': { border: 'var(--cc-success-500)', bg: 'var(--cc-success-50)', badge: 'cc-badge-success' },
      'completed': { border: 'var(--cc-neutral-400)', bg: 'var(--cc-neutral-50)', badge: 'cc-badge-neutral' },
    };
    const colors = statusColors[job.display_status] || statusColors['upcoming'];

    const statusLabel = {
      'upcoming': 'Upcoming',
      'in-progress': 'In Progress',
      'completed': 'Completed',
    }[job.display_status] || job.status;

    const timeDisplay = job.scheduled_start
      ? job.scheduled_start.substring(0, 5)
      : '--:--';

    const durationDisplay = job.estimated_duration_minutes
      ? `${Math.floor(job.estimated_duration_minutes / 60)}h${job.estimated_duration_minutes % 60 ? (job.estimated_duration_minutes % 60) + 'm' : ''}`
      : '';

    const showCheckin = job.display_status === 'upcoming';
    const showNavigate = job.display_status !== 'completed' && job.address;

    return `
      <div id="job-card-${job.id}" class="cc-card cc-card-interactive cc-job-card cc-animate-slide-up"
        role="button" tabindex="0"
        style="border-left-color:${colors.border};cursor:pointer;animation-delay:${index * 60}ms;">
        <!-- Header: Time + Status -->
        <div class="cc-job-card-header" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--cc-space-3);">
          <div style="display:flex;align-items:baseline;gap:var(--cc-space-2);">
            <span style="font-size:var(--cc-text-xl);font-weight:var(--cc-font-bold);color:var(--cc-neutral-900);">${timeDisplay}</span>
            ${durationDisplay ? `<span class="cc-text-sm cc-text-muted">${durationDisplay}</span>` : ''}
          </div>
          <span class="cc-badge ${colors.badge}">${statusLabel}</span>
        </div>

        <!-- Body: Client + Service -->
        <div class="cc-job-card-meta" style="margin-bottom:var(--cc-space-3);">
          <div style="font-size:var(--cc-text-base);font-weight:var(--cc-font-semibold);color:var(--cc-neutral-900);">
            ${this._escapeHtml(job.client_name)}
          </div>
          <div class="cc-job-card-meta-item" style="display:flex;align-items:center;gap:var(--cc-space-2);">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cc-neutral-400)" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
            <span class="cc-text-sm cc-text-muted cc-truncate">${this._escapeHtml(job.address || 'No address')}</span>
          </div>
          <div class="cc-job-card-meta-item" style="display:flex;align-items:center;gap:var(--cc-space-2);">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cc-neutral-400)" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/></svg>
            <span class="cc-text-sm cc-text-muted">${this._escapeHtml(job.service_name)}</span>
          </div>
          ${job.special_instructions ? `
            <div class="cc-text-xs" style="color:var(--cc-warning-600);background:var(--cc-warning-50);padding:var(--cc-space-2) var(--cc-space-3);border-radius:var(--cc-radius-md);margin-top:var(--cc-space-1);display:flex;align-items:center;gap:var(--cc-space-2);">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${this._escapeHtml(job.special_instructions.length > 80 ? job.special_instructions.substring(0, 80) + '...' : job.special_instructions)}</span>
            </div>
          ` : ''}
        </div>

        <!-- Actions -->
        ${showNavigate || showCheckin ? `
        <div style="display:flex;gap:var(--cc-space-2);padding-top:var(--cc-space-3);border-top:1px solid var(--cc-neutral-100);">
          ${showNavigate ? `<button class="cc-btn cc-btn-secondary cc-btn-sm cc-btn-navigate" style="flex:1;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="3 11 22 2 13 21 11 13 3 11"/></svg>
            Navigate
          </button>` : ''}
          ${showCheckin ? `<button class="cc-btn cc-btn-primary cc-btn-sm cc-btn-checkin" style="flex:1;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            Check In
          </button>` : ''}
        </div>
        ` : ''}
      </div>
    `;
  },

  _navigate(job) {
    if (job.latitude && job.longitude) {
      window.open(`https://www.google.com/maps/dir/?api=1&destination=${job.latitude},${job.longitude}`, '_blank');
    } else if (job.address) {
      window.open(`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(job.address)}`, '_blank');
    }
  },

  async _checkIn(bookingId) {
    const btn = document.querySelector(`#job-card-${bookingId} .cc-btn-checkin`);
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Checking in...';
    }

    try {
      // Get GPS position
      let lat = null, lng = null;
      try {
        const pos = await new Promise((resolve, reject) => {
          navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: true,
            timeout: 10000,
          });
        });
        lat = pos.coords.latitude;
        lng = pos.coords.longitude;
      } catch (gpsErr) {
        console.warn('[TeamToday] GPS unavailable:', gpsErr);
      }

      const result = await CleanAPI.cleanPost(`/my-jobs/${bookingId}/checkin`, { lat, lng });

      if (result && !result._queued) {
        if (typeof CleanClaw !== 'undefined' && CleanClaw.showToast) {
          CleanClaw.showToast('Checked in. Have a great cleaning!', 'success');
        }
        // Navigate to job detail
        window.location.hash = `#/team/job/${bookingId}`;
      } else if (result && result._queued) {
        // Queued for offline sync
        if (typeof OfflineStore !== 'undefined') OfflineStore.queueAction({ type: 'checkin', bookingId, lat, lng, timestamp: Date.now() });
      }
    } catch (err) {
      console.error('[TeamToday] Check-in error:', err);
      if (typeof CleanClaw !== 'undefined' && CleanClaw.showToast) {
        CleanClaw.showToast(err.detail || 'Check-in failed. Please try again.', 'error');
      }
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Check In';
      }
    }
  },

  _setupPullToRefresh(container) {
    let startY = 0;
    let pulling = false;

    container.addEventListener('touchstart', (e) => {
      if (container.scrollTop === 0) {
        startY = e.touches[0].clientY;
        pulling = true;
      }
    }, { passive: true });

    container.addEventListener('touchmove', (e) => {
      if (!pulling) return;
      const diff = e.touches[0].clientY - startY;
      if (diff > 80) {
        pulling = false;
        this.loadJobs();
      }
    }, { passive: true });

    container.addEventListener('touchend', () => {
      pulling = false;
    }, { passive: true });
  },

  _escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },
};
