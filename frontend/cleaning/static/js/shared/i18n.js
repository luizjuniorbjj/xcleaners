/**
 * CleanClaw — i18n Module
 *
 * Internationalization for EN/ES/PT.
 * All UI strings use t('key') pattern.
 *
 * Usage:
 *   await I18n.init();             // auto-detect browser language
 *   I18n.setLocale('es');          // switch to Spanish
 *   I18n.t('dashboard.revenue');   // translate key
 *   I18n.t('settings.save');       // translate key
 */

window.I18n = {
  _locale: 'en',
  _strings: {},
  _loaded: {},
  _supported: ['en', 'es', 'pt'],
  _fallback: 'en',

  /**
   * Initialize i18n — detect browser locale and load strings
   */
  async init() {
    const saved = localStorage.getItem('cc_locale');
    const detected = saved || this.detectLocale();
    await this.setLocale(detected);
  },

  /**
   * Detect browser language, map to supported locale
   */
  detectLocale() {
    const browserLang = (navigator.language || navigator.userLanguage || 'en').toLowerCase();
    // Check exact match first
    if (this._supported.includes(browserLang)) return browserLang;
    // Check prefix (e.g., 'pt-BR' -> 'pt')
    const prefix = browserLang.split('-')[0];
    if (this._supported.includes(prefix)) return prefix;
    return this._fallback;
  },

  /**
   * Set locale and load strings
   */
  async setLocale(locale) {
    if (!this._supported.includes(locale)) {
      console.warn(`[i18n] Unsupported locale: ${locale}, falling back to ${this._fallback}`);
      locale = this._fallback;
    }

    // Load if not cached
    if (!this._loaded[locale]) {
      try {
        const resp = await fetch(`/cleaning/static/i18n/${locale}.json?v=1`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        this._loaded[locale] = await resp.json();
      } catch (err) {
        console.error(`[i18n] Failed to load ${locale}.json:`, err);
        // Fallback to English if available
        if (locale !== this._fallback && this._loaded[this._fallback]) {
          this._loaded[locale] = this._loaded[this._fallback];
        } else {
          this._loaded[locale] = {};
        }
      }
    }

    // Also ensure fallback is loaded
    if (!this._loaded[this._fallback] && locale !== this._fallback) {
      try {
        const resp = await fetch(`/cleaning/static/i18n/${this._fallback}.json?v=1`);
        if (resp.ok) {
          this._loaded[this._fallback] = await resp.json();
        }
      } catch { /* ignore */ }
    }

    this._locale = locale;
    this._strings = this._loaded[locale] || {};
    localStorage.setItem('cc_locale', locale);

    // Dispatch event for UI re-render
    window.dispatchEvent(new CustomEvent('cleanclaw:locale-changed', {
      detail: { locale }
    }));
  },

  /**
   * Get current locale
   */
  getLocale() {
    return this._locale;
  },

  /**
   * Translate a key. Supports dot notation: t('dashboard.revenue')
   * Returns the key itself if not found (graceful fallback).
   *
   * @param {string} key - Dot-separated key path
   * @param {object} vars - Optional interpolation variables: t('greeting', {name: 'James'})
   */
  t(key, vars) {
    let value = this._resolve(this._strings, key);

    // Fallback to English
    if (value === undefined && this._locale !== this._fallback) {
      value = this._resolve(this._loaded[this._fallback] || {}, key);
    }

    // Last fallback: return the key
    if (value === undefined) return key;

    // Interpolation: replace {varName} with vars.varName
    if (vars && typeof value === 'string') {
      for (const [k, v] of Object.entries(vars)) {
        value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
      }
    }

    return value;
  },

  /**
   * Resolve dot-notation key in an object
   */
  _resolve(obj, key) {
    return key.split('.').reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), obj);
  },
};
