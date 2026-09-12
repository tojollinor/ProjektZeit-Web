(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 function beta(el){if(el&&!el.querySelector('.beta-tag'))el.insertAdjacentHTML('beforeend',' <span class="beta-tag">Beta</span>');}
 function apply(){
  const isAdmin=typeof state!=='undefined'&&state.user?.role==='admin';
  qa('[data-starface-admin]').forEach(el=>el.style.display=isAdmin?'':'none');
  for(const sel of ['[data-admin-tab="roles"]','[data-admin-tab="policies"]','[data-admin-tab="smtp"]','[data-admin-tab="notifications"]'])beta(q(sel));
  qa('[data-history-load],[data-async-history]').forEach(el=>{if(!el.querySelector('.beta-tag'))el.insertAdjacentHTML('beforeend',' <span class="beta-tag">Beta</span>');});
 }
 let applyPending=false;
 const scheduleApply=()=>{if(applyPending)return;applyPending=true;requestAnimationFrame(()=>{applyPending=false;apply();});};
 const observer=new MutationObserver(scheduleApply);observer.observe(document.body,{childList:true,subtree:true});
 let tries=0;const wait=setInterval(()=>{tries++;apply();if((typeof state!=='undefined'&&state.user)||tries>40)clearInterval(wait);},100);

 // Navigation groups are controls, not routes. Capture them before legacy click handlers
 // and before the old mobile-close helper can treat them like a page navigation.
 let lastCustomerNav=0;
 document.addEventListener('click',event=>{
  const toggle=event.target.closest('.pz-nav-toggle,.admin-nav-toggle');
  if(toggle){
   event.preventDefault();event.stopImmediatePropagation();
   const group=toggle.closest('.pz-nav-group,.admin-nav-group');
   const submenu=group?.querySelector('.pz-nav-submenu,.admin-nav-submenu');
   if(!submenu)return;
   const open=submenu.hidden;submenu.hidden=!open;toggle.setAttribute('aria-expanded',String(open));
   return;
  }
  const adminSub=event.target.closest('.admin-subnav[data-admin-open]');
  if(adminSub){
   event.preventDefault();event.stopImmediatePropagation();
   if(typeof showView==='function')showView('admin-options');
   q('#page-title')&&(q('#page-title').textContent='Admin-Optionen');
   setTimeout(()=>q(`[data-admin-tab="${adminSub.dataset.adminOpen}"]`)?.click(),30);
   setTimeout(()=>window.pzSyncNavigation?.(),70);
   return;
  }
  const custom=event.target.closest('[data-pz-nav-target]');
  if(custom){event.preventDefault();event.stopImmediatePropagation();window.pzOpenNavTarget?.(custom.dataset.pzNavTarget,custom.dataset.pzNavTitle||'');return;}
  const hard=event.target.closest('[data-pz-hard-reload]');
  if(hard){event.preventDefault();event.stopImmediatePropagation();if(window.pzHardReload)window.pzHardReload();else location.reload();return;}
  const customer=event.target.closest('.sidebar [data-view="customers"]');
  if(customer){const now=Date.now();if(now-lastCustomerNav<900){event.preventDefault();event.stopImmediatePropagation();return;}lastCustomerNav=now;}
  if(event.target.closest('#menu-toggle'))setTimeout(()=>window.pzSyncNavigation?.(),0);
 },true);

 const sidebar=q('.sidebar');function syncScrim(){if(!sidebar)return;const scrim=q('.sidebar-scrim');if(scrim)scrim.classList.toggle('open',sidebar.classList.contains('open'));}
 if(sidebar){new MutationObserver(syncScrim).observe(sidebar,{attributes:true,attributeFilter:['class']});document.addEventListener('click',event=>{if(event.target.closest('.nav,[data-go],#menu-toggle,.sidebar-scrim'))setTimeout(syncScrim,0);});window.addEventListener('resize',()=>{if(innerWidth>900){sidebar.classList.remove('open');syncScrim();}});syncScrim();}
 const build=q('meta[name="pz-frontend-version"]')?.content||'';
 function versioned(url){if(!build||/([?&])pzv=/.test(url))return url;return `${url}${url.includes('?')?'&':'?'}pzv=${encodeURIComponent(build)}`;}
 function stylesheet(href,key){if(document.querySelector(`link[data-${key}]`))return;const link=document.createElement('link');link.rel='stylesheet';link.href=versioned(href);link.dataset[key]='';document.head.append(link);}
 function script(src,key){if(document.querySelector(`script[data-${key}]`))return;const el=document.createElement('script');el.src=versioned(src);el.defer=true;el.dataset[key]='';document.body.append(el);}
 // ux-batch.js is already loaded directly by index.html. Loading it a second time doubled
 // document listeners, mutation observers and provider refresh work on every page.
 stylesheet('/provider-api-ui.css?v=0.7.0-1','providerApiUi');script('/provider-api-ui.js?v=0.7.0-1','providerApiUi');script('/network-guard.js?v=0.7.0-1','networkGuard');
 stylesheet('/work-panel-ui.css?v=0.7.0-2','workPanelUi');script('/work-panel-ui.js?v=0.7.0-2','workPanelUi');
 stylesheet('/zammad-ticket-ui.css?v=0.7.0-2','zammadTicketUi');script('/zammad-ticket-ui.js?v=0.7.0-1','zammadTicketUi');script('/zammad-cache-ui.js?v=0.7.0-5','zammadCacheUi');
 stylesheet('/provider-nav-status.css?v=0.7.0-1','providerNavStatus');script('/provider-nav-status.js?v=0.7.0-1','providerNavStatus');
 stylesheet('/customer-extra-ui.css?v=0.7.0-1','customerExtraUi');script('/customer-extra-ui.js?v=0.7.0-1','customerExtraUi');
 stylesheet('/ux-round2.css?v=0.7.0-1','uxRound2');script('/ux-round2.js?v=0.7.0-1','uxRound2');
 stylesheet('/next-batch-ui.css?v=0.7.0-1','nextBatchUi');script('/next-batch-ui.js?v=0.7.0-2','nextBatchUi');script('/next-batch-fixes.js?v=0.7.0-2','nextBatchFixes');
 stylesheet('/final-batch-ui.css?v=0.7.0-1','finalBatchUi');script('/final-batch-ui.js?v=0.7.0-1','finalBatchUi');script('/final-batch-hooks.js?v=0.7.0-1','finalBatchHooks');
 stylesheet('/navigation-v2.css?v=0.8.0-1','navigationV2');script('/navigation-v2.js?v=0.8.0-1','navigationV2');
})();
