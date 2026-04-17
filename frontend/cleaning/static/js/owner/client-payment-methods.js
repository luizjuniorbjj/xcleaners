/**
 * Xcleaners — Owner Client Payment Methods (Stripe Connect setup-intent flow) [3S-1]
 *
 * Route: #/owner/clients/:id/payment-methods
 * Global: OwnerClientPaymentMethods
 *
 * Flow:
 *   1. On render → fetch existing payment methods (GET /clients/{id}/payment-methods)
 *   2. Owner clicks "Collect New Card" → POST /clients/{id}/setup-intent (returns client_secret)
 *   3. Stripe Elements card input → stripe.confirmCardSetup(client_secret)
 *   4. On success → refresh list
 *
 * Endpoints (feature [3S-1]):
 *   POST   /clients/{id}/setup-intent         → {client_secret, publishable_key, stripe_account_id, ...}
 *   GET    /clients/{id}/payment-methods      → {payment_methods: [{id, brand, last4, exp_month, exp_year}]}
 *   DELETE /clients/{id}/payment-methods/{pm} → 204
 */

window.OwnerClientPaymentMethods = {
  _container: null,
  _clientId: null,
  _client: null,
  _methods: [],
  _stripe: null,
  _elements: null,
  _cardElement: null,
  _currentSetupIntent: null,
  _busy: false,

  async render(container, params) {
    this._container = container;
    this._clientId = params?.id;
    if (!this._clientId) {
      container.innerHTML = '<div class="cc-error"><p>No client ID provided.</p></div>';
      return;
    }
    this._container.innerHTML = '<div class="cc-loading">Loading payment methods...</div>';
    await this._load();
  },

  _esc(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  },

  async _load() {
    try {
      const slug = CleanAPI._slug;
      const [client, pmResp] = await Promise.all([
        CleanAPI.request('GET', `/api/v1/clean/${slug}/clients/${this._clientId}`),
        CleanAPI.request('GET', `/api/v1/clean/${slug}/clients/${this._clientId}/payment-methods`),
      ]);
      this._client = client;
      this._methods = (pmResp && pmResp.payment_methods) || [];
      this._renderPage();
    } catch (e) {
      // 409 → business has not connected Stripe yet
      if (e && e.status === 409) {
        this._container.innerHTML = `
          <div class="cc-card" style="max-width:640px;margin:var(--cc-space-8) auto;">
            <h2>Payment Methods</h2>
            <div class="cc-alert cc-alert-warning">
              <strong>Stripe not connected yet.</strong>
              <p class="cc-text-sm">Go to <a href="#/owner/settings/payments">Settings &rsaquo; Payments</a> and complete Stripe onboarding first.</p>
            </div>
            <a href="#/owner/clients/${this._esc(this._clientId)}" class="cc-btn cc-btn-secondary" style="margin-top:var(--cc-space-3);">&larr; Back to Client</a>
          </div>`;
        return;
      }
      this._container.innerHTML = `
        <div class="cc-error">
          <p>Failed to load payment methods: ${this._esc(e.detail || e.message || 'Unknown error')}</p>
          <a href="#/owner/clients/${this._esc(this._clientId)}">Back to Client</a>
        </div>`;
    }
  },

  _renderPage() {
    const c = this._client || {};
    const name = `${c.first_name || ''} ${c.last_name || ''}`.trim() || 'Client';
    const cardsHtml = this._methods.length
      ? this._methods.map(m => `
          <div class="cc-card" style="margin-bottom:var(--cc-space-3);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <div>
                <strong>${this._esc(m.brand || 'card').toUpperCase()}</strong>
                &middot; &middot; &middot; &middot; ${this._esc(m.last4 || '????')}
                <span class="cc-text-muted" style="margin-left:var(--cc-space-3);">
                  exp ${this._esc(String(m.exp_month || '').padStart(2, '0'))}/${this._esc(String(m.exp_year || ''))}
                </span>
              </div>
              <button class="cc-btn cc-btn-sm cc-btn-danger-outline"
                      onclick="OwnerClientPaymentMethods._detach('${this._esc(m.id)}')">
                Remove
              </button>
            </div>
          </div>`).join('')
      : `<div class="cc-empty-state" style="padding:var(--cc-space-6);">
           <p>No cards on file for this client.</p>
         </div>`;

    this._container.innerHTML = `
      <div style="max-width:720px;margin:var(--cc-space-6) auto;padding:0 var(--cc-space-4);">
        <a href="#/owner/clients/${this._esc(this._clientId)}" class="cc-back-link">&larr; Back to ${this._esc(name)}</a>
        <h1 style="margin:var(--cc-space-4) 0;">Payment Methods</h1>
        <p class="cc-text-muted">Collect a card on file for ${this._esc(name)} to enable auto-charging of recurring bookings.</p>

        <div id="pm-list" style="margin-top:var(--cc-space-6);">${cardsHtml}</div>

        <div id="pm-collect-area" style="margin-top:var(--cc-space-6);">
          <button class="cc-btn cc-btn-primary" onclick="OwnerClientPaymentMethods._startCollect()">
            + Collect New Card
          </button>
        </div>

        <div id="pm-collect-form" style="display:none;margin-top:var(--cc-space-6);">
          <div class="cc-card">
            <h3>New card for ${this._esc(name)}</h3>
            <p class="cc-text-sm cc-text-muted">Read card info to Ana over the phone. Card will be saved on file and can be charged for future bookings.</p>
            <div id="pm-card-element" style="padding:var(--cc-space-3);border:1px solid var(--cc-border);border-radius:var(--cc-radius);background:white;min-height:44px;"></div>
            <div id="pm-card-errors" class="cc-alert cc-alert-error" style="display:none;margin-top:var(--cc-space-3);"></div>
            <div style="display:flex;gap:var(--cc-space-3);margin-top:var(--cc-space-4);">
              <button id="pm-confirm-btn" class="cc-btn cc-btn-primary" onclick="OwnerClientPaymentMethods._confirmCard()">
                Save Card
              </button>
              <button class="cc-btn cc-btn-ghost" onclick="OwnerClientPaymentMethods._cancelCollect()">
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
  },

  async _ensureStripeJs() {
    if (window.Stripe) return;
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://js.stripe.com/v3/';
      script.onload = resolve;
      script.onerror = () => reject(new Error('Failed to load Stripe.js'));
      document.head.appendChild(script);
    });
  },

  async _startCollect() {
    if (this._busy) return;
    this._busy = true;
    const btn = document.querySelector('#pm-collect-area button');
    if (btn) btn.disabled = true;

    try {
      await this._ensureStripeJs();

      const slug = CleanAPI._slug;
      const resp = await CleanAPI.request(
        'POST', `/api/v1/clean/${slug}/clients/${this._clientId}/setup-intent`, {}
      );

      if (!resp.publishable_key) {
        throw new Error('Server did not return publishable_key. Check STRIPE_PUBLISHABLE_KEY env var.');
      }

      this._currentSetupIntent = resp;

      // Initialize Stripe with connected account
      this._stripe = window.Stripe(resp.publishable_key, {
        stripeAccount: resp.stripe_account_id,
      });
      this._elements = this._stripe.elements();
      this._cardElement = this._elements.create('card', {
        style: {
          base: {
            fontSize: '16px',
            color: '#1a1a1a',
            '::placeholder': { color: '#8a8a8a' },
          },
        },
      });

      // Show form, hide button
      document.getElementById('pm-collect-area').style.display = 'none';
      const form = document.getElementById('pm-collect-form');
      form.style.display = 'block';
      this._cardElement.mount('#pm-card-element');
      this._cardElement.on('change', (event) => {
        const errDiv = document.getElementById('pm-card-errors');
        if (event.error) {
          errDiv.textContent = event.error.message;
          errDiv.style.display = 'block';
        } else {
          errDiv.style.display = 'none';
        }
      });
    } catch (e) {
      alert('Failed to start card collection: ' + (e.detail || e.message || 'Unknown error'));
      if (btn) btn.disabled = false;
    } finally {
      this._busy = false;
    }
  },

  async _confirmCard() {
    if (this._busy || !this._stripe || !this._cardElement || !this._currentSetupIntent) return;
    this._busy = true;
    const confirmBtn = document.getElementById('pm-confirm-btn');
    if (confirmBtn) { confirmBtn.disabled = true; confirmBtn.textContent = 'Saving...'; }

    try {
      const { setupIntent, error } = await this._stripe.confirmCardSetup(
        this._currentSetupIntent.client_secret,
        {
          payment_method: {
            card: this._cardElement,
            billing_details: {
              name: `${this._client.first_name || ''} ${this._client.last_name || ''}`.trim() || 'Client',
              email: this._client.email || undefined,
            },
          },
        }
      );

      if (error) {
        const errDiv = document.getElementById('pm-card-errors');
        errDiv.textContent = error.message;
        errDiv.style.display = 'block';
        if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = 'Save Card'; }
        return;
      }

      if (setupIntent && setupIntent.status === 'succeeded') {
        alert('Card saved successfully.');
        await this._load();
      } else {
        alert(`Setup ended with status: ${setupIntent?.status || 'unknown'}`);
      }
    } catch (e) {
      alert('Failed to save card: ' + (e.message || 'Unknown error'));
      if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = 'Save Card'; }
    } finally {
      this._busy = false;
    }
  },

  _cancelCollect() {
    if (this._cardElement) {
      try { this._cardElement.unmount(); } catch (e) { /* noop */ }
    }
    this._cardElement = null;
    this._elements = null;
    this._stripe = null;
    this._currentSetupIntent = null;
    document.getElementById('pm-collect-form').style.display = 'none';
    document.getElementById('pm-collect-area').style.display = 'block';
    const btn = document.querySelector('#pm-collect-area button');
    if (btn) btn.disabled = false;
  },

  async _detach(pmId) {
    if (!pmId) return;
    if (!confirm('Remove this card from file? Future recurring bookings will need a new card.')) return;
    try {
      const slug = CleanAPI._slug;
      await CleanAPI.request(
        'DELETE',
        `/api/v1/clean/${slug}/clients/${this._clientId}/payment-methods/${pmId}`
      );
      await this._load();
    } catch (e) {
      alert('Failed to remove card: ' + (e.detail || e.message || 'Unknown error'));
    }
  },
};
