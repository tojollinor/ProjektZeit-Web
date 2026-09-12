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
 function syncWorkPanel(name=activeName()){const panel=q('.work-panel');if(!panel)return;panel.hidden=name==='statistics'||name==='projects'||name.startsWith('settings-')||name.startsWith('workshop-')||['admin-options','logs','bookkeeping','account'].includes(name);}
 function textNode(button,text){if(!button)return;for(const n of button.childNodes){if(n.nodeType===3&&n.nodeValue.trim()){n.nodeValue=text;return;}}button.append(document.createTextNode(text));}
 function setIcon(button,icon){const span=q(':scope > span',button);if(span)span.textContent=icon;}

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

 async function renderProjectPage(){
  const host=q('[data-project-page-list]');if(!host)return;host.innerHTML='<p class="muted">Projekte werden geladen …</p>';
  try{
   const d=await post('/api/v1/next/context',{}),groups={active:[],parked:[],closed:[]};
   for(const p of d.projects||[])(groups[p.status||'active']||groups.active).push(p);
   const labels={active:'Aktiv',parked:'Geparkt',closed:'Geschlossen'};
   host.innerHTML=Object.entries(groups).map(([key,items])=>`<section class="panel pz-project-group"><div class="panel-head"><div><p class="eyebrow">${h(labels[key].toUpperCase())}</p><h3>${h(labels[key])}</h3></div><span class="badge">${items.length}</span></div>${items.length?items.map(p=>`<article class="pz-project-row"><div><strong>${h(p.name)}</strong><small>${h(p.customer||'Ohne Kunde')}</small></div><div class="pz-project-actions">${key!=='active'?`<button class="secondary subtle" data-pz-project="${p.id}" data-status="active">Aktivieren</button>`:''}${key!=='parked'?`<button class="secondary subtle" data-pz-project="${p.id}" data-status="parked">Parken</button>`:''}${key!=='closed'?`<button class="secondary subtle" data-pz-project="${p.id}" data-status="closed">Schließen</button>`:''}</div></article>`).join(''):'<p class="muted">Keine Projekte.</p>'}</section>`).join('');
   qa('[data-pz-project]',host).forEach(b=>b.onclick=async()=>{try{await post('/api/v1/projects/status',{project_id:Number(b.dataset.pzProject),status:b.dataset.status,send_to_billing:false});if(typeof refresh==='function')await refresh();renderProjectPage();}catch(e){window.pzToast?.(e.message,'error');}});
  }catch(e){host.innerHTML=`<p class="error">${h(e.message)}</p>`;}
 }
 function ensureProjectPage(){
  const nav=q('.sidebar nav');if(!nav)return;
  let button=q('[data-pz-nav-target="projects"]',nav);if(!button){button=document.createElement('button');button.type='button';button.className='nav';button.dataset.pzNavTarget='projects';button.dataset.pzNavTitle='Projekte';button.innerHTML='<span>▣</span>Projekte';nav.append(button);}
  let view=q('#view-projects');if(!view){view=document.createElement('section');view.id='view-projects';view.className='view pz-split-view';view.innerHTML='<div class="settings-intro pz-page-intro"><p class="eyebrow">ARBEITSBEREICH</p><h3>Projekte</h3><p class="muted">Projektstatus und Kundenzuordnung zentral verwalten.</p></div><div class="pz-project-grid" data-project-page-list></div>';q('main')?.insertBefore(view,q('#toast'));}
  button.onclick=e=>{e.preventDefault();e.stopImmediatePropagation();window.pzOpenNavTarget?.('projects','Projekte');renderProjectPage();};
 }

 function reorderNav(){
  const nav=q('.sidebar nav');if(!nav)return;
  const oldWorkshop=q('button.nav[data-view="workshop"]',nav);oldWorkshop?.remove();q('#view-workshop')?.remove();
  ensureProjectPage();settingsPolish();
  const stats=q('[data-pz-nav-target="statistics"]',nav);if(stats)setIcon(stats,'◔');
  const dashboard=q('[data-view="dashboard"]',nav);if(dashboard)textNode(dashboard,'Dashboard');
  const order=[
   q('[data-view="dashboard"]',nav),q('[data-pz-nav-target="statistics"]',nav),q('[data-view="tracking"]',nav),q('[data-pz-nav-target="projects"]',nav),q('[data-view="bookkeeping"]',nav),q('[data-view="customers"]',nav),q('[data-view="zammad"]',nav),q('[data-view="starface"]',nav),q('[data-view="teamviewer"]',nav),q('[data-view="logs"]',nav),q('[data-pz-nav-group="settings"]',nav),q('.admin-nav-group',nav),q('[data-pz-nav-group="workshop"]',nav)
  ].filter(Boolean);
  for(const item of order)nav.append(item);
 }

 function installCustomerPrefetch(){
  if(window.pzCustomerPrefetchInstalled)return;window.pzCustomerPrefetchInstalled=true;
  try{
   if(typeof loadCustomerCache==='function'){
    const original=loadCustomerCache;let inflight=null,last=0;
    loadCustomerCache=async function(force=false){
     if(!force&&inflight)return inflight;
     if(!force&&Date.now()-last<15000&&typeof customerCache!=='undefined'&&customerCache?.customers?.length)return customerCache;
     inflight=Promise.resolve(original()).then(v=>{last=Date.now();return v;}).finally(()=>{inflight=null;});return inflight;
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
