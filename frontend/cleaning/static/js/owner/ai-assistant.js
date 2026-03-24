/**
 * CleanClaw — AI Scheduling Assistant Module
 *
 * Provides:
 * - "AI Optimize" button on schedule builder
 * - Suggestion panel (accept/reject each suggestion)
 * - Insights dashboard card
 * - Plan gate: upgrade prompt for Basic plan users
 *
 * Requires: CleanAPI, CleanClaw (app shell)
 */

window.AIAssistant = {
  _slug: null,
  _plan: null,
  _container: null,
  _isLoading: false,

  // ─── Initialization ─────────────────

  /**
   * Initialize the AI assistant. Called from schedule-builder or dashboard.
   */
  init(slug, plan) {
    this._slug = slug;
    this._plan = plan;
  },

  /**
   * Check if AI features are available (Intermediate+ plan).
   */
  isAvailable() {
    return this._plan === 'intermediate' || this._plan === 'maximum';
  },

  // ─── Schedule Builder Integration ─────────────────

  /**
   * Inject the "AI Optimize" button into the schedule builder toolbar.
   * Called by OwnerScheduleBuilder after render.
   */
  injectOptimizeButton(toolbar) {
    if (!toolbar) return;

    const btn = document.createElement('button');
    btn.id = 'btn-ai-optimize';
    btn.className = 'cc-btn cc-btn-ai cc-btn-sm';
    btn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;vertical-align:middle;">
        <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
        <path d="M2 17l10 5 10-5"></path>
        <path d="M2 12l10 5 10-5"></path>
      </svg>
      AI Optimize
    `;

    if (!this.isAvailable()) {
      btn.classList.add('cc-btn-disabled');
      btn.title = 'Upgrade to Intermediate plan to unlock AI scheduling';
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        this._showUpgradePrompt();
      });
    } else {
      btn.title = 'AI analyzes your schedule and suggests optimizations';
      btn.addEventListener('click', () => this._onOptimizeClick());
    }

    toolbar.appendChild(btn);
  },

  /**
   * Inject AI team suggestion into booking detail panel.
   */
  injectTeamSuggestion(panel, bookingId) {
    if (!this.isAvailable() || !panel) return;

    const btn = document.createElement('button');
    btn.className = 'cc-btn cc-btn-ai cc-btn-xs';
    btn.textContent = 'AI Suggest Team';
    btn.title = 'AI recommends the best team for this job';
    btn.addEventListener('click', () => this._suggestTeam(bookingId, panel));

    const wrapper = document.createElement('div');
    wrapper.className = 'cc-ai-suggest-wrapper';
    wrapper.style.marginTop = '8px';
    wrapper.appendChild(btn);

    panel.appendChild(wrapper);
  },

  // ─── Optimize Schedule ─────────────────

  async _onOptimizeClick() {
    if (this._isLoading) return;

    const dateInput = document.getElementById('schedule-date') ||
                      document.querySelector('[data-schedule-date]');
    const selectedDate = dateInput
      ? (dateInput.value || dateInput.dataset.scheduleDate)
      : new Date().toISOString().split('T')[0];

    this._isLoading = true;
    this._showSuggestionPanel('loading');

    try {
      const result = await CleanAPI.request(
        'POST',
        `/api/v1/clean/${this._slug}/ai/optimize-schedule/${selectedDate}`
      );

      if (result && result.status === 'success') {
        this._showSuggestionPanel('results', result.suggestions);
      } else {
        this._showSuggestionPanel('error', result?.suggestions || 'Failed to generate suggestions.');
      }
    } catch (err) {
      const detail = err?.detail || 'Failed to connect to AI service.';
      this._showSuggestionPanel('error', detail);
    } finally {
      this._isLoading = false;
    }
  },

  // ─── Suggest Team ─────────────────

  async _suggestTeam(bookingId, panel) {
    const existingResult = panel.querySelector('.cc-ai-team-result');
    if (existingResult) existingResult.remove();

    const resultDiv = document.createElement('div');
    resultDiv.className = 'cc-ai-team-result';
    resultDiv.innerHTML = '<div class="cc-ai-loading"><div class="cc-spinner-sm"></div> Analyzing...</div>';
    panel.appendChild(resultDiv);

    try {
      const result = await CleanAPI.request(
        'POST',
        `/api/v1/clean/${this._slug}/ai/suggest-team/${bookingId}`
      );

      if (result && result.status === 'success') {
        resultDiv.innerHTML = `
          <div class="cc-ai-suggestion-box">
            <div class="cc-ai-suggestion-header">
              <span class="cc-ai-icon">AI</span> Team Recommendation
            </div>
            <div class="cc-ai-suggestion-body">${this._formatMarkdown(result.suggestion)}</div>
          </div>
        `;
      } else {
        resultDiv.innerHTML = `
          <div class="cc-ai-error">${this._escapeHtml(result?.suggestion || 'Error')}</div>
        `;
      }
    } catch (err) {
      resultDiv.innerHTML = `
        <div class="cc-ai-error">${this._escapeHtml(err?.detail || 'Failed to get suggestion.')}</div>
      `;
    }
  },

  // ─── Insights Dashboard Card ─────────────────

  /**
   * Render the AI insights card for the owner dashboard.
   */
  async renderInsightsCard(container) {
    if (!container) return;

    if (!this.isAvailable()) {
      container.innerHTML = this._buildUpgradeCard();
      container.querySelector('.cc-ai-upgrade-btn')?.addEventListener('click', () => this._showUpgradePrompt());
      return;
    }

    container.innerHTML = `
      <div class="cc-card cc-ai-insights-card">
        <div class="cc-card-header">
          <span class="cc-ai-icon">AI</span>
          <span>Scheduling Insights</span>
          <button class="cc-btn cc-btn-ghost cc-btn-xs" id="btn-refresh-insights">Refresh</button>
        </div>
        <div class="cc-card-body" id="ai-insights-body">
          <div class="cc-ai-loading"><div class="cc-spinner-sm"></div> Generating insights...</div>
        </div>
      </div>
    `;

    document.getElementById('btn-refresh-insights')?.addEventListener('click', () => this._loadInsights());
    await this._loadInsights();
  },

  async _loadInsights() {
    const body = document.getElementById('ai-insights-body');
    if (!body) return;

    body.innerHTML = '<div class="cc-ai-loading"><div class="cc-spinner-sm"></div> Analyzing your schedule data...</div>';

    try {
      const result = await CleanAPI.request(
        'GET',
        `/api/v1/clean/${this._slug}/ai/insights`
      );

      if (result && result.status === 'success') {
        body.innerHTML = `
          <div class="cc-ai-insights-content">${this._formatMarkdown(result.insights)}</div>
          <div class="cc-ai-insights-footer">
            <small>Generated ${this._formatTimestamp(result.generated_at)}</small>
          </div>
        `;
      } else {
        body.innerHTML = `<div class="cc-ai-error">${this._escapeHtml(result?.insights || 'Failed.')}</div>`;
      }
    } catch (err) {
      body.innerHTML = `<div class="cc-ai-error">${this._escapeHtml(err?.detail || 'Failed to load insights.')}</div>`;
    }
  },

  // ─── Duration Prediction ─────────────────

  /**
   * Predict duration for a client/service. Returns the result object.
   * Can be called from client-detail or booking forms.
   */
  async predictDuration(clientId, serviceTypeId) {
    if (!this.isAvailable()) return null;

    try {
      const result = await CleanAPI.request(
        'POST',
        `/api/v1/clean/${this._slug}/ai/predict-duration`,
        { client_id: clientId, service_type_id: serviceTypeId || null }
      );
      return result;
    } catch (err) {
      logger.warn('AI predict-duration error:', err);
      return null;
    }
  },

  // ─── Suggestion Panel ─────────────────

  _showSuggestionPanel(state, content) {
    let panel = document.getElementById('ai-suggestion-panel');

    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'ai-suggestion-panel';
      panel.className = 'cc-ai-panel';

      // Insert after the schedule summary bar or at top of schedule page
      const schedPage = document.querySelector('.cc-schedule-page');
      const summaryBar = document.querySelector('.cc-schedule-summary');
      if (summaryBar && summaryBar.parentNode) {
        summaryBar.parentNode.insertBefore(panel, summaryBar.nextSibling);
      } else if (schedPage) {
        schedPage.prepend(panel);
      } else {
        document.body.appendChild(panel);
      }
    }

    panel.style.display = 'block';

    if (state === 'loading') {
      panel.innerHTML = `
        <div class="cc-ai-panel-header">
          <span class="cc-ai-icon">AI</span>
          <span>Analyzing Schedule...</span>
          <button class="cc-ai-panel-close" onclick="AIAssistant._closeSuggestionPanel()">&times;</button>
        </div>
        <div class="cc-ai-panel-body">
          <div class="cc-ai-loading">
            <div class="cc-spinner-sm"></div>
            <span>AI is analyzing your schedule, teams, and locations. This may take 10-20 seconds...</span>
          </div>
        </div>
      `;
    } else if (state === 'results') {
      panel.innerHTML = `
        <div class="cc-ai-panel-header">
          <span class="cc-ai-icon">AI</span>
          <span>Schedule Optimization Suggestions</span>
          <button class="cc-ai-panel-close" onclick="AIAssistant._closeSuggestionPanel()">&times;</button>
        </div>
        <div class="cc-ai-panel-body">
          <div class="cc-ai-suggestions-content">${this._formatMarkdown(content)}</div>
        </div>
        <div class="cc-ai-panel-footer">
          <small>Review suggestions above. Apply changes manually using drag-and-drop in the schedule.</small>
        </div>
      `;
    } else if (state === 'error') {
      panel.innerHTML = `
        <div class="cc-ai-panel-header">
          <span class="cc-ai-icon cc-ai-icon-error">AI</span>
          <span>Error</span>
          <button class="cc-ai-panel-close" onclick="AIAssistant._closeSuggestionPanel()">&times;</button>
        </div>
        <div class="cc-ai-panel-body">
          <div class="cc-ai-error">${this._escapeHtml(content)}</div>
        </div>
      `;
    }
  },

  _closeSuggestionPanel() {
    const panel = document.getElementById('ai-suggestion-panel');
    if (panel) panel.style.display = 'none';
  },

  // ─── Plan Gate / Upgrade ─────────────────

  _showUpgradePrompt() {
    const modal = document.createElement('div');
    modal.className = 'cc-modal-overlay';
    modal.innerHTML = `
      <div class="cc-modal cc-ai-upgrade-modal">
        <div class="cc-modal-header">
          <h3>Unlock AI Scheduling</h3>
          <button class="cc-modal-close" onclick="this.closest('.cc-modal-overlay').remove()">&times;</button>
        </div>
        <div class="cc-modal-body">
          <div class="cc-ai-upgrade-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
              <path d="M2 17l10 5 10-5"></path>
              <path d="M2 12l10 5 10-5"></path>
            </svg>
          </div>
          <p><strong>AI Scheduling Assistant</strong> is available on the <strong>Intermediate</strong> plan and above.</p>
          <ul class="cc-ai-feature-list">
            <li>AI schedule optimization (reduce travel, balance workload)</li>
            <li>Smart team assignment suggestions</li>
            <li>Duration predictions based on history</li>
            <li>Business insights and pattern detection</li>
            <li>Cancellation trend analysis</li>
          </ul>
          <p class="cc-ai-upgrade-price">Upgrade to <strong>Intermediate</strong> for just <strong>$49/mo</strong></p>
        </div>
        <div class="cc-modal-footer">
          <button class="cc-btn cc-btn-ghost" onclick="this.closest('.cc-modal-overlay').remove()">Maybe Later</button>
          <button class="cc-btn cc-btn-primary cc-ai-upgrade-action">Upgrade Now</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // Upgrade action — redirect to plan upgrade
    modal.querySelector('.cc-ai-upgrade-action')?.addEventListener('click', async () => {
      try {
        const result = await CleanAPI.request('POST', `/api/v1/clean/${this._slug}/plan/upgrade`);
        if (result?.checkout_url) {
          window.location.href = result.checkout_url;
        } else {
          CleanClaw.showToast('Plan upgrade will be available soon. Contact support.', 'info');
        }
      } catch (err) {
        CleanClaw.showToast(err?.detail || 'Upgrade failed.', 'error');
      }
      modal.remove();
    });

    // Close on overlay click
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });
  },

  _buildUpgradeCard() {
    return `
      <div class="cc-card cc-ai-upgrade-card">
        <div class="cc-card-header">
          <span class="cc-ai-icon">AI</span>
          <span>AI Scheduling Assistant</span>
        </div>
        <div class="cc-card-body" style="text-align:center; padding:24px;">
          <p>Unlock AI-powered schedule optimization, smart team suggestions, and business insights.</p>
          <button class="cc-btn cc-btn-primary cc-ai-upgrade-btn" style="margin-top:12px;">
            Upgrade to Intermediate ($49/mo)
          </button>
        </div>
      </div>
    `;
  },

  // ─── Formatting Helpers ─────────────────

  /**
   * Simple markdown-to-HTML converter for AI responses.
   * Handles: bold, headers, lists, line breaks.
   */
  _formatMarkdown(text) {
    if (!text) return '';
    let html = this._escapeHtml(text);

    // Headers (### → h4, ## → h3, # → h2)
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Bullet lists
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // Line breaks
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');

    return `<p>${html}</p>`;
  },

  _escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },

  _formatTimestamp(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch {
      return iso;
    }
  },
};
