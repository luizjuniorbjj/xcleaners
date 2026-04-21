/**
 * Xcleaners — Public Visitor Chat Widget
 * AI Turbo Webchat Publico 2026-04-21.
 *
 * Standalone widget pra site publico do business. NAO requer autenticacao.
 * Endpoint: POST /api/v1/clean/{slug}/ai/demo-chat
 *
 * Setup minimo pra integrar em qualquer HTML do business publico:
 *   <link rel="stylesheet" href="/cleaning/static/css/ai-chat.css">
 *   <script>window.XCLEANERS_SLUG = 'my-business-slug';</script>
 *   <script src="/cleaning/static/js/public/ai-demo-chat.js"></script>
 *
 * Slug detection: tenta URL path /b/{slug}|/site/{slug}|/clean/{slug} primeiro.
 * Fallback: window.XCLEANERS_SLUG antes de carregar o script.
 */
(function () {
  'use strict';

  const PublicChat = {
    _conversationId: null,
    _sending: false,
    _slug: null,
    _mounted: false,

    _getSlug() {
      const m = location.pathname.match(/\/(?:b|site|clean)\/([^\/]+)/);
      if (m) return m[1];
      return window.XCLEANERS_SLUG || null;
    },

    _escape(s) {
      if (s === null || s === undefined) return '';
      return String(s).replace(/[&<>"']/g, (c) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
      );
    },

    _formatTime(t) {
      if (!t) return '';
      try {
        return new Date(t).toLocaleString();
      } catch {
        return '';
      }
    },

    _notify(msg, type) {
      const n = document.createElement('div');
      n.className = 'ai-chat-notify ai-chat-notify-' + (type || 'info');
      n.textContent = msg;
      document.body.appendChild(n);
      setTimeout(() => n.remove(), 4000);
    },

    init() {
      if (this._mounted) return;
      this._slug = this._getSlug();
      if (!this._slug) {
        console.warn('[PublicChat] No business slug detected — widget not mounted. Set window.XCLEANERS_SLUG before loading.');
        return;
      }
      this._mount();
      this._mounted = true;
    },

    _mount() {
      const wrap = document.createElement('div');
      wrap.id = 'ai-chat-widget';
      wrap.innerHTML = `
        <button id="ai-chat-fab" aria-label="Chat with us" title="Chat with us">💬</button>
        <div id="ai-chat-panel" hidden>
          <div id="ai-chat-header">
            <span id="ai-chat-title">Chat with us</span>
            <button id="ai-chat-close" aria-label="Close">×</button>
          </div>
          <div id="ai-chat-messages" role="log" aria-live="polite"></div>
          <div id="ai-chat-input-row">
            <textarea id="ai-chat-input" rows="1" placeholder="Ask a question or request a quote..." aria-label="Message"></textarea>
            <button id="ai-chat-send" aria-label="Send">Send</button>
          </div>
        </div>`;
      document.body.appendChild(wrap);

      document.getElementById('ai-chat-fab').addEventListener('click', () => this.toggle());
      document.getElementById('ai-chat-close').addEventListener('click', () => this.toggle());
      document.getElementById('ai-chat-send').addEventListener('click', () => this.send());
      document.getElementById('ai-chat-input').addEventListener('keydown', (e) => this.onKeyDown(e));
    },

    toggle() {
      const panel = document.getElementById('ai-chat-panel');
      if (!panel) return;
      panel.hidden = !panel.hidden;
      if (!panel.hidden) {
        document.getElementById('ai-chat-input').focus();
        const messagesEl = document.getElementById('ai-chat-messages');
        if (messagesEl && !messagesEl.children.length) this._showEmpty();
      }
    },

    _showEmpty() {
      const el = document.getElementById('ai-chat-messages');
      el.innerHTML = '<div class="ai-chat-empty">Hi! I can answer questions, give rough price estimates, and help you request a service. How can I help?</div>';
    },

    _appendMessage(role, content, timestamp) {
      const el = document.getElementById('ai-chat-messages');
      const empty = el.querySelector('.ai-chat-empty');
      if (empty) empty.remove();
      const msg = document.createElement('div');
      msg.className = 'ai-chat-msg ai-chat-msg-' + role;
      msg.innerHTML = `${this._escape(content)}<div class="ai-chat-msg-time">${this._escape(this._formatTime(timestamp))}</div>`;
      el.appendChild(msg);
      el.scrollTop = el.scrollHeight;
    },

    _showLeadCard(leadId) {
      const el = document.getElementById('ai-chat-messages');
      const card = document.createElement('div');
      card.className = 'ai-chat-draft-card';
      card.innerHTML = `
        <div class="ai-chat-draft-title">✓ Request received</div>
        <div class="ai-chat-draft-body">Our team will contact you soon to confirm.</div>`;
      el.appendChild(card);
      el.scrollTop = el.scrollHeight;
    },

    _showTyping() {
      const el = document.getElementById('ai-chat-messages');
      const t = document.createElement('div');
      t.className = 'ai-chat-typing';
      t.id = 'ai-chat-typing';
      t.innerHTML = '<span></span><span></span><span></span>';
      el.appendChild(t);
      el.scrollTop = el.scrollHeight;
    },

    _hideTyping() {
      const t = document.getElementById('ai-chat-typing');
      if (t) t.remove();
    },

    onKeyDown(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    },

    async send() {
      if (this._sending) return;
      const input = document.getElementById('ai-chat-input');
      const message = input.value.trim();
      if (!message) return;
      input.value = '';
      input.style.height = 'auto';
      this._sending = true;
      document.getElementById('ai-chat-send').disabled = true;

      this._appendMessage('user', message, new Date().toISOString());
      this._showTyping();

      try {
        const body = { message };
        if (this._conversationId) body.conversation_id = this._conversationId;
        const res = await fetch(`/api/v1/clean/${this._slug}/ai/demo-chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          let err = {};
          try {
            err = await res.json();
          } catch {
            /* noop */
          }
          throw new Error(err.detail || err.message || `HTTP ${res.status}`);
        }
        const data = await res.json();
        this._hideTyping();
        this._conversationId = data.conversation_id;
        this._appendMessage('assistant', data.response, new Date().toISOString());
        if (data.lead_captured_id) this._showLeadCard(data.lead_captured_id);
      } catch (e) {
        this._hideTyping();
        this._notify(e.message || 'Failed to send message', 'error');
        console.error('[PublicChat] send failed:', e);
      } finally {
        this._sending = false;
        document.getElementById('ai-chat-send').disabled = false;
        input.focus();
      }
    },
  };

  window.PublicChat = PublicChat;

  // Auto-init on DOMContentLoaded (only if slug is detectable)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => PublicChat.init());
  } else {
    PublicChat.init();
  }
})();
