/**
 * Xcleaners — AI Chat Widget (Homeowner)
 * AI Turbo Sprint Bloco 2.1 (2026-04-20).
 *
 * Portado de clawtobusiness/frontend/static/js/chat.js com 7 adaptacoes:
 *   1. API.* → CleanAPI.* (xcleaners wrapper)
 *   2. Toast.error → notify inline (sem toast global em xcleaners)
 *   3. Utils.escapeHtml → _escape inline
 *   4. Utils.formatDateTime → Date.toLocaleString
 *   5. Memories removido (nao aplica)
 *   6. Endpoint /chat/message → /api/v1/clean/{slug}/ai/chat
 *   7. Slug injetado via URL path ou window.XCLEANERS_SLUG
 *
 * Widget auto-injeta FAB flutuante ao detectar token homeowner logado.
 * Handle response.proposed_draft_id → mostra card de confirmacao com link.
 */
(function () {
  'use strict';

  const AIChat = {
    _conversationId: null,
    _sending: false,
    _slug: null,
    _mounted: false,

    _getSlug() {
      // /b/{slug}/..., /site/{slug}/..., /clean/{slug}/...
      const m = location.pathname.match(/\/(?:b|site|clean)\/([^\/]+)/);
      if (m) return m[1];
      return window.XCLEANERS_SLUG || 'default';
    },

    _getToken() {
      return (
        localStorage.getItem('access_token') ||
        localStorage.getItem('xcleaners_token') ||
        localStorage.getItem('token') ||
        ''
      );
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
      this._mount();
      this._mounted = true;
    },

    _mount() {
      const wrap = document.createElement('div');
      wrap.id = 'ai-chat-widget';
      wrap.innerHTML = `
        <button id="ai-chat-fab" aria-label="Open AI chat" title="Chat with AI">💬</button>
        <div id="ai-chat-panel" hidden>
          <div id="ai-chat-header">
            <span id="ai-chat-title">AI Assistant</span>
            <button id="ai-chat-close" aria-label="Close">×</button>
          </div>
          <div id="ai-chat-messages" role="log" aria-live="polite"></div>
          <div id="ai-chat-input-row">
            <textarea id="ai-chat-input" rows="1" placeholder="Ask me to book a cleaning..." aria-label="Message"></textarea>
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
      const greeting =
        (window.I18n && window.I18n.t && window.I18n.t('ai_chat.empty')) ||
        'Hi! I can help you book, reschedule, or ask questions about your cleanings.';
      el.innerHTML = `<div class="ai-chat-empty">${this._escape(greeting)}</div>`;
    },

    _appendMessage(role, content, timestamp) {
      const el = document.getElementById('ai-chat-messages');
      const empty = el.querySelector('.ai-chat-empty');
      if (empty) empty.remove();

      const msg = document.createElement('div');
      msg.className = 'ai-chat-msg ai-chat-msg-' + role;
      msg.innerHTML = `${this._escape(content)}<div class="ai-chat-msg-time">${this._escape(this._formatTime(timestamp))}</div>`;
      el.appendChild(msg);
      this._scroll();
    },

    _showDraftCard(draftId) {
      const el = document.getElementById('ai-chat-messages');
      const card = document.createElement('div');
      card.className = 'ai-chat-draft-card';
      card.innerHTML = `
        <div class="ai-chat-draft-title">✓ Request submitted</div>
        <div class="ai-chat-draft-body">The business will review and confirm shortly.</div>
        <a href="#/homeowner/bookings/${this._escape(draftId)}" class="ai-chat-draft-link">View request →</a>`;
      el.appendChild(card);
      this._scroll();
    },

    _showTyping() {
      const el = document.getElementById('ai-chat-messages');
      const t = document.createElement('div');
      t.className = 'ai-chat-typing';
      t.id = 'ai-chat-typing';
      t.innerHTML = '<span></span><span></span><span></span>';
      el.appendChild(t);
      this._scroll();
    },

    _hideTyping() {
      const t = document.getElementById('ai-chat-typing');
      if (t) t.remove();
    },

    _scroll() {
      const el = document.getElementById('ai-chat-messages');
      if (el) el.scrollTop = el.scrollHeight;
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

        const url = `/api/v1/clean/${this._slug}/ai/chat`;
        // Prefer CleanAPI wrapper (handles auth + error format).
        // Fallback to raw fetch if CleanAPI not loaded.
        const data =
          window.CleanAPI && typeof window.CleanAPI.post === 'function'
            ? await window.CleanAPI.post(url, body)
            : await this._fetchPost(url, body);

        this._hideTyping();
        this._conversationId = data.conversation_id;
        this._appendMessage('assistant', data.response, new Date().toISOString());

        if (data.proposed_draft_id) {
          this._showDraftCard(data.proposed_draft_id);
        }
      } catch (e) {
        this._hideTyping();
        const errorMsg = (e && e.detail) || (e && e.message) || 'Failed to send message';
        this._notify(errorMsg, 'error');
        console.error('[AIChat] send failed:', e);
      } finally {
        this._sending = false;
        document.getElementById('ai-chat-send').disabled = false;
        input.focus();
      }
    },

    async _fetchPost(url, body) {
      const token = this._getToken();
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        let err = {};
        try {
          err = await res.json();
        } catch {
          /* noop */
        }
        const msg = err.detail || err.message || `HTTP ${res.status}`;
        throw new Error(msg);
      }
      return res.json();
    },
  };

  // Expose globally for router/app integration
  window.AIChat = AIChat;

  // Auto-init on DOMContentLoaded if homeowner token is present.
  // Router/auth-ui can also call AIChat.init() explicitly after login.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      if (AIChat._getToken()) AIChat.init();
    });
  } else {
    if (AIChat._getToken()) AIChat.init();
  }
})();
