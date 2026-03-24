/**
 * CleanClaw — Push Notification Manager (Sprint 4)
 *
 * TODO: NOT YET IMPLEMENTED — Backend push routes do not exist yet.
 * This file is planned functionality. Do NOT load in app.html until
 * POST /api/v1/clean/{slug}/push/subscribe and
 * POST /api/v1/clean/{slug}/push/unsubscribe
 * backend endpoints are implemented.
 *
 * VAPID-based Web Push subscription management.
 * Handles: permission request, subscription, notification display,
 * and click routing to appropriate screens.
 */

window.PushManager = {
  // VAPID public key (set from server config)
  _vapidPublicKey: null,

  // Service worker registration
  _swRegistration: null,

  /**
   * Initialize push manager
   * @param {string} vapidPublicKey - Base64-encoded VAPID public key
   */
  async init(vapidPublicKey) {
    this._vapidPublicKey = vapidPublicKey;

    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      console.warn('[PUSH] Push notifications not supported in this browser');
      return false;
    }

    try {
      this._swRegistration = await navigator.serviceWorker.ready;
      console.log('[PUSH] Service worker ready for push');
      return true;
    } catch (err) {
      console.error('[PUSH] Service worker not ready:', err);
      return false;
    }
  },

  /**
   * Check current permission status
   * @returns {'granted'|'denied'|'default'}
   */
  getPermissionStatus() {
    if (!('Notification' in window)) return 'denied';
    return Notification.permission;
  },

  /**
   * Request push notification permission
   * Shows the browser permission dialog.
   * @returns {boolean} Whether permission was granted
   */
  async requestPermission() {
    if (!('Notification' in window)) {
      console.warn('[PUSH] Notifications not supported');
      return false;
    }

    const permission = await Notification.requestPermission();
    if (permission === 'granted') {
      console.log('[PUSH] Permission granted');
      return true;
    }

    console.log('[PUSH] Permission:', permission);
    return false;
  },

  /**
   * Subscribe to push notifications
   * Creates or retrieves the push subscription and sends it to the server.
   * @returns {boolean} Whether subscription succeeded
   */
  async subscribe() {
    if (!this._swRegistration || !this._vapidPublicKey) {
      console.warn('[PUSH] Not initialized');
      return false;
    }

    const permission = this.getPermissionStatus();
    if (permission !== 'granted') {
      const granted = await this.requestPermission();
      if (!granted) return false;
    }

    try {
      // Check existing subscription
      let subscription = await this._swRegistration.pushManager.getSubscription();

      if (!subscription) {
        // Create new subscription
        const applicationServerKey = this._urlBase64ToUint8Array(this._vapidPublicKey);
        subscription = await this._swRegistration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: applicationServerKey,
        });
        console.log('[PUSH] New subscription created');
      } else {
        console.log('[PUSH] Using existing subscription');
      }

      // Send subscription to server
      await this._sendSubscriptionToServer(subscription);
      return true;

    } catch (err) {
      console.error('[PUSH] Subscription failed:', err);
      return false;
    }
  },

  /**
   * Unsubscribe from push notifications
   * @returns {boolean} Whether unsubscription succeeded
   */
  async unsubscribe() {
    if (!this._swRegistration) return false;

    try {
      const subscription = await this._swRegistration.pushManager.getSubscription();
      if (subscription) {
        await subscription.unsubscribe();
        // Notify server
        await this._removeSubscriptionFromServer(subscription);
        console.log('[PUSH] Unsubscribed');
      }
      return true;
    } catch (err) {
      console.error('[PUSH] Unsubscribe failed:', err);
      return false;
    }
  },

  /**
   * Check if currently subscribed
   * @returns {boolean}
   */
  async isSubscribed() {
    if (!this._swRegistration) return false;
    const subscription = await this._swRegistration.pushManager.getSubscription();
    return !!subscription;
  },

  /**
   * Send subscription to server for storage
   */
  async _sendSubscriptionToServer(subscription) {
    const slug = CleanAPI._slug;
    if (!slug) {
      console.warn('[PUSH] No business slug set');
      return;
    }

    try {
      await CleanAPI.request('POST', `/api/v1/clean/${slug}/push/subscribe`, {
        subscription: subscription.toJSON(),
      });
      console.log('[PUSH] Subscription sent to server');
    } catch (err) {
      console.error('[PUSH] Failed to send subscription to server:', err);
    }
  },

  /**
   * Remove subscription from server
   */
  async _removeSubscriptionFromServer(subscription) {
    const slug = CleanAPI._slug;
    if (!slug) return;

    try {
      await CleanAPI.request('POST', `/api/v1/clean/${slug}/push/unsubscribe`, {
        subscription: subscription.toJSON(),
      });
    } catch (err) {
      console.error('[PUSH] Failed to remove subscription from server:', err);
    }
  },

  /**
   * Handle notification click (called from service worker)
   * Routes to the appropriate screen based on notification data.
   */
  handleNotificationClick(data) {
    if (!data) return;

    const routes = {
      booking_confirmation: '#/homeowner/bookings',
      reminder_24h: '#/homeowner/bookings',
      invoice_sent: '#/homeowner/invoices',
      payment_reminder: '#/homeowner/invoices',
      schedule_changed: '#/team/today',
      checkin_alert: '#/owner/schedule',
    };

    const targetRoute = routes[data.template_key] || data.url || '#/';

    // If the app is already open, navigate
    if (window.location.pathname.includes('app.html')) {
      window.location.hash = targetRoute;
    } else {
      // Open the app at the right route
      window.open(`/cleaning/app.html${targetRoute}`, '_self');
    }
  },

  /**
   * Convert URL-safe base64 to Uint8Array for applicationServerKey
   */
  _urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
      .replace(/-/g, '+')
      .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  },

  /**
   * Show a UI prompt to enable push notifications
   * Call this after login or on first visit.
   * @param {HTMLElement} container - Container to render the prompt into
   */
  renderPermissionPrompt(container) {
    const status = this.getPermissionStatus();

    if (status === 'granted') {
      // Already granted, just ensure subscribed
      this.subscribe();
      return;
    }

    if (status === 'denied') {
      // User blocked — show instructions
      container.innerHTML = `
        <div class="cc-push-prompt cc-push-blocked">
          <p>Push notifications are blocked. To enable:</p>
          <ol>
            <li>Click the lock/info icon in your browser's address bar</li>
            <li>Find "Notifications" and change to "Allow"</li>
            <li>Refresh the page</li>
          </ol>
        </div>
      `;
      return;
    }

    // Default — show enable prompt
    container.innerHTML = `
      <div class="cc-push-prompt">
        <div class="cc-push-prompt-content">
          <strong>Stay Updated</strong>
          <p>Get notified about schedule changes, new bookings, and payment updates.</p>
        </div>
        <button class="cc-btn cc-btn-primary cc-push-enable-btn" id="cc-enable-push">
          Enable Notifications
        </button>
        <button class="cc-btn cc-btn-ghost cc-push-dismiss-btn" id="cc-dismiss-push">
          Not now
        </button>
      </div>
    `;

    document.getElementById('cc-enable-push')?.addEventListener('click', async () => {
      const success = await this.subscribe();
      if (success) {
        container.innerHTML = `
          <div class="cc-push-prompt cc-push-success">
            <p>Notifications enabled! You'll be notified about important updates.</p>
          </div>
        `;
        setTimeout(() => { container.innerHTML = ''; }, 3000);
      }
    });

    document.getElementById('cc-dismiss-push')?.addEventListener('click', () => {
      container.innerHTML = '';
      // Remember dismissal for this session
      sessionStorage.setItem('cc_push_dismissed', 'true');
    });
  },
};
