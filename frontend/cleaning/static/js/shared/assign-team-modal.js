/**
 * Xcleaners — Assign Team Modal (shared helper)
 *
 * Opens a modal to reassign a booking to a different team. Calls
 * POST /schedule/assign and invokes onSuccess({booking_id, team_id}).
 *
 * Usage:
 *   AssignTeamModal.open({
 *     bookingId: 'uuid',
 *     currentTeamId: 'uuid' | null,
 *     onSuccess: (result) => { ... refresh list ... },
 *   });
 *
 * Backend: POST /api/v1/clean/{slug}/schedule/assign
 *          body: { booking_id, team_id }
 *
 * Loads teams list from GET /teams on first open (cached).
 */

window.AssignTeamModal = {
  _teamsCache: null,
  _teamsCacheAt: 0,
  _CACHE_TTL_MS: 60_000,

  async open({ bookingId, currentTeamId = null, onSuccess = null } = {}) {
    if (!bookingId) {
      console.error('[AssignTeamModal] bookingId is required');
      return;
    }
    this._mount();
    this._renderLoading();
    try {
      const teams = await this._fetchTeams();
      this._renderPicker(teams, { bookingId, currentTeamId, onSuccess });
    } catch (err) {
      this._renderError((err && err.detail) || String(err));
    }
  },

  _mount() {
    let el = document.getElementById('assign-team-modal');
    if (el) el.remove();
    el = document.createElement('div');
    el.id = 'assign-team-modal';
    el.className = 'cc-modal-backdrop';
    el.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center;padding:1rem;';
    el.addEventListener('click', (e) => {
      if (e.target === el) this.close();
    });
    document.body.appendChild(el);
    this._el = el;
  },

  close() {
    const el = document.getElementById('assign-team-modal');
    if (el) el.remove();
  },

  _escape(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  },

  _renderLoading() {
    this._el.innerHTML = `
      <div class="cc-modal" style="background:var(--cc-color-surface,#fff);border-radius:12px;max-width:480px;width:100%;padding:1.5rem;">
        <div style="display:flex;align-items:center;gap:.75rem;">
          <div class="cc-loading-overlay-spinner"></div>
          <span class="cc-text-sm cc-text-muted">Loading teams…</span>
        </div>
      </div>
    `;
  },

  _renderError(detail) {
    this._el.innerHTML = `
      <div class="cc-modal" style="background:var(--cc-color-surface,#fff);border-radius:12px;max-width:480px;width:100%;padding:1.5rem;">
        <h2 style="margin:0 0 .5rem 0;">Could not load teams</h2>
        <p class="cc-text-sm cc-text-muted" style="margin:0 0 1rem 0;">${this._escape(detail)}</p>
        <div style="display:flex;justify-content:flex-end;">
          <button class="cc-btn cc-btn-secondary" onclick="AssignTeamModal.close()">Close</button>
        </div>
      </div>
    `;
  },

  async _fetchTeams() {
    const now = Date.now();
    if (this._teamsCache && now - this._teamsCacheAt < this._CACHE_TTL_MS) {
      return this._teamsCache;
    }
    const resp = await CleanAPI.cleanGet('/teams');
    const teams = Array.isArray(resp) ? resp : (resp && resp.teams) || [];
    this._teamsCache = teams.filter((t) => t.is_active !== false);
    this._teamsCacheAt = now;
    return this._teamsCache;
  },

  _renderPicker(teams, ctx) {
    const { bookingId, currentTeamId, onSuccess } = ctx;

    if (!teams.length) {
      this._el.innerHTML = `
        <div class="cc-modal" style="background:var(--cc-color-surface,#fff);border-radius:12px;max-width:480px;width:100%;padding:1.5rem;">
          <h2 style="margin:0 0 .5rem 0;">No teams available</h2>
          <p class="cc-text-sm cc-text-muted" style="margin:0 0 1rem 0;">
            Create a team first in the Teams section before assigning bookings.
          </p>
          <div style="display:flex;justify-content:flex-end;gap:.5rem;">
            <button class="cc-btn cc-btn-secondary" onclick="AssignTeamModal.close()">Close</button>
            <button class="cc-btn cc-btn-primary" onclick="AssignTeamModal.close(); CleanRouter.navigate('/teams');">Go to Teams</button>
          </div>
        </div>
      `;
      return;
    }

    const options = teams.map((t) => {
      const id = t.id;
      const name = this._escape(t.name || `Team ${id.slice(0, 8)}`);
      const size = t.member_count || (Array.isArray(t.members) ? t.members.length : null);
      const sizeLabel = size !== null && size !== undefined ? ` · ${size} member${size === 1 ? '' : 's'}` : '';
      const checked = String(id) === String(currentTeamId) ? 'checked' : '';
      return `
        <label style="display:flex;align-items:center;gap:.75rem;padding:.75rem;border:1px solid var(--cc-color-border,#e2e8f0);border-radius:8px;cursor:pointer;margin-bottom:.5rem;">
          <input type="radio" name="assign-team-radio" value="${this._escape(id)}" ${checked}>
          <div>
            <div style="font-weight:500;">${name}</div>
            ${sizeLabel ? `<div class="cc-text-xs cc-text-muted">${sizeLabel}</div>` : ''}
          </div>
        </label>
      `;
    }).join('');

    this._el.innerHTML = `
      <div class="cc-modal" style="background:var(--cc-color-surface,#fff);border-radius:12px;max-width:480px;width:100%;padding:1.5rem;max-height:90vh;overflow-y:auto;">
        <h2 style="margin:0 0 .25rem 0;">Reassign team</h2>
        <p class="cc-text-sm cc-text-muted" style="margin:0 0 1rem 0;">
          Pick a team to handle this booking. The previous team will be notified of the change.
        </p>
        <form id="assign-team-form">
          ${options}
        </form>
        <div id="assign-team-err" class="cc-text-sm" style="color:var(--cc-color-error,#dc2626);margin-top:.5rem;display:none;"></div>
        <div style="display:flex;justify-content:flex-end;gap:.5rem;margin-top:1rem;">
          <button type="button" class="cc-btn cc-btn-secondary" onclick="AssignTeamModal.close()">Cancel</button>
          <button type="button" id="assign-team-submit" class="cc-btn cc-btn-primary">Assign</button>
        </div>
      </div>
    `;

    document.getElementById('assign-team-submit').addEventListener('click', async () => {
      const radio = document.querySelector('input[name="assign-team-radio"]:checked');
      if (!radio) {
        this._showError('Select a team.');
        return;
      }
      const newTeamId = radio.value;
      if (String(newTeamId) === String(currentTeamId)) {
        this._showError('That team is already assigned.');
        return;
      }
      await this._submit(bookingId, newTeamId, onSuccess);
    });
  },

  _showError(msg) {
    const el = document.getElementById('assign-team-err');
    if (el) {
      el.textContent = msg;
      el.style.display = 'block';
    }
  },

  async _submit(bookingId, teamId, onSuccess) {
    const btn = document.getElementById('assign-team-submit');
    const cancel = this._el.querySelector('.cc-btn-secondary');
    if (btn) btn.disabled = true;
    if (cancel) cancel.disabled = true;
    try {
      const result = await CleanAPI.cleanPost('/schedule/assign', {
        booking_id: bookingId,
        team_id: teamId,
      });
      this.close();
      if (typeof onSuccess === 'function') {
        onSuccess({ booking_id: bookingId, team_id: teamId, ...result });
      }
    } catch (err) {
      this._showError(`Could not assign: ${(err && err.detail) || err}`);
      if (btn) btn.disabled = false;
      if (cancel) cancel.disabled = false;
    }
  },
};
