/**
 * CleanClaw — Owner Schedule Builder Module (S2.5 + S2.6)
 *
 * Native calendar implementation (no external dependencies):
 * - Weekly view (7 days, 7am–6pm, 30-min slots)
 * - Day / Week navigation with prev/next
 * - Drag-and-drop (move between times and days)
 * - Click-to-open booking detail side panel
 * - Click empty slot → Add Booking modal
 * - Summary bar (stats)
 * - SSE real-time updates
 * - Generate/regenerate schedule button
 * - Team filter chips
 * - Mobile: single day view (<768px)
 */

window.OwnerScheduleBuilder = {
  _calendar: null,
  _slug: null,
  _teams: [],
  _selectedDate: null,
  _sidePanel: null,
  _undoTimer: null,
  _undoData: null,
  _fcLoaded: false,

  // Native calendar state
  _weekStart: null,
  _events: [],
  _visibleTeams: new Set(),
  _isMobile: false,
  _mobileDay: null,   // Date object for mobile single-day view
  _dragState: null,

  // Constants
  _SLOT_HEIGHT: 28,   // px per 30-min slot
  _START_HOUR: 7,
  _END_HOUR: 18,

  /**
   * Render the schedule builder into the container.
   */
  async render(container, params) {
    this._slug = CleanAPI._slug;
    this._selectedDate = new Date().toISOString().split('T')[0];
    this._isMobile = window.innerWidth < 768;
    this._mobileDay = new Date();
    this._mobileDay.setHours(0, 0, 0, 0);

    // Compute current week start (Monday)
    const today = new Date();
    this._weekStart = this._getWeekStart(today);

    container.innerHTML = this._buildHTML();

    // No-op: no external library needed
    await this._loadFullCalendar();

    // Load teams and summary in parallel
    await Promise.all([
      this._loadTeams(),
      this._loadSummary(),
    ]);

    // Initialize native calendar
    this._initCalendar();

    // Connect SSE
    this._connectSSE();

    // Bind UI events
    this._bindEvents();

    // Responsive listener
    this._resizeHandler = () => {
      const wasMobile = this._isMobile;
      this._isMobile = window.innerWidth < 768;
      if (wasMobile !== this._isMobile) {
        this._renderCalendar();
      }
    };
    window.addEventListener('resize', this._resizeHandler);

    // Listen for data changes from other screens (teams, bookings, clients)
    if (typeof DemoData !== 'undefined') {
      this._dataChangeHandler = (e) => {
        if (e.type === 'team') {
          // Refresh local teams cache and re-render filter chips
          this._teams = DemoData._teams || [];
          this._teamColorMap = {};
          this._teams.forEach(t => { this._teamColorMap[t.id] = t.color || '#3B82F6'; });
          this._teamColorMap['unassigned'] = '#F59E0B';
          this._visibleTeams = new Set(this._teams.map(t => String(t.id)));
          this._renderTeamFilter();
        }
        if (e.type === 'booking') {
          // Re-render calendar to show new bookings
          this._renderCalendar();
          this._loadSummary();
        }
      };
      DemoData.on('dataChanged', this._dataChangeHandler);
    }
  },

  // --- HTML Template ---

  _buildHTML() {
    return `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
        <!-- Summary Bar -->
        <div style="display:grid;grid-template-columns:repeat(4,1fr) auto;gap:var(--cc-space-3);align-items:center;" id="schedule-summary">
          <div class="cc-card cc-stat-card" style="padding:var(--cc-space-3) var(--cc-space-4);">
            <div>
              <div class="cc-stat-card-value cc-text-xl" id="summary-jobs">-</div>
              <div class="cc-stat-card-label">Jobs Today</div>
            </div>
          </div>
          <div class="cc-card cc-stat-card cc-stat-success" style="padding:var(--cc-space-3) var(--cc-space-4);">
            <div>
              <div class="cc-stat-card-value cc-text-xl" id="summary-revenue">$0</div>
              <div class="cc-stat-card-label">Revenue</div>
            </div>
          </div>
          <div class="cc-card cc-stat-card cc-stat-info" style="padding:var(--cc-space-3) var(--cc-space-4);">
            <div>
              <div class="cc-stat-card-value cc-text-xl" id="summary-teams">-</div>
              <div class="cc-stat-card-label">Teams Active</div>
            </div>
          </div>
          <div class="cc-card cc-stat-card cc-card-interactive" style="padding:var(--cc-space-3) var(--cc-space-4);cursor:pointer;" id="summary-unassigned-btn">
            <div>
              <div class="cc-stat-card-value cc-text-xl" id="summary-unassigned">0</div>
              <div class="cc-stat-card-label">Unassigned</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:var(--cc-space-2);">
            <button class="cc-btn cc-btn-primary cc-btn-sm" id="btn-generate" title="Generate schedule from recurring bookings">
              Generate Schedule
            </button>
            <div id="sse-status" style="display:none;"></div>
          </div>
        </div>

        <!-- Team Filter -->
        <div id="team-filter" style="display:none;align-items:center;gap:var(--cc-space-2);flex-wrap:wrap;">
          <span class="cc-text-sm cc-font-medium cc-text-muted">Filter teams:</span>
          <div id="team-filter-chips" style="display:flex;gap:var(--cc-space-2);flex-wrap:wrap;"></div>
        </div>

        <!-- Calendar Container -->
        <div class="cc-card" style="padding:var(--cc-space-3);overflow:hidden;">
          <div id="fc-calendar"></div>
        </div>

        <!-- Side Panel (booking detail) -->
        <div class="cc-modal-backdrop" id="side-panel-overlay"></div>
        <div id="side-panel" style="display:none;position:fixed;top:0;right:0;bottom:0;width:400px;max-width:90vw;background:#fff;box-shadow:var(--cc-shadow-xl);z-index:var(--cc-z-modal);flex-direction:column;overflow-y:auto;">
          <div style="display:flex;align-items:center;justify-content:space-between;padding:var(--cc-space-5);border-bottom:1px solid var(--cc-neutral-200);">
            <h3 id="panel-title" style="margin:0;">Booking Detail</h3>
            <button class="cc-btn cc-btn-ghost cc-btn-sm" id="panel-close" aria-label="Close" style="font-size:1.25rem;">&times;</button>
          </div>
          <div id="panel-body" style="flex:1;padding:var(--cc-space-5);overflow-y:auto;"></div>
          <div id="panel-footer" style="padding:var(--cc-space-4) var(--cc-space-5);border-top:1px solid var(--cc-neutral-200);"></div>
        </div>

        <!-- Undo toast -->
        <div id="undo-toast" style="display:none;position:fixed;bottom:calc(var(--cc-bottombar-height, 0px) + var(--cc-space-4));left:50%;transform:translateX(-50%);background:var(--cc-neutral-800);color:#fff;padding:var(--cc-space-3) var(--cc-space-5);border-radius:var(--cc-radius-lg);box-shadow:var(--cc-shadow-lg);z-index:var(--cc-z-toast);align-items:center;gap:var(--cc-space-3);">
          <span id="undo-message" class="cc-text-sm">Booking moved</span>
          <button class="cc-btn cc-btn-xs" id="undo-btn" style="background:rgba(255,255,255,0.2);color:#fff;border:1px solid rgba(255,255,255,0.3);">Undo</button>
        </div>

        <!-- Generate modal -->
        <div class="cc-modal-backdrop" id="generate-modal" onclick="OwnerScheduleBuilder._closeGenerateModal(event)">
          <div class="cc-modal" onclick="event.stopPropagation()" style="max-width:420px;">
            <div class="cc-modal-header">
              <h3 class="cc-modal-title">Generate Schedule</h3>
              <button class="cc-modal-close" onclick="OwnerScheduleBuilder._closeGenerateModal()">&times;</button>
            </div>
            <div class="cc-modal-body">
              <p class="cc-text-sm cc-text-muted" style="margin-bottom:var(--cc-space-4);">Generate daily schedule from recurring client bookings.</p>
              <div class="cc-form-group">
                <label class="cc-label">Date</label>
                <input type="date" id="generate-date" class="cc-input" />
              </div>
              <div class="cc-form-group">
                <label class="cc-checkbox">
                  <input type="checkbox" id="generate-force" class="cc-checkbox-input" />
                  <span class="cc-text-sm">Force regenerate (cancel existing)</span>
                </label>
              </div>
            </div>
            <div class="cc-modal-footer">
              <button class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerScheduleBuilder._closeGenerateModal()">Cancel</button>
              <button class="cc-btn cc-btn-primary cc-btn-sm" id="btn-generate-confirm">Generate</button>
            </div>
          </div>
        </div>

        <!-- Add Booking modal -->
        <div class="cc-modal-backdrop" id="add-booking-modal" onclick="OwnerScheduleBuilder._closeAddBookingModal(event)">
          <div class="cc-modal" onclick="event.stopPropagation()" style="max-width:480px;">
            <div class="cc-modal-header">
              <h3 class="cc-modal-title" id="add-booking-modal-title">Add Booking</h3>
              <button class="cc-modal-close" onclick="OwnerScheduleBuilder._closeAddBookingModal()">&times;</button>
            </div>
            <div class="cc-modal-body" style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
              <div class="cc-form-group">
                <label class="cc-label">Client</label>
                <select id="add-booking-client" class="cc-input"></select>
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Team</label>
                <select id="add-booking-team" class="cc-input"></select>
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Service</label>
                <select id="add-booking-service" class="cc-input"></select>
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Date</label>
                <input type="date" id="add-booking-date" class="cc-input" />
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
                <div class="cc-form-group">
                  <label class="cc-label">Start Time</label>
                  <select id="add-booking-start" class="cc-input"></select>
                </div>
                <div class="cc-form-group">
                  <label class="cc-label">End Time</label>
                  <select id="add-booking-end" class="cc-input"></select>
                </div>
              </div>
              <div class="cc-form-group">
                <label class="cc-label">Notes</label>
                <textarea id="add-booking-notes" class="cc-input" rows="2" placeholder="Optional notes..."></textarea>
              </div>
            </div>
            <div class="cc-modal-footer">
              <button class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerScheduleBuilder._closeAddBookingModal()">Cancel</button>
              <button class="cc-btn cc-btn-primary cc-btn-sm" id="btn-add-booking-save">Save Booking</button>
            </div>
          </div>
        </div>
      </div>
    `;
  },

  // --- FullCalendar CDN Loading (NO-OP) ---

  async _loadFullCalendar() {
    // Native calendar — no external library needed
    this._fcLoaded = true;
    return;
  },

  // --- Native Calendar Initialization ---

  _initCalendar() {
    this._injectCalendarStyles();
    this._renderCalendar();
  },

  _injectCalendarStyles() {
    if (document.getElementById('nc-calendar-styles')) return;
    const style = document.createElement('style');
    style.id = 'nc-calendar-styles';
    style.textContent = `
      .nc-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 4px;
        margin-bottom: 8px;
        flex-wrap: wrap;
        gap: 8px;
      }
      .nc-header-title {
        font-size: 1rem;
        font-weight: 600;
        color: var(--cc-neutral-800, #1f2937);
        white-space: nowrap;
      }
      .nc-header-nav {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .nc-nav-btn {
        padding: 4px 12px;
        border: 1px solid var(--cc-neutral-300, #d1d5db);
        background: #fff;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.8rem;
        font-weight: 500;
        color: var(--cc-neutral-700, #374151);
        transition: background 0.15s, border-color 0.15s;
      }
      .nc-nav-btn:hover {
        background: var(--cc-neutral-100, #f3f4f6);
        border-color: var(--cc-neutral-400, #9ca3af);
      }
      .nc-grid-wrapper {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
      }
      .nc-grid {
        display: grid;
        min-width: 600px;
        border: 1px solid var(--cc-neutral-200, #e5e7eb);
        border-radius: 8px;
        overflow: hidden;
      }
      .nc-grid-header {
        display: contents;
      }
      .nc-grid-header-cell {
        padding: 8px 4px;
        text-align: center;
        font-size: 0.75rem;
        font-weight: 600;
        color: var(--cc-neutral-600, #4b5563);
        background: var(--cc-neutral-50, #f9fafb);
        border-bottom: 1px solid var(--cc-neutral-200, #e5e7eb);
        text-transform: uppercase;
        letter-spacing: 0.03em;
      }
      .nc-grid-header-cell.nc-today {
        color: var(--cc-primary-600, #2563eb);
        background: var(--cc-primary-50, #eff6ff);
      }
      .nc-time-label {
        padding: 2px 6px 2px 4px;
        text-align: right;
        font-size: 0.65rem;
        color: var(--cc-neutral-400, #9ca3af);
        border-right: 1px solid var(--cc-neutral-200, #e5e7eb);
        background: var(--cc-neutral-50, #f9fafb);
        min-width: 48px;
        box-sizing: border-box;
        position: relative;
      }
      .nc-time-label span {
        position: relative;
        top: -6px;
      }
      .nc-day-col {
        position: relative;
        border-right: 1px solid var(--cc-neutral-100, #f3f4f6);
        min-height: ${28}px;
        cursor: pointer;
        transition: background 0.1s;
      }
      .nc-day-col:last-child {
        border-right: none;
      }
      .nc-day-col:hover {
        background: var(--cc-neutral-50, #f9fafb);
      }
      .nc-day-col.nc-today-col {
        background: rgba(37, 99, 235, 0.02);
      }
      .nc-slot-row {
        display: contents;
      }
      .nc-slot-border-top {
        border-top: 1px solid var(--cc-neutral-100, #f3f4f6);
      }
      .nc-slot-border-hour {
        border-top: 1px solid var(--cc-neutral-200, #e5e7eb);
      }
      .nc-event {
        position: absolute;
        left: 2px;
        right: 2px;
        border-radius: 4px;
        padding: 2px 4px;
        font-size: 0.68rem;
        line-height: 1.3;
        overflow: hidden;
        cursor: pointer;
        z-index: 2;
        box-shadow: 0 1px 2px rgba(0,0,0,0.08);
        transition: box-shadow 0.15s, transform 0.15s;
        border-left: 3px solid rgba(0,0,0,0.15);
        user-select: none;
      }
      .nc-event:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        transform: translateY(-1px);
        z-index: 3;
      }
      .nc-event.nc-dragging {
        opacity: 0.7;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        z-index: 10;
      }
      .nc-event-time {
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .nc-event-title {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .nc-event-address {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        opacity: 0.8;
        font-size: 0.6rem;
      }
      .nc-now-line {
        position: absolute;
        left: 0;
        right: 0;
        height: 2px;
        background: var(--cc-danger-500, #ef4444);
        z-index: 5;
        pointer-events: none;
      }
      .nc-now-line::before {
        content: '';
        position: absolute;
        left: -4px;
        top: -3px;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--cc-danger-500, #ef4444);
      }
      .nc-drop-target {
        background: var(--cc-primary-50, #eff6ff) !important;
        outline: 2px dashed var(--cc-primary-300, #93c5fd);
        outline-offset: -2px;
      }

      /* Mobile cards */
      .nc-mobile-card {
        display: flex;
        gap: 12px;
        padding: 12px;
        border: 1px solid var(--cc-neutral-200, #e5e7eb);
        border-radius: 8px;
        margin-bottom: 8px;
        cursor: pointer;
        transition: box-shadow 0.15s;
        background: #fff;
      }
      .nc-mobile-card:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      }
      .nc-mobile-card-color {
        width: 4px;
        border-radius: 2px;
        flex-shrink: 0;
      }
      .nc-mobile-card-body {
        flex: 1;
        min-width: 0;
      }
      .nc-mobile-card-time {
        font-size: 0.75rem;
        font-weight: 600;
        color: var(--cc-neutral-600, #4b5563);
      }
      .nc-mobile-card-title {
        font-size: 0.875rem;
        font-weight: 600;
        color: var(--cc-neutral-800, #1f2937);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .nc-mobile-card-meta {
        font-size: 0.7rem;
        color: var(--cc-neutral-500, #6b7280);
      }

      /* Status colors on events */
      .nc-status-completed { opacity: 0.6; }
      .nc-status-cancelled { opacity: 0.4; text-decoration: line-through; }
      .nc-status-in_progress { animation: nc-pulse 2s ease-in-out infinite; }
      @keyframes nc-pulse {
        0%, 100% { box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
        50% { box-shadow: 0 0 0 3px rgba(37,99,235,0.15); }
      }

      @media (max-width: 767px) {
        .nc-grid { min-width: unset; }
        .nc-header-title { font-size: 0.875rem; }
      }
    `;
    document.head.appendChild(style);
  },

  // --- Week Helpers ---

  _getWeekStart(date) {
    const d = new Date(date);
    d.setHours(0, 0, 0, 0);
    const day = d.getDay(); // 0=Sun
    const diff = day === 0 ? -6 : 1 - day; // Monday start
    d.setDate(d.getDate() + diff);
    return d;
  },

  _getWeekDays() {
    const days = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(this._weekStart);
      d.setDate(d.getDate() + i);
      days.push(d);
    }
    return days;
  },

  _formatDateRange() {
    const days = this._getWeekDays();
    const first = days[0];
    const last = days[6];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    if (first.getMonth() === last.getMonth()) {
      return `${months[first.getMonth()]} ${first.getDate()} - ${last.getDate()}, ${first.getFullYear()}`;
    }
    return `${months[first.getMonth()]} ${first.getDate()} - ${months[last.getMonth()]} ${last.getDate()}, ${last.getFullYear()}`;
  },

  _formatMobileDayTitle() {
    const d = this._mobileDay;
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${dayNames[d.getDay()]}, ${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  },

  _isToday(date) {
    const today = new Date();
    return date.getFullYear() === today.getFullYear() &&
           date.getMonth() === today.getMonth() &&
           date.getDate() === today.getDate();
  },

  _dateStr(date) {
    return date.toISOString().split('T')[0];
  },

  _timeSlots() {
    const slots = [];
    for (let h = this._START_HOUR; h < this._END_HOUR; h++) {
      slots.push({ hour: h, min: 0 });
      slots.push({ hour: h, min: 30 });
    }
    return slots;
  },

  _formatTime12(h, m) {
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h === 0 ? 12 : (h > 12 ? h - 12 : h);
    return `${h12}:${m.toString().padStart(2, '0')} ${ampm}`;
  },

  _formatTime24(h, m) {
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
  },

  // --- Calendar Rendering ---

  async _renderCalendar() {
    const calendarEl = document.getElementById('fc-calendar');
    if (!calendarEl) return;

    // Fetch events for the visible range
    await this._refreshEvents();

    if (this._isMobile) {
      this._renderMobileView(calendarEl);
    } else {
      this._renderWeekView(calendarEl);
    }
  },

  async _refreshEvents() {
    let start, end;
    if (this._isMobile) {
      start = this._dateStr(this._mobileDay);
      const next = new Date(this._mobileDay);
      next.setDate(next.getDate() + 1);
      end = this._dateStr(next);
    } else {
      const days = this._getWeekDays();
      start = this._dateStr(days[0]);
      const after = new Date(days[6]);
      after.setDate(after.getDate() + 1);
      end = this._dateStr(after);
    }
    this._events = await this._fetchEvents(start, end);
  },

  _renderWeekView(container) {
    const days = this._getWeekDays();
    const slots = this._timeSlots();
    const totalSlots = slots.length;
    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Build header
    let html = `
      <div class="nc-header">
        <div class="nc-header-nav">
          <button class="nc-nav-btn" id="nc-prev-week">&larr; Prev</button>
          <button class="nc-nav-btn" id="nc-today-btn">Today</button>
          <button class="nc-nav-btn" id="nc-next-week">Next &rarr;</button>
        </div>
        <div class="nc-header-title">${this._formatDateRange()}</div>
      </div>
    `;

    // Grid: 1 time column + 7 day columns
    html += `<div class="nc-grid-wrapper"><div class="nc-grid" style="grid-template-columns: 52px repeat(7, 1fr);">`;

    // Header row
    html += `<div class="nc-grid-header-cell" style="border-right:1px solid var(--cc-neutral-200,#e5e7eb);"></div>`;
    days.forEach((d, i) => {
      const isToday = this._isToday(d);
      html += `<div class="nc-grid-header-cell${isToday ? ' nc-today' : ''}">
        ${dayNames[i]}<br><span style="font-size:1.1em;">${d.getDate()}</span>
      </div>`;
    });

    // Slot rows with day columns (each column is a positioned container)
    slots.forEach((slot, si) => {
      const isHour = slot.min === 0;
      const borderClass = isHour ? 'nc-slot-border-hour' : 'nc-slot-border-top';

      // Time label
      html += `<div class="nc-time-label ${borderClass}" style="grid-row:${si + 2};">`;
      if (isHour) {
        html += `<span>${this._formatTime12(slot.hour, 0)}</span>`;
      }
      html += `</div>`;

      // Day columns for this slot
      days.forEach((d, di) => {
        const isToday = this._isToday(d);
        const dateStr = this._dateStr(d);
        const timeStr = this._formatTime24(slot.hour, slot.min);
        html += `<div class="nc-day-col ${borderClass}${isToday ? ' nc-today-col' : ''}"
                      data-date="${dateStr}"
                      data-time="${timeStr}"
                      data-slot-index="${si}"
                      data-day-index="${di}"
                      style="grid-row:${si + 2};grid-column:${di + 2};"></div>`;
      });
    });

    html += `</div></div>`; // close grid + wrapper

    container.innerHTML = html;

    // Now render events as absolutely positioned blocks inside day columns
    this._renderEventsOnGrid(days, slots);

    // Render now indicator
    this._renderNowIndicator(days, slots);

    // Bind calendar navigation
    this._bindCalendarNav();

    // Bind slot clicks and drag
    this._bindSlotInteractions();
  },

  _renderEventsOnGrid(days, slots) {
    const slotH = this._SLOT_HEIGHT;
    const filteredEvents = this._getFilteredEvents();

    days.forEach((d, di) => {
      const dateStr = this._dateStr(d);
      const dayEvents = filteredEvents.filter(e => {
        const eDate = (e.start || '').split('T')[0];
        return eDate === dateStr;
      });

      if (dayEvents.length === 0) return;

      // Find all cells for this day to get positioning reference
      const firstCell = document.querySelector(`.nc-day-col[data-date="${dateStr}"][data-slot-index="0"]`);
      if (!firstCell) return;

      // Create an overlay container for events in this day column
      const colRect = firstCell.getBoundingClientRect();
      const parentGrid = firstCell.closest('.nc-grid');
      if (!parentGrid) return;

      dayEvents.forEach(event => {
        const startTime = this._parseEventTime(event.start);
        const endTime = this._parseEventTime(event.end || event.start);
        if (!startTime) return;

        const startMin = (startTime.h - this._START_HOUR) * 60 + startTime.m;
        const endMin = endTime ? (endTime.h - this._START_HOUR) * 60 + endTime.m : startMin + 60;
        const topSlots = startMin / 30;
        const heightSlots = Math.max((endMin - startMin) / 30, 1);

        // Find the target cell to position relative to
        const startSlotIdx = Math.floor(startMin / 30);
        const targetCell = document.querySelector(`.nc-day-col[data-date="${dateStr}"][data-slot-index="${startSlotIdx}"]`);
        if (!targetCell) return;

        const props = event.extendedProps || {};
        const teamColor = this._getEventColor(event);
        const status = props.status || event.status || 'scheduled';
        const clientName = props.client_name || event.title || '';
        const address = props.address || '';
        const timeText = this._formatEventTimeRange(event);

        const eventEl = document.createElement('div');
        eventEl.className = `nc-event nc-status-${status}`;
        eventEl.dataset.eventId = event.id;
        eventEl.style.cssText = `
          top: 0px;
          height: ${heightSlots * slotH - 2}px;
          background: ${teamColor}20;
          color: ${this._darkenColor(teamColor)};
          border-left-color: ${teamColor};
        `;
        eventEl.title = `${clientName} - ${props.service_type || ''}\n${address}`;
        eventEl.innerHTML = `
          <div class="nc-event-time">${timeText}</div>
          <div class="nc-event-title">${clientName}</div>
          ${address && heightSlots >= 2 ? `<div class="nc-event-address">${address}</div>` : ''}
        `;
        eventEl.draggable = true;

        // Click handler
        eventEl.addEventListener('click', (e) => {
          e.stopPropagation();
          this._handleNativeEventClick(event);
        });

        // Drag start
        eventEl.addEventListener('dragstart', (e) => {
          e.dataTransfer.setData('text/plain', event.id);
          e.dataTransfer.effectAllowed = 'move';
          eventEl.classList.add('nc-dragging');
          this._dragState = { eventId: event.id, event: event };
        });
        eventEl.addEventListener('dragend', () => {
          eventEl.classList.remove('nc-dragging');
          document.querySelectorAll('.nc-drop-target').forEach(el => el.classList.remove('nc-drop-target'));
          this._dragState = null;
        });

        // We need to position the event spanning multiple slot rows.
        // Use the first slot cell as the anchor, position relative inside it.
        // Since grid cells can't easily contain absolute children spanning rows,
        // we place the event in the first cell and let it overflow.
        targetCell.style.position = 'relative';
        targetCell.style.overflow = 'visible';
        targetCell.style.zIndex = '1';
        targetCell.appendChild(eventEl);
      });
    });
  },

  _renderNowIndicator(days, slots) {
    const now = new Date();
    const todayStr = this._dateStr(now);
    const dayIdx = days.findIndex(d => this._dateStr(d) === todayStr);
    if (dayIdx < 0) return;

    const nowMin = (now.getHours() - this._START_HOUR) * 60 + now.getMinutes();
    if (nowMin < 0 || nowMin > (this._END_HOUR - this._START_HOUR) * 60) return;

    const slotIdx = Math.floor(nowMin / 30);
    const offsetInSlot = (nowMin % 30) / 30 * this._SLOT_HEIGHT;

    const targetCell = document.querySelector(`.nc-day-col[data-date="${todayStr}"][data-slot-index="${slotIdx}"]`);
    if (!targetCell) return;

    const line = document.createElement('div');
    line.className = 'nc-now-line';
    line.style.top = `${offsetInSlot}px`;
    targetCell.style.position = 'relative';
    targetCell.style.overflow = 'visible';
    targetCell.appendChild(line);
  },

  _renderMobileView(container) {
    const dateStr = this._dateStr(this._mobileDay);
    const filteredEvents = this._getFilteredEvents();
    const dayEvents = filteredEvents.filter(e => (e.start || '').split('T')[0] === dateStr);

    // Sort by start time
    dayEvents.sort((a, b) => (a.start || '').localeCompare(b.start || ''));

    let html = `
      <div class="nc-header">
        <div class="nc-header-nav">
          <button class="nc-nav-btn" id="nc-prev-day">&larr;</button>
          <button class="nc-nav-btn" id="nc-today-btn">Today</button>
          <button class="nc-nav-btn" id="nc-next-day">&rarr;</button>
        </div>
        <div class="nc-header-title">${this._formatMobileDayTitle()}</div>
      </div>
      <div style="padding:4px 0;">
        <button class="cc-btn cc-btn-ghost cc-btn-sm" style="width:100%;margin-bottom:8px;" id="nc-mobile-add-btn">+ Add Booking</button>
    `;

    if (dayEvents.length === 0) {
      html += `<div style="text-align:center;padding:32px 16px;color:var(--cc-neutral-400,#9ca3af);">
        <p style="font-size:0.875rem;">No bookings for this day</p>
      </div>`;
    } else {
      dayEvents.forEach(event => {
        const props = event.extendedProps || {};
        const teamColor = this._getEventColor(event);
        const status = props.status || event.status || 'scheduled';
        const clientName = props.client_name || event.title || '';
        const address = props.address || '';
        const timeText = this._formatEventTimeRange(event);
        const teamName = props.team_name || '';

        html += `
          <div class="nc-mobile-card" data-event-id="${event.id}">
            <div class="nc-mobile-card-color" style="background:${teamColor};"></div>
            <div class="nc-mobile-card-body">
              <div class="nc-mobile-card-time">${timeText}</div>
              <div class="nc-mobile-card-title">${clientName}</div>
              <div class="nc-mobile-card-meta">${props.service_type || ''} ${teamName ? '&middot; ' + teamName : ''} ${address ? '&middot; ' + address : ''}</div>
            </div>
            <span class="cc-badge ${this._getStatusBadgeClass(status)}" style="align-self:center;font-size:0.6rem;">${status}</span>
          </div>
        `;
      });
    }

    html += `</div>`;
    container.innerHTML = html;

    // Bind mobile card clicks
    container.querySelectorAll('.nc-mobile-card').forEach(card => {
      card.addEventListener('click', () => {
        const eventId = card.dataset.eventId;
        const event = this._events.find(e => String(e.id) === String(eventId));
        if (event) this._handleNativeEventClick(event);
      });
    });

    // Bind mobile nav
    this._bindCalendarNav();

    // Bind mobile add button
    const addBtn = document.getElementById('nc-mobile-add-btn');
    if (addBtn) addBtn.addEventListener('click', () => this._openAddBookingModal(dateStr, '09:00'));
  },

  // --- Event Helpers ---

  _getFilteredEvents() {
    if (this._visibleTeams.size === 0 && this._teams.length > 0) {
      // If no filter set, show all
      return this._events;
    }
    if (this._visibleTeams.size === 0) return this._events;
    return this._events.filter(e => {
      const teamId = (e.extendedProps || {}).team_id || e.resourceId || e.team_id;
      if (!teamId) return true; // unassigned - always show
      return this._visibleTeams.has(String(teamId));
    });
  },

  _parseEventTime(dateTimeStr) {
    if (!dateTimeStr) return null;
    // Handle "2026-03-23T09:00:00" or "09:00:00" or "09:00"
    let timePart = dateTimeStr;
    if (dateTimeStr.includes('T')) {
      timePart = dateTimeStr.split('T')[1];
    }
    const parts = timePart.split(':');
    return { h: parseInt(parts[0], 10), m: parseInt(parts[1] || '0', 10) };
  },

  _formatEventTimeRange(event) {
    const start = this._parseEventTime(event.start);
    const end = this._parseEventTime(event.end);
    if (!start) return '';
    const s = this._formatTime12(start.h, start.m);
    if (!end) return s;
    const e = this._formatTime12(end.h, end.m);
    return `${s} - ${e}`;
  },

  _getEventColor(event) {
    const props = event.extendedProps || {};
    const teamId = props.team_id || event.resourceId || event.team_id;
    if (teamId && this._teamColorMap && this._teamColorMap[teamId]) {
      return this._teamColorMap[teamId];
    }
    // Try to find from color property directly
    if (event.color || event.backgroundColor) return event.color || event.backgroundColor;
    return '#3B82F6'; // default blue
  },

  _darkenColor(hex) {
    // Return a darker version for text contrast
    if (!hex || hex.length < 7) return '#1f2937';
    const r = Math.max(0, parseInt(hex.slice(1, 3), 16) - 60);
    const g = Math.max(0, parseInt(hex.slice(3, 5), 16) - 60);
    const b = Math.max(0, parseInt(hex.slice(5, 7), 16) - 60);
    return `rgb(${r},${g},${b})`;
  },

  _getStatusBadgeClass(status) {
    const map = {
      scheduled: 'cc-badge-primary',
      confirmed: 'cc-badge-info',
      in_progress: 'cc-badge-warning',
      completed: 'cc-badge-success',
      cancelled: 'cc-badge-danger',
    };
    return map[status] || 'cc-badge-neutral';
  },

  // --- Calendar Navigation ---

  _bindCalendarNav() {
    // Week nav
    const prevWeek = document.getElementById('nc-prev-week');
    const nextWeek = document.getElementById('nc-next-week');
    const todayBtn = document.getElementById('nc-today-btn');

    if (prevWeek) prevWeek.addEventListener('click', () => {
      if (this._isMobile) return;
      this._weekStart.setDate(this._weekStart.getDate() - 7);
      this._selectedDate = this._dateStr(this._weekStart);
      this._renderCalendar();
      this._loadSummary();
    });
    if (nextWeek) nextWeek.addEventListener('click', () => {
      if (this._isMobile) return;
      this._weekStart.setDate(this._weekStart.getDate() + 7);
      this._selectedDate = this._dateStr(this._weekStart);
      this._renderCalendar();
      this._loadSummary();
    });

    // Mobile day nav
    const prevDay = document.getElementById('nc-prev-day');
    const nextDay = document.getElementById('nc-next-day');

    if (prevDay) prevDay.addEventListener('click', () => {
      this._mobileDay.setDate(this._mobileDay.getDate() - 1);
      this._selectedDate = this._dateStr(this._mobileDay);
      this._renderCalendar();
      this._loadSummary();
    });
    if (nextDay) nextDay.addEventListener('click', () => {
      this._mobileDay.setDate(this._mobileDay.getDate() + 1);
      this._selectedDate = this._dateStr(this._mobileDay);
      this._renderCalendar();
      this._loadSummary();
    });

    // Today button (both views)
    if (todayBtn) todayBtn.addEventListener('click', () => {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      if (this._isMobile) {
        this._mobileDay = today;
      } else {
        this._weekStart = this._getWeekStart(today);
      }
      this._selectedDate = this._dateStr(today);
      this._renderCalendar();
      this._loadSummary();
    });
  },

  // --- Slot Interactions (click + drag-drop) ---

  _bindSlotInteractions() {
    const cells = document.querySelectorAll('.nc-day-col');
    cells.forEach(cell => {
      // Click on empty area -> add booking
      cell.addEventListener('click', (e) => {
        // Don't trigger if clicking on an event
        if (e.target.closest('.nc-event')) return;
        const date = cell.dataset.date;
        const time = cell.dataset.time;
        this._openAddBookingModal(date, time);
      });

      // Drag over
      cell.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        cell.classList.add('nc-drop-target');
      });
      cell.addEventListener('dragleave', () => {
        cell.classList.remove('nc-drop-target');
      });

      // Drop
      cell.addEventListener('drop', (e) => {
        e.preventDefault();
        cell.classList.remove('nc-drop-target');
        const eventId = e.dataTransfer.getData('text/plain');
        if (!eventId) return;
        const newDate = cell.dataset.date;
        const newTime = cell.dataset.time;
        this._handleNativeDrop(eventId, newDate, newTime);
      });
    });
  },

  // --- Native Event Handlers ---

  _handleNativeEventClick(event) {
    const props = event.extendedProps || {};
    const startTime = this._parseEventTime(event.start);
    const endTime = this._parseEventTime(event.end);

    this._openSidePanel(event.id, {
      title: event.title,
      client_name: props.client_name || event.title,
      address: props.address,
      city: props.city,
      service_type: props.service_type,
      status: props.status || event.status || 'scheduled',
      team_name: props.team_name,
      team_id: props.team_id || event.resourceId,
      duration_minutes: props.duration_minutes,
      quoted_price: props.quoted_price,
      access_instructions: props.access_instructions,
      special_instructions: props.special_instructions,
      start: startTime ? this._formatTime12(startTime.h, startTime.m) : '',
      end: endTime ? this._formatTime12(endTime.h, endTime.m) : '',
      date: event.start ? event.start.split('T')[0] : '',
    });
  },

  async _handleNativeDrop(eventId, newDate, newTime) {
    const event = this._events.find(e => String(e.id) === String(eventId));
    if (!event) return;

    const props = event.extendedProps || {};
    const status = props.status || event.status;

    if (status === 'confirmed') {
      if (!confirm('This booking is confirmed. Rescheduling will notify the client. Continue?')) {
        return;
      }
    }

    // Save undo data (old event state)
    const oldStart = event.start;
    this._undoData = {
      bookingId: eventId,
      revert: () => {
        // Re-fetch to revert visually
        this._renderCalendar();
      },
    };

    const updateData = {
      scheduled_date: newDate,
      scheduled_start: newTime + ':00',
    };

    try {
      await CleanAPI.cleanPatch(`/bookings/${eventId}`, updateData);
      this._showUndoToast('Booking moved');
      this._loadSummary();
      await this._renderCalendar();
    } catch (err) {
      console.error('[Schedule] Move failed:', err);
      await this._renderCalendar(); // revert visual
      CleanClaw.showToast(err.detail || 'Could not move booking. The time slot may overlap with another job.', 'error');
    }
  },

  // --- Add Booking Modal ---

  _openAddBookingModal(date, time, editEvent) {
    const modal = document.getElementById('add-booking-modal');
    if (!modal) return;

    const titleEl = document.getElementById('add-booking-modal-title');
    const dateInput = document.getElementById('add-booking-date');
    const startSelect = document.getElementById('add-booking-start');
    const endSelect = document.getElementById('add-booking-end');
    const clientSelect = document.getElementById('add-booking-client');
    const teamSelect = document.getElementById('add-booking-team');
    const serviceSelect = document.getElementById('add-booking-service');
    const notesEl = document.getElementById('add-booking-notes');
    const saveBtn = document.getElementById('btn-add-booking-save');

    // Populate time options
    const timeOptions = [];
    for (let h = this._START_HOUR; h <= this._END_HOUR; h++) {
      timeOptions.push(this._formatTime24(h, 0));
      if (h < this._END_HOUR) timeOptions.push(this._formatTime24(h, 30));
    }

    startSelect.innerHTML = timeOptions.map(t =>
      `<option value="${t}"${t === time ? ' selected' : ''}>${this._formatTime12(parseInt(t), parseInt(t.split(':')[1]))}</option>`
    ).join('');

    // Default end = start + 1 hour
    const startH = parseInt(time);
    const startM = parseInt(time.split(':')[1]);
    const endH = Math.min(startH + 1, this._END_HOUR);
    const endDefault = this._formatTime24(endH, startM);
    endSelect.innerHTML = timeOptions.map(t =>
      `<option value="${t}"${t === endDefault ? ' selected' : ''}>${this._formatTime12(parseInt(t), parseInt(t.split(':')[1]))}</option>`
    ).join('');

    dateInput.value = date || this._selectedDate;

    // Populate teams — always read LIVE data from DemoData if available
    const liveTeams = (typeof DemoData !== 'undefined' && DemoData._teams) ? DemoData._teams : this._teams;
    teamSelect.innerHTML = `<option value="">-- Select Team --</option>` +
      liveTeams.filter(t => t.is_active !== false).map(t => `<option value="${t.id}">${t.name}</option>`).join('');

    // Populate clients and services — read LIVE from DemoData at modal open time
    clientSelect.innerHTML = `<option value="">Loading...</option>`;
    serviceSelect.innerHTML = `<option value="">Loading...</option>`;

    this._loadClientsForModal(clientSelect);
    this._loadServicesForModal(serviceSelect);

    if (notesEl) notesEl.value = '';

    // Handle edit mode
    this._editingBookingId = null;
    if (editEvent) {
      titleEl.textContent = 'Edit Booking';
      this._editingBookingId = editEvent.id;
      // Pre-fill will be handled after clients/services load
    } else {
      titleEl.textContent = 'Add Booking';
    }

    modal.classList.add('cc-visible');

    // Save handler (remove old, add new)
    const newSaveBtn = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSaveBtn, saveBtn);
    newSaveBtn.id = 'btn-add-booking-save';
    newSaveBtn.addEventListener('click', () => this._saveBooking());
  },

  _closeAddBookingModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('add-booking-modal');
    if (modal) modal.classList.remove('cc-visible');
    this._editingBookingId = null;
  },

  async _loadClientsForModal(selectEl) {
    try {
      const data = await CleanAPI.cleanGet('/clients');
      const clients = (data && data.clients) ? data.clients : (Array.isArray(data) ? data : []);
      selectEl.innerHTML = `<option value="">-- Select Client --</option>` +
        clients.map(c => `<option value="${c.id}">${c.name || c.full_name || (c.first_name + ' ' + c.last_name)}</option>`).join('');
    } catch (err) {
      selectEl.innerHTML = `<option value="">No clients available</option>`;
    }
  },

  async _loadServicesForModal(selectEl) {
    try {
      const data = await CleanAPI.cleanGet('/services');
      const services = (data && data.services) ? data.services : (Array.isArray(data) ? data : []);
      selectEl.innerHTML = `<option value="">-- Select Service --</option>` +
        services.map(s => `<option value="${s.id}">${s.name} ${s.duration_minutes ? '(' + s.duration_minutes + ' min)' : ''}</option>`).join('');
    } catch (err) {
      selectEl.innerHTML = `<option value="">No services available</option>`;
    }
  },

  async _saveBooking() {
    const clientId = document.getElementById('add-booking-client')?.value;
    const teamId = document.getElementById('add-booking-team')?.value;
    const serviceId = document.getElementById('add-booking-service')?.value;
    const date = document.getElementById('add-booking-date')?.value;
    const startTime = document.getElementById('add-booking-start')?.value;
    const endTime = document.getElementById('add-booking-end')?.value;
    const notes = document.getElementById('add-booking-notes')?.value;

    if (!clientId) {
      CleanClaw.showToast('Please select a client.', 'warning');
      return;
    }
    if (!date || !startTime) {
      CleanClaw.showToast('Please select date and start time.', 'warning');
      return;
    }

    const payload = {
      client_id: clientId,
      team_id: teamId || null,
      service_id: serviceId || null,
      scheduled_date: date,
      scheduled_start: startTime + ':00',
      scheduled_end: endTime ? endTime + ':00' : null,
      notes: notes || null,
    };

    try {
      if (this._editingBookingId) {
        await CleanAPI.cleanPatch(`/bookings/${this._editingBookingId}`, payload);
        CleanClaw.showToast('Booking updated.', 'success');
      } else {
        await CleanAPI.cleanPost('/bookings', payload);
        CleanClaw.showToast('Booking added.', 'success');
      }
      this._closeAddBookingModal();
      await this._renderCalendar();
      this._loadSummary();
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Could not save booking. Please try again.', 'error');
    }
  },

  // --- Data Fetching ---

  async _fetchEvents(start, end) {
    try {
      const startDate = start.split('T')[0];
      const endDate = end.split('T')[0];
      const events = await CleanAPI.cleanGet(`/schedule/calendar?start=${startDate}&end=${endDate}`);
      return Array.isArray(events) ? events : (events?.events || []);
    } catch (err) {
      console.error('[Schedule] Event fetch error:', err);
      return [];
    }
  },

  async _loadTeams() {
    try {
      const data = await CleanAPI.cleanGet('/teams');
      this._teams = (data && data.teams) ? data.teams : (Array.isArray(data) ? data : []);

      // Build team color map
      this._teamColorMap = {};
      this._teams.forEach(t => {
        this._teamColorMap[t.id] = t.color || '#3B82F6';
      });
      this._teamColorMap['unassigned'] = '#F59E0B';

      // Initialize visible teams (all visible)
      this._visibleTeams = new Set(this._teams.map(t => String(t.id)));

      // Build team filter chips
      this._renderTeamFilter();
    } catch (err) {
      console.error('[Schedule] Failed to load teams:', err);
      this._teams = [];
    }
  },

  async _loadSummary() {
    try {
      const data = await CleanAPI.cleanGet(`/schedule/summary?date=${this._selectedDate}`) || {};
      const t = data.today || {};
      if (!data || Object.keys(data).length === 0) return;
      const jobCount = t.active_jobs || t.total || 0;
      const teamsActive = t.teams_active || data.teams_active || 0;
      const unassigned = t.unassigned_jobs || t.unassigned || 0;
      document.getElementById('summary-jobs').textContent = jobCount;
      document.getElementById('summary-revenue').textContent = `$${(t.revenue || 0).toFixed(0)}`;
      document.getElementById('summary-teams').textContent = teamsActive;

      const unEl = document.getElementById('summary-unassigned');
      unEl.textContent = unassigned;

      // Update stat card color based on unassigned count
      const unCard = document.getElementById('summary-unassigned-btn');
      if (unCard) {
        unCard.querySelector('.cc-stat-card-value')?.classList.toggle('cc-text-warning', unassigned > 0);
        if (unassigned > 0) {
          unCard.classList.add('cc-stat-warning');
        } else {
          unCard.classList.remove('cc-stat-warning');
        }
      }
    } catch (err) {
      console.error('[Schedule] Failed to load summary:', err);
    }
  },

  // --- Team Filter ---

  _renderTeamFilter() {
    if (this._teams.length <= 1) return;

    const filterEl = document.getElementById('team-filter');
    const chipsEl = document.getElementById('team-filter-chips');
    if (!filterEl || !chipsEl) return;

    filterEl.style.display = 'flex';

    chipsEl.innerHTML = this._teams.map(t => `
      <label class="cc-tag cc-tag-primary" style="cursor:pointer;border-color:${t.color || 'var(--cc-primary-200)'};gap:var(--cc-space-2);">
        <input type="checkbox" checked data-team-id="${t.id}" onchange="OwnerScheduleBuilder._onTeamFilterChange()" style="accent-color:${t.color || 'var(--cc-primary-500)'};" />
        <span class="cc-status-dot" style="background:${t.color || 'var(--cc-primary-500)'};width:8px;height:8px;border-radius:50%;display:inline-block;"></span>
        ${t.name}
      </label>
    `).join('');
  },

  _onTeamFilterChange() {
    const checkboxes = document.querySelectorAll('#team-filter-chips input[type=checkbox]');
    this._visibleTeams = new Set();
    checkboxes.forEach(cb => {
      if (cb.checked) this._visibleTeams.add(cb.dataset.teamId);
    });
    // Re-render calendar with filtered events
    this._renderCalendar();
  },

  // --- Event Click (Side Panel) --- preserved from original

  _openSidePanel(bookingId, data) {
    const overlay = document.getElementById('side-panel-overlay');
    const panel = document.getElementById('side-panel');
    const body = document.getElementById('panel-body');
    const footer = document.getElementById('panel-footer');
    const title = document.getElementById('panel-title');

    if (!panel || !body) return;

    title.textContent = data.client_name || 'Booking Detail';

    const statusMap = {
      scheduled: 'cc-badge-primary',
      confirmed: 'cc-badge-info',
      in_progress: 'cc-badge-warning',
      completed: 'cc-badge-success',
      cancelled: 'cc-badge-danger',
    };
    const statusBadge = `<span class="cc-badge ${statusMap[data.status] || 'cc-badge-neutral'}">${data.status || 'scheduled'}</span>`;

    body.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:var(--cc-space-5);">
        <div style="display:flex;flex-direction:column;gap:var(--cc-space-3);">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span class="cc-text-sm cc-text-muted">Status</span>
            ${statusBadge}
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span class="cc-text-sm cc-text-muted">Service</span>
            <span class="cc-text-sm cc-font-medium">${data.service_type || '-'}</span>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span class="cc-text-sm cc-text-muted">Date</span>
            <span class="cc-text-sm cc-font-medium">${data.date || '-'}</span>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span class="cc-text-sm cc-text-muted">Time</span>
            <span class="cc-text-sm cc-font-medium">${data.start}${data.end ? ' - ' + data.end : ''}</span>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span class="cc-text-sm cc-text-muted">Duration</span>
            <span class="cc-text-sm cc-font-medium">${data.duration_minutes ? data.duration_minutes + ' min' : '-'}</span>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span class="cc-text-sm cc-text-muted">Team</span>
            <span class="cc-text-sm cc-font-medium">${data.team_name || 'Unassigned'}</span>
          </div>
        </div>

        <div style="border-top:1px solid var(--cc-neutral-200);padding-top:var(--cc-space-4);">
          <h4 style="margin:0 0 var(--cc-space-3);" class="cc-text-sm cc-font-semibold">Location</h4>
          <p class="cc-text-sm">${data.address || '-'}${data.city ? ', ' + data.city : ''}</p>
          ${data.address ? `
            <a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((data.address || '') + ' ' + (data.city || ''))}"
               target="_blank" rel="noopener" class="cc-btn cc-btn-ghost cc-btn-xs" style="margin-top:var(--cc-space-2);">
              Navigate &rarr;
            </a>
          ` : ''}
        </div>

        ${data.access_instructions ? `
          <div style="border-top:1px solid var(--cc-neutral-200);padding-top:var(--cc-space-4);">
            <h4 style="margin:0 0 var(--cc-space-2);" class="cc-text-sm cc-font-semibold">Access Instructions</h4>
            <p class="cc-text-sm cc-text-muted">${data.access_instructions}</p>
          </div>
        ` : ''}

        ${data.special_instructions ? `
          <div style="border-top:1px solid var(--cc-neutral-200);padding-top:var(--cc-space-4);">
            <h4 style="margin:0 0 var(--cc-space-2);" class="cc-text-sm cc-font-semibold">Special Instructions</h4>
            <p class="cc-text-sm cc-text-muted">${data.special_instructions}</p>
          </div>
        ` : ''}

        ${data.quoted_price ? `
          <div style="border-top:1px solid var(--cc-neutral-200);padding-top:var(--cc-space-4);display:flex;align-items:center;justify-content:space-between;">
            <span class="cc-text-sm cc-text-muted">Price</span>
            <span style="font-size:var(--cc-text-xl);font-weight:var(--cc-font-bold);color:var(--cc-success-600);">$${data.quoted_price.toFixed(2)}</span>
          </div>
        ` : ''}
      </div>
    `;

    footer.innerHTML = `
      <div style="display:flex;gap:var(--cc-space-2);">
        <button class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerScheduleBuilder._editBookingFromPanel('${bookingId}')">
          Edit
        </button>
        <button class="cc-btn cc-btn-danger cc-btn-sm" onclick="OwnerScheduleBuilder._cancelBooking('${bookingId}')">
          Cancel Booking
        </button>
      </div>
    `;

    overlay.classList.add('cc-visible');
    panel.style.display = 'flex';

    // Close on Escape
    this._panelEscHandler = (e) => {
      if (e.key === 'Escape') this._closeSidePanel();
    };
    document.addEventListener('keydown', this._panelEscHandler);
  },

  _closeSidePanel() {
    const overlay = document.getElementById('side-panel-overlay');
    const panel = document.getElementById('side-panel');
    if (overlay) overlay.classList.remove('cc-visible');
    if (panel) panel.style.display = 'none';
    if (this._panelEscHandler) {
      document.removeEventListener('keydown', this._panelEscHandler);
    }
  },

  _editBookingFromPanel(bookingId) {
    const event = this._events.find(e => String(e.id) === String(bookingId));
    if (!event) return;
    this._closeSidePanel();

    const startTime = this._parseEventTime(event.start);
    const date = event.start ? event.start.split('T')[0] : this._selectedDate;
    const time = startTime ? this._formatTime24(startTime.h, startTime.m) : '09:00';

    this._openAddBookingModal(date, time, event);
  },

  async _cancelBooking(bookingId) {
    if (!confirm('Are you sure you want to cancel this booking?')) return;

    try {
      await CleanAPI.cleanPatch(`/bookings/${bookingId}`, { status: 'cancelled' });
      this._closeSidePanel();
      await this._renderCalendar();
      this._loadSummary();
      CleanClaw.showToast('Booking cancelled. The client has been notified.', 'success');
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Could not cancel booking. Please try again.', 'error');
    }
  },

  // --- Undo Toast ---

  _showUndoToast(message) {
    const toast = document.getElementById('undo-toast');
    const msgEl = document.getElementById('undo-message');
    if (!toast) return;

    msgEl.textContent = message;
    toast.style.display = 'flex';

    if (this._undoTimer) clearTimeout(this._undoTimer);
    this._undoTimer = setTimeout(() => {
      toast.style.display = 'none';
      this._undoData = null;
    }, 5000);
  },

  _handleUndo() {
    if (this._undoData && this._undoData.revert) {
      this._undoData.revert();
      this._loadSummary();
    }
    const toast = document.getElementById('undo-toast');
    if (toast) toast.style.display = 'none';
    if (this._undoTimer) clearTimeout(this._undoTimer);
    this._undoData = null;
  },

  // --- Generate Schedule ---

  _openGenerateModal() {
    const modal = document.getElementById('generate-modal');
    const dateInput = document.getElementById('generate-date');
    if (modal) modal.classList.add('cc-visible');
    if (dateInput) dateInput.value = this._selectedDate || new Date().toISOString().split('T')[0];
  },

  _closeGenerateModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('generate-modal');
    if (modal) modal.classList.remove('cc-visible');
  },

  async _doGenerate() {
    const dateInput = document.getElementById('generate-date');
    const forceCheck = document.getElementById('generate-force');
    const targetDate = dateInput ? dateInput.value : this._selectedDate;
    const force = forceCheck ? forceCheck.checked : false;

    try {
      const result = await CleanAPI.cleanPost('/schedule/generate', {
        date: targetDate,
        force: force,
      });

      this._closeGenerateModal();

      // Navigate to generated date
      const genDate = new Date(targetDate + 'T00:00:00');
      if (this._isMobile) {
        this._mobileDay = genDate;
      } else {
        this._weekStart = this._getWeekStart(genDate);
      }
      this._selectedDate = targetDate;
      await this._renderCalendar();
      this._loadSummary();

      CleanClaw.showToast(result.message || `Generated schedule for ${targetDate}`, 'success');
    } catch (err) {
      if (err.status === 409) {
        CleanClaw.showToast(err.detail || 'A schedule already exists for this date. Check "Force regenerate" to replace it.', 'warning');
      } else {
        CleanClaw.showToast(err.detail || 'Could not generate schedule. Please check your teams and clients, then try again.', 'error');
      }
    }
  },

  // --- SSE Integration (S2.6) ---

  _connectSSE() {
    if (typeof SSEClient === 'undefined') return;

    const streamUrl = `${window.location.origin}/api/v1/clean/${this._slug}/schedule/stream`;
    SSEClient.connect(streamUrl);

    // Schedule changed -> refetch events
    SSEClient.on('schedule.changed', (data) => {
      this._renderCalendar();
      this._loadSummary();
      const action = data?.data?.action || 'changed';
      const clientName = data?.data?.client_name || '';
      CleanClaw.showToast(`Schedule updated: ${clientName} (${action})`, 'info');
    });

    // Schedule generated -> full refetch
    SSEClient.on('schedule.generated', (data) => {
      this._renderCalendar();
      this._loadSummary();
      const dateStr = data?.data?.scheduled_date || '';
      CleanClaw.showToast(`Schedule generated for ${dateStr}`, 'success');
    });

    // Booking cancelled -> refetch
    SSEClient.on('booking.cancelled', (data) => {
      this._renderCalendar();
      this._loadSummary();
      const clientName = data?.data?.client_name || '';
      CleanClaw.showToast(`Booking cancelled: ${clientName}`, 'warning');
    });

    // Booking confirmed -> refetch
    SSEClient.on('booking.confirmed', (data) => {
      this._renderCalendar();
    });

    // Polling fallback -> refetch
    SSEClient.on('poll', () => {
      this._renderCalendar();
      this._loadSummary();
    });
  },

  // --- UI Binding ---

  _bindEvents() {
    // Generate schedule button
    const genBtn = document.getElementById('btn-generate');
    if (genBtn) genBtn.addEventListener('click', () => this._openGenerateModal());

    // Generate confirm button
    const confirmBtn = document.getElementById('btn-generate-confirm');
    if (confirmBtn) confirmBtn.addEventListener('click', () => this._doGenerate());

    // Side panel overlay close
    const overlay = document.getElementById('side-panel-overlay');
    if (overlay) overlay.addEventListener('click', () => this._closeSidePanel());

    // Side panel close button
    const closeBtn = document.getElementById('panel-close');
    if (closeBtn) closeBtn.addEventListener('click', () => this._closeSidePanel());

    // Undo button
    const undoBtn = document.getElementById('undo-btn');
    if (undoBtn) undoBtn.addEventListener('click', () => this._handleUndo());

    // Unassigned jobs badge click — scroll to first unassigned event
    const unBtn = document.getElementById('summary-unassigned-btn');
    if (unBtn) unBtn.addEventListener('click', () => {
      const unassignedEvent = this._events.find(e => {
        const teamId = (e.extendedProps || {}).team_id || e.resourceId || e.team_id;
        return !teamId || teamId === 'unassigned';
      });
      if (unassignedEvent) {
        const el = document.querySelector(`.nc-event[data-event-id="${unassignedEvent.id}"]`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  },

  // --- Refetch helper (called by SSE and external code) ---

  refetchEvents() {
    this._renderCalendar();
  },

  // --- Cleanup ---

  destroy() {
    if (typeof SSEClient !== 'undefined') {
      SSEClient.disconnect();
    }
    if (this._undoTimer) clearTimeout(this._undoTimer);
    if (this._resizeHandler) {
      window.removeEventListener('resize', this._resizeHandler);
    }
    this._calendar = null;
    this._events = [];
  },
};
