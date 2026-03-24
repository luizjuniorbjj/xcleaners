/**
 * CleanClaw — Team My Schedule Module (Sprint 3)
 *
 * Week view of the team's schedule.
 */
window.TeamMySchedule = {
  _currentStart: null,

  async render(container) {
    const today = new Date();
    const dayOfWeek = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - ((dayOfWeek + 6) % 7));
    this._currentStart = monday;

    container.innerHTML = `
      <div class="cc-my-schedule" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <!-- Navigation Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <button class="cc-btn cc-btn-ghost cc-btn-sm" id="cc-sched-prev" style="padding:var(--cc-space-2);">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
          </button>
          <h2 id="cc-sched-title" style="margin:0;font-size:var(--cc-text-xl);"></h2>
          <button class="cc-btn cc-btn-ghost cc-btn-sm" id="cc-sched-next" style="padding:var(--cc-space-2);">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>
          </button>
        </div>

        <!-- Days Grid (skeleton) -->
        <div id="cc-sched-days" style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
          ${[1,2,3,4,5,6,7].map(() => `
            <div class="cc-card" style="padding:var(--cc-space-3);">
              <div style="display:flex;align-items:center;gap:var(--cc-space-3);">
                <div class="cc-skeleton" style="width:40px;height:40px;border-radius:var(--cc-radius-md);"></div>
                <div style="flex:1;">
                  <div class="cc-skeleton cc-skeleton-text" style="width:50%;"></div>
                  <div class="cc-skeleton cc-skeleton-text" style="width:30%;margin-top:var(--cc-space-1);"></div>
                </div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;

    document.getElementById('cc-sched-prev').addEventListener('click', () => {
      this._currentStart.setDate(this._currentStart.getDate() - 7);
      this._loadWeek();
    });
    document.getElementById('cc-sched-next').addEventListener('click', () => {
      this._currentStart.setDate(this._currentStart.getDate() + 7);
      this._loadWeek();
    });

    await this._loadWeek();
  },

  async _loadWeek() {
    const start = this._formatDate(this._currentStart);
    const endDate = new Date(this._currentStart);
    endDate.setDate(endDate.getDate() + 6);
    const end = this._formatDate(endDate);

    const titleEl = document.getElementById('cc-sched-title');
    if (titleEl) {
      titleEl.textContent = `${this._currentStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${endDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
    }

    const daysEl = document.getElementById('cc-sched-days');

    try {
      const rawData = await CleanAPI.cleanGet(`/my-schedule?start=${start}&end=${end}`);
      const data = (rawData && typeof rawData === 'object' && Object.keys(rawData).length > 0) ? rawData : { days: {} };

      const days = data.days || {};
      let html = '';
      const today = this._formatDate(new Date());

      for (let i = 0; i < 7; i++) {
        const d = new Date(this._currentStart);
        d.setDate(d.getDate() + i);
        const dateStr = this._formatDate(d);
        const dayJobs = days[dateStr] || [];
        const isToday = dateStr === today;
        const dayName = d.toLocaleDateString('en-US', { weekday: 'short' });
        const dayNum = d.getDate();
        const monthName = d.toLocaleDateString('en-US', { month: 'short' });

        html += `
          <div class="cc-card cc-animate-slide-up ${isToday ? '' : ''}" style="padding:0;overflow:hidden;${isToday ? 'border:2px solid var(--cc-primary-500);' : ''}animation-delay:${i * 40}ms;">
            <!-- Day Header -->
            <div style="display:flex;align-items:center;gap:var(--cc-space-3);padding:var(--cc-space-3) var(--cc-space-4);${isToday ? 'background:var(--cc-primary-50);' : 'background:var(--cc-neutral-50);'}border-bottom:1px solid var(--cc-neutral-100);">
              <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-width:40px;height:40px;border-radius:var(--cc-radius-md);${isToday ? 'background:var(--cc-primary-500);color:#fff;' : 'background:#fff;color:var(--cc-neutral-700);border:1px solid var(--cc-neutral-200);'}">
                <span style="font-size:var(--cc-text-xs);font-weight:var(--cc-font-semibold);line-height:1;text-transform:uppercase;">${dayName}</span>
                <span style="font-size:var(--cc-text-lg);font-weight:var(--cc-font-bold);line-height:1;">${dayNum}</span>
              </div>
              <div style="flex:1;">
                <span class="cc-text-sm cc-font-medium" style="${isToday ? 'color:var(--cc-primary-700);' : 'color:var(--cc-neutral-700);'}">${isToday ? 'Today' : monthName + ' ' + dayNum}</span>
              </div>
              <span class="cc-badge ${dayJobs.length > 0 ? 'cc-badge-primary' : 'cc-badge-neutral'}">${dayJobs.length} job${dayJobs.length !== 1 ? 's' : ''}</span>
            </div>

            <!-- Jobs -->
            <div style="padding:${dayJobs.length > 0 ? 'var(--cc-space-2) var(--cc-space-3)' : 'var(--cc-space-3) var(--cc-space-4)'};">
              ${dayJobs.length === 0
                ? '<p class="cc-text-sm cc-text-muted" style="text-align:center;">No jobs</p>'
                : dayJobs.map(j => {
                    const jobStatusMap = {
                      'confirmed': { border: 'var(--cc-primary-500)', badge: 'cc-badge-primary' },
                      'scheduled': { border: 'var(--cc-primary-500)', badge: 'cc-badge-primary' },
                      'in_progress': { border: 'var(--cc-success-500)', badge: 'cc-badge-success' },
                      'completed': { border: 'var(--cc-neutral-400)', badge: 'cc-badge-neutral' },
                      'cancelled': { border: 'var(--cc-danger-500)', badge: 'cc-badge-danger' },
                    };
                    const jColors = jobStatusMap[j.status] || jobStatusMap['scheduled'];
                    return `
                      <div class="cc-card-interactive" onclick="window.location.hash='#/team/job/${j.id}'"
                        style="display:flex;align-items:center;gap:var(--cc-space-3);padding:var(--cc-space-2) var(--cc-space-3);margin-bottom:var(--cc-space-1);border-radius:var(--cc-radius-md);border-left:3px solid ${jColors.border};cursor:pointer;">
                        <span class="cc-font-semibold cc-text-sm" style="color:var(--cc-neutral-900);min-width:40px;">
                          ${j.scheduled_start ? j.scheduled_start.substring(0, 5) : '--:--'}
                        </span>
                        <div style="flex:1;min-width:0;">
                          <div class="cc-text-sm cc-font-medium cc-truncate" style="color:var(--cc-neutral-800);">${this._esc(j.client_name)}</div>
                          <div class="cc-text-xs cc-text-muted cc-truncate">${this._esc(j.service_name)}</div>
                        </div>
                      </div>
                    `;
                  }).join('')
              }
            </div>
          </div>
        `;
      }

      daysEl.innerHTML = html;

    } catch (err) {
      console.error('[MySchedule] Error:', err);
      daysEl.innerHTML = `
        <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:80px;height:80px;font-size:2rem;">!</div>
          <div class="cc-empty-state-title">Could not load schedule</div>
          <div class="cc-empty-state-description">Please try again later.</div>
        </div>
      `;
    }
  },

  _formatDate(d) {
    return d.toISOString().split('T')[0];
  },

  _esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },
};
