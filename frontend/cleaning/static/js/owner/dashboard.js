/**
 * CleanClaw — Owner Dashboard Module
 *
 * Displays KPI cards, team progress bars (SSE-driven),
 * revenue chart (pure CSS bars), overdue payments,
 * recent activity, and quick actions.
 *
 * Responsive: 4-col KPIs on desktop, 2x2 on mobile.
 */

window.OwnerDashboard = {
  _data: null,
  _teams: null,
  _chartPeriod: 'month',
  _sseHandler: null,

  async render(container) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;

    // Greeting logic
    const _hour = new Date().getHours();
    const _greeting = _hour < 12 ? 'Good morning' : _hour < 18 ? 'Good afternoon' : 'Good evening';
    const _userName = CleanClaw._user?.name || CleanClaw._user?.nome || 'Admin';
    const _timeIcon = _hour < 6 ? '\u{1F319}' : _hour < 12 ? '\u{2600}\u{FE0F}' : _hour < 18 ? '\u{1F324}\u{FE0F}' : '\u{1F319}';

    container.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-6);">
        <!-- Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <div>
            <h2 style="margin:0;">${t('dashboard.title')}</h2>
            <span class="cc-text-sm cc-text-muted" id="dash-date"></span>
          </div>
        </div>

        <!-- Greeting Card -->
        <div class="cc-card" id="greeting-card" style="background:linear-gradient(135deg, var(--cc-primary-500), var(--cc-primary-700));color:#fff;padding:var(--cc-space-6);display:flex;align-items:center;justify-content:space-between;border-radius:var(--cc-radius-xl);margin-bottom:var(--cc-space-4);">
          <div>
            <div style="font-size:var(--cc-text-2xl);font-weight:var(--cc-font-bold);margin-bottom:var(--cc-space-2);">
              ${_greeting}, ${_userName}!
            </div>
            <div style="opacity:0.85;font-size:var(--cc-text-sm);" id="greeting-summary">
              Loading today's summary...
            </div>
          </div>
          <div style="font-size:3rem;opacity:0.3;">
            ${_timeIcon}
          </div>
        </div>

        <!-- KPI Stat Cards -->
        <div id="kpi-cards" class="cc-dash-kpis">
          ${this._renderKpiSkeleton()}
        </div>

        <!-- Team Progress -->
        <div class="cc-card" id="team-progress-card">
          <div class="cc-card-header">
            <span class="cc-card-title">${t('dashboard.team_progress')}</span>
            <a href="#/owner/schedule" class="cc-btn cc-btn-ghost cc-btn-xs">${t('dashboard.view_schedule')}</a>
          </div>
          <div id="team-progress-body" class="cc-card-body">
            <div class="cc-skeleton cc-skeleton-text" style="width:100%;height:20px;margin-bottom:var(--cc-space-3);"></div>
            <div class="cc-skeleton cc-skeleton-text" style="width:80%;height:20px;"></div>
          </div>
        </div>

        <!-- Revenue Chart + Overdue + Quick Actions -->
        <div class="cc-dash-bottom">
          <!-- Revenue Chart -->
          <div class="cc-card" style="grid-row:span 2;">
            <div class="cc-card-header">
              <span class="cc-card-title">${t('dashboard.revenue_chart')}</span>
              <div style="display:flex;gap:var(--cc-space-1);">
                <button class="cc-btn cc-btn-xs ${this._chartPeriod === 'week' ? 'cc-btn-primary' : 'cc-btn-secondary'}" data-period="week">${t('dashboard.week')}</button>
                <button class="cc-btn cc-btn-xs ${this._chartPeriod === 'month' ? 'cc-btn-primary' : 'cc-btn-secondary'}" data-period="month">${t('dashboard.month')}</button>
                <button class="cc-btn cc-btn-xs ${this._chartPeriod === 'quarter' ? 'cc-btn-primary' : 'cc-btn-secondary'}" data-period="quarter">${t('dashboard.quarter')}</button>
              </div>
            </div>
            <div id="revenue-chart" class="cc-card-body">
              <div class="cc-skeleton" style="width:100%;height:160px;"></div>
            </div>
          </div>

          <!-- Overdue Payments -->
          <div class="cc-card">
            <div class="cc-card-header">
              <span class="cc-card-title">${t('dashboard.overdue_payments')}</span>
            </div>
            <div id="overdue-list" class="cc-card-body">
              <div class="cc-skeleton cc-skeleton-text" style="margin-bottom:var(--cc-space-2);"></div>
              <div class="cc-skeleton cc-skeleton-text" style="width:70%;"></div>
            </div>
            <div class="cc-card-footer">
              <a href="#/owner/invoices" class="cc-btn cc-btn-ghost cc-btn-xs">${t('dashboard.view_invoices')}</a>
            </div>
          </div>

          <!-- Quick Actions -->
          <div class="cc-card">
            <div class="cc-card-header">
              <span class="cc-card-title">${t('dashboard.quick_actions')}</span>
            </div>
            <div class="cc-card-body" style="display:flex;flex-direction:column;gap:var(--cc-space-2);">
              <button class="cc-btn cc-btn-outline cc-btn-sm cc-btn-block" id="btn-gen-schedule">
                ${t('dashboard.generate_schedule')}
              </button>
              <button class="cc-btn cc-btn-outline cc-btn-sm cc-btn-block" id="btn-unassigned">
                ${t('dashboard.view_unassigned')}
              </button>
              <button class="cc-btn cc-btn-outline cc-btn-sm cc-btn-block" id="btn-reminders">
                ${t('dashboard.send_reminders')}
              </button>
            </div>
          </div>
        </div>
      </div>
    `;

    // Bind events
    this._bindEvents(container);

    // Load data
    await this._loadDashboard();
    await this._loadRevenueChart();
    await this._loadTeams();
    await this._loadOverdue();

    // SSE for team progress
    this._subscribeSSE();
  },

  // ---- Data Loading ----

  async _loadDashboard() {
    try {
      const resp = await CleanAPI.cleanGet('/dashboard');
      this._data = (resp && resp.today_bookings_count !== undefined) ? resp : {
        today_bookings_count: 0, active_clients: 0, active_teams: 0,
        month_revenue: 0, revenue_this_month: 0, revenue_change_pct: 0,
        bookings_today: { total: 0, completed: 0 },
        date: new Date().toISOString(),
        overdue_invoices: { count: 0, total_amount: 0 }
      };
      this._renderKpis();
      const dateEl = document.getElementById('dash-date');
      if (dateEl) {
        dateEl.textContent = new Date(this._data.date || Date.now()).toLocaleDateString(I18n?.getLocale() || 'en', {
          weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
        });
      }
    } catch (err) {
      console.warn('[Dashboard] Using default data:', err.message || err);
      this._data = {
        today_bookings_count: 0, active_clients: 0, active_teams: 0,
        month_revenue: 0, revenue_this_month: 0, revenue_change_pct: 0,
        bookings_today: { total: 0, completed: 0 },
        date: new Date().toISOString(),
        overdue_invoices: { count: 0, total_amount: 0 }
      };
      this._renderKpis();
    }
  },

  async _loadRevenueChart() {
    try {
      const resp = await CleanAPI.cleanGet(`/dashboard/revenue?period=${this._chartPeriod}`);
      const data = (resp && resp.data) ? resp : { data: [], total_revenue: 0 };
      this._renderRevenueChart(data);
    } catch (err) {
      console.error('[Dashboard] Failed to load revenue chart:', err);
      const chartEl = document.getElementById('revenue-chart');
      if (chartEl) chartEl.innerHTML = '<p class="cc-text-sm cc-text-muted" style="padding:var(--cc-space-4);">Failed to load chart data.</p>';
    }
  },

  async _loadTeams() {
    try {
      const resp = await CleanAPI.cleanGet('/dashboard/teams');
      this._teams = Array.isArray(resp) ? resp : (resp && resp.teams ? resp.teams : []);
      this._renderTeamProgress();
    } catch (err) {
      console.error('[Dashboard] Failed to load team performance:', err);
      this._teams = [];
      this._renderTeamProgress();
    }
  },

  async _loadOverdue() {
    try {
      // Use existing invoice endpoint filtered to overdue
      const resp = await CleanAPI.cleanGet('/invoices?status=overdue&limit=5');
      const invoices = Array.isArray(resp) ? resp : (resp && resp.invoices ? resp.invoices : []);
      this._renderOverdue(invoices);
    } catch {
      // If endpoint not available, show from summary data
      const el = document.getElementById('overdue-list');
      if (this._data && this._data.overdue_invoices && this._data.overdue_invoices.count > 0) {
        const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
        el.innerHTML = `
          <div style="display:flex;align-items:center;justify-content:space-between;padding:var(--cc-space-2) 0;">
            <span class="cc-text-sm cc-font-semibold">${this._data.overdue_invoices.count} ${t('dashboard.overdue_invoices')}</span>
            <span class="cc-badge cc-badge-danger">$${this._data.overdue_invoices.total_amount.toFixed(2)}</span>
          </div>
        `;
      } else {
        el.innerHTML = `
          <div class="cc-empty-state" style="padding:var(--cc-space-6) var(--cc-space-4);">
            <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.payment : '&#10003;'}</div>
            <div class="cc-empty-state-title cc-text-sm">All caught up</div>
          </div>
        `;
      }
    }
  },

  // ---- Rendering ----

  _renderKpiSkeleton() {
    const card = `
      <div class="cc-card cc-stat-card">
        <div>
          <div class="cc-skeleton" style="width:80px;height:28px;margin-bottom:var(--cc-space-2);"></div>
          <div class="cc-skeleton cc-skeleton-text" style="width:100px;"></div>
        </div>
        <div class="cc-skeleton cc-skeleton-circle" style="width:48px;height:48px;"></div>
      </div>
    `;
    return card.repeat(4);
  },

  _renderKpis() {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    const d = this._data || {};
    // Null-safe access with defaults
    const revenue = d.revenue_this_month || d.month_revenue || 0;
    const revPct = d.revenue_change_pct || 0;
    const bookingsToday = d.bookings_today || { total: d.today_bookings_count || 0, completed: 0 };
    const clients = d.active_clients || 0;
    const teams = d.active_teams || 0;
    const isUp = revPct >= 0;
    const pctSign = isUp ? '+' : '';

    // Update greeting summary with live data
    const greetingSummary = document.getElementById('greeting-summary');
    if (greetingSummary) {
      greetingSummary.textContent = `You have ${bookingsToday.total} booking${bookingsToday.total !== 1 ? 's' : ''} today, ${teams} team${teams !== 1 ? 's' : ''} active`;
    }

    const kpiEl = document.getElementById('kpi-cards');
    if (!kpiEl) return;
    kpiEl.innerHTML = `
      <div class="cc-card cc-stat-card cc-card-interactive cc-stat-success" onclick="location.hash='#/owner/invoices'">
        <div>
          <div class="cc-stat-card-value">$${revenue.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
          <div class="cc-stat-card-label">${t('dashboard.revenue_this_month')}</div>
          <span class="cc-stat-card-change ${isUp ? 'cc-positive' : 'cc-negative'}">${pctSign}${revPct}% ${t('dashboard.vs_last_month')}</span>
        </div>
        <div class="cc-stat-card-icon" style="background:var(--cc-success-50);color:var(--cc-success-500);">$</div>
      </div>

      <div class="cc-card cc-stat-card cc-card-interactive" onclick="location.hash='#/owner/schedule'">
        <div>
          <div class="cc-stat-card-value">${bookingsToday.total}</div>
          <div class="cc-stat-card-label">${t('dashboard.bookings_today')}</div>
          <span class="cc-text-xs cc-text-muted">${bookingsToday.completed} ${t('dashboard.completed')}</span>
        </div>
        <div class="cc-stat-card-icon">&#128197;</div>
      </div>

      <div class="cc-card cc-stat-card cc-card-interactive cc-stat-info" onclick="location.hash='#/owner/clients'">
        <div>
          <div class="cc-stat-card-value">${clients}</div>
          <div class="cc-stat-card-label">${t('dashboard.active_clients')}</div>
        </div>
        <div class="cc-stat-card-icon" style="background:var(--cc-info-100);color:var(--cc-info-500);">&#128101;</div>
      </div>

      <div class="cc-card cc-stat-card cc-card-interactive ${(d.overdue_invoices && d.overdue_invoices.count > 0) ? 'cc-stat-danger' : 'cc-stat-warning'}" onclick="location.hash='#/owner/invoices'">
        <div>
          <div class="cc-stat-card-value">${d.overdue_invoices ? d.overdue_invoices.count : 0}</div>
          <div class="cc-stat-card-label">${t('dashboard.overdue_invoices')}</div>
          <span class="cc-text-xs cc-text-muted">$${d.overdue_invoices ? (d.overdue_invoices.total_amount || 0).toFixed(2) : '0.00'}</span>
        </div>
        <div class="cc-stat-card-icon" style="background:var(--cc-danger-50);color:var(--cc-danger-500);">&#9888;</div>
      </div>
    `;
  },

  _renderKpiError() {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    const kpiEl = document.getElementById('kpi-cards');
    if (!kpiEl) return;
    kpiEl.innerHTML = `
      <div class="cc-card" style="grid-column:1/-1;padding:var(--cc-space-6);text-align:center;">
        <p class="cc-text-sm cc-text-danger">${t('common.error')}. <a href="javascript:void(0)" onclick="OwnerDashboard._loadDashboard()" class="cc-text-primary">${t('common.retry')}</a></p>
      </div>
    `;
  },

  _renderTeamProgress() {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    const el = document.getElementById('team-progress-body');
    if (!el) return;

    if (!this._teams || this._teams.length === 0) {
      el.innerHTML = `
        <div class="cc-empty-state">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.welcome : '&#128101;'}</div>
          <div class="cc-empty-state-title">Welcome to your dashboard</div>
          <div class="cc-empty-state-description">Complete your setup to see your business stats here. Add clients, teams, and your first week's schedule.</div>
          <button class="cc-btn cc-btn-primary" onclick="location.hash='#/owner/teams'">Start Setup</button>
        </div>
      `;
      return;
    }

    el.innerHTML = `<div style="display:flex;flex-direction:column;gap:var(--cc-space-4);">` +
      this._teams.map(team => {
        const today = team.today || {};
        const total = today.total_jobs || 1;
        const completed = today.completed || 0;
        const pct = Math.round((completed / total) * 100);
        const isInProgress = (today.in_progress || 0) > 0;
        const isDone = completed === total && total > 0;
        const statusLabel = isInProgress
          ? t('dashboard.in_progress')
          : isDone
            ? t('dashboard.completed')
            : t('dashboard.not_started');
        const statusClass = isInProgress ? 'cc-badge-primary' : isDone ? 'cc-badge-success' : 'cc-badge-neutral';

        return `
          <div data-team-id="${team.team_id}" style="display:flex;flex-direction:column;gap:var(--cc-space-2);">
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div style="display:flex;align-items:center;gap:var(--cc-space-2);">
                <span class="cc-status-dot" style="background:${team.team_color || '#888'};width:10px;height:10px;border-radius:50%;display:inline-block;"></span>
                <span class="cc-font-medium cc-text-sm">${team.team_name}</span>
              </div>
              <span class="cc-badge ${statusClass}">${statusLabel}</span>
            </div>
            <div style="width:100%;height:8px;background:var(--cc-neutral-200);border-radius:var(--cc-radius-full);overflow:hidden;">
              <div style="width:${pct}%;height:100%;background:${team.team_color || 'var(--cc-primary-500)'};border-radius:var(--cc-radius-full);transition:width 0.5s ease;"></div>
            </div>
            <div style="display:flex;justify-content:space-between;" class="cc-text-xs cc-text-muted">
              <span>${completed}/${today.total_jobs || 0} ${t('dashboard.jobs')}</span>
              <span>${today.total_hours || 0}h</span>
            </div>
          </div>
        `;
      }).join('') + '</div>';
  },

  _renderRevenueChart(data) {
    const el = document.getElementById('revenue-chart');
    if (!el) return;
    if (!data || !data.data || data.data.length === 0) {
      el.innerHTML = `
        <div class="cc-empty-state" style="padding:var(--cc-space-8) var(--cc-space-4);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.chart : '&#128200;'}</div>
          <div class="cc-empty-state-title cc-text-sm">No revenue data yet</div>
        </div>
      `;
      return;
    }

    const maxRev = Math.max(...data.data.map(d => d.revenue), 1);
    const barWidth = Math.max(4, Math.floor(100 / data.data.length) - 1);

    // Show total
    const totalFormatted = (data.total_revenue || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });

    let html = `<div style="font-size:var(--cc-text-2xl);font-weight:var(--cc-font-bold);color:var(--cc-neutral-900);margin-bottom:var(--cc-space-4);">$${totalFormatted}</div>`;
    html += '<div style="display:flex;align-items:flex-end;gap:2px;height:140px;padding-top:var(--cc-space-2);">';

    // Only show labels every Nth bar to avoid crowding
    const labelEvery = data.data.length > 14 ? 7 : data.data.length > 7 ? 3 : 1;

    data.data.forEach((point, i) => {
      const pointRevenue = point.revenue || 0;
      const height = Math.max(2, Math.round((pointRevenue / maxRev) * 120));
      const showLabel = i % labelEvery === 0;
      const dayLabel = point.date ? new Date(point.date + 'T12:00:00').toLocaleDateString(I18n?.getLocale() || 'en', {
        month: 'short', day: 'numeric',
      }) : '';

      html += `
        <div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;" title="$${pointRevenue.toFixed(2)} - ${point.date || ''}">
          <div style="width:100%;max-width:24px;height:${height}px;background:var(--cc-primary-500);border-radius:var(--cc-radius-sm) var(--cc-radius-sm) 0 0;transition:height 0.3s ease;opacity:0.85;"></div>
          ${showLabel ? `<span class="cc-text-xs cc-text-muted" style="margin-top:var(--cc-space-1);white-space:nowrap;">${dayLabel}</span>` : ''}
        </div>
      `;
    });

    html += '</div>';
    el.innerHTML = html;
  },

  _renderOverdue(invoices) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    const el = document.getElementById('overdue-list');
    if (!el) return;

    const invoiceList = Array.isArray(invoices) ? invoices : (invoices?.invoices || []);
    if (!invoiceList || invoiceList.length === 0) {
      el.innerHTML = `
        <div class="cc-empty-state" style="padding:var(--cc-space-6) var(--cc-space-4);">
          <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.payment : '&#10003;'}</div>
          <div class="cc-empty-state-title cc-text-sm">No overdue payments</div>
        </div>
      `;
      return;
    }

    el.innerHTML = `<div style="display:flex;flex-direction:column;gap:var(--cc-space-1);">` +
      invoiceList.map(inv => {
        const due = new Date(inv.due_date);
        const now = new Date();
        const daysOverdue = Math.floor((now - due) / (1000 * 60 * 60 * 24));
        const balance = (inv.balance_due != null ? inv.balance_due : (inv.total_amount || inv.total || 0) - (inv.paid_amount || 0)).toFixed(2);

        return `
          <div style="display:flex;align-items:center;justify-content:space-between;padding:var(--cc-space-3) 0;border-bottom:1px solid var(--cc-neutral-100);">
            <div>
              <div class="cc-text-sm cc-font-medium">${inv.client_name || 'Client'}</div>
              <span class="cc-badge cc-badge-sm cc-badge-danger">${daysOverdue} ${t('dashboard.days_overdue')}</span>
            </div>
            <span class="cc-font-semibold cc-text-danger">$${balance}</span>
          </div>
        `;
      }).join('') + '</div>';
  },

  // ---- Events ----

  _bindEvents(container) {
    // Chart period toggle
    container.querySelectorAll('[data-period]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        this._chartPeriod = e.target.dataset.period;
        container.querySelectorAll('[data-period]').forEach(b => {
          b.classList.remove('cc-btn-primary');
          b.classList.add('cc-btn-secondary');
        });
        e.target.classList.remove('cc-btn-secondary');
        e.target.classList.add('cc-btn-primary');
        this._loadRevenueChart();
      });
    });

    // Quick actions
    container.querySelector('#btn-gen-schedule')?.addEventListener('click', async () => {
      const btn = container.querySelector('#btn-gen-schedule');
      if (btn) { btn.disabled = true; btn.textContent = 'Generating...'; }
      try {
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        const dateStr = tomorrow.toISOString().split('T')[0];
        const result = await CleanAPI.cleanPost('/schedule/generate', { date: dateStr });
        const jobCount = result?.jobs_assigned || result?.total || '';
        const teamCount = result?.teams_used || '';
        const msg = jobCount
          ? `Schedule generated! ${jobCount} jobs assigned${teamCount ? ` to ${teamCount} teams` : ''}.`
          : 'Schedule generated for tomorrow. Your team has been notified.';
        CleanClaw.showToast(msg, 'success');
      } catch (err) {
        CleanClaw.showToast(err.detail || 'Could not generate the schedule. Please check your teams and clients, then try again.', 'error');
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = typeof I18n !== 'undefined' ? I18n.t('dashboard.generate_schedule') : 'Generate Tomorrow\'s Schedule'; }
      }
    });

    container.querySelector('#btn-unassigned')?.addEventListener('click', () => {
      location.hash = '#/owner/schedule?filter=unassigned';
    });

    container.querySelector('#btn-reminders')?.addEventListener('click', async () => {
      const btn = container.querySelector('#btn-reminders');
      if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }
      try {
        await CleanAPI.cleanPost('/invoices/send-reminders', {});
        CleanClaw.showToast('Payment reminders sent to clients with overdue invoices.', 'success');
      } catch (err) {
        // Fallback: navigate to invoices if endpoint not available
        CleanClaw.showToast('Redirecting to invoices...', 'info');
        location.hash = '#/owner/invoices';
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = typeof I18n !== 'undefined' ? I18n.t('dashboard.send_reminders') : 'Send Reminders'; }
      }
    });
  },

  // ---- SSE ----

  _subscribeSSE() {
    // Listen for SSE events to update team progress in real-time
    this._sseHandler = (e) => {
      const data = e.detail;
      if (data.event === 'job.status_changed' || data.event === 'schedule.changed') {
        this._loadTeams(); // Refresh team progress
      }
    };
    window.addEventListener('cleanclaw:sse', this._sseHandler);
  },

  destroy() {
    if (this._sseHandler) {
      window.removeEventListener('cleanclaw:sse', this._sseHandler);
      this._sseHandler = null;
    }
  },
};
