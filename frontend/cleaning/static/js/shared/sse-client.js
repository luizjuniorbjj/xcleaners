/**
 * CleanClaw — SSE Client (S2.6)
 *
 * EventSource wrapper with auto-reconnect, exponential backoff,
 * event dispatch, and fallback polling.
 *
 * Usage:
 *   SSEClient.connect('/api/v1/clean/my-biz/schedule/stream');
 *   SSEClient.on('schedule.changed', (data) => { ... });
 *   SSEClient.on('schedule.generated', (data) => { ... });
 *   SSEClient.disconnect();
 */

window.SSEClient = {
  _eventSource: null,
  _url: null,
  _handlers: {},     // eventType -> [callback]
  _retryCount: 0,
  _maxRetries: 3,    // before switching to polling fallback
  _retryTimer: null,
  _pollTimer: null,
  _pollInterval: 30000,  // 30s polling fallback
  _sseRetryTimer: null,
  _sseRetryInterval: 300000,  // 5min: retry SSE in background while polling
  _connected: false,
  _mode: 'disconnected',  // 'sse' | 'polling' | 'disconnected'
  _lastEventTimestamp: null,
  _statusEl: null,

  /**
   * Connect to an SSE endpoint.
   * @param {string} url - Full SSE endpoint URL
   */
  connect(url) {
    this._url = url;
    this._retryCount = 0;
    this._stopPolling();
    this._connectSSE();
  },

  /**
   * Disconnect and clean up all connections.
   */
  disconnect() {
    this._mode = 'disconnected';
    this._connected = false;

    if (this._eventSource) {
      this._eventSource.close();
      this._eventSource = null;
    }
    if (this._retryTimer) {
      clearTimeout(this._retryTimer);
      this._retryTimer = null;
    }
    this._stopPolling();
    this._updateStatusUI('disconnected');
  },

  /**
   * Register an event handler.
   * @param {string} eventType - e.g. 'schedule.changed', 'booking.cancelled'
   * @param {Function} callback - receives parsed data object
   */
  on(eventType, callback) {
    if (!this._handlers[eventType]) {
      this._handlers[eventType] = [];
    }
    this._handlers[eventType].push(callback);

    // If SSE is already connected, add listener to EventSource
    if (this._eventSource && this._mode === 'sse') {
      this._eventSource.addEventListener(eventType, (e) => {
        this._handleEvent(eventType, e.data);
      });
    }
  },

  /**
   * Remove all handlers for an event type.
   */
  off(eventType) {
    delete this._handlers[eventType];
  },

  /**
   * Check connection status.
   */
  isConnected() {
    return this._connected;
  },

  getMode() {
    return this._mode;
  },

  // ─── Internal: SSE Connection ─────────────────

  _connectSSE() {
    if (!this._url) return;

    const token = CleanAPI.getToken();
    // EventSource doesn't support custom headers, so pass token as query param
    const separator = this._url.includes('?') ? '&' : '?';
    const urlWithAuth = `${this._url}${separator}token=${encodeURIComponent(token || '')}`;

    try {
      this._eventSource = new EventSource(urlWithAuth);
    } catch (err) {
      console.warn('[SSE] Failed to create EventSource:', err);
      this._onSSEError();
      return;
    }

    this._eventSource.onopen = () => {
      console.log('[SSE] Connected to', this._url);
      this._connected = true;
      this._mode = 'sse';
      this._retryCount = 0;
      this._stopPolling();
      this._updateStatusUI('connected');
    };

    this._eventSource.onerror = () => {
      console.warn('[SSE] Connection error');
      this._connected = false;
      this._onSSEError();
    };

    // Listen for the connected event
    this._eventSource.addEventListener('connected', (e) => {
      console.log('[SSE] Server confirmed connection:', e.data);
    });

    // Listen for error events from server
    this._eventSource.addEventListener('error', (e) => {
      console.warn('[SSE] Server error event:', e.data);
    });

    // Register all existing handlers
    for (const eventType of Object.keys(this._handlers)) {
      this._eventSource.addEventListener(eventType, (e) => {
        this._handleEvent(eventType, e.data);
      });
    }

    // Also listen for generic 'message' events
    this._eventSource.addEventListener('message', (e) => {
      try {
        const parsed = JSON.parse(e.data);
        const eventType = parsed.event || 'message';
        this._handleEvent(eventType, e.data);
      } catch {
        // Not JSON, ignore
      }
    });
  },

  _onSSEError() {
    if (this._eventSource) {
      this._eventSource.close();
      this._eventSource = null;
    }

    this._retryCount++;
    this._updateStatusUI('reconnecting');

    if (this._retryCount <= this._maxRetries) {
      // Exponential backoff: 1s, 2s, 4s
      const delay = Math.min(1000 * Math.pow(2, this._retryCount - 1), 30000);
      console.log(`[SSE] Retry ${this._retryCount}/${this._maxRetries} in ${delay}ms`);
      this._retryTimer = setTimeout(() => this._connectSSE(), delay);
    } else {
      // Switch to polling fallback
      console.warn('[SSE] Max retries reached. Switching to polling fallback.');
      this._startPolling();
    }
  },

  // ─── Internal: Polling Fallback ─────────────────

  _startPolling() {
    this._mode = 'polling';
    this._updateStatusUI('polling');

    // Show polling banner ONCE only
    if (!this._pollingToastShown && typeof CleanClaw !== 'undefined' && CleanClaw.showToast) {
      CleanClaw.showToast('Live updates unavailable. Refreshing every 30s.', 'warning');
      this._pollingToastShown = true;
    }

    // Poll immediately, then at interval
    this._poll();
    this._pollTimer = setInterval(() => this._poll(), this._pollInterval);

    // Try SSE again every 5 minutes
    this._sseRetryTimer = setInterval(() => {
      console.log('[SSE] Retrying SSE connection in background...');
      this._retryCount = 0;
      this._connectSSE();
    }, this._sseRetryInterval);
  },

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    if (this._sseRetryTimer) {
      clearInterval(this._sseRetryTimer);
      this._sseRetryTimer = null;
    }
  },

  async _poll() {
    // Dispatch a synthetic 'poll' event so the calendar can refetch
    this._dispatch('poll', { mode: 'polling', timestamp: new Date().toISOString() });
  },

  // ─── Internal: Event Handling ─────────────────

  _handleEvent(eventType, rawData) {
    this._lastEventTimestamp = new Date().toISOString();

    let data;
    try {
      data = JSON.parse(rawData);
    } catch {
      data = { raw: rawData };
    }

    this._dispatch(eventType, data);
  },

  _dispatch(eventType, data) {
    const handlers = this._handlers[eventType] || [];
    for (const handler of handlers) {
      try {
        handler(data);
      } catch (err) {
        console.error(`[SSE] Error in handler for ${eventType}:`, err);
      }
    }

    // Also dispatch to wildcard handlers
    const wildcardHandlers = this._handlers['*'] || [];
    for (const handler of wildcardHandlers) {
      try {
        handler(eventType, data);
      } catch (err) {
        console.error('[SSE] Error in wildcard handler:', err);
      }
    }
  },

  // ─── Internal: Status UI ─────────────────

  _updateStatusUI(status) {
    // Update status indicator if it exists in the DOM
    const el = document.getElementById('sse-status');
    if (!el) return;

    const colors = {
      connected: '#10B981',     // green
      reconnecting: '#F59E0B',  // yellow
      polling: '#F59E0B',       // yellow
      disconnected: '#EF4444',  // red
    };

    const labels = {
      connected: 'Live',
      reconnecting: 'Reconnecting...',
      polling: 'Polling (30s)',
      disconnected: 'Offline',
    };

    el.style.display = 'flex';
    el.innerHTML = `
      <span style="
        display:inline-block;
        width:8px;height:8px;
        border-radius:50%;
        background:${colors[status] || colors.disconnected};
        margin-right:6px;
      "></span>
      <span style="font-size:12px;color:var(--color-neutral-500);">
        ${labels[status] || status}
      </span>
    `;
  },
};
