/**
 * Xcleaners API Client
 *
 * Shared API client for all Xcleaners modules.
 * Handles JWT injection, auto-refresh, error handling, and offline queue.
 */

window.CleanAPI = {
  // Base URL - auto-detect from current host
  _baseUrl: '',

  // Current business slug (set after role detection)
  _slug: null,

  // Offline request queue (stored in localStorage for persistence)
  _QUEUE_KEY: 'cc_offline_queue',

  /**
   * Initialize the API client
   */
  init(slug) {
    this._slug = slug;
    // Base URL: same origin
    this._baseUrl = window.location.origin;
    // Process offline queue if online
    if (navigator.onLine) {
      this._processQueue();
    }
    window.addEventListener('online', () => this._processQueue());
  },

  /**
   * Get stored JWT token
   */
  getToken() {
    return localStorage.getItem('cc_access_token');
  },

  /**
   * Get refresh token
   */
  getRefreshToken() {
    return localStorage.getItem('cc_refresh_token');
  },

  /**
   * Store tokens
   */
  setTokens(access, refresh) {
    localStorage.setItem('cc_access_token', access);
    if (refresh) localStorage.setItem('cc_refresh_token', refresh);
  },

  /**
   * Clear tokens (logout)
   */
  clearTokens() {
    localStorage.removeItem('cc_access_token');
    localStorage.removeItem('cc_refresh_token');
    localStorage.removeItem('cc_user_roles');
    localStorage.removeItem('cc_current_role');
    localStorage.removeItem('cc_slug');
  },

  /**
   * Decode JWT payload
   */
  decodeToken(token) {
    if (!token) return null;
    try {
      const payload = token.split('.')[1];
      return JSON.parse(atob(payload));
    } catch {
      return null;
    }
  },

  /**
   * Check if token is expired
   */
  isTokenExpired(token) {
    const payload = this.decodeToken(token);
    if (!payload || !payload.exp) return true;
    return Date.now() >= payload.exp * 1000;
  },

  /**
   * Get current user info from JWT
   */
  getUser() {
    const token = this.getToken();
    const payload = this.decodeToken(token);
    if (!payload) return null;
    return {
      user_id: payload.sub,
      email: payload.email,
      name: payload.name || payload.email?.split('@')[0] || 'User',
    };
  },

  /**
   * Try to refresh the JWT
   */
  async refreshToken() {
    const refresh = this.getRefreshToken();
    if (!refresh) return false;
    try {
      const resp = await fetch(`${this._baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!resp.ok) return false;
      const data = await resp.json();
      this.setTokens(data.access_token, data.refresh_token || refresh);
      return true;
    } catch {
      return false;
    }
  },

  /**
   * Core request method
   */
  async request(method, path, body = null, options = {}) {
    const url = `${this._baseUrl}${path}`;
    const headers = {};

    if (body && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const config = { method, headers };
    if (body) {
      config.body = body instanceof FormData ? body : JSON.stringify(body);
    }
    // AbortController support — caller may pass { signal } in options
    // (used by debounced pricing preview to cancel stale in-flight requests).
    if (options.signal) {
      config.signal = options.signal;
    }

    try {
      let resp = await fetch(url, config);

      // 401 - try refresh (skip in demo mode)
      if (resp.status === 401 && !options._retried) {
        if (Xcleaners._user && Xcleaners._user.id && Xcleaners._user.id.startsWith('demo-')) {
          // Demo mode — handle write operations first
          if (method !== 'GET' && typeof DemoData !== 'undefined' && DemoData.handleWrite) {
            const writeResult = DemoData.handleWrite(method, path, body);
            if (writeResult !== null) {
              console.log('[CleanAPI] Demo mode: handled write for', method, path);
              return writeResult;
            }
          }
          // Demo mode — use mock data from DemoData provider (reads)
          if (typeof DemoData !== 'undefined') {
            const mockData = DemoData.match(path);
            if (mockData !== null) {
              console.log('[CleanAPI] Demo mode: returning mock data for', path);
              return mockData;
            }
          }
          console.warn('[CleanAPI] Demo mode: no mock data for', path);
          return {};
        }
        const refreshed = await this.refreshToken();
        if (refreshed) {
          headers['Authorization'] = `Bearer ${this.getToken()}`;
          config.headers = headers;
          resp = await fetch(url, config);
        } else {
          // Redirect to login
          this.clearTokens();
          window.location.hash = '#/login';
          return null;
        }
      }

      // 403 - access denied. Read detail from body so caller can distinguish
      // a forbidden response from an empty-but-successful one (e.g.,
      // "You are not assigned to a team." vs. "No jobs today"). The marker
      // object is truthy and Object.keys(...).length > 0, so views that
      // check `rawData && data.jobs` continue to behave as before; views
      // that want to show a banner can test `rawData?._forbidden`.
      if (resp.status === 403) {
        const err = await resp.json().catch(() => ({}));
        const detail = typeof err.detail === 'string'
          ? err.detail
          : (Array.isArray(err.detail)
              ? err.detail.map(e => e.msg || JSON.stringify(e)).join('; ')
              : 'Access denied. You do not have permission for this action.');
        if (Xcleaners && typeof Xcleaners.showToast === 'function') {
          Xcleaners.showToast(detail, 'error');
        }
        return { _forbidden: true, status: 403, detail };
      }

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        const detail = typeof err.detail === 'string'
          ? err.detail
          : Array.isArray(err.detail)
            ? err.detail.map(e => e.msg || JSON.stringify(e)).join('; ')
            : JSON.stringify(err.detail || err);
        throw { status: resp.status, detail: detail || `Request failed (${resp.status})` };
      }

      // Handle 204 No Content
      if (resp.status === 204) return {};

      return await resp.json();
    } catch (err) {
      // Demo mode — use mock data on any error
      if (Xcleaners._user && Xcleaners._user.id && Xcleaners._user.id.startsWith('demo-')) {
        if (typeof DemoData !== 'undefined') {
          // Handle writes first
          if (method !== 'GET' && DemoData.handleWrite) {
            const writeResult = DemoData.handleWrite(method, path, body);
            if (writeResult !== null) {
              console.log('[CleanAPI] Demo mode (catch): handled write for', method, path);
              return writeResult;
            }
          }
          const mockData = DemoData.match(path);
          if (mockData !== null) return mockData;
        }
        return {};
      }
      // Network error - queue if offline and method is mutating
      if (!navigator.onLine && method !== 'GET') {
        this._enqueue({ method, path, body, timestamp: Date.now() });
        Xcleaners.showToast('You are offline. This action will be synced when you reconnect.', 'warning');
        return { _queued: true };
      }
      throw err;
    }
  },

  // Convenience methods

  get(path, opts) { return this.request('GET', path, null, opts || {}); },
  post(path, body, opts) { return this.request('POST', path, body, opts || {}); },
  put(path, body, opts) { return this.request('PUT', path, body, opts || {}); },
  patch(path, body, opts) { return this.request('PATCH', path, body, opts || {}); },
  del(path, opts) { return this.request('DELETE', path, null, opts || {}); },

  // Cleaning-scoped helpers (prepend /api/v1/clean/{slug}/)
  // opts supports { signal } for AbortController.

  cleanGet(endpoint, opts) {
    return this.get(`/api/v1/clean/${this._slug}${endpoint}`, opts);
  },
  cleanPost(endpoint, body, opts) {
    return this.post(`/api/v1/clean/${this._slug}${endpoint}`, body, opts);
  },
  cleanPatch(endpoint, body, opts) {
    return this.patch(`/api/v1/clean/${this._slug}${endpoint}`, body, opts);
  },
  cleanPut(endpoint, body, opts) {
    return this.put(`/api/v1/clean/${this._slug}${endpoint}`, body, opts);
  },
  cleanDel(endpoint, opts) {
    return this.del(`/api/v1/clean/${this._slug}${endpoint}`, opts);
  },

  // ----- Offline Queue -----

  _enqueue(item) {
    const queue = JSON.parse(localStorage.getItem(this._QUEUE_KEY) || '[]');
    queue.push(item);
    localStorage.setItem(this._QUEUE_KEY, JSON.stringify(queue));
  },

  async _processQueue() {
    const queue = JSON.parse(localStorage.getItem(this._QUEUE_KEY) || '[]');
    if (queue.length === 0) return;

    console.log(`[CleanAPI] Processing ${queue.length} queued requests`);
    const failed = [];

    for (const item of queue) {
      try {
        await this.request(item.method, item.path, item.body, { _retried: true });
      } catch (err) {
        console.warn('[CleanAPI] Queued request failed:', item.path, err);
        failed.push(item);
      }
    }

    localStorage.setItem(this._QUEUE_KEY, JSON.stringify(failed));
    if (queue.length - failed.length > 0) {
      Xcleaners.showToast(`${queue.length - failed.length} queued action(s) synced.`, 'success');
    }
  },
};
