(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const h=v=>typeof esc==='function'?esc(v):String(v??'');
 function applyChartSizes(){
  const root=q('#view-statistics');if(!root)return;
  for(const el of qa('.pz-stat-bar i[style],.pz-week-bars i[style]',root)){
   const raw=el.getAttribute('style')||'',m=raw.match(/(width|height)\s*:\s*([0-9.]+)%/i);if(!m)continue;
   el.removeAttribute('style');el.style[m[1].toLowerCase()]=`${Math.max(0,Math.min(100,Number(m[2])))}%`;
  }
 }
 function activeName(){return q('.view.active-view')?.id?.replace(/^view-/,'')||'';}
 function syncWorkPanel(name=activeName()){const panel=q('.work-panel');if(!panel)return;panel.hidden=name==='statistics'||name.startsWith('settings-')||name.startsWith('workshop-')||['admin-options','staff-settings','absence-approvals','logs','bookkeeping','account'].includes(name);}
 function textNode(button,text){if(!button)return;for(const n of button.childNodes){if(n.nodeType===3&&n.nodeValue.trim()){n.nodeValue=text;return;}}button.append(document.createTextNode(text));}
 function setIcon(button,icon){const span=q(':scope > span',button);if(span&&!span.querySelector('svg')&&span.textContent!==icon)span.textContent=icon;}

 function settingsPolish(){
  const group=q('[data-pz-nav-group="settings"]');if(group){const toggle=q('.pz-nav-toggle',group);setIcon(toggle,'⚙');}
  const client=q('[data-pz-nav-target="settings-client"]');if(client)client.textContent='Downloads';
  const page=q('#view-settings-client .pz-page-intro h3');if(page)page.textContent='Downloads';
  const copy=q('#view-settings-client .pz-page-intro .muted');if(copy)copy.textContent='ProjektZeit-Anwendungen und Clients herunterladen.';
  const con=q('#view-settings-connections');if(con){
   const intros=qa(':scope > .settings-intro',con);if(intros.length){intros[0].innerHTML='<p class="eyebrow">EINSTELLUNGEN</p><h3>Verbindungen</h3><p class="muted">Externe Dienste mit ProjektZeit verbinden und verwalten.</p>';for(const extra of intros.slice(1))extra.remove();}
   for(const node of qa('.debug-output,.debug-step',con))node.classList.add('hidden');
   for(const p of qa('p',con)){if(/debug|diagnose|diagnostik/i.test(p.textContent||''))p.remove();}
  }
 }

 function renderProjectPage(){return window.pzProjects.render();}
 function ensureProjectPage(){
  const nav=q('.sidebar nav');if(!nav)return;
  let button=q('[data-pz-nav-target="projects"]',nav);if(!button){button=document.createElement('button');button.type='button';button.className='nav';button.dataset.pzNavTarget='projects';button.dataset.pzNavTitle='Projekte';button.innerHTML='<span>▣</span>Projekte';nav.append(button);}
  let view=q('#view-projects');if(!view){view=document.createElement('section');view.id='view-projects';view.className='view pz-split-view';view.innerHTML='<div class="settings-intro pz-page-intro"><p class="eyebrow">ARBEITSBEREICH</p><h3>Projekte</h3><p class="muted">Projektstatus und Kundenzuordnung zentral verwalten.</p></div><div class="pz-project-grid" data-project-page-list></div>';q('main')?.insertBefore(view,q('#toast'));}
  button.onclick=e=>{e.preventDefault();e.stopImmediatePropagation();window.pzOpenNavTarget?.('projects','Projekte');};
 }

 function applyIcons(nav){
  const paths={"dashboard": "M2 2h9v20H2zM14 2h8v9h-8zM14 14h8v8h-8z", "statistics": "M11 2a10 10 0 1 0 11 11H11zM14 1v9h9a10 10 0 0 0-9-9", "tracking": "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m-1 4h2v6l4 3-1 2-5-4z", "projects": "M2 5h8l2 3h10v13H2zM3 2h8l2 3H3z", "bookkeeping": "M3 2h18v20l-3-2-3 2-3-2-3 2-3-2-3 2zM6 6v2h12V6zm0 5v2h12v-2zm0 5v2h7v-2z", "customers": "M8 2a4 4 0 1 0 0 8 4 4 0 0 0 0-8m9 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6M1 21v-3a7 7 0 0 1 14 0v3zm16 0v-3a9 9 0 0 0-2-6h2a6 6 0 0 1 6 6v3z", "zammad": "M2 3h20v14H10l-6 5v-5H2zm4 4v2h12V7zm0 4v2h8v-2z", "starface": "M3 2h5l2 6-3 2a16 16 0 0 0 7 7l2-3 6 2v5c-1 4-10 0-14-4S0 3 3 2", "teamviewer": "M2 3h20v14H2zm3 7 4 4v-3h6v3l4-4-4-4v3H9V6zm3 9h8v2h4v2H4v-2h4z", "logs": "M4 2h12l4 4v16H4zm3 5v2h10V7zm0 4v2h10v-2zm0 4v2h10v-2z", "settings": "M9 1h6l1 4 3-1 3 5-3 3 3 3-3 5-3-1-1 4H9l-1-4-3 1-3-5 3-3-3-3 3-5 3 1zm3 7a4 4 0 1 0 0 8 4 4 0 0 0 0-8", "admin": "M12 1 22 5v7c0 5-6 9-10 11C8 21 2 17 2 12V5zm-1 5v7h2V6zm0 10v2h2v-2z", "workshop": "M14 2a6 6 0 0 0-5 9l-8 8 4 4 8-8a6 6 0 0 0 9-7l-4 4-4-4 4-4z"};
  for(const b of qa('button.nav',nav)){
   const key=b.dataset.view||b.dataset.pzNavTarget||b.dataset.companyNav||b.closest('[data-pz-nav-group]')?.dataset.pzNavGroup||(b.classList.contains('admin-nav-toggle')?'admin':'');
   paths.calendar='M5 1h2v3h10V1h2v3h3v18H2V4h3zm-1 8v11h16V9zm2 3h4v3H6zm8 0h4v3h-4z';const alias={'admin-options':'admin','absence-approvals':'calendar'};const iconKey=alias[key]||key;if(!paths[iconKey])continue;const span=q(':scope > span',b);if(!span||span.dataset.pzUnifiedIcon===key)continue;
   span.innerHTML=`<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" d="${paths[iconKey]}"/></svg>`;span.dataset.pzUnifiedIcon=key;span.dataset.pzCustomerIcon='1';
  }
 }
 function reorderNav(){
  const nav=q('.sidebar nav');if(!nav)return;
  const oldWorkshop=q('button.nav[data-view="workshop"]',nav);oldWorkshop?.remove();q('#view-workshop')?.remove();
  ensureProjectPage();settingsPolish();
  const stats=q('[data-pz-nav-target="statistics"]',nav);if(stats)setIcon(stats,'◔');
  const dashboard=q('[data-view="dashboard"]',nav);if(dashboard)textNode(dashboard,'Dashboard');
  const order=[
   q('[data-view="dashboard"]',nav),q('[data-pz-nav-target="statistics"]',nav),q('[data-view="tracking"]',nav),q('[data-company-nav="calendar"]',nav),q('[data-pz-nav-target="projects"]',nav),q('[data-view="bookkeeping"]',nav),q('[data-company-nav="absence-approvals"]',nav),q('[data-view="customers"]',nav),q('[data-view="zammad"]',nav),q('[data-view="starface"]',nav),q('[data-view="teamviewer"]',nav),q('[data-view="logs"]',nav),q('[data-pz-nav-group="settings"]',nav),q('.admin-nav-group',nav),q('[data-pz-nav-group="workshop"]',nav)
  ].filter(Boolean);
  applyIcons(nav);
  const current=[...nav.children].filter(n=>order.includes(n));if(order.some((n,i)=>current[i]!==n))for(const item of order)nav.append(item);
 }

 window.pzArrangeNavigation=reorderNav;document.addEventListener('pz-app-ready',reorderNav);document.addEventListener('pz-company-ready',reorderNav);
 function installCustomerPrefetch(){
  if(window.pzCustomerPrefetchInstalled)return;window.pzCustomerPrefetchInstalled=true;
  try{
   if(typeof loadCustomerCache==='function'){
    const original=loadCustomerCache;let inflight=null,last=0;document.addEventListener('pz-data-changed',()=>{last=0;});
    loadCustomerCache=async function(force=false){
     if(!force&&inflight)return inflight;
     if(!force&&Date.now()-last<15000&&typeof customerCache!=='undefined'&&customerCache?.customers?.length)return customerCache;
     inflight=Promise.resolve(original(force)).then(v=>{last=Date.now();return v;}).finally(()=>{inflight=null;});return inflight;
    };
    let tries=0;const t=setInterval(()=>{tries++;if(typeof state!=='undefined'&&state.user){clearInterval(t);loadCustomerCache().catch(()=>{});}else if(tries>100)clearInterval(t);},100);
   }
  }catch(_){}
 }

 function install(){
  if(!window.pzOpenNavTarget||window.pzNavigationPolishInstalled)return false;
  window.pzNavigationPolishInstalled=true;
  const original=window.pzOpenNavTarget;
  window.pzOpenNavTarget=(name,label)=>{original(name,label);syncWorkPanel(name);requestAnimationFrame(applyChartSizes);if(name==='projects')renderProjectPage();};
  const stats=q('#view-statistics');if(stats){let pending=false;new MutationObserver(()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;applyChartSizes();});}).observe(stats,{childList:true,subtree:true});}
  reorderNav();installCustomerPrefetch();applyChartSizes();syncWorkPanel();
  let rounds=0;const settle=setInterval(()=>{rounds++;reorderNav();if(rounds>=15)clearInterval(settle);},150);
  return true;
 }
 document.addEventListener('click',event=>{const nav=event.target.closest('.sidebar [data-view], [data-go]');if(!nav)return;const name=nav.dataset.view||nav.dataset.go||'';setTimeout(()=>{syncWorkPanel(name);reorderNav();},0);});
 if(!install()){let tries=0;const timer=setInterval(()=>{tries++;if(install()||tries>=30)clearInterval(timer);},50);}
})();
