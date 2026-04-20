/**
 * Xcleaners Auth UI
 *
 * Renders login and register screens.
 * Handles Google OAuth flow and email/password auth.
 */

window.AuthUI = {
  /**
   * Render login screen into the auth container
   */
  renderLogin(container) {
    container.innerHTML = `
      <div class="cc-auth-backdrop">
        <div class="cc-card cc-auth-card" style="max-width:420px;width:100%;margin:auto;padding:var(--cc-space-6);">
          <!-- Brand -->
          <div style="text-align:center;margin-bottom:var(--cc-space-5);">
            <img src="/cleaning/static/img/logo.png" alt="Xcleaners" style="width:200px;max-width:65vw;margin-bottom:var(--cc-space-3);display:block;margin-left:auto;margin-right:auto;">
            <p class="cc-text-sm cc-text-muted">Smart Cleaning Management</p>
            <div style="display:flex;align-items:center;justify-content:center;gap:var(--cc-space-2);margin-top:var(--cc-space-2);">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cc-neutral-400)" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
              <span style="font-size:11px;color:var(--cc-neutral-400);">256-bit encrypted &middot; Trusted by 50+ cleaning businesses</span>
            </div>
          </div>

          <!-- Error -->
          <div class="cc-auth-error" id="auth-error" style="display:none;padding:var(--cc-space-3);border-radius:var(--cc-radius-md);background:var(--cc-danger-50);color:var(--cc-danger-600);font-size:var(--cc-text-sm);margin-bottom:var(--cc-space-4);border:1px solid var(--cc-danger-200);"></div>

          <!-- Login Form -->
          <form onsubmit="return AuthUI.handleLogin(event)">
            <div class="cc-form-group">
              <label class="cc-label" for="login-email">Email</label>
              <div style="position:relative;">
                <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--cc-neutral-400);pointer-events:none;">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 7L2 7"/></svg>
                </span>
                <input type="email" id="login-email" class="cc-input" placeholder="you@email.com" required autocomplete="email" style="padding-left:36px;">
              </div>
            </div>

            <div class="cc-form-group">
              <div style="display:flex;align-items:center;justify-content:space-between;">
                <label class="cc-label" for="login-password" style="margin-bottom:0;">Password</label>
                <a href="#" class="cc-text-xs" style="color:var(--cc-primary-500);" onclick="AuthUI.showForgotPassword(event)">Forgot password?</a>
              </div>
              <div style="position:relative;margin-top:var(--cc-space-1);">
                <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--cc-neutral-400);pointer-events:none;">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                </span>
                <input type="password" id="login-password" class="cc-input" placeholder="Enter your password" required autocomplete="current-password" style="padding-left:36px;padding-right:42px;">
                <button type="button" class="cc-auth-toggle-pwd" onclick="AuthUI._togglePasswordVisibility('login-password', this)" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);background:none;border:none;padding:4px 6px;cursor:pointer;color:var(--cc-neutral-400);display:flex;align-items:center;" title="Show password">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                </button>
              </div>
            </div>

            <button type="submit" class="cc-btn cc-btn-primary cc-btn-lg cc-btn-block" id="login-submit-btn" style="margin-top:var(--cc-space-2);">
              Sign In
            </button>
          </form>

          <!-- Divider -->
          <div style="display:flex;align-items:center;gap:var(--cc-space-3);margin:var(--cc-space-6) 0;">
            <div style="flex:1;height:1px;background:var(--cc-neutral-200);"></div>
            <span class="cc-text-xs cc-text-muted" style="white-space:nowrap;">or continue with</span>
            <div style="flex:1;height:1px;background:var(--cc-neutral-200);"></div>
          </div>

          <!-- Google OAuth -->
          <button class="cc-btn cc-btn-outline cc-btn-lg cc-btn-block" onclick="AuthUI.loginWithGoogle()" style="border-color:var(--cc-neutral-300);color:var(--cc-neutral-700);">
            <svg width="18" height="18" viewBox="0 0 18 18"><path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/><path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/><path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/></svg>
            Sign in with Google
          </button>

          <!-- Footer -->
          <p style="text-align:center;margin-top:var(--cc-space-6);font-size:var(--cc-text-sm);color:var(--cc-neutral-500);">
            Don't have an account? <a href="/register" style="color:var(--cc-primary-500);font-weight:var(--cc-font-medium);">Sign up</a>
          </p>
          <p style="text-align:center;margin-top:var(--cc-space-2);font-size:var(--cc-text-xs);color:var(--cc-neutral-400);">
            Are you a homeowner? <a href="#/register?role=homeowner" style="color:var(--cc-primary-500);">Sign up here</a>
          </p>
        </div>
      </div>
    `;
  },

  /**
   * Render register screen
   */
  renderRegister(container, inviteToken) {
    const isInvite = !!inviteToken;
    // Check if role=homeowner is in the URL query or hash params
    const hashParams = new URLSearchParams((window.location.pathname.split('?')[1]) || '');
    const isHomeownerPreset = hashParams.get('role') === 'homeowner';

    container.innerHTML = `
      <div class="cc-auth-backdrop">
        <div class="cc-card cc-auth-card" style="max-width:420px;width:100%;margin:auto;padding:var(--cc-space-6);">
          <!-- Brand -->
          <div style="text-align:center;margin-bottom:var(--cc-space-6);">
            <img src="/cleaning/static/img/logo.png" alt="Xcleaners" style="width:200px;max-width:65vw;margin-bottom:var(--cc-space-3);display:block;margin-left:auto;margin-right:auto;">
          </div>

          ${isInvite ? `
            <div id="invite-banner" style="background:var(--cc-primary-50);border:1px solid var(--cc-primary-200);border-radius:var(--cc-radius-lg);padding:var(--cc-space-4);text-align:center;margin-bottom:var(--cc-space-5);">
              <p class="cc-text-sm cc-text-muted" style="margin-bottom:var(--cc-space-1);">You've been invited to join</p>
              <h3 class="cc-text-lg cc-font-semibold" id="invite-business-name" style="color:var(--cc-primary-700);">Loading...</h3>
              <p class="cc-text-sm" id="invite-role-text" style="color:var(--cc-primary-600);margin-top:var(--cc-space-1);"></p>
            </div>
          ` : `
            <h3 style="text-align:center;margin-bottom:var(--cc-space-5);color:var(--cc-neutral-800);">Create your account</h3>
          `}

          <!-- Error -->
          <div class="cc-auth-error" id="auth-error" style="display:none;padding:var(--cc-space-3);border-radius:var(--cc-radius-md);background:var(--cc-danger-50);color:var(--cc-danger-600);font-size:var(--cc-text-sm);margin-bottom:var(--cc-space-4);border:1px solid var(--cc-danger-200);"></div>

          <!-- Google OAuth -->
          <button class="cc-btn cc-btn-outline cc-btn-lg cc-btn-block" onclick="AuthUI.registerWithGoogle('${inviteToken || ''}')" style="border-color:var(--cc-neutral-300);color:var(--cc-neutral-700);margin-bottom:var(--cc-space-4);">
            <svg width="18" height="18" viewBox="0 0 18 18"><path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/><path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/><path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/></svg>
            ${isInvite ? 'Accept with Google' : 'Sign up with Google'}
          </button>

          <!-- Divider -->
          <div style="display:flex;align-items:center;gap:var(--cc-space-3);margin-bottom:var(--cc-space-4);">
            <div style="flex:1;height:1px;background:var(--cc-neutral-200);"></div>
            <span class="cc-text-xs cc-text-muted" style="white-space:nowrap;">${isInvite ? 'or create an account' : 'or register with email'}</span>
            <div style="flex:1;height:1px;background:var(--cc-neutral-200);"></div>
          </div>

          <!-- Register Form -->
          <form onsubmit="return AuthUI.handleRegister(event, '${inviteToken || ''}')">
            <div class="cc-form-group">
              <label class="cc-label" for="reg-name">Full Name</label>
              <div style="position:relative;">
                <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--cc-neutral-400);pointer-events:none;">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                </span>
                <input type="text" id="reg-name" class="cc-input" placeholder="Your full name" required autocomplete="name" style="padding-left:36px;">
              </div>
            </div>

            <div class="cc-form-group">
              <label class="cc-label" for="reg-email">Email</label>
              <div style="position:relative;">
                <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--cc-neutral-400);pointer-events:none;">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 7L2 7"/></svg>
                </span>
                <input type="email" id="reg-email" class="cc-input" placeholder="you@email.com" required autocomplete="email" style="padding-left:36px;">
              </div>
            </div>

            <div class="cc-form-group">
              <label class="cc-label" for="reg-password">Password</label>
              <div style="position:relative;">
                <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--cc-neutral-400);pointer-events:none;">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                </span>
                <input type="password" id="reg-password" class="cc-input" placeholder="Create a password" required minlength="8" autocomplete="new-password" style="padding-left:36px;padding-right:42px;">
                <button type="button" class="cc-auth-toggle-pwd" onclick="AuthUI._togglePasswordVisibility('reg-password', this)" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);background:none;border:none;padding:4px 6px;cursor:pointer;color:var(--cc-neutral-400);display:flex;align-items:center;" title="Show password">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                </button>
              </div>
              <!-- Password strength bar -->
              <div style="margin-top:var(--cc-space-2);">
                <div id="pwd-strength-bar" style="height:4px;border-radius:var(--cc-radius-full);background:var(--cc-neutral-200);overflow:hidden;">
                  <div id="pwd-strength-fill" style="height:100%;width:0%;border-radius:var(--cc-radius-full);transition:width 0.3s ease, background 0.3s ease;"></div>
                </div>
                <div style="display:flex;gap:var(--cc-space-3);margin-top:var(--cc-space-2);flex-wrap:wrap;">
                  <span id="req-length" class="cc-text-xs" style="color:var(--cc-neutral-400);display:flex;align-items:center;gap:4px;">
                    <span class="cc-pwd-check-icon" style="display:inline-flex;width:14px;height:14px;border-radius:50%;border:1.5px solid var(--cc-neutral-300);align-items:center;justify-content:center;flex-shrink:0;transition:all 0.2s ease;"></span>
                    8+ chars
                  </span>
                  <span id="req-upper" class="cc-text-xs" style="color:var(--cc-neutral-400);display:flex;align-items:center;gap:4px;">
                    <span class="cc-pwd-check-icon" style="display:inline-flex;width:14px;height:14px;border-radius:50%;border:1.5px solid var(--cc-neutral-300);align-items:center;justify-content:center;flex-shrink:0;transition:all 0.2s ease;"></span>
                    1 uppercase
                  </span>
                  <span id="req-number" class="cc-text-xs" style="color:var(--cc-neutral-400);display:flex;align-items:center;gap:4px;">
                    <span class="cc-pwd-check-icon" style="display:inline-flex;width:14px;height:14px;border-radius:50%;border:1.5px solid var(--cc-neutral-300);align-items:center;justify-content:center;flex-shrink:0;transition:all 0.2s ease;"></span>
                    1 number
                  </span>
                </div>
              </div>
            </div>

            <div class="cc-form-group">
              <label class="cc-label" for="reg-confirm">Confirm Password</label>
              <div style="position:relative;">
                <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--cc-neutral-400);pointer-events:none;">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                </span>
                <input type="password" id="reg-confirm" class="cc-input" placeholder="Confirm your password" required autocomplete="new-password" style="padding-left:36px;">
              </div>
            </div>

            <!-- Homeowner registration option -->
            ${!isInvite ? `
            <div style="margin-bottom:var(--cc-space-4);padding:var(--cc-space-3);border-radius:var(--cc-radius-md);border:1px solid var(--cc-neutral-200);background:var(--cc-neutral-50);">
              <label class="cc-checkbox" style="font-size:var(--cc-text-sm);color:var(--cc-neutral-700);">
                <input type="checkbox" class="cc-checkbox-input" id="reg-homeowner" ${isHomeownerPreset ? 'checked' : ''} onchange="AuthUI._toggleHomeownerFields()">
                <span style="font-weight:var(--cc-font-medium);">I'm a homeowner looking for cleaning services</span>
              </label>
              <div id="reg-homeowner-fields" style="margin-top:var(--cc-space-3);display:${isHomeownerPreset ? 'block' : 'none'};">
                <div class="cc-form-group" style="margin-bottom:0;">
                  <label class="cc-label cc-label-required" for="reg-business-code">Business Code</label>
                  <input type="text" id="reg-business-code" class="cc-input" placeholder="e.g. clean-new-orleans" style="font-size:var(--cc-text-sm);">
                  <p class="cc-text-xs cc-text-muted" style="margin-top:var(--cc-space-1);">Ask your cleaning company for their business code.</p>
                </div>
              </div>
            </div>
            ` : ''}

            <!-- Terms checkbox -->
            <div style="margin-bottom:var(--cc-space-4);">
              <label class="cc-checkbox" style="font-size:var(--cc-text-sm);color:var(--cc-neutral-600);">
                <input type="checkbox" class="cc-checkbox-input" id="reg-terms" required>
                <span>I agree to the <a href="#" style="color:var(--cc-primary-500);">Terms of Service</a> and <a href="#" style="color:var(--cc-primary-500);">Privacy Policy</a></span>
              </label>
            </div>

            <button type="submit" class="cc-btn cc-btn-primary cc-btn-lg cc-btn-block" id="reg-submit-btn">
              ${isInvite ? 'Accept Invitation' : 'Create Account'}
            </button>
          </form>

          <!-- Footer -->
          <p style="text-align:center;margin-top:var(--cc-space-6);font-size:var(--cc-text-sm);color:var(--cc-neutral-500);">
            Already have an account? <a href="/login" style="color:var(--cc-primary-500);font-weight:var(--cc-font-medium);">Sign in</a>
          </p>
        </div>
      </div>
    `;

    // Password requirement live validation
    const pwdInput = document.getElementById('reg-password');
    if (pwdInput) {
      pwdInput.addEventListener('input', () => this._validatePassword(pwdInput.value));
    }

    // If invite, validate token and show details
    if (isInvite) {
      this._validateInvite(inviteToken);
    }
  },

  /**
   * Handle email/password login
   */
  // SECURITY FIX C-1: Demo credentials removed from client-side JS (2026-04-09)

  async handleLogin(event) {
    event.preventDefault();
    const email = document.getElementById('login-email').value.trim().toLowerCase();
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('auth-error');
    const submitBtn = document.getElementById('login-submit-btn');

    errorEl.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.classList.add('cc-btn-loading');
    submitBtn.textContent = 'Signing in...';

    // Login via API
    try {
      const resp = await fetch(`${window.location.origin}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || 'Invalid email or password.');
      }

      const data = await resp.json();
      CleanAPI.setTokens(data.access_token, data.refresh_token);

      // Initialize app after login
      await Xcleaners.initAfterAuth();
    } catch (err) {
      errorEl.textContent = err.message || 'Login failed. Please try again.';
      errorEl.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove('cc-btn-loading');
      submitBtn.textContent = 'Sign In';
    }
    return false;
  },

  /**
   * Handle registration
   */
  async handleRegister(event, inviteToken) {
    event.preventDefault();
    const name = document.getElementById('reg-name').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value;
    const confirm = document.getElementById('reg-confirm').value;
    const errorEl = document.getElementById('auth-error');
    const submitBtn = document.getElementById('reg-submit-btn');

    errorEl.style.display = 'none';

    // Validate password match
    if (password !== confirm) {
      errorEl.textContent = 'Passwords do not match.';
      errorEl.style.display = 'block';
      return false;
    }

    // Validate password strength
    if (password.length < 8 || !/[A-Z]/.test(password) || !/[0-9]/.test(password)) {
      errorEl.textContent = 'Password must be at least 8 characters with 1 uppercase and 1 number.';
      errorEl.style.display = 'block';
      return false;
    }

    // Check homeowner option
    const homeownerCheckbox = document.getElementById('reg-homeowner');
    const isHomeowner = homeownerCheckbox && homeownerCheckbox.checked;
    const businessCode = isHomeowner ? (document.getElementById('reg-business-code')?.value?.trim() || '') : '';

    if (isHomeowner && !businessCode) {
      errorEl.textContent = 'Please enter the business code provided by your cleaning company.';
      errorEl.style.display = 'block';
      return false;
    }

    // Terms of Service must be accepted (backend enforces)
    const termsCheckbox = document.getElementById('reg-terms');
    const acceptedTerms = termsCheckbox && termsCheckbox.checked;
    if (!acceptedTerms) {
      errorEl.textContent = 'You must accept the Terms of Service and Privacy Policy to continue.';
      errorEl.style.display = 'block';
      return false;
    }

    submitBtn.disabled = true;
    submitBtn.classList.add('cc-btn-loading');
    submitBtn.textContent = 'Creating account...';

    // Invite flow: homeowner self-register from email link. Uses a dedicated
    // public endpoint that validates the UUID token, creates/links the user,
    // and returns tokens. No demo fallback — errors here must surface so the
    // client knows what went wrong instead of silently landing on a fake demo.
    if (inviteToken) {
      try {
        const resp = await fetch(`${window.location.origin}/api/v1/clean/accept-client-invite`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            invite_token: inviteToken,
            nome: name,
            password,
            accepted_terms: true,
          }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          throw new Error(data.detail || 'Invitation could not be accepted.');
        }
        const data = await resp.json();
        CleanAPI.setTokens(data.access_token, data.refresh_token);
        await Xcleaners.initAfterAuth();
      } catch (err) {
        errorEl.textContent = err.message || 'Invitation could not be accepted.';
        errorEl.style.display = 'block';
      } finally {
        submitBtn.disabled = false;
        submitBtn.classList.remove('cc-btn-loading');
        submitBtn.textContent = 'Accept Invitation';
      }
      return false;
    }

    // Demo mode: if any email/password passes basic validation, log in as demo
    const isDemoMode = typeof Xcleaners !== 'undefined' && (Xcleaners._demoMode || (Xcleaners._user && Xcleaners._user.id && Xcleaners._user.id.startsWith('demo-')));
    // Also detect demo mode if the demo accounts exist and no real backend
    const canTryDemo = typeof DemoData !== 'undefined';

    if (canTryDemo) {
      try {
        // Try real registration first, fall back to demo on network error
        const testResp = await fetch(`${window.location.origin}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ nome: name, email, password, accepted_terms: true }),
        });
        if (testResp.ok) {
          const data = await testResp.json();
          CleanAPI.setTokens(data.access_token, data.refresh_token);
          if (inviteToken) {
            try { await CleanAPI.post('/api/v1/clean/accept-invite', { token: inviteToken }); } catch { /* ignore */ }
          }
          await Xcleaners.initAfterAuth();
          return false;
        }
        // If 4xx error (not network), fall through to demo
        if (testResp.status >= 500) throw new Error('Server error');
      } catch {
        // Network error or server down -- proceed with demo login
      }

      // Demo registration: log in as homeowner or owner
      const demoRole = isHomeowner ? 'homeowner' : 'owner';
      const demoSlug = isHomeowner && businessCode ? businessCode : 'clean-new-orleans';
      console.log(`[Xcleaners] Demo register: ${demoRole} (${name}) for ${demoSlug}`);
      Xcleaners._user = { id: 'demo-' + demoRole, email: email, nome: name, name: name };
      Xcleaners._roles = [{ role: demoRole, business_slug: demoSlug, plan: 'maximum', business_name: demoSlug.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) }];
      Xcleaners._currentRole = demoRole;
      Xcleaners._currentSlug = demoSlug;
      Xcleaners._currentPlan = 'maximum';
      CleanAPI.init(Xcleaners._currentSlug);
      localStorage.setItem('cc_current_role', demoRole);
      localStorage.setItem('cc_slug', demoSlug);
      localStorage.setItem('cc_demo_session', JSON.stringify({
        user: Xcleaners._user,
        roles: Xcleaners._roles,
        role: demoRole,
        slug: demoSlug,
        plan: 'maximum',
      }));
      if (typeof I18n !== 'undefined') await I18n.init();
      Xcleaners._renderShell();
      const defaultRoute = demoRole === 'owner' ? '/dashboard'
        : demoRole === 'homeowner' ? '/my-bookings'
        : '/today';
      window.location.pathname = defaultRoute;
      CleanRouter.init(demoRole, 'maximum');
      document.getElementById('auth-container').style.display = 'none';
      document.getElementById('main-layout').style.display = 'flex';
      document.getElementById('loading-screen').style.display = 'none';
      CleanRouter.navigate(defaultRoute);
      Xcleaners._initPullToRefresh();
      Xcleaners._initialized = true;
      submitBtn.disabled = false;
      submitBtn.classList.remove('cc-btn-loading');
      submitBtn.textContent = inviteToken ? 'Accept Invitation' : 'Create Account';
      return false;
    }

    try {
      // Register via API (non-demo mode)
      const regBody = { nome: name, email, password, accepted_terms: true };
      if (isHomeowner) {
        regBody.role = 'homeowner';
        regBody.business_code = businessCode;
      }
      const resp = await fetch(`${window.location.origin}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(regBody),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || 'Registration failed.');
      }

      const data = await resp.json();
      CleanAPI.setTokens(data.access_token, data.refresh_token);

      // If invite token, accept it
      if (inviteToken) {
        try {
          await CleanAPI.post('/api/v1/clean/accept-invite', { token: inviteToken });
        } catch (err) {
          console.warn('Invite acceptance failed:', err);
        }
      }

      await Xcleaners.initAfterAuth();
    } catch (err) {
      errorEl.textContent = err.message || 'Registration failed. Please try again.';
      errorEl.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove('cc-btn-loading');
      submitBtn.textContent = inviteToken ? 'Accept Invitation' : 'Create Account';
    }
    return false;
  },

  /**
   * Google OAuth login
   */
  loginWithGoogle() {
    const redirectUri = encodeURIComponent(window.location.origin + '/dashboard');
    window.location.href = `${window.location.origin}/auth/google?redirect_uri=${redirectUri}`;
  },

  /**
   * Google OAuth register (with optional invite)
   */
  registerWithGoogle(inviteToken) {
    let redirectUri = window.location.origin + '/dashboard';
    if (inviteToken) {
      redirectUri += `?invite=${inviteToken}`;
    }
    window.location.href = `${window.location.origin}/auth/google?redirect_uri=${encodeURIComponent(redirectUri)}`;
  },

  /**
   * Show forgot password inline
   */
  showForgotPassword(event) {
    event.preventDefault();
    const errorEl = document.getElementById('auth-error');
    errorEl.textContent = 'Password reset is not yet implemented. Contact support.';
    errorEl.style.display = 'block';
    errorEl.style.background = 'var(--cc-info-50)';
    errorEl.style.color = 'var(--cc-info-600)';
    errorEl.style.borderColor = 'var(--cc-info-200)';
  },

  /**
   * Toggle password visibility
   */
  _togglePasswordVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const isPassword = input.type === 'password';
    input.type = isPassword ? 'text' : 'password';
    // Swap eye icon
    btn.innerHTML = isPassword
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  },

  /**
   * Toggle homeowner registration fields visibility
   */
  _toggleHomeownerFields() {
    const checkbox = document.getElementById('reg-homeowner');
    const fields = document.getElementById('reg-homeowner-fields');
    if (fields) {
      fields.style.display = checkbox && checkbox.checked ? 'block' : 'none';
    }
  },

  /**
   * Validate invite token
   */
  async _validateInvite(token) {
    try {
      // Decode invite token (JWT) to show business name and role
      const payload = CleanAPI.decodeToken(token);
      if (payload) {
        const banner = document.getElementById('invite-banner');
        const nameEl = document.getElementById('invite-business-name');
        const roleEl = document.getElementById('invite-role-text');
        if (nameEl) nameEl.textContent = payload.business_name || 'a cleaning business';
        if (roleEl) roleEl.textContent = `as a ${payload.role || 'team member'}`;

        // Pre-fill email if in token
        if (payload.email) {
          const emailInput = document.getElementById('reg-email');
          if (emailInput) {
            emailInput.value = payload.email;
            emailInput.readOnly = true;
          }
        }
      }
    } catch (err) {
      const errorEl = document.getElementById('auth-error');
      errorEl.textContent = 'This invitation may have expired. Contact your cleaning company.';
      errorEl.style.display = 'block';
    }
  },

  /**
   * Live password validation with strength bar
   */
  _validatePassword(value) {
    const lengthEl = document.getElementById('req-length');
    const upperEl = document.getElementById('req-upper');
    const numberEl = document.getElementById('req-number');
    const fillEl = document.getElementById('pwd-strength-fill');

    const hasLength = value.length >= 8;
    const hasUpper = /[A-Z]/.test(value);
    const hasNumber = /[0-9]/.test(value);

    // Update requirement indicators
    this._updateReqIndicator(lengthEl, hasLength);
    this._updateReqIndicator(upperEl, hasUpper);
    this._updateReqIndicator(numberEl, hasNumber);

    // Update strength bar
    if (fillEl) {
      const score = (hasLength ? 1 : 0) + (hasUpper ? 1 : 0) + (hasNumber ? 1 : 0);
      const pct = value.length === 0 ? 0 : Math.round((score / 3) * 100);
      fillEl.style.width = pct + '%';
      if (score === 0 || value.length === 0) {
        fillEl.style.background = 'var(--cc-neutral-300)';
      } else if (score === 1) {
        fillEl.style.background = 'var(--cc-danger-500)';
      } else if (score === 2) {
        fillEl.style.background = 'var(--cc-warning-500)';
      } else {
        fillEl.style.background = 'var(--cc-success-500)';
      }
    }
  },

  /**
   * Update a single requirement indicator (checkmark or circle)
   */
  _updateReqIndicator(el, met) {
    if (!el) return;
    const icon = el.querySelector('.cc-pwd-check-icon');
    if (met) {
      el.style.color = 'var(--cc-success-600)';
      if (icon) {
        icon.style.background = 'var(--cc-success-500)';
        icon.style.borderColor = 'var(--cc-success-500)';
        icon.innerHTML = '<svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
      }
    } else {
      el.style.color = 'var(--cc-neutral-400)';
      if (icon) {
        icon.style.background = 'transparent';
        icon.style.borderColor = 'var(--cc-neutral-300)';
        icon.innerHTML = '';
      }
    }
  },

  /**
   * Handle OAuth callback (tokens in URL params)
   */
  handleCallback() {
    const params = new URLSearchParams(window.location.search);
    const access = params.get('access_token');
    const refresh = params.get('refresh_token');
    if (access) {
      console.log('[AuthUI] OAuth callback detected — storing tokens');
      CleanAPI.setTokens(access, refresh);
      // Clean URL: remove query params, keep pathname only
      window.history.replaceState({}, '', window.location.pathname);
      return true;
    }
    return false;
  },
};
