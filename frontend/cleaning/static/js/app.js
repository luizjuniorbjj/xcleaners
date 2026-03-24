/**
 * CleanClaw — Main App Entry Point
 *
 * Initializes the PWA shell:
 *  1. Register service worker
 *  2. Check auth (JWT in localStorage)
 *  3. If no JWT -> show login
 *  4. If JWT -> fetch roles -> determine role -> render nav -> init router
 *  5. Initialize SSE connection
 *  6. Page transitions, toast system, skeleton loading, pull-to-refresh
 */

window.CleanClaw = {
  // State
  _user: null,
  _roles: [],
  _currentRole: null,
  _currentSlug: null,
  _currentPlan: 'basic',
  _sseConnection: null,
  _initialized: false,
  _pullToRefresh: null,

  // ----- Initialization -----

  async init() {
    console.log('[CleanClaw] Initializing...');

    // Register service worker
    this._registerSW();

    // Listen for online/offline
    window.addEventListener('online', () => this._onOnline());
    window.addEventListener('offline', () => this._onOffline());

    // Preview mode — bypass auth for UI testing (add ?preview=owner to URL)
    const urlParams = new URLSearchParams(window.location.search);
    const previewRole = urlParams.get('preview');
    if (previewRole && ['owner', 'homeowner', 'cleaner', 'team_lead', 'super_admin'].includes(previewRole)) {
      console.log(`[CleanClaw] PREVIEW MODE: ${previewRole}`);
      this._user = { id: 'preview', email: 'preview@demo.com', nome: 'Preview User', name: 'Preview User' };
      this._roles = [{ role: previewRole, business_slug: 'demo-business', plan: 'maximum' }];
      this._currentRole = previewRole;
      this._currentSlug = 'demo-business';
      this._currentPlan = 'maximum';
      CleanAPI.init(this._currentSlug);
      if (typeof I18n !== 'undefined') await I18n.init();
      this._renderShell();
      const defRoute = CleanRouter.getDefaultRoute ? CleanRouter.getDefaultRoute() : '/dashboard';
      window.CleanRouter.navigate(defRoute);
      CleanRouter.init(this._currentRole, this._currentPlan);
      document.getElementById('auth-container').style.display = 'none';
      document.getElementById('main-layout').style.display = 'flex';
      document.getElementById('loading-screen').style.display = 'none';
      CleanRouter.navigate(defRoute);
      this._initPullToRefresh();
      this._initialized = true;
      return;
    }

    // Restore demo session from localStorage (survives page refresh)
    const demoSession = localStorage.getItem('cc_demo_session');
    if (demoSession) {
      try {
        const session = JSON.parse(demoSession);
        if (session.role && session.slug) {
          console.log(`[CleanClaw] Restoring demo session: ${session.role}`);
          this._user = session.user;
          this._roles = session.roles;
          this._currentRole = session.role;
          this._currentSlug = session.slug;
          this._currentPlan = session.plan || 'maximum';
          CleanAPI.init(this._currentSlug);
          if (typeof I18n !== 'undefined') await I18n.init();
          this._renderShell();
          const savedHash = window.location.pathname;
          const defaultRoute = CleanRouter.getDefaultRoute ? CleanRouter.getDefaultRoute() : '/dashboard';
          const targetRoute = savedHash && savedHash !== '/' && savedHash !== '/login' ? savedHash : defaultRoute;
          window.CleanRouter.navigate(targetRoute);
          CleanRouter.init(this._currentRole, this._currentPlan);
          document.getElementById('auth-container').style.display = 'none';
          document.getElementById('main-layout').style.display = 'flex';
          document.getElementById('loading-screen').style.display = 'none';
          CleanRouter.navigate(targetRoute);
          this._initPullToRefresh();
          this._initialized = true;
          return;
        }
      } catch { localStorage.removeItem('cc_demo_session'); }
    }

    // Handle OAuth callback tokens in URL
    AuthUI.handleCallback();

    // Check if we have a valid token
    const token = CleanAPI.getToken();
    if (!token || CleanAPI.isTokenExpired(token)) {
      // Try refresh
      if (CleanAPI.getRefreshToken()) {
        const refreshed = await CleanAPI.refreshToken();
        if (!refreshed) {
          this._showLogin();
          return;
        }
      } else {
        this._showLogin();
        return;
      }
    }

    // Token exists and is valid - init after auth
    await this.initAfterAuth();
  },

  /**
   * Called after successful login/registration or on page load with valid token
   */
  async initAfterAuth() {
    const loadingScreen = document.getElementById('loading-screen');
    loadingScreen.style.display = 'flex';

    try {
      // Get user info
      this._user = CleanAPI.getUser();
      if (!this._user) {
        this._showLogin();
        return;
      }

      // Fetch cleaning roles
      const rolesResp = await CleanAPI.get('/api/v1/clean/my-roles');
      if (!rolesResp || !rolesResp.roles || rolesResp.roles.length === 0) {
        // User has no cleaning roles - show message or redirect to onboarding
        this._showNoRoles();
        return;
      }

      this._roles = rolesResp.roles;

      // Determine current role (saved preference or first)
      const savedRole = localStorage.getItem('cc_current_role');
      const savedSlug = localStorage.getItem('cc_slug');
      const matchedRole = this._roles.find(r =>
        r.role === savedRole && r.business_slug === savedSlug
      );
      const activeRole = matchedRole || this._roles[0];

      this._currentRole = activeRole.role;
      this._currentSlug = activeRole.business_slug;
      this._currentPlan = activeRole.plan || 'basic';

      localStorage.setItem('cc_current_role', this._currentRole);
      localStorage.setItem('cc_slug', this._currentSlug);

      // Initialize API with slug
      CleanAPI.init(this._currentSlug);

      // Initialize i18n (auto-detect browser language)
      if (typeof I18n !== 'undefined') {
        await I18n.init();
      }

      // Render the app shell (nav, etc.)
      this._renderShell();

      // Show main layout
      const authContainer = document.getElementById('auth-container');
      const mainLayout = document.getElementById('main-layout');
      authContainer.style.display = 'none';
      mainLayout.style.display = 'flex';
      loadingScreen.style.display = 'none';

      // Initialize router with role
      CleanRouter.init(this._currentRole, this._currentPlan);

      // Navigate to default if on login/register or root
      const hash = window.location.pathname;
      if (!hash || hash === '/' || hash === '/login' || hash === '/register') {
        CleanRouter.navigate(CleanRouter.getDefaultRoute());
      }

      // Initialize SSE for owner/team
      this._initSSE();

      // Initialize pull-to-refresh for mobile
      this._initPullToRefresh();

      this._initialized = true;
      console.log(`[CleanClaw] Ready. Role: ${this._currentRole}, Slug: ${this._currentSlug}, Plan: ${this._currentPlan}`);

    } catch (err) {
      console.error('[CleanClaw] Init failed:', err);
      loadingScreen.style.display = 'none';
      this._showLogin();
    }
  },

  // ----- Shell Rendering -----

  _renderShell() {
    const sidebar = document.getElementById('sidebar');
    const topNav = document.getElementById('top-nav');
    const bottomTabs = document.getElementById('bottom-tabs');
    const hamburger = document.getElementById('mobile-hamburger');
    const contentArea = document.getElementById('content-area');

    // Reset all nav elements
    sidebar.style.display = 'none';
    topNav.style.display = 'none';
    bottomTabs.style.display = 'none';
    hamburger.style.display = 'none';
    const globalSearch = document.getElementById('global-search');
    if (globalSearch) globalSearch.style.display = 'none';

    // Remove layout modifier classes
    contentArea.className = 'cc-content';

    switch (this._currentRole) {
      case 'super_admin':
        this._renderSuperAdminNav();
        break;
      case 'owner':
        this._renderOwnerNav();
        break;
      case 'homeowner':
        this._renderHomeownerNav();
        break;
      case 'team_lead':
      case 'cleaner':
        this._renderTeamNav();
        break;
    }

    // Role switcher (if multiple roles)
    const switchBtn = document.getElementById('role-switch-btn');
    if (switchBtn) {
      switchBtn.style.display = this._roles.length > 1 ? 'block' : 'none';
    }

    // User info
    this._renderUserInfo();
  },

  _renderSuperAdminNav() {
    const topNav = document.getElementById('top-nav');
    const topNavLinks = document.getElementById('top-nav-links');
    const topNavUser = document.getElementById('top-nav-user');
    const contentArea = document.getElementById('content-area');

    topNav.style.display = 'flex';
    contentArea.classList.add('cc-content--with-topnav');

    // Override brand text
    const brand = topNav.querySelector('.cc-top-nav-brand');
    if (brand) {
      brand.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 48 48" fill="none" style="margin-right:8px;">
          <circle cx="24" cy="24" r="20" stroke="var(--cc-primary-500)" stroke-width="3"/>
          <path d="M16 24l5 5 11-11" stroke="var(--cc-primary-500)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span style="font-weight:700;color:var(--cc-primary-500);">Xcleaners Admin</span>
      `;
    }

    // No nav links for super admin (single page)
    topNavLinks.innerHTML = '';

    // User / logout
    topNavUser.innerHTML = `
      <span class="cc-text-sm" style="margin-right:var(--cc-space-3);color:var(--cc-neutral-600);">${this._user?.name || 'Admin'}</span>
      <button class="cc-btn cc-btn-sm cc-btn-ghost" onclick="CleanClaw.logout()">Log Out</button>
    `;
  },

  _renderOwnerNav() {
    const sidebar = document.getElementById('sidebar');
    const hamburger = document.getElementById('mobile-hamburger');
    const sidebarNav = document.getElementById('sidebar-nav');
    const businessName = document.getElementById('sidebar-business-name');
    const contentArea = document.getElementById('content-area');

    sidebar.style.display = 'flex';
    hamburger.style.display = 'block';
    contentArea.classList.add('cc-content--with-sidebar');

    // Business name
    businessName.textContent = this._currentSlug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

    // Nav items
    const items = [
      { label: 'Dashboard', route: '/dashboard', icon: 'dashboard' },
      { label: 'Schedule', route: '/schedule', icon: 'schedule' },
      { label: 'Bookings', route: '/bookings', icon: 'list' },
      { label: 'Calendar', route: '/calendar', icon: 'calendar' },
      { label: 'Teams', route: '/teams', icon: 'teams' },
      { label: 'Clients', route: '/clients', icon: 'clients' },
      ...(this._currentPlan === 'maximum' ? [{ label: 'CRM / Leads', route: '/crm', icon: 'crm' }] : []),
      { label: 'Invoices', route: '/invoices', icon: 'invoices' },
      { label: 'Reports', route: '/reports', icon: 'reports' },
      ...(this._currentPlan !== 'basic' ? [{ label: 'AI Chat', route: '/chat', icon: 'chat' }] : []),
      { label: 'Settings', route: '/settings', icon: 'settings' },
    ];

    sidebarNav.innerHTML = items.map(item => `
      <button class="cc-nav-item" data-route="${item.route}" onclick="CleanRouter.navigate('${item.route}');CleanClaw.closeMobileMenu();">
        ${this._getIcon(item.icon)}
        <span>${item.label}</span>
      </button>
    `).join('');

    // Show global search bar for owner
    this._initGlobalSearch();
  },

  _renderHomeownerNav() {
    const topNav = document.getElementById('top-nav');
    const topNavLinks = document.getElementById('top-nav-links');
    const topNavUser = document.getElementById('top-nav-user');
    const bottomTabs = document.getElementById('bottom-tabs');
    const contentArea = document.getElementById('content-area');

    topNav.style.display = 'flex';
    bottomTabs.style.display = 'flex';
    contentArea.classList.add('cc-content--with-topnav', 'cc-content--with-bottomtabs');

    const links = [
      { label: 'My Bookings', route: '/my-bookings' },
      { label: 'My Invoices', route: '/my-invoices' },
      { label: 'My Home', route: '/preferences' },
    ];

    topNavLinks.innerHTML = links.map(l => `
      <a class="cc-top-nav-link" data-route="${l.route}" href="${l.route}">${l.label}</a>
    `).join('');

    topNavUser.innerHTML = `
      <span class="cc-top-nav-username">${this._user?.name || this._user?.nome || 'User'}</span>
      <button class="cc-btn-icon" onclick="CleanClaw.logout()" title="Log out">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
      </button>
    `;

    bottomTabs.innerHTML = links.map(l => `
      <button class="cc-tab-item" data-route="${l.route}" onclick="CleanRouter.navigate('${l.route}')">
        ${l.label === 'My Bookings' ? this._getIcon('calendar') : l.label === 'My Invoices' ? this._getIcon('invoices') : this._getIcon('home')}
        <span>${l.label.replace('My ', '')}</span>
      </button>
    `).join('');
  },

  _renderTeamNav() {
    const bottomTabs = document.getElementById('bottom-tabs');
    const contentArea = document.getElementById('content-area');

    bottomTabs.style.display = 'flex';
    contentArea.classList.add('cc-content--with-bottomtabs');

    const tabs = [
      { label: 'Today', route: '/today', icon: 'list' },
      { label: 'Schedule', route: '/my-schedule', icon: 'calendar' },
      { label: 'Earnings', route: '/earnings', icon: 'dollar' },
      { label: 'Profile', route: '/profile', icon: 'user' },
    ];

    bottomTabs.innerHTML = tabs.map(t => `
      <button class="cc-tab-item" data-route="${t.route}" onclick="CleanRouter.navigate('${t.route}')">
        ${this._getIcon(t.icon)}
        <span>${t.label}</span>
      </button>
    `).join('');
  },

  _renderUserInfo() {
    const sidebarUser = document.getElementById('sidebar-user');
    if (sidebarUser && this._user) {
      const displayName = this._user.name || this._user.nome || this._user.email;
      sidebarUser.innerHTML = `
        <div class="cc-user-avatar">${(displayName).charAt(0).toUpperCase()}</div>
        <div class="cc-user-name">${displayName}</div>
      `;
    }
  },

  // ----- Auth States -----

  _showLogin() {
    const loadingScreen = document.getElementById('loading-screen');
    loadingScreen.style.display = 'none';

    // Navigate to login hash
    if (window.location.pathname !== '/login' && window.location.pathname !== '/register' && !window.location.pathname.startsWith('#/register/invite/')) {
      window.CleanRouter.navigate('/login');
    }

    const authContainer = document.getElementById('auth-container');
    const mainLayout = document.getElementById('main-layout');
    authContainer.style.display = 'flex';
    mainLayout.style.display = 'none';

    if (window.location.pathname.startsWith('/register')) {
      const inviteToken = window.location.pathname.startsWith('#/register/invite/')
        ? window.location.pathname.split('#/register/invite/')[1]
        : null;
      AuthUI.renderRegister(authContainer, inviteToken);
    } else {
      AuthUI.renderLogin(authContainer);
    }
  },

  _showNoRoles() {
    const loadingScreen = document.getElementById('loading-screen');
    const authContainer = document.getElementById('auth-container');
    const mainLayout = document.getElementById('main-layout');

    loadingScreen.style.display = 'none';
    mainLayout.style.display = 'none';
    authContainer.style.display = 'flex';

    authContainer.innerHTML = `
      <div class="cc-auth-card">
        <div class="cc-auth-logo">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="22" stroke="#3B82F6" stroke-width="3"/>
            <path d="M16 24l5 5 11-11" stroke="#3B82F6" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <h1>Xcleaners</h1>
        </div>
        <h2 class="cc-auth-heading">No cleaning business found</h2>
        <p style="text-align:center;color:var(--cc-neutral-500);margin-bottom:24px;">
          You don't have access to any cleaning business yet.
          If you were invited, check your email for an invitation link.
        </p>
        <button class="cc-btn cc-btn-primary cc-btn-block" onclick="CleanClaw.logout()">Log Out</button>
      </div>
    `;
  },

  // ----- Logout -----

  logout() {
    CleanAPI.clearTokens();
    localStorage.removeItem('cc_demo_session');
    this._user = null;
    this._roles = [];
    this._currentRole = null;
    this._currentSlug = null;
    this._initialized = false;
    if (this._sseConnection) {
      this._sseConnection.close();
      this._sseConnection = null;
    }
    window.CleanRouter.navigate('/login');
    window.location.reload();
  },

  // ----- Mobile Menu (smooth sidebar toggle) -----

  toggleMobileMenu() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobile-overlay');
    const isOpen = sidebar.classList.contains('open');

    if (isOpen) {
      this.closeMobileMenu();
    } else {
      sidebar.classList.add('open');
      overlay.classList.add('open');
      // Animate sidebar in smoothly
      sidebar.style.transition = 'transform var(--cc-duration-slow) var(--cc-ease-out)';
    }
  },

  closeMobileMenu() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobile-overlay');
    sidebar.style.transition = 'transform var(--cc-duration-slow) var(--cc-ease-out)';
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
  },

  // ----- Role Switcher -----

  showRoleSwitcher() {
    const modal = document.getElementById('role-modal');
    const content = document.getElementById('role-modal-content');

    content.innerHTML = this._roles.map(r => `
      <label class="cc-role-option ${r.role === this._currentRole && r.business_slug === this._currentSlug ? 'active' : ''}">
        <input type="radio" name="role" value="${r.role}:${r.business_slug}"
          ${r.role === this._currentRole && r.business_slug === this._currentSlug ? 'checked' : ''}
          onchange="CleanClaw.switchRole('${r.role}', '${r.business_slug}')">
        <div>
          <strong>${r.role.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</strong>
          ${r.team_name ? ` (${r.team_name})` : ''}
          <br><small>${r.business_name || r.business_slug}</small>
        </div>
      </label>
    `).join('');

    modal.style.display = 'flex';
  },

  closeRoleSwitcher(event) {
    if (event && event.target !== event.currentTarget) return;
    document.getElementById('role-modal').style.display = 'none';
  },

  async switchRole(role, slug) {
    this._currentRole = role;
    this._currentSlug = slug;
    localStorage.setItem('cc_current_role', role);
    localStorage.setItem('cc_slug', slug);

    // Re-init
    CleanAPI.init(slug);

    // Find plan for this role
    const roleInfo = this._roles.find(r => r.role === role && r.business_slug === slug);
    this._currentPlan = roleInfo?.plan || 'basic';

    this.closeRoleSwitcher();
    this._renderShell();

    // Re-init router with new role
    CleanRouter._currentHash = null;
    CleanRouter.init(this._currentRole, this._currentPlan);
    CleanRouter.navigate(CleanRouter.getDefaultRoute());
  },

  // ----- SSE -----

  _initSSE() {
    if (this._currentRole === 'homeowner') return; // Homeowners use push, not SSE

    const token = CleanAPI.getToken();
    if (!token) return;

    let sseUrl;
    if (this._currentRole === 'owner') {
      sseUrl = `/api/v1/clean/${this._currentSlug}/schedule/stream?token=${token}`;
    } else {
      // Team member - get team_id from role info
      const roleInfo = this._roles.find(r => r.role === this._currentRole && r.business_slug === this._currentSlug);
      if (roleInfo?.team_id) {
        sseUrl = `/api/v1/clean/${this._currentSlug}/schedule/stream/team/${roleInfo.team_id}?token=${token}`;
      }
    }

    if (!sseUrl) return;

    try {
      this._sseConnection = new EventSource(sseUrl);
      this._sseConnection.onopen = () => console.log('[SSE] Connected');
      this._sseConnection.onerror = (err) => {
        console.warn('[SSE] Connection error, will retry');
      };
      this._sseConnection.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this._handleSSEEvent(data);
        } catch (e) {
          console.warn('[SSE] Parse error:', e);
        }
      };
    } catch (err) {
      console.warn('[SSE] Failed to init:', err);
    }
  },

  _handleSSEEvent(data) {
    console.log('[SSE] Event:', data.event, data);
    // Dispatch custom event for modules to listen to
    window.dispatchEvent(new CustomEvent('cleanclaw:sse', { detail: data }));
  },

  // ----- Online/Offline -----

  _onOnline() {
    const banner = document.getElementById('offline-banner');
    if (banner) banner.style.display = 'none';
    this.showToast('Back online. Your changes will sync now.', 'success');
  },

  _onOffline() {
    const banner = document.getElementById('offline-banner');
    if (banner) banner.style.display = 'block';
  },

  // ----- Service Worker -----

  _registerSW() {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/cleaning/sw.js', { scope: '/cleaning/' })
        .then(reg => console.log('[SW] Registered, scope:', reg.scope))
        .catch(err => console.warn('[SW] Registration failed:', err));
    }
  },

  // ----- Toast Notifications (design-system toast classes) -----

  showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `cc-toast cc-toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    // Animate in using design-system animation
    requestAnimationFrame(() => {
      toast.classList.add('show');
      toast.classList.add('cc-animate-slide-in-right');
    });

    // Auto-dismiss
    setTimeout(() => {
      toast.classList.remove('show');
      toast.classList.add('cc-toast-dismiss');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  },

  // ----- Skeleton Loading -----

  /**
   * Show skeleton loading placeholders in the content view.
   * Call this before loading a view module.
   */
  showContentSkeleton() {
    const contentView = document.getElementById('content-view');
    if (!contentView) return;

    contentView.innerHTML = `
      <div class="cc-animate-fade-in" style="display:flex;flex-direction:column;gap:var(--cc-space-4);padding:var(--cc-space-4);">
        <div class="cc-skeleton cc-skeleton-text" style="width:40%;height:28px;"></div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:var(--cc-space-4);">
          <div class="cc-skeleton cc-skeleton-card"></div>
          <div class="cc-skeleton cc-skeleton-card"></div>
          <div class="cc-skeleton cc-skeleton-card"></div>
          <div class="cc-skeleton cc-skeleton-card"></div>
        </div>
        <div class="cc-skeleton cc-skeleton-card" style="height:200px;"></div>
        <div class="cc-skeleton cc-skeleton-text" style="width:70%;"></div>
        <div class="cc-skeleton cc-skeleton-text" style="width:50%;"></div>
      </div>
    `;
  },

  // ----- Pull-to-Refresh (Mobile) -----

  _initPullToRefresh() {
    const contentArea = document.getElementById('content-area');
    if (!contentArea || !('ontouchstart' in window)) return;

    let startY = 0;
    let pulling = false;
    let pullIndicator = null;
    const THRESHOLD = 80;

    contentArea.addEventListener('touchstart', (e) => {
      // Only trigger if scrolled to the top
      if (contentArea.scrollTop <= 0) {
        startY = e.touches[0].clientY;
        pulling = true;
      }
    }, { passive: true });

    contentArea.addEventListener('touchmove', (e) => {
      if (!pulling) return;
      const currentY = e.touches[0].clientY;
      const distance = currentY - startY;

      if (distance > 0 && contentArea.scrollTop <= 0) {
        // Create pull indicator if not exists
        if (!pullIndicator) {
          pullIndicator = document.createElement('div');
          pullIndicator.className = 'cc-pull-refresh-indicator';
          pullIndicator.style.cssText = `
            position: fixed; top: 0; left: 50%; transform: translateX(-50%);
            z-index: var(--cc-z-toast); padding: var(--cc-space-2) var(--cc-space-4);
            background: var(--cc-primary-500); color: #fff; border-radius: 0 0 var(--cc-radius-md) var(--cc-radius-md);
            font-size: var(--cc-text-sm); font-weight: var(--cc-font-medium);
            transition: opacity var(--cc-duration-fast); opacity: 0;
          `;
          document.body.appendChild(pullIndicator);
        }

        const progress = Math.min(distance / THRESHOLD, 1);
        pullIndicator.style.opacity = progress;
        pullIndicator.textContent = distance >= THRESHOLD ? 'Release to refresh' : 'Pull to refresh...';
      }
    }, { passive: true });

    contentArea.addEventListener('touchend', (e) => {
      if (!pulling) return;
      pulling = false;

      if (pullIndicator) {
        const currentY = e.changedTouches[0].clientY;
        const distance = currentY - startY;

        if (distance >= THRESHOLD && contentArea.scrollTop <= 0) {
          pullIndicator.textContent = 'Refreshing...';
          pullIndicator.style.opacity = '1';

          // Trigger page refresh for current view
          const currentHash = window.location.pathname;
          CleanRouter._currentHash = null; // Force re-render
          CleanRouter.navigate(currentHash);

          setTimeout(() => {
            if (pullIndicator) {
              pullIndicator.style.opacity = '0';
              setTimeout(() => {
                if (pullIndicator && pullIndicator.parentNode) {
                  pullIndicator.parentNode.removeChild(pullIndicator);
                }
                pullIndicator = null;
              }, 200);
            }
          }, 800);
        } else {
          pullIndicator.style.opacity = '0';
          setTimeout(() => {
            if (pullIndicator && pullIndicator.parentNode) {
              pullIndicator.parentNode.removeChild(pullIndicator);
            }
            pullIndicator = null;
          }, 200);
        }
      }
    }, { passive: true });
  },

  // ----- Global Search -----

  _searchDebounceTimer: null,

  _initGlobalSearch() {
    const el = document.getElementById('global-search');
    const input = document.getElementById('global-search-input');
    if (!el || !input) return;

    el.style.display = 'block';

    // Remove old listeners by cloning
    const newInput = input.cloneNode(true);
    input.parentNode.replaceChild(newInput, input);

    newInput.addEventListener('input', () => {
      clearTimeout(this._searchDebounceTimer);
      this._searchDebounceTimer = setTimeout(() => {
        this._onGlobalSearch(newInput.value.trim());
      }, 300);
    });

    newInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this._closeSearchResults();
        newInput.blur();
      }
    });

    // Click outside to close
    document.addEventListener('click', (e) => {
      const searchEl = document.getElementById('global-search');
      if (searchEl && !searchEl.contains(e.target)) {
        this._closeSearchResults();
      }
    });
  },

  _onGlobalSearch(query) {
    const resultsEl = document.getElementById('global-search-results');
    if (!resultsEl) return;

    if (!query || query.length < 2) {
      this._closeSearchResults();
      return;
    }

    const q = query.toLowerCase();
    const grouped = { client: [], team: [], booking: [], service: [] };

    if (typeof DemoData !== 'undefined') {
      // Search clients
      DemoData._clients.filter(c =>
        `${c.first_name} ${c.last_name} ${c.email} ${c.phone} ${c.address}`.toLowerCase().includes(q)
      ).slice(0, 5).forEach(c => grouped.client.push({
        name: `${c.first_name} ${c.last_name}`,
        sub: c.email,
        route: `#/owner/clients/${c.id}`
      }));

      // Search teams
      DemoData._teams.filter(t =>
        `${t.name} ${t.members.map(m => m.name).join(' ')}`.toLowerCase().includes(q)
      ).slice(0, 3).forEach(t => grouped.team.push({
        name: t.name,
        sub: `${t.member_count || t.members.length} members`,
        route: '/teams'
      }));

      // Search bookings
      const bookings = DemoData.getBookings ? DemoData.getBookings() : [];
      bookings.filter(b =>
        `${b.client_name} ${b.team_name} ${b.service} ${b.address} ${b.scheduled_date}`.toLowerCase().includes(q)
      ).slice(0, 5).forEach(b => grouped.booking.push({
        name: `${b.client_name} — ${b.service}`,
        sub: `${b.scheduled_date} ${b.scheduled_start} (${b.team_name})`,
        route: '/schedule'
      }));

      // Search services
      DemoData._services.filter(s =>
        `${s.name} ${s.slug} ${s.category}`.toLowerCase().includes(q)
      ).slice(0, 3).forEach(s => grouped.service.push({
        name: s.name,
        sub: `$${s.base_price} — ${s.category}`,
        route: '/settings'
      }));
    }

    const totalResults = Object.values(grouped).reduce((sum, arr) => sum + arr.length, 0);

    if (totalResults === 0) {
      resultsEl.innerHTML = '<div class="cc-search-no-results">No results found</div>';
      resultsEl.classList.add('open');
      return;
    }

    const typeIcons = {
      client: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
      team: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
      booking: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
      service: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    };

    const categoryLabels = { client: 'Clients', team: 'Teams', booking: 'Bookings', service: 'Services' };

    let html = '';
    for (const [type, items] of Object.entries(grouped)) {
      if (items.length === 0) continue;
      html += `<div class="cc-search-results-category">${categoryLabels[type]}</div>`;
      for (const item of items) {
        html += `
          <a class="cc-search-result-item" href="${item.route}" onclick="CleanClaw._closeSearchResults();CleanRouter.navigate('${item.route}');return false;">
            <div class="cc-search-result-icon ${type}">${typeIcons[type]}</div>
            <div class="cc-search-result-info">
              <div class="cc-search-result-name">${this._escHtml(item.name)}</div>
              <div class="cc-search-result-sub">${this._escHtml(item.sub)}</div>
            </div>
            <span class="cc-search-result-badge ${type}">${type}</span>
          </a>`;
      }
    }

    resultsEl.innerHTML = html;
    resultsEl.classList.add('open');
  },

  _closeSearchResults() {
    const resultsEl = document.getElementById('global-search-results');
    if (resultsEl) resultsEl.classList.remove('open');
  },

  _escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },

  // ----- Icon Helper -----

  _getIcon(name) {
    const icons = {
      dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>',
      schedule: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><rect x="6" y="13" width="4" height="4"/></svg>',
      calendar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
      teams: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
      clients: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
      crm: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
      invoices: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
      chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
      settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
      list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
      dollar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
      user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
      home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
      reports: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20"><path d="M21 21H3V3"/><path d="M18 9l-5 5-2-2-4 4"/></svg>',
    };
    return icons[name] || '';
  },
};

// ----- Boot -----
document.addEventListener('DOMContentLoaded', () => CleanClaw.init());
