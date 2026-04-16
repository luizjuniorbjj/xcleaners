/**
 * Xcleaners — Owner Payments Settings (Stripe Connect Express)
 *
 * Route: /settings/payments
 * Global: OwnerPaymentsSettings
 *
 * States:
 *   - not_connected → big "Connect Stripe" button
 *   - pending       → "Finish onboarding" (refresh link) + status badge
 *   - active        → green badge + Express Dashboard link
 *   - restricted / rejected → error banner + action required
 *
 * Endpoints (Sprint E item 1 — commit b626907):
 *   POST /stripe/connect/create-account   → {account_id, onboarding_url, reused_existing}
 *   GET  /stripe/connect/status           → {connected, charges_enabled, payouts_enabled, status, requirements_due}
 *   POST /stripe/connect/dashboard-link   → {dashboard_url}
 *   POST /stripe/connect/refresh-link     → {onboarding_url}
 */

window.OwnerPaymentsSettings = {
  _container: null,
  _status: null,

  async render(container) {
    this._container = container;
    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-left:var(--cc-space-3);">Loading payment settings…</span>
      </div>
    `;
    await this._fetchStatus();
    this._renderPage();
  },

  async _fetchStatus() {
    try {
      this._status = await CleanAPI.cleanGet('/stripe/connect/status');
    } catch (err) {
      if (err && err.status === 503) {
        this._status = { __unconfigured: true };
      } else {
        this._status = { __error: true, __detail: (err && err.detail) || String(err) };
      }
    }
  },

  _escape(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  },

  _wrap(inner) {
    return `<div class="cc-stack" style="gap:var(--cc-space-6);max-width:800px;">${inner}</div>`;
  },

  _renderPage() {
    const s = this._status || {};

    if (s.__unconfigured) {
      this._container.innerHTML = this._wrap(`
        <div class="cc-card">
          <h1 class="cc-text-2xl" style="margin:0 0 var(--cc-space-3) 0;">Payments</h1>
          <div class="cc-alert cc-alert-warning">
            <strong>Payments are not configured on this server.</strong>
            <p class="cc-text-sm" style="margin:var(--cc-space-2) 0 0 0;">
              Contact support to enable Stripe Connect for your business.
            </p>
          </div>
        </div>
      `);
      return;
    }

    if (s.__error) {
      this._container.innerHTML = this._wrap(`
        <div class="cc-card">
          <h1 class="cc-text-2xl" style="margin:0 0 var(--cc-space-3) 0;">Payments</h1>
          <div class="cc-alert cc-alert-error">
            <strong>Could not load payment status.</strong>
            <p class="cc-text-sm">${this._escape(s.__detail)}</p>
            <button class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerPaymentsSettings.render(document.getElementById('content-view'))" style="margin-top:var(--cc-space-2);">Retry</button>
          </div>
        </div>
      `);
      return;
    }

    if (!s.connected) {
      this._container.innerHTML = this._wrap(this._renderNotConnected());
    } else {
      this._container.innerHTML = this._wrap(this._renderConnected(s));
    }
    this._wire();
  },

  _renderNotConnected() {
    return `
      <div class="cc-card">
        <h1 class="cc-text-2xl" style="margin:0 0 var(--cc-space-2) 0;">Payments</h1>
        <p class="cc-text-muted" style="margin:0 0 var(--cc-space-4) 0;">
          Connect your Stripe account to accept client payments. You'll receive payouts
          directly to your bank, typically within 2 business days.
        </p>
        <div class="cc-stack" style="gap:var(--cc-space-3);padding:var(--cc-space-4);background:var(--cc-color-surface-alt,#f8fafc);border-radius:var(--cc-radius-md,8px);">
          <div class="cc-text-sm"><strong>How it works</strong></div>
          <ol class="cc-text-sm cc-text-muted" style="padding-left:var(--cc-space-4);margin:0;">
            <li>Click "Connect with Stripe" below</li>
            <li>Complete a short onboarding form (business info, bank account, ID)</li>
            <li>You'll be redirected back once approved</li>
            <li>Start accepting saved cards for auto-charge on recurring bookings</li>
          </ol>
          <div class="cc-text-sm cc-text-muted">
            <strong>Fees:</strong> Stripe charges 2.9% + $0.30 per card transaction.
            Xcleaners takes 0% — you receive 100% of what your clients are charged.
          </div>
        </div>
        <div style="margin-top:var(--cc-space-4);">
          <button id="stripe-connect-btn" class="cc-btn cc-btn-primary cc-btn-lg">Connect with Stripe</button>
        </div>
      </div>
    `;
  },

  _renderConnected(s) {
    const status = s.status || 'pending';
    const badgeClass = {
      active: 'cc-badge-success',
      pending: 'cc-badge-warning',
      restricted: 'cc-badge-warning',
      rejected: 'cc-badge-danger',
    }[status] || 'cc-badge-muted';
    const badgeText = {
      active: 'Active',
      pending: 'Onboarding in progress',
      restricted: 'Additional info needed',
      rejected: 'Rejected by Stripe',
    }[status] || status;

    const reqs = Array.isArray(s.requirements_due) ? s.requirements_due : [];
    const hasRequirements = reqs.length > 0;

    let actionBlock = '';
    if (status === 'active') {
      actionBlock = `
        <div class="cc-alert cc-alert-success">
          <strong>Your Stripe account is active.</strong>
          <p class="cc-text-sm" style="margin:var(--cc-space-2) 0 0 0;">
            Charges: ${s.charges_enabled ? 'enabled' : 'disabled'} ·
            Payouts: ${s.payouts_enabled ? 'enabled (T+2 days)' : 'disabled'}
          </p>
        </div>
        <div class="cc-stack cc-stack-horizontal" style="gap:var(--cc-space-2);margin-top:var(--cc-space-3);">
          <button id="stripe-dashboard-btn" class="cc-btn cc-btn-primary">Open Express Dashboard</button>
          <button id="stripe-refresh-btn" class="cc-btn cc-btn-ghost">Refresh status</button>
        </div>
      `;
    } else if (status === 'pending') {
      actionBlock = `
        <div class="cc-alert cc-alert-warning">
          <strong>Onboarding not complete.</strong>
          <p class="cc-text-sm" style="margin:var(--cc-space-2) 0 0 0;">
            Stripe needs more information before you can accept payments.
            ${hasRequirements ? 'Missing: ' + reqs.slice(0, 5).map((r) => this._escape(r)).join(', ') : ''}
          </p>
        </div>
        <div class="cc-stack cc-stack-horizontal" style="gap:var(--cc-space-2);margin-top:var(--cc-space-3);">
          <button id="stripe-resume-btn" class="cc-btn cc-btn-primary">Finish onboarding</button>
          <button id="stripe-refresh-btn" class="cc-btn cc-btn-ghost">Refresh status</button>
        </div>
      `;
    } else if (status === 'restricted') {
      actionBlock = `
        <div class="cc-alert cc-alert-warning">
          <strong>Your account is temporarily restricted.</strong>
          <p class="cc-text-sm" style="margin:var(--cc-space-2) 0 0 0;">
            Stripe needs additional information to resume payouts.
            ${hasRequirements ? 'Missing: ' + reqs.slice(0, 5).map((r) => this._escape(r)).join(', ') : ''}
          </p>
        </div>
        <div class="cc-stack cc-stack-horizontal" style="gap:var(--cc-space-2);margin-top:var(--cc-space-3);">
          <button id="stripe-resume-btn" class="cc-btn cc-btn-primary">Provide missing info</button>
          <button id="stripe-dashboard-btn" class="cc-btn cc-btn-ghost">Open Express Dashboard</button>
        </div>
      `;
    } else if (status === 'rejected') {
      actionBlock = `
        <div class="cc-alert cc-alert-error">
          <strong>Stripe has rejected this account.</strong>
          <p class="cc-text-sm" style="margin:var(--cc-space-2) 0 0 0;">
            This usually means business verification failed. Contact Stripe support
            or reach out to us for help.
          </p>
        </div>
      `;
    }

    return `
      <div class="cc-card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:var(--cc-space-3);flex-wrap:wrap;">
          <div>
            <h1 class="cc-text-2xl" style="margin:0 0 var(--cc-space-1) 0;">Payments</h1>
            <div class="cc-text-sm cc-text-muted">Account: <code>${this._escape(s.account_id)}</code></div>
          </div>
          <span class="cc-badge ${badgeClass}">${badgeText}</span>
        </div>
        <div style="margin-top:var(--cc-space-4);">${actionBlock}</div>
      </div>

      <div class="cc-card">
        <h2 class="cc-text-lg" style="margin:0 0 var(--cc-space-2) 0;">How payouts work</h2>
        <p class="cc-text-sm cc-text-muted" style="margin:0;">
          When a client is charged, Stripe deposits the net amount (gross − Stripe fees)
          to your bank account on a <strong>daily rolling schedule with a 2-day delay</strong>.
          You can change the payout schedule in the Express Dashboard above.
        </p>
      </div>
    `;
  },

  _wire() {
    document.getElementById('stripe-connect-btn')?.addEventListener('click', () => this._connect());
    document.getElementById('stripe-resume-btn')?.addEventListener('click', () => this._resume());
    document.getElementById('stripe-refresh-btn')?.addEventListener('click', () => this._refreshStatus());
    document.getElementById('stripe-dashboard-btn')?.addEventListener('click', () => this._openDashboard());
  },

  async _connect() {
    try {
      this._setLoading(true);
      const resp = await CleanAPI.cleanPost('/stripe/connect/create-account', {});
      if (resp.onboarding_url) {
        window.location.href = resp.onboarding_url;
      } else {
        alert('Stripe did not return an onboarding URL. Try again.');
        this._setLoading(false);
      }
    } catch (err) {
      alert(`Could not connect Stripe: ${(err && err.detail) || err}`);
      this._setLoading(false);
    }
  },

  async _resume() {
    try {
      this._setLoading(true);
      const resp = await CleanAPI.cleanPost('/stripe/connect/refresh-link', {});
      if (resp.onboarding_url) {
        window.location.href = resp.onboarding_url;
      }
    } catch (err) {
      alert(`Could not resume onboarding: ${(err && err.detail) || err}`);
      this._setLoading(false);
    }
  },

  async _openDashboard() {
    try {
      this._setLoading(true);
      const resp = await CleanAPI.cleanPost('/stripe/connect/dashboard-link', {});
      if (resp.dashboard_url) {
        window.open(resp.dashboard_url, '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      alert(`Could not open dashboard: ${(err && err.detail) || err}`);
    } finally {
      this._setLoading(false);
    }
  },

  async _refreshStatus() {
    await this._fetchStatus();
    this._renderPage();
  },

  _setLoading(on) {
    this._container.querySelectorAll('button').forEach((b) => { b.disabled = !!on; });
  },
};
