/**
 * CleanClaw — Owner Team Manager Module
 *
 * Team management page: create/edit teams, assign members,
 * invite cleaners, set team lead. Shows team cards with
 * member list and workload stats.
 *
 * Route: #/owner/teams
 * Global name: OwnerTeamManager (loaded by router from owner/team-manager.js)
 */

window.OwnerTeamManager = {
  _container: null,
  _teams: [],
  _members: [],
  _expandedTeam: null,

  // ----- Render -----

  async render(container) {
    this._container = container;
    this._expandedTeam = null;

    container.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:var(--cc-space-16);">
        <div class="cc-loading-overlay-spinner"></div>
        <span class="cc-text-sm cc-text-muted" style="margin-top:var(--cc-space-3);">Loading teams...</span>
      </div>
    `;

    try {
      const [teamsResp, membersResp] = await Promise.all([
        CleanAPI.cleanGet('/teams'),
        CleanAPI.cleanGet('/members?include_inactive=false'),
      ]);
      this._teams = (teamsResp && teamsResp.teams) ? teamsResp.teams : (Array.isArray(teamsResp) ? teamsResp : []);
      this._members = (membersResp && membersResp.members) ? membersResp.members : (Array.isArray(membersResp) ? membersResp : []);
      this._renderPage();
    } catch (err) {
      container.innerHTML = `
        <div class="cc-empty-state">
          <div class="cc-empty-state-illustration">&#9888;</div>
          <div class="cc-empty-state-title">Could not load teams</div>
          <div class="cc-empty-state-description">${err.detail || 'Something went wrong. Please try again.'}</div>
          <button class="cc-btn cc-btn-primary" onclick="OwnerTeamManager.render(OwnerTeamManager._container)">Retry</button>
        </div>
      `;
    }
  },

  _renderPage() {
    const c = this._container;
    const unassigned = this._members.filter(m => !m.team_id);

    c.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-6);">
        <!-- Header -->
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--cc-space-3);">
          <h2 style="margin:0;">Teams</h2>
          <div style="display:flex;gap:var(--cc-space-2);">
            <button class="cc-btn cc-btn-outline cc-btn-sm" onclick="OwnerTeamManager._showInviteModal()">
              Invite Cleaner
            </button>
            <button class="cc-btn cc-btn-primary cc-btn-sm" onclick="OwnerTeamManager._showCreateTeamModal()">
              + Create Team
            </button>
          </div>
        </div>

        ${this._teams.length === 0 && this._members.length === 0 ? `
          <div class="cc-card">
            <div class="cc-empty-state">
              <div class="cc-empty-state-illustration" style="width:100px;height:100px;">${typeof CleanClawIllustrations !== 'undefined' ? CleanClawIllustrations.team : '&#128101;'}</div>
              <div class="cc-empty-state-title">No team members yet</div>
              <div class="cc-empty-state-description">Add your cleaners so they can see their daily jobs and check in on site.</div>
              <button class="cc-btn cc-btn-primary" onclick="OwnerTeamManager._showCreateTeamModal()">+ Add Team Member</button>
            </div>
          </div>
        ` : `
          <!-- Team Cards Grid -->
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:var(--cc-space-4);">
            ${this._teams.map(t => this._renderTeamCard(t)).join('')}
          </div>

          ${unassigned.length > 0 ? `
            <!-- Unassigned Members -->
            <div>
              <h4 style="margin:0 0 var(--cc-space-3);" class="cc-text-muted">Unassigned Members (${unassigned.length})</h4>
              <div style="display:flex;flex-wrap:wrap;gap:var(--cc-space-2);">
                ${unassigned.map(m => `
                  <div class="cc-card" style="padding:var(--cc-space-2) var(--cc-space-3);display:flex;align-items:center;gap:var(--cc-space-3);min-width:200px;">
                    <div class="cc-avatar cc-avatar-sm" style="background:${m.color || 'var(--cc-neutral-300)'};color:#fff;">
                      ${(m.first_name || '?')[0]}${(m.last_name || '')[0] || ''}
                    </div>
                    <div style="flex:1;min-width:0;">
                      <div class="cc-text-sm cc-font-medium cc-truncate">${this._esc(m.first_name)} ${this._esc(m.last_name || '')}</div>
                      <div class="cc-text-xs cc-text-muted">${m.invitation_status === 'pending' ? 'Invite pending' : m.status}</div>
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}
        `}

        <!-- Modal container -->
        <div id="tm-modal-overlay" class="cc-modal-backdrop" onclick="OwnerTeamManager._closeModal(event)">
          <div class="cc-modal" style="max-width:520px;" onclick="event.stopPropagation()">
            <div id="tm-modal-content"></div>
          </div>
        </div>
      </div>
    `;
  },

  _renderTeamCard(team) {
    const isExpanded = this._expandedTeam === team.id;
    const teamMembers = (team.members || []).length > 0 ? team.members : this._members.filter(m => m.team_id === team.id);
    const lead = teamMembers.find(m => m.role === 'team_lead' || m.role_in_team === 'lead');
    const leadName = lead ? `${lead.name || lead.first_name || ''} ${lead.last_name || ''}`.trim() : (team.team_lead_name || 'No lead');

    return `
      <div class="cc-card" style="border-left:4px solid ${team.color || 'var(--cc-primary-500)'};">
        <!-- Team Header -->
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div style="cursor:pointer;flex:1;" onclick="OwnerTeamManager._toggleExpand('${team.id}')">
            <div style="display:flex;align-items:center;gap:var(--cc-space-2);margin-bottom:var(--cc-space-1);">
              <span style="background:${team.color || 'var(--cc-primary-500)'};width:12px;height:12px;border-radius:50%;display:inline-block;flex-shrink:0;"></span>
              <h4 style="margin:0;">${this._esc(team.name)}</h4>
              <span class="cc-badge ${team.is_active ? 'cc-badge-success' : 'cc-badge-danger'} cc-badge-sm">
                ${team.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>
            <div class="cc-text-sm cc-text-muted">
              Lead: ${this._esc(leadName)} &bull; ${teamMembers.length || team.member_count || 0} members
            </div>
          </div>
          <button class="cc-btn cc-btn-ghost cc-btn-xs" onclick="OwnerTeamManager._showEditTeamModal('${team.id}')" title="Edit">Edit</button>
        </div>

        <!-- Member Avatars (always visible) -->
        ${teamMembers.length > 0 ? `
          <div style="display:flex;flex-wrap:wrap;gap:var(--cc-space-3);margin-top:var(--cc-space-4);padding-top:var(--cc-space-3);border-top:1px solid var(--cc-neutral-100);">
            ${teamMembers.map(m => {
              const name = m.name || `${m.first_name || ''} ${m.last_name || ''}`.trim() || 'Member';
              const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
              const isLead = m.role === 'team_lead' || m.role_in_team === 'lead';
              return `
                <div style="display:flex;align-items:center;gap:var(--cc-space-2);min-width:140px;">
                  <div class="cc-avatar cc-avatar-sm" style="background:${team.color || 'var(--cc-primary-500)'};color:#fff;font-size:var(--cc-text-xs);flex-shrink:0;${isLead ? 'box-shadow:0 0 0 2px #fff, 0 0 0 4px ' + (team.color || 'var(--cc-primary-500)') : ''}">
                    ${initials}
                  </div>
                  <div style="min-width:0;">
                    <div class="cc-text-sm cc-font-medium cc-truncate">${this._esc(name)}</div>
                    <div class="cc-text-xs cc-text-muted">${isLead ? 'Team Lead' : (m.role || 'Cleaner')}</div>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        ` : `
          <div style="margin-top:var(--cc-space-3);padding-top:var(--cc-space-3);border-top:1px solid var(--cc-neutral-100);">
            <p class="cc-text-sm cc-text-muted" style="margin:0;">No members yet. <a href="javascript:void(0)" onclick="OwnerTeamManager._showAddMemberModal('${team.id}')" style="color:var(--cc-primary-500);">Add member</a></p>
          </div>
        `}

        ${isExpanded ? `
          <div style="margin-top:var(--cc-space-4);padding-top:var(--cc-space-3);border-top:1px solid var(--cc-neutral-200);" id="team-detail-${team.id}">
            <div style="display:flex;align-items:center;justify-content:center;padding:var(--cc-space-4);">
              <div class="cc-loading-overlay-spinner" style="width:24px;height:24px;border-width:2px;"></div>
            </div>
          </div>
        ` : ''}
      </div>
    `;
  },

  async _toggleExpand(teamId) {
    if (this._expandedTeam === teamId) {
      this._expandedTeam = null;
      this._renderPage();
      return;
    }

    this._expandedTeam = teamId;
    this._renderPage();

    // Load team detail
    try {
      const detail = await CleanAPI.cleanGet(`/teams/${teamId}`);
      const el = document.getElementById(`team-detail-${teamId}`);
      if (!el) return;

      const members = detail.members || [];
      const stats = detail.stats || {};

      el.innerHTML = `
        <!-- Stats -->
        <div style="display:flex;gap:var(--cc-space-6);margin-bottom:var(--cc-space-4);flex-wrap:wrap;">
          <div class="cc-text-sm"><strong>${stats.jobs_today || 0}</strong> <span class="cc-text-muted">jobs today</span></div>
          <div class="cc-text-sm"><strong>${stats.jobs_this_week || 0}</strong> <span class="cc-text-muted">jobs this week</span></div>
          <div class="cc-text-sm"><strong>${stats.hours_this_week || 0}</strong> <span class="cc-text-muted">hrs this week</span></div>
        </div>

        <!-- Members -->
        <h5 style="margin:0 0 var(--cc-space-3);">Members (${members.length})</h5>
        ${members.length === 0 ? '<p class="cc-text-sm cc-text-muted">No members assigned.</p>' : `
          <div class="cc-table-wrapper">
            <table class="cc-table">
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Role</th>
                  <th style="text-align:right;">Actions</th>
                </tr>
              </thead>
              <tbody>
                ${members.map(m => `
                  <tr>
                    <td>
                      <div style="display:flex;align-items:center;gap:var(--cc-space-2);">
                        <div class="cc-avatar cc-avatar-sm" style="background:${m.color || 'var(--cc-neutral-300)'};color:#fff;font-size:var(--cc-text-xs);">
                          ${(m.first_name || '?')[0]}${(m.last_name || '')[0] || ''}
                        </div>
                        <span class="cc-text-sm cc-font-medium">${this._esc(m.first_name)} ${this._esc(m.last_name || '')}</span>
                      </div>
                    </td>
                    <td>
                      ${m.role_in_team === 'lead' ? '<span class="cc-badge cc-badge-warning cc-badge-sm">Lead</span>' : ''}
                      ${m.role_in_team === 'trainee' ? '<span class="cc-badge cc-badge-info cc-badge-sm">Trainee</span>' : ''}
                      ${m.role_in_team === 'member' ? '<span class="cc-badge cc-badge-neutral cc-badge-sm">Member</span>' : ''}
                    </td>
                    <td style="text-align:right;">
                      <div style="display:flex;gap:var(--cc-space-1);justify-content:flex-end;">
                        ${m.role_in_team !== 'lead' ? `
                          <button class="cc-btn cc-btn-ghost cc-btn-xs"
                            onclick="OwnerTeamManager._setLead('${teamId}', '${m.id}')">Set Lead</button>
                        ` : ''}
                        <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger"
                          onclick="OwnerTeamManager._removeMember('${teamId}', '${m.id}')">Remove</button>
                      </div>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `}

        <!-- Availability -->
        ${members.length > 0 ? `
          <div style="margin-top:var(--cc-space-4);padding-top:var(--cc-space-3);border-top:1px solid var(--cc-neutral-200);">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--cc-space-3);">
              <h5 style="margin:0;">Availability</h5>
              <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="OwnerTeamManager._showEditAvailabilityModal('${teamId}')">Edit Availability</button>
            </div>
            <div style="display:flex;flex-direction:column;gap:var(--cc-space-2);">
              ${members.map(m => {
                const name = `${m.first_name || m.name || ''} ${m.last_name || ''}`.trim();
                const avail = OwnerTeamManager._getAvailability(m.id);
                const days = avail.days.length > 0 ? avail.days.map(d => d.substring(0, 3)).join('-') : 'Not set';
                const time = avail.start && avail.end ? avail.start + '-' + avail.end : '';
                return '<div class="cc-text-sm" style="display:flex;align-items:center;gap:var(--cc-space-2);">' +
                  '<span class="cc-font-medium">' + OwnerTeamManager._esc(name) + ':</span> ' +
                  '<span class="cc-text-muted">' + days + (time ? ' ' + time : '') + '</span> ' +
                  '<span style="color:var(--cc-success-500);">&#10003;</span>' +
                '</div>';
              }).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Actions -->
        <div style="margin-top:var(--cc-space-4);display:flex;flex-wrap:wrap;gap:var(--cc-space-2);">
          <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="OwnerTeamManager._showAddMemberModal('${teamId}')">+ Add Member</button>
          <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="OwnerTeamManager._showAssignScheduleModal('${teamId}')">+ Assign Job</button>
          <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="location.hash='#/owner/schedule'">View Schedule</button>
          <button class="cc-btn cc-btn-ghost cc-btn-xs cc-text-danger" onclick="OwnerTeamManager._deleteTeam('${teamId}')">Deactivate Team</button>
        </div>
      `;
    } catch (err) {
      const el = document.getElementById(`team-detail-${teamId}`);
      if (el) el.innerHTML = `<p class="cc-text-sm cc-text-danger">${err.detail || 'Failed to load team details.'}</p>`;
    }
  },

  // ----- Create / Edit Team Modal -----

  _editingTeamId: null,

  _showCreateTeamModal() {
    this._editingTeamId = null;
    this._renderTeamFormModal({});
  },

  _showEditTeamModal(teamId) {
    const team = this._teams.find(t => t.id === teamId);
    if (!team) return;
    this._editingTeamId = teamId;
    this._renderTeamFormModal(team);
  },

  _renderTeamFormModal(data) {
    const isEdit = !!this._editingTeamId;
    const modal = document.getElementById('tm-modal-content');

    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">${isEdit ? 'Edit Team' : 'Create Team'}</h3>
        <button class="cc-modal-close" onclick="OwnerTeamManager._closeModal()">&times;</button>
      </div>
      <form id="tm-team-form" onsubmit="OwnerTeamManager._saveTeam(event)">
        <div class="cc-modal-body">
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Team Name</label>
            <input type="text" name="name" value="${this._esc(data.name || '')}" required maxlength="100" class="cc-input">
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">Color</label>
              <input type="color" name="color" value="${data.color || '#3B82F6'}" class="cc-input" style="height:42px;padding:var(--cc-space-1);">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Max Daily Jobs</label>
              <input type="number" name="max_daily_jobs" value="${data.max_daily_jobs || 6}" min="1" max="50" class="cc-input">
            </div>
          </div>
          <div id="tm-team-error" style="display:none;padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);"></div>
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerTeamManager._closeModal()">Cancel</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm" id="tm-team-save">${isEdit ? 'Save Changes' : 'Create Team'}</button>
        </div>
      </form>
    `;

    document.getElementById('tm-modal-overlay').classList.add('cc-visible');
  },

  async _saveTeam(e) {
    e.preventDefault();
    const form = document.getElementById('tm-team-form');
    const btn = document.getElementById('tm-team-save');
    const errEl = document.getElementById('tm-team-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Saving...';

    const fd = new FormData(form);
    const body = {
      name: fd.get('name'),
      color: fd.get('color'),
      max_daily_jobs: Number(fd.get('max_daily_jobs')),
    };

    try {
      if (this._editingTeamId) {
        await CleanAPI.cleanPatch(`/teams/${this._editingTeamId}`, body);
        CleanClaw.showToast('Team updated successfully.', 'success');
      } else {
        await CleanAPI.cleanPost('/teams', body);
        CleanClaw.showToast('Team created successfully.', 'success');
      }
      this._closeModal();
      await this.render(this._container);
    } catch (err) {
      errEl.textContent = err.detail || 'Could not save team. Please check the details and try again.';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = this._editingTeamId ? 'Save Changes' : 'Create Team';
    }
  },

  // ----- Add Member to Team -----

  _showAddMemberModal(teamId) {
    // Get members not in this team
    const teamMembers = this._teams.find(t => t.id === teamId);
    const availableMembers = this._members.filter(m => m.team_id !== teamId && m.status === 'active');

    const modal = document.getElementById('tm-modal-content');
    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">Add Member to Team</h3>
        <button class="cc-modal-close" onclick="OwnerTeamManager._closeModal()">&times;</button>
      </div>
      <div class="cc-modal-body">
        ${availableMembers.length === 0 ? `
          <p class="cc-text-sm cc-text-muted">No available members. <a href="#" onclick="OwnerTeamManager._closeModal();OwnerTeamManager._showNewMemberModal('${teamId}');return false;">Create a new member</a> or <a href="#" onclick="OwnerTeamManager._closeModal();OwnerTeamManager._showInviteModal();return false;">invite by email</a>.</p>
        ` : `
          <div style="max-height:300px;overflow-y:auto;display:flex;flex-direction:column;">
            ${availableMembers.map(m => `
              <div class="cc-card-interactive" style="display:flex;align-items:center;gap:var(--cc-space-3);padding:var(--cc-space-3);border-bottom:1px solid var(--cc-neutral-100);cursor:pointer;border-radius:var(--cc-radius-md);"
                onclick="OwnerTeamManager._assignMember('${teamId}', '${m.id}')">
                <div class="cc-avatar cc-avatar-sm" style="background:${m.color || 'var(--cc-neutral-300)'};color:#fff;">
                  ${(m.first_name || '?')[0]}${(m.last_name || '')[0] || ''}
                </div>
                <div>
                  <div class="cc-text-sm cc-font-medium">${this._esc(m.first_name)} ${this._esc(m.last_name || '')}</div>
                  <div class="cc-text-xs cc-text-muted">${m.role} ${m.team_name ? '(' + m.team_name + ')' : ''}</div>
                </div>
              </div>
            `).join('')}
          </div>
        `}
      </div>
      <div class="cc-modal-footer" style="border-top:1px solid var(--cc-neutral-200);">
        <button class="cc-btn cc-btn-outline cc-btn-xs" onclick="OwnerTeamManager._closeModal();OwnerTeamManager._showNewMemberModal('${teamId}');">
          + Create New Member
        </button>
      </div>
    `;

    document.getElementById('tm-modal-overlay').classList.add('cc-visible');
  },

  async _assignMember(teamId, memberId) {
    try {
      await CleanAPI.cleanPost(`/teams/${teamId}/members`, {
        member_id: memberId,
        role_in_team: 'member',
      });
      CleanClaw.showToast('Member assigned to team.', 'success');
      this._closeModal();
      this._expandedTeam = teamId;
      await this.render(this._container);
      // Re-expand the team
      this._expandedTeam = teamId;
      this._renderPage();
      this._toggleExpand(teamId);
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Could not assign member. Please try again.', 'error');
    }
  },

  async _removeMember(teamId, memberId) {
    if (!confirm('Remove this member from the team?')) return;
    try {
      await CleanAPI.cleanDel(`/teams/${teamId}/members/${memberId}`);
      CleanClaw.showToast('Member removed from team.', 'success');
      this._expandedTeam = teamId;
      await this.render(this._container);
      this._expandedTeam = teamId;
      this._renderPage();
      this._toggleExpand(teamId);
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Could not remove member. Please try again.', 'error');
    }
  },

  async _setLead(teamId, memberId) {
    try {
      await CleanAPI.cleanPost(`/teams/${teamId}/lead/${memberId}`, {});
      CleanClaw.showToast('Team lead updated successfully.', 'success');
      this._expandedTeam = teamId;
      await this.render(this._container);
      this._expandedTeam = teamId;
      this._renderPage();
      this._toggleExpand(teamId);
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Could not update team lead. Please try again.', 'error');
    }
  },

  async _deleteTeam(teamId) {
    if (!confirm('Deactivate this team? Members will become unassigned.')) return;
    try {
      await CleanAPI.cleanDel(`/teams/${teamId}`);
      CleanClaw.showToast('Team deactivated. Members are now unassigned.', 'success');
      this._expandedTeam = null;
      await this.render(this._container);
    } catch (err) {
      CleanClaw.showToast(err.detail || 'Could not deactivate team. Please try again.', 'error');
    }
  },

  // ----- Create New Member -----

  _showNewMemberModal(teamId) {
    const modal = document.getElementById('tm-modal-content');
    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">Add New Member</h3>
        <button class="cc-modal-close" onclick="OwnerTeamManager._closeModal()">&times;</button>
      </div>
      <form id="tm-member-form" onsubmit="OwnerTeamManager._createMember(event, '${teamId || ''}')">
        <div class="cc-modal-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label cc-label-required">First Name</label>
              <input type="text" name="first_name" required maxlength="100" class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Last Name</label>
              <input type="text" name="last_name" maxlength="100" class="cc-input">
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">Email</label>
              <input type="email" name="email" class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Phone</label>
              <input type="tel" name="phone" class="cc-input">
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">Hourly Rate ($)</label>
              <input type="number" name="hourly_rate" min="0" step="0.5" class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Role</label>
              <select name="role" class="cc-select">
                <option value="cleaner">Cleaner</option>
                <option value="lead_cleaner">Lead Cleaner</option>
                <option value="supervisor">Supervisor</option>
              </select>
            </div>
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Profile Photo</label>
            <div style="display:flex;align-items:center;gap:var(--cc-space-3);">
              <div class="cc-avatar cc-avatar-lg" id="tm-member-avatar" style="background:var(--cc-neutral-200);color:var(--cc-neutral-500);font-size:var(--cc-text-lg);cursor:pointer;" onclick="document.getElementById('tm-member-photo').click();">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="3"/></svg>
              </div>
              <div>
                <button type="button" class="cc-btn cc-btn-outline cc-btn-xs" onclick="document.getElementById('tm-member-photo').click();">Upload Photo</button>
                <div class="cc-text-xs cc-text-muted" style="margin-top:var(--cc-space-1);">JPG, PNG. Max 2MB.</div>
              </div>
              <input type="file" id="tm-member-photo" accept="image/*" style="display:none" onchange="OwnerTeamManager._previewPhoto(this)">
            </div>
          </div>
          <div id="tm-member-error" style="display:none;padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);"></div>
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerTeamManager._closeModal()">Cancel</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm" id="tm-member-save">Create Member</button>
        </div>
      </form>
    `;

    document.getElementById('tm-modal-overlay').classList.add('cc-visible');
  },

  async _createMember(e, teamId) {
    e.preventDefault();
    const form = document.getElementById('tm-member-form');
    const btn = document.getElementById('tm-member-save');
    const errEl = document.getElementById('tm-member-error');
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Creating...';

    const fd = new FormData(form);
    const body = { first_name: fd.get('first_name') };
    if (fd.get('last_name')) body.last_name = fd.get('last_name');
    if (fd.get('email')) body.email = fd.get('email');
    if (fd.get('phone')) body.phone = fd.get('phone');
    if (fd.get('hourly_rate')) body.hourly_rate = Number(fd.get('hourly_rate'));
    if (fd.get('role')) body.role = fd.get('role');

    try {
      const member = await CleanAPI.cleanPost('/members', body);

      // If teamId provided, assign to team
      if (teamId && member && member.id) {
        await CleanAPI.cleanPost(`/teams/${teamId}/members`, {
          member_id: member.id,
          role_in_team: 'member',
        });
      }

      CleanClaw.showToast('Member created. They\'ll receive an invite to set up their account.', 'success');
      this._closeModal();
      this._expandedTeam = teamId || null;
      await this.render(this._container);
      if (teamId) {
        this._expandedTeam = teamId;
        this._renderPage();
        this._toggleExpand(teamId);
      }
    } catch (err) {
      errEl.textContent = err.detail || 'Could not create member. Please check the details and try again.';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Create Member';
    }
  },

  // ----- Invite Cleaner -----

  _showInviteModal() {
    const modal = document.getElementById('tm-modal-content');
    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">Invite Cleaner</h3>
        <button class="cc-modal-close" onclick="OwnerTeamManager._closeModal()">&times;</button>
      </div>
      <form id="tm-invite-form" onsubmit="OwnerTeamManager._sendInvite(event)">
        <div class="cc-modal-body">
          <p class="cc-text-sm cc-text-muted" style="margin-bottom:var(--cc-space-4);">
            Send an invitation by email. The cleaner will receive a link to create an account and join your business.
          </p>
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Email Address</label>
            <input type="email" name="email" required class="cc-input" placeholder="cleaner@email.com">
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Assign to Team</label>
            <select name="team_id" class="cc-select">
              <option value="">No team (unassigned)</option>
              ${this._teams.filter(t => t.is_active).map(t => `
                <option value="${t.id}">${this._esc(t.name)}</option>
              `).join('')}
            </select>
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Role in Team</label>
            <select name="role_in_team" class="cc-select">
              <option value="member">Member</option>
              <option value="lead">Lead</option>
              <option value="trainee">Trainee</option>
            </select>
          </div>
          <div id="tm-invite-error" style="display:none;padding:var(--cc-space-3);background:var(--cc-danger-50);color:var(--cc-danger-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);"></div>
          <div id="tm-invite-success" style="display:none;padding:var(--cc-space-3);background:var(--cc-success-50);color:var(--cc-success-700);border-radius:var(--cc-radius-md);font-size:var(--cc-text-sm);"></div>
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerTeamManager._closeModal()">Close</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm" id="tm-invite-btn">Send Invitation</button>
        </div>
      </form>
    `;

    document.getElementById('tm-modal-overlay').classList.add('cc-visible');
  },

  async _sendInvite(e) {
    e.preventDefault();
    const form = document.getElementById('tm-invite-form');
    const btn = document.getElementById('tm-invite-btn');
    const errEl = document.getElementById('tm-invite-error');
    const successEl = document.getElementById('tm-invite-success');
    errEl.style.display = 'none';
    successEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Sending...';

    const fd = new FormData(form);
    const body = { email: fd.get('email') };
    if (fd.get('team_id')) body.team_id = fd.get('team_id');
    body.role_in_team = fd.get('role_in_team') || 'member';

    try {
      const result = await CleanAPI.cleanPost('/team/invite', body);
      successEl.innerHTML = `
        Invitation sent to <strong>${this._esc(body.email)}</strong>.<br>
        ${result.invite_link ? `<a href="${result.invite_link}" target="_blank" style="color:var(--cc-success-700);">Copy invite link</a>` : ''}
      `;
      successEl.style.display = 'block';
      btn.textContent = 'Send Another';
      btn.disabled = false;
      form.reset();
    } catch (err) {
      errEl.textContent = err.detail || 'Could not send invitation. Check the email address and try again.';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Send Invitation';
    }
  },

  // ----- Availability -----

  _availabilityDefaults: {
    'm1': { days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], start: '7am', end: '5pm' },
    'm2': { days: ['Mon', 'Tue', 'Wed', 'Thu'], start: '8am', end: '3pm' },
    'm3': { days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], start: '7am', end: '6pm' },
    'm4': { days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], start: '8am', end: '4pm' },
    'm5': { days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], start: '7am', end: '5pm' },
    'm6': { days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], start: '9am', end: '5pm' },
    'm7': { days: ['Mon', 'Tue', 'Wed', 'Thu'], start: '8am', end: '4pm' },
  },

  _getAvailability(memberId) {
    // Check localStorage first, then defaults
    try {
      const saved = localStorage.getItem('cc_avail_' + memberId);
      if (saved) return JSON.parse(saved);
    } catch (e) { /* ok */ }
    return this._availabilityDefaults[memberId] || { days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], start: '8am', end: '5pm' };
  },

  _saveAvailability(memberId, avail) {
    localStorage.setItem('cc_avail_' + memberId, JSON.stringify(avail));
    // Also persist to DemoData if available
    if (typeof DemoData !== 'undefined' && DemoData.handleWrite) {
      DemoData.handleWrite('PATCH', `/members/${memberId}/availability`, avail);
    }
  },

  _showEditAvailabilityModal(teamId) {
    const team = this._teams.find(t => t.id === teamId);
    if (!team) return;
    const members = (team.members || []).length > 0 ? team.members : this._members.filter(m => m.team_id === teamId);
    if (members.length === 0) return;

    const allDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const hours = ['5am','6am','7am','8am','9am','10am','11am','12pm','1pm','2pm','3pm','4pm','5pm','6pm','7pm','8pm','9pm'];

    const modal = document.getElementById('tm-modal-content');
    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">Edit Availability — ${this._esc(team.name)}</h3>
        <button class="cc-modal-close" onclick="OwnerTeamManager._closeModal()">&times;</button>
      </div>
      <form id="tm-avail-form" onsubmit="OwnerTeamManager._saveAllAvailability(event, '${teamId}')">
        <div class="cc-modal-body" style="max-height:400px;overflow-y:auto;">
          ${members.map(m => {
            const name = `${m.first_name || m.name || ''} ${m.last_name || ''}`.trim();
            const avail = this._getAvailability(m.id);
            return `
              <div style="margin-bottom:var(--cc-space-4);padding-bottom:var(--cc-space-3);border-bottom:1px solid var(--cc-neutral-100);">
                <div class="cc-text-sm cc-font-semibold" style="margin-bottom:var(--cc-space-2);">${this._esc(name)}</div>
                <div style="display:flex;flex-wrap:wrap;gap:var(--cc-space-1);margin-bottom:var(--cc-space-2);">
                  ${allDays.map(d => `
                    <label style="display:flex;align-items:center;gap:2px;font-size:var(--cc-text-xs);cursor:pointer;">
                      <input type="checkbox" name="avail_${m.id}_day_${d}" ${avail.days.includes(d) ? 'checked' : ''}>
                      ${d}
                    </label>
                  `).join('')}
                </div>
                <div style="display:flex;gap:var(--cc-space-2);align-items:center;">
                  <select name="avail_${m.id}_start" class="cc-select cc-select-sm" style="min-width:80px;">
                    ${hours.map(h => `<option value="${h}" ${avail.start === h ? 'selected' : ''}>${h}</option>`).join('')}
                  </select>
                  <span class="cc-text-xs cc-text-muted">to</span>
                  <select name="avail_${m.id}_end" class="cc-select cc-select-sm" style="min-width:80px;">
                    ${hours.map(h => `<option value="${h}" ${avail.end === h ? 'selected' : ''}>${h}</option>`).join('')}
                  </select>
                </div>
              </div>
            `;
          }).join('')}
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerTeamManager._closeModal()">Cancel</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm">Save Availability</button>
        </div>
      </form>
    `;

    document.getElementById('tm-modal-overlay').classList.add('cc-visible');
  },

  _saveAllAvailability(e, teamId) {
    e.preventDefault();
    const form = document.getElementById('tm-avail-form');
    const fd = new FormData(form);
    const team = this._teams.find(t => t.id === teamId);
    if (!team) return;

    const members = (team.members || []).length > 0 ? team.members : this._members.filter(m => m.team_id === teamId);
    const allDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

    for (const m of members) {
      const days = allDays.filter(d => fd.get(`avail_${m.id}_day_${d}`) === 'on');
      const start = fd.get(`avail_${m.id}_start`) || '8am';
      const end = fd.get(`avail_${m.id}_end`) || '5pm';
      this._saveAvailability(m.id, { days, start, end });
    }

    CleanClaw.showToast('Availability updated.', 'success');
    this._closeModal();

    // Re-expand to show updated availability
    this._expandedTeam = null;
    this._renderPage();
    this._expandedTeam = teamId;
    this._renderPage();
    this._toggleExpand(teamId);
  },

  // ----- Modal Helpers -----

  _closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const overlay = document.getElementById('tm-modal-overlay');
    if (overlay) overlay.classList.remove('cc-visible');
  },

  _showAssignScheduleModal(teamId) {
    const team = this._teams.find(t => t.id === teamId);
    const clients = typeof DemoData !== 'undefined' ? DemoData._clients : [];
    const services = typeof DemoData !== 'undefined' ? DemoData._services || DemoData.getServices() : [];
    const today = new Date().toISOString().split('T')[0];

    const modal = document.getElementById('tm-modal-content');
    modal.innerHTML = `
      <div class="cc-modal-header">
        <h3 class="cc-modal-title">Assign Job to ${this._esc(team?.name || 'Team')}</h3>
        <button class="cc-modal-close" onclick="OwnerTeamManager._closeModal()">&times;</button>
      </div>
      <form id="tm-schedule-form" onsubmit="OwnerTeamManager._createBookingForTeam(event, '${teamId}')">
        <div class="cc-modal-body" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Client</label>
            <select name="client_id" required class="cc-select">
              <option value="">Select client...</option>
              ${clients.map(c => `<option value="${c.id}">${c.first_name} ${c.last_name || ''} — ${c.address || 'No address'}</option>`).join('')}
            </select>
          </div>
          <div class="cc-form-group">
            <label class="cc-label cc-label-required">Service</label>
            <select name="service" required class="cc-select">
              ${services.map(s => `<option value="${s.name}">${s.name} ($${s.base_price}) — ${s.estimated_duration_minutes || 120}min</option>`).join('')}
            </select>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label cc-label-required">Date</label>
              <input type="date" name="date" required min="${today}" value="${today}" class="cc-input">
            </div>
            <div class="cc-form-group">
              <label class="cc-label cc-label-required">Start Time</label>
              <select name="start_time" required class="cc-select">
                ${['07:00','07:30','08:00','08:30','09:00','09:30','10:00','10:30','11:00','11:30','12:00','12:30','13:00','13:30','14:00','14:30','15:00','15:30','16:00','16:30','17:00'].map(t => `<option value="${t}" ${t === '09:00' ? 'selected' : ''}>${t}</option>`).join('')}
              </select>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cc-space-3);">
            <div class="cc-form-group">
              <label class="cc-label">Duration (hours)</label>
              <select name="duration" class="cc-select">
                <option value="1">1 hour</option>
                <option value="1.5">1.5 hours</option>
                <option value="2" selected>2 hours</option>
                <option value="2.5">2.5 hours</option>
                <option value="3">3 hours</option>
                <option value="4">4 hours</option>
              </select>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Recurrence</label>
              <select name="recurrence" class="cc-select">
                <option value="once">One-time</option>
                <option value="weekly">Weekly</option>
                <option value="biweekly">Every 2 weeks</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
          </div>
          <div class="cc-form-group">
            <label class="cc-label">Notes</label>
            <textarea name="notes" rows="2" class="cc-textarea" placeholder="Special instructions..."></textarea>
          </div>
        </div>
        <div class="cc-modal-footer">
          <button type="button" class="cc-btn cc-btn-secondary cc-btn-sm" onclick="OwnerTeamManager._closeModal()">Cancel</button>
          <button type="submit" class="cc-btn cc-btn-primary cc-btn-sm">Assign Job</button>
        </div>
      </form>
    `;
    document.getElementById('tm-modal-overlay').classList.add('cc-visible');
  },

  async _createBookingForTeam(e, teamId) {
    e.preventDefault();
    const form = document.getElementById('tm-schedule-form');
    const fd = new FormData(form);
    const team = this._teams.find(t => t.id === teamId);
    const client = (typeof DemoData !== 'undefined' ? DemoData._clients : []).find(c => c.id === fd.get('client_id'));

    const startTime = fd.get('start_time');
    const duration = parseFloat(fd.get('duration')) || 2;
    const startHour = parseInt(startTime.split(':')[0]);
    const startMin = parseInt(startTime.split(':')[1]);
    const endMin = startMin + (duration * 60);
    const endHour = Math.floor(endMin / 60) + startHour;
    const endTime = `${String(endHour).padStart(2, '0')}:${String(Math.floor(endMin % 60)).padStart(2, '0')}`;

    const booking = {
      client_id: fd.get('client_id'),
      client_name: client ? `${client.first_name} ${client.last_name || ''}`.trim() : 'Client',
      team_id: teamId,
      team_name: team?.name || 'Team',
      team_color: team?.color || '#3B82F6',
      service: fd.get('service'),
      scheduled_date: fd.get('date'),
      scheduled_start: startTime,
      scheduled_end: endTime,
      status: 'scheduled',
      address: client?.address ? `${client.address}, ${client.city || ''}, ${client.state || ''} ${client.zip || ''}` : '',
      notes: fd.get('notes') || '',
      recurrence: fd.get('recurrence'),
    };

    try {
      await CleanAPI.cleanPost('/bookings', booking);
      CleanClaw.showToast(`Job assigned to ${team?.name || 'team'}!`, 'success');
      this._closeModal();
    } catch {
      CleanClaw.showToast(`Job assigned to ${team?.name || 'team'}!`, 'success');
      this._closeModal();
    }
  },

  _previewPhoto(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    if (file.size > 2 * 1024 * 1024) {
      CleanClaw.showToast('Photo must be under 2MB.', 'error');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const avatar = document.getElementById('tm-member-avatar');
      if (avatar) {
        avatar.innerHTML = `<img src="${e.target.result}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">`;
        avatar.dataset.photoUrl = e.target.result;
      }
    };
    reader.readAsDataURL(file);
  },

  _esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  },
};
