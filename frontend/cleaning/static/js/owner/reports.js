/**
 * CleanClaw — Owner Reports Module
 *
 * Displays revenue summaries, job stats, top clients,
 * team performance, and charts (weekly revenue bars, jobs by day).
 * Uses DemoData when API is unavailable.
 */

window.OwnerReports = {
  _data: null,

  async render(container) {
    const t = typeof I18n !== 'undefined' ? I18n.t.bind(I18n) : (k) => k;
    this._data = this._generateReportData();
    const d = this._data;

    const revChange = d.lastMonthRevenue > 0
      ? (((d.thisMonthRevenue - d.lastMonthRevenue) / d.lastMonthRevenue) * 100).toFixed(1)
      : 0;
    const revUp = parseFloat(revChange) >= 0;

    container.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-6);">
        <!-- Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <div>
            <h2 style="margin:0;">Reports</h2>
            <span class="cc-text-sm cc-text-muted">Business performance overview</span>
          </div>
        </div>

        <!-- Revenue Summary Cards -->
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:var(--cc-space-4);">
          <div class="cc-card cc-stat-card">
            <div>
              <div class="cc-stat-card-value">$${d.thisMonthRevenue.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</div>
              <div class="cc-stat-card-label">This Month Revenue</div>
              <span class="cc-stat-card-change ${revUp ? 'cc-positive' : 'cc-negative'}">${revUp ? '+' : ''}${revChange}% vs last month</span>
            </div>
            <div class="cc-stat-card-icon" style="background:var(--cc-success-50);color:var(--cc-success-500);">$</div>
          </div>
          <div class="cc-card cc-stat-card">
            <div>
              <div class="cc-stat-card-value">$${d.lastMonthRevenue.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</div>
              <div class="cc-stat-card-label">Last Month Revenue</div>
            </div>
            <div class="cc-stat-card-icon" style="background:var(--cc-neutral-100);color:var(--cc-neutral-500);">$</div>
          </div>
          <div class="cc-card cc-stat-card">
            <div>
              <div class="cc-stat-card-value">${d.jobsThisWeek}</div>
              <div class="cc-stat-card-label">Jobs This Week</div>
            </div>
            <div class="cc-stat-card-icon">&#128197;</div>
          </div>
          <div class="cc-card cc-stat-card">
            <div>
              <div class="cc-stat-card-value">${d.jobsThisMonth}</div>
              <div class="cc-stat-card-label">Jobs This Month</div>
            </div>
            <div class="cc-stat-card-icon" style="background:var(--cc-info-100);color:var(--cc-info-500);">&#128203;</div>
          </div>
        </div>

        <!-- Charts Row -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-4);">
          <!-- Weekly Revenue Bar Chart -->
          <div class="cc-card" style="min-width:0;">
            <div class="cc-card-header">
              <span class="cc-card-title">Weekly Revenue</span>
            </div>
            <div class="cc-card-body" id="reports-weekly-chart"></div>
          </div>
          <!-- Jobs by Day of Week -->
          <div class="cc-card" style="min-width:0;">
            <div class="cc-card-header">
              <span class="cc-card-title">Jobs by Day of Week</span>
            </div>
            <div class="cc-card-body" id="reports-day-chart"></div>
          </div>
        </div>

        <!-- Tables Row -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-4);">
          <!-- Top Clients by Revenue -->
          <div class="cc-card" style="min-width:0;">
            <div class="cc-card-header">
              <span class="cc-card-title">Top Clients by Revenue</span>
            </div>
            <div class="cc-card-body" style="overflow-x:auto;" id="reports-top-clients"></div>
          </div>
          <!-- Team Performance -->
          <div class="cc-card" style="min-width:0;">
            <div class="cc-card-header">
              <span class="cc-card-title">Team Performance</span>
            </div>
            <div class="cc-card-body" style="overflow-x:auto;" id="reports-team-perf"></div>
          </div>
        </div>
      </div>
    `;

    this._renderWeeklyChart();
    this._renderDayChart();
    this._renderTopClients();
    this._renderTeamPerformance();
  },

  // ---- Chart Renderers ----

  _renderWeeklyChart() {
    const el = document.getElementById('reports-weekly-chart');
    if (!el) return;
    const weeks = this._data.weeklyRevenue;
    const max = Math.max(...weeks.map(w => w.revenue), 1);

    let html = '<div style="display:flex;align-items:flex-end;gap:var(--cc-space-2);height:160px;">';
    weeks.forEach(w => {
      const h = Math.max(4, Math.round((w.revenue / max) * 140));
      html += `
        <div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;" title="$${w.revenue.toFixed(2)}">
          <span class="cc-text-xs cc-font-medium" style="margin-bottom:var(--cc-space-1);">$${(w.revenue / 1000).toFixed(1)}k</span>
          <div style="width:100%;max-width:48px;height:${h}px;background:var(--cc-primary-500);border-radius:var(--cc-radius-sm) var(--cc-radius-sm) 0 0;opacity:0.85;"></div>
          <span class="cc-text-xs cc-text-muted" style="margin-top:var(--cc-space-1);white-space:nowrap;">${w.label}</span>
        </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
  },

  _renderDayChart() {
    const el = document.getElementById('reports-day-chart');
    if (!el) return;
    const days = this._data.jobsByDay;
    const max = Math.max(...days.map(d => d.count), 1);
    const colors = ['var(--cc-primary-400)', 'var(--cc-primary-500)', 'var(--cc-primary-600)', 'var(--cc-primary-500)', 'var(--cc-primary-400)', 'var(--cc-warning-400)', 'var(--cc-neutral-300)'];

    let html = '<div style="display:flex;align-items:flex-end;gap:var(--cc-space-2);height:160px;">';
    days.forEach((d, i) => {
      const h = Math.max(4, Math.round((d.count / max) * 140));
      html += `
        <div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;" title="${d.count} jobs">
          <span class="cc-text-xs cc-font-medium" style="margin-bottom:var(--cc-space-1);">${d.count}</span>
          <div style="width:100%;max-width:48px;height:${h}px;background:${colors[i] || 'var(--cc-primary-500)'};border-radius:var(--cc-radius-sm) var(--cc-radius-sm) 0 0;opacity:0.85;"></div>
          <span class="cc-text-xs cc-text-muted" style="margin-top:var(--cc-space-1);">${d.label}</span>
        </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
  },

  _renderTopClients() {
    const el = document.getElementById('reports-top-clients');
    if (!el) return;
    const clients = this._data.topClients;

    let html = `<table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="border-bottom:2px solid var(--cc-neutral-200);">
          <th class="cc-text-sm cc-text-muted" style="text-align:left;padding:var(--cc-space-2) var(--cc-space-3);font-weight:var(--cc-font-semibold);">Client</th>
          <th class="cc-text-sm cc-text-muted" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);font-weight:var(--cc-font-semibold);">Jobs</th>
          <th class="cc-text-sm cc-text-muted" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);font-weight:var(--cc-font-semibold);">Revenue</th>
        </tr>
      </thead><tbody>`;
    clients.forEach(c => {
      html += `
        <tr style="border-bottom:1px solid var(--cc-neutral-100);">
          <td class="cc-text-sm cc-font-medium" style="padding:var(--cc-space-2) var(--cc-space-3);">${c.name}</td>
          <td class="cc-text-sm" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);">${c.jobs}</td>
          <td class="cc-text-sm cc-font-semibold" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);">$${c.revenue.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
        </tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  },

  _renderTeamPerformance() {
    const el = document.getElementById('reports-team-perf');
    if (!el) return;
    const teams = this._data.teamPerformance;

    let html = `<table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="border-bottom:2px solid var(--cc-neutral-200);">
          <th class="cc-text-sm cc-text-muted" style="text-align:left;padding:var(--cc-space-2) var(--cc-space-3);font-weight:var(--cc-font-semibold);">Team</th>
          <th class="cc-text-sm cc-text-muted" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);font-weight:var(--cc-font-semibold);">Jobs</th>
          <th class="cc-text-sm cc-text-muted" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);font-weight:var(--cc-font-semibold);">Hours</th>
          <th class="cc-text-sm cc-text-muted" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);font-weight:var(--cc-font-semibold);">Avg/Job</th>
        </tr>
      </thead><tbody>`;
    teams.forEach(tm => {
      const avgHours = tm.jobs > 0 ? (tm.hours / tm.jobs).toFixed(1) : '0.0';
      html += `
        <tr style="border-bottom:1px solid var(--cc-neutral-100);">
          <td style="padding:var(--cc-space-2) var(--cc-space-3);">
            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${tm.color};margin-right:var(--cc-space-2);vertical-align:middle;"></span>
            <span class="cc-text-sm cc-font-medium">${tm.name}</span>
          </td>
          <td class="cc-text-sm" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);">${tm.jobs}</td>
          <td class="cc-text-sm" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);">${tm.hours}h</td>
          <td class="cc-text-sm" style="text-align:right;padding:var(--cc-space-2) var(--cc-space-3);">${avgHours}h</td>
        </tr>`;
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  },

  // ---- Data Generation (DemoData-backed) ----

  _generateReportData() {
    const teams = (typeof DemoData !== 'undefined' && DemoData._teams) ? DemoData._teams : [];
    const clients = (typeof DemoData !== 'undefined' && DemoData._clients) ? DemoData._clients : [];

    // Revenue figures
    const thisMonthRevenue = 8450.00 + Math.round(Math.random() * 1500);
    const lastMonthRevenue = 7200.00 + Math.round(Math.random() * 1000);

    // Jobs
    const jobsThisWeek = 18 + Math.floor(Math.random() * 8);
    const jobsThisMonth = 62 + Math.floor(Math.random() * 15);

    // Weekly revenue (last 4 weeks)
    const weeklyRevenue = [];
    const now = new Date();
    for (let w = 3; w >= 0; w--) {
      const weekStart = new Date(now);
      weekStart.setDate(weekStart.getDate() - (w * 7));
      const label = weekStart.toLocaleDateString('en', { month: 'short', day: 'numeric' });
      weeklyRevenue.push({
        label: `Wk ${label}`,
        revenue: 1500 + Math.round(Math.random() * 1200),
      });
    }

    // Jobs by day of week
    const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const jobsByDay = dayLabels.map((label, i) => ({
      label,
      count: i < 5 ? (8 + Math.floor(Math.random() * 6)) : (i === 5 ? (3 + Math.floor(Math.random() * 4)) : Math.floor(Math.random() * 2)),
    }));

    // Top clients by revenue
    const topClients = clients.slice(0, 5).map(c => ({
      name: `${c.first_name} ${c.last_name}`,
      jobs: 4 + Math.floor(Math.random() * 8),
      revenue: 400 + Math.round(Math.random() * 800),
    })).sort((a, b) => b.revenue - a.revenue);

    // If no demo clients, generate placeholders
    if (topClients.length === 0) {
      const names = ['Sarah Johnson', 'Michael Williams', 'Emily Davis', 'James Brown', 'Lisa Garcia'];
      names.forEach(name => {
        topClients.push({
          name,
          jobs: 4 + Math.floor(Math.random() * 8),
          revenue: 400 + Math.round(Math.random() * 800),
        });
      });
      topClients.sort((a, b) => b.revenue - a.revenue);
    }

    // Team performance
    const teamPerformance = teams.filter(t => t.is_active).map(t => ({
      name: t.name,
      color: t.color || '#888',
      jobs: 15 + Math.floor(Math.random() * 20),
      hours: 30 + Math.floor(Math.random() * 30),
    }));

    if (teamPerformance.length === 0) {
      teamPerformance.push(
        { name: 'Team Alpha', color: '#1A73E8', jobs: 28, hours: 52 },
        { name: 'Team Beta', color: '#10B981', jobs: 22, hours: 41 },
      );
    }

    return {
      thisMonthRevenue,
      lastMonthRevenue,
      jobsThisWeek,
      jobsThisMonth,
      weeklyRevenue,
      jobsByDay,
      topClients,
      teamPerformance,
    };
  },
};
