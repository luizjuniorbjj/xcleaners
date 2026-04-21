/**
 * Xcleaners Router - History API with clean URLs
 */
window.CleanRouter = {
  _routes: {
    '/login':            { module: null, roles: ['*'], title: 'Sign In' },
    '/register':         { module: null, roles: ['*'], title: 'Register' },
    '/register/invite':  { module: null, roles: ['*'], title: 'Accept Invitation' },
    '/dashboard':        { module: 'owner/dashboard.js', roles: ['owner'], title: 'Dashboard' },
    '/schedule':         { module: 'owner/schedule-builder.js', roles: ['owner'], title: 'Schedule' },
    '/calendar':         { module: 'owner/schedule-builder.js', roles: ['owner'], title: 'Calendar' },
    '/bookings':         { module: 'owner/bookings.js', roles: ['owner'], title: 'All Bookings' },
    '/teams':            { module: 'owner/team-manager.js', roles: ['owner'], title: 'Teams' },
    '/clients':          { module: 'owner/client-manager.js', roles: ['owner'], title: 'Clients' },
    '/clients/:id':      { module: 'owner/client-detail.js', roles: ['owner'], title: 'Client Detail' },
    '/crm':              { module: 'owner/crm.js', roles: ['owner'], plan: 'maximum', title: 'CRM' },
    '/invoices':         { module: 'owner/invoice-manager.js', roles: ['owner'], title: 'Invoices' },
    '/chat':             { module: 'owner/chat-monitor.js', roles: ['owner'], plan: 'intermediate', title: 'AI Chat' },
    '/onboarding':       { module: 'owner/onboarding.js', roles: ['owner'], title: 'Setup Wizard' },
    '/services':         { module: 'owner/services.js', roles: ['owner'], title: 'Services' },
    '/reports':          { module: 'owner/reports.js', roles: ['owner'], title: 'Reports' },
    '/settings':         { module: 'owner/settings.js', roles: ['owner'], title: 'Settings' },
    '/my-bookings':      { module: 'homeowner/my-bookings.js', roles: ['homeowner'], title: 'My Bookings' },
    '/my-bookings/:id':  { module: 'homeowner/booking-detail.js', roles: ['homeowner'], title: 'Booking Detail' },
    '/my-invoices':      { module: 'homeowner/my-invoices.js', roles: ['homeowner'], title: 'My Invoices' },
    '/preferences':      { module: 'homeowner/preferences.js', roles: ['homeowner'], title: 'My Preferences' },
    '/admin':            { module: 'admin/super-admin.js', roles: ['super_admin'], title: 'Admin Dashboard' },
    '/today':            { module: 'team/today.js', roles: ['team_lead', 'cleaner'], title: 'Today' },
    '/job/:id':          { module: 'team/job-detail.js', roles: ['team_lead', 'cleaner'], title: 'Job Detail' },
    '/my-schedule':      { module: 'team/my-schedule.js', roles: ['team_lead', 'cleaner'], title: 'Schedule' },
    '/earnings':         { module: 'team/earnings.js', roles: ['team_lead', 'cleaner'], title: 'Earnings' },
    '/route':            { module: 'team/today.js', roles: ['team_lead', 'cleaner'], title: 'Route' },
    '/profile':          { module: 'team/profile.js', roles: ['team_lead', 'cleaner'], title: 'Profile' },
  },
  _legacyMap: {'#/owner/dashboard':'/dashboard','#/owner/schedule':'/schedule','#/owner/calendar':'/calendar','#/owner/bookings':'/bookings','#/owner/teams':'/teams','#/owner/clients':'/clients','#/owner/crm':'/crm','#/owner/invoices':'/invoices','#/owner/chat-monitor':'/chat','#/owner/onboarding':'/onboarding','#/owner/services':'/services','#/owner/reports':'/reports','#/owner/settings':'/settings','#/homeowner/bookings':'/my-bookings','#/homeowner/invoices':'/my-invoices','#/homeowner/preferences':'/preferences','#/admin/dashboard':'/admin','#/team/today':'/today','#/team/schedule':'/my-schedule','#/team/earnings':'/earnings','#/team/route':'/route','#/team/profile':'/profile','#/login':'/login','#/register':'/register'},
  _defaults: { super_admin:'/admin', owner:'/dashboard', homeowner:'/my-bookings', team_lead:'/today', cleaner:'/today' },
  _currentPath:null, _loadedModules:{}, _userRole:null, _userPlan:null, _transitioning:false, _transitionDuration:250, _isFirstLoad:true,

  init(role, plan) {
    this._userRole = role; this._userPlan = plan || 'basic';
    window.addEventListener('popstate', () => this._onRouteChange());
    if (window.location.hash) {
      const h = window.location.hash;
      for (const [lh,np] of Object.entries(this._legacyMap)) {
        if (h===lh||h.startsWith(lh+'/')) { history.replaceState({},'',np+h.substring(lh.length)); break; }
      }
    }
    this._onRouteChange();
  },

  navigate(path) {
    if (path.startsWith('#')) {
      const b=path.split('/').slice(0,3).join('/'), r=path.split('/').slice(3).join('/');
      path=(this._legacyMap[b]||path.replace('#',''))+(r?'/'+r:'');
    }
    if (path===this._currentPath) return;
    history.pushState({},'',path);
    this._onRouteChange();
  },

  getDefaultRoute() { return this._defaults[this._userRole]||'/login'; },

  _matchRoute(path) {
    path=path.replace(/\/+$/,'')||'/';
    if (this._routes[path]) return {route:this._routes[path],params:{}};
    const pp=path.split('/');
    for (const [pat,route] of Object.entries(this._routes)) {
      const rp=pat.split('/');
      if (rp.length!==pp.length) continue;
      const params={}; let match=true;
      for (let i=0;i<rp.length;i++) { if(rp[i].startsWith(':'))params[rp[i].substring(1)]=pp[i]; else if(rp[i]!==pp[i]){match=false;break;} }
      if (match) return {route,params};
    }
    return null;
  },

  async _onRouteChange() {
    const path=window.location.pathname;
    if (path===this._currentPath&&!this._isFirstLoad) return;
    this._isFirstLoad=false; this._currentPath=path;
    if (path==='/'||path==='') { this.navigate(this._userRole?this.getDefaultRoute():'/login'); return; }
    if (path==='/login'||path==='/register'||path.startsWith('/register/invite')) {
      if (this._userRole) { this.navigate(this.getDefaultRoute()); return; }
      const tk=path.startsWith('/register/invite/')?path.split('/')[3]:null;
      this._renderAuthRoute(path,tk); return;
    }
    const m=this._matchRoute(path);
    if (!m) { this._render404(); return; }
    const {route,params}=m;
    if (!route.roles.includes('*')&&!route.roles.includes(this._userRole)) { this.navigate(this.getDefaultRoute()); return; }
    if (route.plan) { const pl={basic:0,intermediate:1,maximum:2}; if ((pl[this._userPlan]||0)<(pl[route.plan]||0)){this._renderPlanGate(route.plan,route.title);return;} }
    await this._transition(route,params);
  },

  async _transition(route,params) {
    if (this._transitioning) return; this._transitioning=true;
    const cv=document.getElementById('content-view');
    if (cv&&cv.innerHTML.trim()) { cv.classList.add('cc-page-exit'); await new Promise(r=>setTimeout(r,this._transitionDuration)); cv.classList.remove('cc-page-exit'); }
    this._transitioning=false;
    const ca=document.getElementById('content-area'); if(ca)ca.scrollTo({top:0,behavior:'instant'});
    await this._loadAndRender(route,params);
    if(cv){cv.classList.add('cc-page-enter');const c=()=>{cv.classList.remove('cc-page-enter');cv.removeEventListener('animationend',c);};cv.addEventListener('animationend',c);}
  },

  _renderAuthRoute(path,inviteToken) {
    document.getElementById('loading-screen').style.display='none';
    document.getElementById('main-layout').style.display='none';
    const c=document.getElementById('auth-container'); c.style.display='flex';
    if(path==='/register'||path.startsWith('/register/invite')) AuthUI.renderRegister(c,inviteToken);
    else AuthUI.renderLogin(c);
  },

  async _loadAndRender(route,params) {
    const cv=document.getElementById('content-view'),cl=document.getElementById('content-loading');
    if(!route.module) return;
    if(typeof Xcleaners!=='undefined'&&Xcleaners.showContentSkeleton)Xcleaners.showContentSkeleton();
    else{cl.style.display='flex';cv.innerHTML='';}
    this._updateNavActive();
    document.title=route.title+' \u2014 Xcleaners';
    try{
      if(!this._loadedModules[route.module]){await this._loadScript('/cleaning/static/js/'+route.module+'?v=21');this._loadedModules[route.module]=true;}
      const mn=this._getModuleName(route.module);
      if(window[mn]&&typeof window[mn].render==='function'){cv.innerHTML='';await window[mn].render(cv,params);}
      else cv.innerHTML='<div class="cc-placeholder"><h2>'+route.title+'</h2><p>Coming soon.</p></div>';
    }catch(e){console.error('[Router]',route.module,e);cv.innerHTML='<div class="cc-placeholder cc-placeholder-error"><h2>Error</h2><button class="cc-btn cc-btn-primary" onclick="location.reload()">Refresh</button></div>';}
    finally{cl.style.display='none';}
  },

  _loadScript(src){return new Promise((ok,err)=>{if(document.querySelector('script[src="'+src+'"]')){ok();return;}const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=err;document.head.appendChild(s);});},
  _getModuleName(p){return p.replace('.js','').split('/').map(x=>x.split('-').map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join('')).join('');},
  _updateNavActive(){document.querySelectorAll('.cc-nav-item,.cc-tab-item,.cc-top-nav-link').forEach(i=>{i.classList.toggle('active',i.dataset.route===this._currentPath);});},
  _renderPlanGate(rp,fn){const cv=document.getElementById('content-view');document.getElementById('content-loading').style.display='none';cv.innerHTML='<div class="cc-plan-gate cc-animate-fade-in"><h2>'+fn+'</h2><p>Available on <strong>'+(rp==='intermediate'?'Intermediate':'Maximum')+'</strong> plan.</p><button class="cc-btn cc-btn-primary" onclick="CleanRouter.navigate(\'/settings\')">Upgrade</button></div>';},
  _render404(){const cv=document.getElementById('content-view'),cl=document.getElementById('content-loading');if(cl)cl.style.display='none';if(cv)cv.innerHTML='<div class="cc-placeholder cc-animate-fade-in"><h2>Page Not Found</h2><button class="cc-btn cc-btn-primary" onclick="CleanRouter.navigate(CleanRouter.getDefaultRoute())">Home</button></div>';},
};
