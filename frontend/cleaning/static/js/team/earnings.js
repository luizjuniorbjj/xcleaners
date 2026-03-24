/**
 * CleanClaw — Team Earnings Module (Sprint 3)
 *
 * Earnings summary: hours, jobs, daily breakdown.
 */
window.TeamEarnings = {
  _currentPeriod: 'week',

  async render(container) {
    container.innerHTML = `
      <div class="cc-earnings" style="display:flex;flex-direction:column;gap:var(--cc-space-5);">
        <!-- Page Header -->
        <h2 style="margin:0;">My Earnings</h2>

        <!-- Period Tabs -->
        <div style="display:flex;gap:var(--cc-space-1);background:var(--cc-neutral-100);border-radius:var(--cc-radius-lg);padding:var(--cc-space-1);">
          <button class="cc-btn cc-btn-sm cc-earnings-tab cc-earnings-tab-active" data-period="week"
            style="flex:1;border-radius:var(--cc-radius-md);font-weight:var(--cc-font-semibold);transition:all var(--cc-duration-fast) var(--cc-ease-default);">
            This Week
          </button>
          <button class="cc-btn cc-btn-sm cc-earnings-tab" data-period="month"
            style="flex:1;border-radius:var(--cc-radius-md);font-weight:var(--cc-font-medium);transition:all var(--cc-duration-fast) var(--cc-ease-default);">
            This Month
          </button>
          <button class="cc-btn cc-btn-sm cc-earnings-tab" data-period="year"
            style="flex:1;border-radius:var(--cc-radius-md);font-weight:var(--cc-font-medium);transition:all var(--cc-duration-fast) var(--cc-ease-default);">
            This Year
          </button>
        </div>

        <!-- Content -->
        <div id="cc-earnings-content" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
          <!-- Skeleton: Stats -->
          <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:var(--cc-space-3);">
            <div class="cc-card" style="padding:var(--cc-space-4);">
              <div class="cc-skeleton" style="width:40px;height:28px;margin-bottom:var(--cc-space-2);"></div>
              <div class="cc-skeleton cc-skeleton-text" style="width:60%;"></div>
            </div>
            <div class="cc-card" style="padding:var(--cc-space-4);">
              <div class="cc-skeleton" style="width:40px;height:28px;margin-bottom:var(--cc-space-2);"></div>
              <div class="cc-skeleton cc-skeleton-text" style="width:60%;"></div>
            </div>
            <div class="cc-card" style="padding:var(--cc-space-4);">
              <div class="cc-skeleton" style="width:40px;height:28px;margin-bottom:var(--cc-space-2);"></div>
              <div class="cc-skeleton cc-skeleton-text" style="width:60%;"></div>
            </div>
            <div class="cc-card" style="padding:var(--cc-space-4);">
              <div class="cc-skeleton" style="width:40px;height:28px;margin-bottom:var(--cc-space-2);"></div>
              <div class="cc-skeleton cc-skeleton-text" style="width:60%;"></div>
            </div>
          </div>
        </div>
      </div>
    `;

    container.querySelectorAll('.cc-earnings-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        container.querySelectorAll('.cc-earnings-tab').forEach(t => {
          t.classList.remove('cc-earnings-tab-active');
          t.style.background = 'transparent';
          t.style.color = 'var(--cc-neutral-600)';
          t.style.boxShadow = 'none';
        });
        tab.classList.add('cc-earnings-tab-active');
        tab.style.background = '#fff';
        tab.style.color = 'var(--cc-neutral-900)';
        tab.style.boxShadow = 'var(--cc-shadow-sm)';
        this._currentPeriod = tab.dataset.period;
        this._loadEarnings();
      });
    });

    // Style active tab on load
    const activeTab = container.querySelector('.cc-earnings-tab-active');
    if (activeTab) {
      activeTab.style.background = '#fff';
      activeTab.style.color = 'var(--cc-neutral-900)';
      activeTab.style.boxShadow = 'var(--cc-shadow-sm)';
    }

    await this._loadEarnings();
  },

  async _loadEarnings() {
    const contentEl = document.getElementById('cc-earnings-content');
    contentEl.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:var(--cc-space-3);">
        <div class="cc-card" style="padding:var(--cc-space-4);">
          <div class="cc-skeleton" style="width:40px;height:28px;margin-bottom:var(--cc-space-2);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:60%;"></div>
        </div>
        <div class="cc-card" style="padding:var(--cc-space-4);">
          <div class="cc-skeleton" style="width:40px;height:28px;margin-bottom:var(--cc-space-2);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:60%;"></div>
        </div>
      </div>
    `;

    try {
      const rawData = await CleanAPI.cleanGet(`/my-earnings?period=${this._currentPeriod}`);
      const data = (rawData && typeof rawData === 'object' && Object.keys(rawData).length > 0) ? rawData : { summary: {}, daily: [] };

      const summary = data.summary || {};
      const daily = Array.isArray(data.daily) ? data.daily : [];

      // Find max jobs for bar chart scaling
      const maxJobs = daily.length > 0 ? Math.max(...daily.map(d => d.jobs || 0), 1) : 1;

      contentEl.innerHTML = `
        <!-- Summary Stat Cards -->
        <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:var(--cc-space-3);" class="cc-animate-fade-in">
          <div class="cc-card cc-stat-card cc-stat-success" style="flex-direction:column;align-items:flex-start;border-left-width:4px;">
            <div class="cc-stat-card-icon" style="background:var(--cc-success-50);color:var(--cc-success-500);width:36px;height:36px;margin-bottom:var(--cc-space-2);">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            </div>
            <div class="cc-stat-card-value" style="font-size:var(--cc-text-2xl);">${summary.completed_jobs || 0}</div>
            <div class="cc-stat-card-label">Jobs Completed</div>
          </div>

          <div class="cc-card cc-stat-card" style="flex-direction:column;align-items:flex-start;border-left-width:4px;">
            <div class="cc-stat-card-icon" style="width:36px;height:36px;margin-bottom:var(--cc-space-2);">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </div>
            <div class="cc-stat-card-value" style="font-size:var(--cc-text-2xl);">${summary.actual_hours || 0}h</div>
            <div class="cc-stat-card-label">Hours Worked</div>
          </div>

          <div class="cc-card cc-stat-card cc-stat-info" style="flex-direction:column;align-items:flex-start;border-left-width:4px;">
            <div class="cc-stat-card-icon" style="background:var(--cc-info-100);color:var(--cc-info-500);width:36px;height:36px;margin-bottom:var(--cc-space-2);">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
            </div>
            <div class="cc-stat-card-value" style="font-size:var(--cc-text-2xl);">${summary.total_jobs || 0}</div>
            <div class="cc-stat-card-label">Total Scheduled</div>
          </div>

          <div class="cc-card cc-stat-card cc-stat-warning" style="flex-direction:column;align-items:flex-start;border-left-width:4px;">
            <div class="cc-stat-card-icon" style="background:var(--cc-warning-50);color:var(--cc-warning-500);width:36px;height:36px;margin-bottom:var(--cc-space-2);">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v10l4.5 4.5"/><circle cx="12" cy="12" r="10"/></svg>
            </div>
            <div class="cc-stat-card-value" style="font-size:var(--cc-text-2xl);">${summary.estimated_hours || 0}h</div>
            <div class="cc-stat-card-label">Est. Hours</div>
          </div>
        </div>

        <!-- Period Range -->
        <div class="cc-text-sm cc-text-muted cc-text-center" style="padding:var(--cc-space-1) 0;">
          ${data.start_date || ''} to ${data.end_date || ''}
        </div>

        <!-- Daily Breakdown with Bar Chart -->
        ${daily.length > 0 ? `
        <div class="cc-card cc-animate-fade-in" style="padding:var(--cc-space-5);">
          <div class="cc-card-header">
            <span class="cc-card-title">Daily Breakdown</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
            ${daily.map((d, i) => {
              const pct = d.jobs > 0 ? Math.round((d.completed / d.jobs) * 100) : 0;
              const barWidth = d.jobs > 0 ? Math.round((d.jobs / maxJobs) * 100) : 0;
              return `
                <div class="cc-animate-slide-up" style="display:flex;align-items:center;gap:var(--cc-space-3);animation-delay:${i * 40}ms;">
                  <!-- Day label -->
                  <div style="min-width:70px;flex-shrink:0;">
                    <div class="cc-text-sm cc-font-semibold" style="color:var(--cc-neutral-800);">
                      ${new Date(d.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short' })}
                    </div>
                    <div class="cc-text-xs cc-text-muted">
                      ${new Date(d.date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    </div>
                  </div>

                  <!-- Bar -->
                  <div style="flex:1;display:flex;flex-direction:column;gap:var(--cc-space-1);">
                    <div style="height:8px;background:var(--cc-neutral-100);border-radius:var(--cc-radius-full);overflow:hidden;">
                      <div style="height:100%;border-radius:var(--cc-radius-full);transition:width var(--cc-duration-slow) var(--cc-ease-out);width:${barWidth}%;background:${pct === 100 ? 'var(--cc-success-500)' : pct > 0 ? 'var(--cc-primary-500)' : 'var(--cc-neutral-300)'};"></div>
                    </div>
                  </div>

                  <!-- Stats -->
                  <div style="min-width:80px;text-align:right;flex-shrink:0;">
                    <span class="cc-text-sm cc-font-medium" style="color:var(--cc-neutral-800);">${d.completed}/${d.jobs}</span>
                    <span class="cc-text-xs cc-text-muted"> ${d.hours}h</span>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
        ` : `
        <div class="cc-card cc-empty-state cc-animate-fade-in" style="padding:var(--cc-space-6);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.chart : '&#128200;'}</div>
          <div class="cc-empty-state-title" style="font-size:var(--cc-text-lg);">No activity yet</div>
          <div class="cc-empty-state-description">Your earnings breakdown will appear here once you start completing jobs. Check back after your next shift.</div>
        </div>
        `}
      `;
    } catch (err) {
      console.error('[Earnings] Error:', err);
      contentEl.innerHTML = `
        <div class="cc-card cc-empty-state" style="padding:var(--cc-space-8);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.error : '!'}</div>
          <div class="cc-empty-state-title">Could not load earnings</div>
          <div class="cc-empty-state-description">Please check your connection and try again.</div>
        </div>
      `;
    }
  },
};
