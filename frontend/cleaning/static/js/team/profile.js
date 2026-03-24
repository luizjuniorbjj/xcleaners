/**
 * CleanClaw — Team Profile Screen
 * Shows cleaner/team_lead profile info and settings.
 * Persists to localStorage when API is unavailable (demo mode).
 */

window.TeamProfile = {
  _profile: null,

  async render(container) {
    const user = CleanClaw._user || {};
    const role = CleanClaw._currentRole || 'cleaner';

    // Load profile: API first, then localStorage fallback
    let profile = {};
    try {
      const resp = await CleanAPI.cleanGet('/me');
      if (resp && resp.email) {
        profile = resp;
      }
    } catch { /* ignore */ }

    // Merge with localStorage saved data
    const saved = JSON.parse(localStorage.getItem('cc_profile') || '{}');
    profile = { ...profile, ...saved };

    // Defaults
    const displayName = profile.name || user.name || user.nome || user.email || 'Team Member';
    const email = profile.email || user.email || '';
    const phone = profile.phone || '';
    const initials = displayName.charAt(0).toUpperCase();
    const roleLabel = role === 'team_lead' ? 'Team Lead' : 'Cleaner';
    const prefs = profile.preferences || {};

    this._profile = profile;

    container.innerHTML = `
      <div class="cc-animate-fade-in" style="max-width:600px;margin:0 auto;">
        <h2 class="cc-text-2xl cc-font-bold" style="margin-bottom:var(--cc-space-6);">My Profile</h2>

        <!-- Avatar + Name -->
        <div class="cc-card" style="text-align:center;padding:var(--cc-space-8);">
          <div class="cc-avatar cc-avatar-xl" id="profile-avatar" style="margin:0 auto var(--cc-space-4);background:var(--cc-primary-500);color:white;font-size:var(--cc-text-2xl);">
            ${initials}
          </div>
          <div class="cc-text-xl cc-font-semibold" id="profile-display-name">${displayName}</div>
          <div class="cc-text-sm cc-text-muted" style="margin-top:var(--cc-space-1);">${email}</div>
          <span class="cc-badge cc-badge-primary" style="margin-top:var(--cc-space-2);display:inline-block;">${roleLabel}</span>
        </div>

        <!-- Contact Info -->
        <div class="cc-card" style="margin-top:var(--cc-space-4);">
          <div class="cc-card-header">
            <div class="cc-card-title">Contact Information</div>
          </div>
          <div class="cc-card-body" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
            <div class="cc-form-group">
              <label class="cc-label">Full Name</label>
              <input type="text" class="cc-input" value="${displayName}" id="profile-name" placeholder="Your name">
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Email</label>
              <input type="email" class="cc-input" value="${email}" disabled style="background:var(--cc-neutral-100);cursor:not-allowed;">
              <span class="cc-input-help">Email cannot be changed</span>
            </div>
            <div class="cc-form-group">
              <label class="cc-label">Phone</label>
              <input type="tel" class="cc-input" value="${phone}" id="profile-phone" placeholder="(555) 123-4567">
            </div>
          </div>
        </div>

        <!-- Notification Preferences -->
        <div class="cc-card" style="margin-top:var(--cc-space-4);">
          <div class="cc-card-header">
            <div class="cc-card-title">Notifications</div>
          </div>
          <div class="cc-card-body" style="display:flex;flex-direction:column;gap:var(--cc-space-5);">
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div>
                <div class="cc-font-medium cc-text-sm">Push Notifications</div>
                <div class="cc-text-xs cc-text-muted">New jobs and schedule changes</div>
              </div>
              <label class="cc-toggle">
                <input type="checkbox" class="cc-toggle-input" ${prefs.push !== false ? 'checked' : ''} id="profile-push">
                <span class="cc-toggle-track"><span class="cc-toggle-thumb"></span></span>
              </label>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div>
                <div class="cc-font-medium cc-text-sm">SMS Notifications</div>
                <div class="cc-text-xs cc-text-muted">Urgent updates via text message</div>
              </div>
              <label class="cc-toggle">
                <input type="checkbox" class="cc-toggle-input" ${prefs.sms ? 'checked' : ''} id="profile-sms">
                <span class="cc-toggle-track"><span class="cc-toggle-thumb"></span></span>
              </label>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div>
                <div class="cc-font-medium cc-text-sm">Email Notifications</div>
                <div class="cc-text-xs cc-text-muted">Daily schedule summary</div>
              </div>
              <label class="cc-toggle">
                <input type="checkbox" class="cc-toggle-input" ${prefs.email !== false ? 'checked' : ''} id="profile-email-notif">
                <span class="cc-toggle-track"><span class="cc-toggle-thumb"></span></span>
              </label>
            </div>
          </div>
        </div>

        <!-- App Settings -->
        <div class="cc-card" style="margin-top:var(--cc-space-4);">
          <div class="cc-card-header">
            <div class="cc-card-title">App Settings</div>
          </div>
          <div class="cc-card-body" style="display:flex;flex-direction:column;gap:var(--cc-space-4);">
            <div class="cc-form-group">
              <label class="cc-label">Language</label>
              <select class="cc-select" id="profile-lang">
                <option value="en" ${(prefs.language || 'en') === 'en' ? 'selected' : ''}>English</option>
                <option value="es" ${prefs.language === 'es' ? 'selected' : ''}>Español</option>
                <option value="pt" ${prefs.language === 'pt' ? 'selected' : ''}>Português</option>
              </select>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div>
                <div class="cc-font-medium cc-text-sm">Dark Mode</div>
                <div class="cc-text-xs cc-text-muted">Reduce eye strain in low light</div>
              </div>
              <label class="cc-toggle">
                <input type="checkbox" class="cc-toggle-input" ${document.documentElement.getAttribute('data-theme') === 'dark' ? 'checked' : ''} id="profile-dark" onchange="TeamProfile._toggleDark(this.checked)">
                <span class="cc-toggle-track"><span class="cc-toggle-thumb"></span></span>
              </label>
            </div>
          </div>
        </div>

        <!-- Save -->
        <button class="cc-btn cc-btn-primary cc-btn-lg cc-btn-block" style="margin-top:var(--cc-space-6);" id="profile-save-btn" onclick="TeamProfile._save()">
          Save Changes
        </button>

        <!-- Divider -->
        <div style="height:1px;background:var(--cc-neutral-200);margin:var(--cc-space-6) 0;"></div>

        <!-- Logout -->
        <button class="cc-btn cc-btn-outline cc-btn-block" style="color:var(--cc-danger-500);border-color:var(--cc-danger-200);" onclick="CleanClaw.logout()">
          Log Out
        </button>

        <!-- Version -->
        <p class="cc-text-xs cc-text-muted" style="text-align:center;margin-top:var(--cc-space-4);">
          CleanClaw v1.0.0
        </p>
      </div>
    `;

    // Live preview: update avatar when name changes
    const nameInput = document.getElementById('profile-name');
    if (nameInput) {
      nameInput.addEventListener('input', () => {
        const val = nameInput.value.trim();
        const newInitial = val ? val.charAt(0).toUpperCase() : 'U';
        const avatar = document.getElementById('profile-avatar');
        const displayEl = document.getElementById('profile-display-name');
        if (avatar) avatar.textContent = newInitial;
        if (displayEl) displayEl.textContent = val || 'Team Member';
      });
    }
  },

  _toggleDark(enabled) {
    document.documentElement.setAttribute('data-theme', enabled ? 'dark' : 'light');
    localStorage.setItem('cc_theme', enabled ? 'dark' : 'light');
  },

  async _save() {
    const btn = document.getElementById('profile-save-btn');
    if (btn) {
      btn.disabled = true;
      btn.classList.add('cc-btn-loading');
      btn.textContent = 'Saving...';
    }

    const data = {
      name: document.getElementById('profile-name')?.value?.trim() || '',
      phone: document.getElementById('profile-phone')?.value?.trim() || '',
      preferences: {
        push: document.getElementById('profile-push')?.checked ?? true,
        sms: document.getElementById('profile-sms')?.checked ?? false,
        email: document.getElementById('profile-email-notif')?.checked ?? true,
        language: document.getElementById('profile-lang')?.value || 'en',
        darkMode: document.getElementById('profile-dark')?.checked ?? false,
      },
    };

    // Save to localStorage (always works)
    localStorage.setItem('cc_profile', JSON.stringify(data));

    // Update user object in memory
    if (CleanClaw._user) {
      CleanClaw._user.name = data.name;
      CleanClaw._user.nome = data.name;
    }

    // Try API save
    try {
      await CleanAPI.cleanPatch('/me', data);
    } catch {
      // API unavailable — localStorage save is sufficient
    }

    // Apply language if changed
    if (data.preferences.language && typeof I18n !== 'undefined') {
      I18n.setLocale(data.preferences.language);
    }

    if (btn) {
      btn.disabled = false;
      btn.classList.remove('cc-btn-loading');
      btn.textContent = 'Save Changes';
    }

    CleanClaw.showToast('Looking good! Your profile is up to date.', 'success');
  },
};
