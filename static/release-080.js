/* ProjektZeit 0.8.0: route-stable navigation, shared creation actions and timeline gestures. */
(()=>{
 const q=(selector,root=document)=>root?.querySelector?.(selector)||null;
 const qa=(selector,root=document)=>root?.querySelectorAll?[...root.querySelectorAll(selector)]:[];
 const h=value=>typeof esc==='function'?esc(value):String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
 const notify=(message,level='info')=>window.pzToast?.(message,level,5000)||((typeof toast==='function')&&toast(message));
 const activeView=()=>q('.view.active-view')?.id?.replace(/^view-/,'')||'';
 let applyingRoute=false;

 const paths={
  dashboard:'/',tracking:'/zeiterfassung',calendar:'/kalender',projects:'/projekte',
  bookkeeping:'/buchhaltung/projekte','employee-billing':'/buchhaltung/mitarbeiter','absence-approvals':'/buchhaltung/abwesenheiten',
  customers:'/kunden',zammad:'/zammad',starface:'/starface',teamviewer:'/teamviewer',logs:'/protokolle',statistics:'/statistiken',
  'settings-profile':'/einstellungen/profil','settings-connections':'/einstellungen/verbindungen','settings-client':'/einstellungen/downloads',
  'settings-data':'/einstellungen/daten','settings-api':'/einstellungen/api','workshop-status':'/werkstatt/status','admin-options':'/admin/unternehmen'
 };
 const titles={dashboard:'Übersicht',tracking:'Zeiterfassung',calendar:'Kalender',projects:'Projekte',bookkeeping:'Projektabrechnung','employee-billing':'Mitarbeiterabrechnung','absence-approvals':'Urlaub & Abwesenheiten',customers:'Kunden',zammad:'Zammad',starface:'STARFACE',teamviewer:'TeamViewer',logs:'Protokolle',statistics:'Statistiken','settings-profile':'Persönliches Profil','settings-connections':'Verbindungen','settings-client':'Downloads','settings-data':'Import & Export','settings-api':'API','workshop-status':'Werkstatt'};
 const routeToView=path=>{
  if(path==='/'||path==='/dashboard')return['dashboard'];
  if(path==='/zeiterfassung')return['tracking'];
  if(path==='/kalender')return['calendar'];
  if(/^\/projekte\/\d+$/.test(path))return['project-detail',Number(path.split('/').pop())];
  if(path==='/projekte/zeitvergleich')return['projects','comparison'];
  if(path==='/projekte/tags')return['projects','tags'];
  if(path==='/projekte')return['projects','overview'];
  if(path==='/buchhaltung'||path==='/buchhaltung/projekte')return['bookkeeping'];
  if(path==='/buchhaltung/mitarbeiter')return['employee-billing'];
  if(path==='/buchhaltung/abwesenheiten')return['absence-approvals'];
  if(path==='/kunden')return['customers'];
  if(path==='/zammad'||path==='/starface'||path==='/teamviewer')return[path.slice(1)];
  if(path==='/protokolle')return['logs'];
  if(path==='/statistiken')return['statistics'];
  if(path==='/einstellungen'||path==='/einstellungen/profil')return['settings-profile'];
  if(path==='/einstellungen/verbindungen')return['settings-connections'];
  if(path==='/einstellungen/downloads')return['settings-client'];
  if(path==='/einstellungen/daten')return['settings-data'];
  if(path==='/einstellungen/api')return['settings-api'];
  if(path==='/werkstatt'||path==='/werkstatt/status')return['workshop-status'];
  if(path.startsWith('/admin/'))return['admin-options',path.slice(7)||'company'];
  return null;
 };
 function validLocalPath(value){try{const url=new URL(value,location.origin);return url.origin===location.origin&&url.pathname.startsWith('/')&&!url.pathname.startsWith('//')?url.pathname+url.search+url.hash:'';}catch(_){return'';}}
 window.pzRoutePath=(path,{replace=false}={})=>{const target=validLocalPath(path);if(!target)return;if(location.pathname+location.search+location.hash===target)return;history[replace?'replaceState':'pushState']({pz:true},'',target);syncNavigation();};
 window.pzReloadCurrentPage=()=>location.reload();

 function openDynamic(name){
  const target=q(`[data-company-nav="${name}"]`)||q(`[data-view="${name}"]`)||q(`[data-pz-nav-target="${name}"]`);
  if(target){target.click();return true;}
  if(q('#view-'+name)&&typeof showView==='function'){showView(name);const title=q('#page-title');if(title)title.textContent=titles[name]||title.textContent;return true;}
  return false;
 }
 async function applyRoute(){
  if(!state?.user)return;
  if(location.pathname==='/client/authorize'){openAuthorization();return;}
  if(location.pathname==='/login'){
   const requested=validLocalPath(new URLSearchParams(location.search).get('return')||'/');
   history.replaceState({pz:true},'',requested||'/');
  }
  const route=routeToView(location.pathname)||['dashboard'];applyingRoute=true;
  try{
   if(route[0]==='project-detail'){await window.pzProjects?.detail?.(route[1]);return;}
   if(route[0]==='admin-options'){await window.pzAdmin?.open?.(route[1]);return;}
   openDynamic(route[0]);
   if(route[0]==='projects'&&route[1])requestAnimationFrame(()=>q(`[data-pc-tab="${route[1]}"]`)?.click());
  }finally{setTimeout(()=>{applyingRoute=false;syncNavigation();},0);}
 }
 function currentPath(){
  const view=activeView();
  if(view==='project-detail'&&/^\/projekte\/\d+$/.test(location.pathname))return location.pathname;
  if(view==='projects'&&location.pathname.startsWith('/projekte/'))return location.pathname;
  if(view==='admin-options'){
   const tab=qa('[data-admin-tab]').find(button=>button.classList.contains('primary')||button.getAttribute('aria-selected')==='true');
   return '/admin/'+(tab?.dataset.adminTab||'company');
  }
  return paths[view]||location.pathname;
 }
 function syncNavigation(){
  const view=activeView();
  qa('.sidebar .nav,.sidebar .pz-subnav,.sidebar .admin-subnav').forEach(button=>{
   const own=button.dataset.view||button.dataset.pzNavTarget||button.dataset.companyNav;
   button.classList.toggle('active',own===view);
  });
  for(const [group,names] of [['bookkeeping',['bookkeeping','employee-billing','absence-approvals']],['settings',['settings-profile','settings-connections','settings-client','settings-data','settings-api']],['workshop',['workshop-status']]]){
   const root=q(`[data-pz-nav-group="${group}"]`),toggle=q(':scope > .pz-nav-toggle',root);
   toggle?.classList.toggle('active',names.includes(view));
  }
  const admin=q('.admin-nav-group'),adminToggle=q(':scope > .admin-nav-toggle',admin);adminToggle?.classList.toggle('active',view==='admin-options');
  q(`[data-company-nav="calendar"]`)?.classList.toggle('active',view==='calendar');
 }
 document.addEventListener('pz-view-changed',()=>{syncNavigation();if(!applyingRoute&&location.pathname!=='/client/authorize'&&location.pathname!=='/login')window.pzRoutePath(currentPath());});
 document.addEventListener('click',event=>{const tab=event.target.closest('[data-admin-tab]');if(tab)setTimeout(()=>window.pzRoutePath('/admin/'+tab.dataset.adminTab),0);});
 window.addEventListener('popstate',applyRoute);

 /* Any expired protected session goes straight back to the login screen. */
 const nativeFetch=window.fetch.bind(window);
 let authRedirecting=false;
 const publicApi=path=>/^\/api\/v1\/(?:login|auth\/|client-auth\/|frontend\/version)/.test(path);
 function requireLogin(){
  if(authRedirecting)return;authRedirecting=true;
  if(typeof state!=='undefined')state.user=null;
  q('#app')?.classList.add('hidden');q('#login')?.classList.remove('hidden');
  if(location.pathname!=='/login'&&location.pathname!=='/client/authorize'){
   const target=location.pathname+location.search+location.hash;
   history.replaceState({},'',`/login?return=${encodeURIComponent(target)}`);
  }
  setTimeout(()=>{authRedirecting=false;q('#login-user')?.focus();},50);
 }
 window.fetch=async(input,init={})=>{
  const response=await nativeFetch(input,init),url=new URL(typeof input==='string'?input:input.url,location.href);
  if(response.status===401&&url.origin===location.origin&&url.pathname.startsWith('/api/')&&!publicApi(url.pathname))requireLogin();
  return response;
 };

 /* Browser authorization for the Windows desktop client (authorization-code + PKCE). */
 function loopback(value){try{const url=new URL(value);return url.protocol==='http:'&&['127.0.0.1','[::1]'].includes(url.hostname)&&!!url.port&&url.pathname==='/callback'&&!url.username&&!url.password&&!url.search&&!url.hash?url:null;}catch(_){return null;}}
 async function openAuthorization(){
  if(!state?.user)return;
  const params=new URLSearchParams(location.search),redirect=loopback(params.get('redirect_uri')||'');
  const required=['client_id','redirect_uri','code_challenge','state'];
  let d=q('#pz-client-authorization');if(d?.open)return;d?.remove();
  d=document.createElement('dialog');d.id='pz-client-authorization';d.className='pz-client-authorization';
  const valid=required.every(key=>params.get(key))&&redirect&&params.get('response_type')==='code'&&params.get('code_challenge_method')==='S256';
  d.innerHTML=`<form><p class="eyebrow">SICHERE CLIENT-ANMELDUNG</p><h2>${valid?h(params.get('client_name')||'ProjektZeit für Windows'):'Ungültige Anmeldeanfrage'}</h2>${valid?`<p>Die Anwendung auf diesem Computer möchte sich mit <strong>${h(location.host)}</strong> verbinden.</p><ul><li>Arbeitszeit und laufende Projekte anzeigen</li><li>Arbeit, Pausen und Projekte starten oder beenden</li><li>Deine hinterlegten Verbindungen verwenden</li></ul><p class="pz-auth-account">Angemeldet als <strong>${h(state.user.username)}</strong></p>`:'<p class="error">Die Rücksprungadresse oder der PKCE-Anmeldenachweis ist ungültig. Bitte die Anmeldung im Windows-Client neu starten.</p>'}<p role="alert" class="error" data-auth-error></p><div class="panel-actions"><button type="button" class="secondary" data-auth-cancel>Abbrechen</button>${valid?'<button type="submit" class="primary">Verbindung erlauben</button>':''}</div></form>`;
  document.body.append(d);d.addEventListener('cancel',event=>event.preventDefault());d.addEventListener('close',()=>d.remove(),{once:true});
  q('[data-auth-cancel]',d).onclick=()=>{if(redirect){redirect.searchParams.set('error','access_denied');redirect.searchParams.set('state',params.get('state')||'');location.replace(redirect.href);}else d.close();};
  q('form',d).onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;q('[data-auth-error]',d).textContent='';try{const result=await post('/api/v1/client-auth/authorize',Object.fromEntries(params));location.replace(result.redirect_url);}catch(error){q('[data-auth-error]',d).textContent=error.message;button.disabled=false;}};
  d.showModal();
 }

 /* Shared compact creation actions beside customer and project selectors. */
 window.pzOpenProjectCreate=async({customer_id=''}={})=>{
  let catalog;try{catalog=await post('/api/v1/project-catalog/list',{});}catch(error){notify(error.message,'error');return;}
  q('#pz-project-create')?.remove();const d=document.createElement('dialog');d.id='pz-project-create';d.className='pz-create-dialog';
  d.innerHTML=`<form><p class="eyebrow">STAMMDATEN</p><h2>Projekt anlegen</h2><label>Projektname<input name="name" maxlength="120" required autofocus></label><label>Kunde<div class="pz-select-action"><select name="customer_id"><option value="">Ohne Kunde</option>${(catalog.customers||[]).map(customer=>`<option value="${customer.id}" ${String(customer.id)===String(customer_id)?'selected':''}>${h(customer.name)}</option>`).join('')}</select><button type="button" class="secondary pz-inline-add" data-create-customer title="Kunde anlegen" aria-label="Kunde anlegen">+</button></div></label><p role="alert" class="error"></p><div class="panel-actions"><button type="button" class="secondary" data-close>Schließen</button><button class="primary" type="submit">Projekt anlegen</button></div></form>`;
  document.body.append(d);q('[data-close]',d).onclick=()=>d.close();q('[data-create-customer]',d).onclick=()=>window.pzOpenCustomerCreate?.();d.addEventListener('close',()=>d.remove(),{once:true});
  q('form',d).onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{await post('/api/v1/projects',{name:event.currentTarget.elements.name.value.trim(),customer_id:Number(event.currentTarget.elements.customer_id.value)||null});notify('Projekt angelegt','success');location.reload();}catch(error){q('.error',d).textContent=error.message;button.disabled=false;}};d.showModal();
 };
 function enhanceSelect(select,kind){
  if(!select||select.dataset.pzCreateAction||select.closest('.pz-select-action'))return;select.dataset.pzCreateAction=kind;
  const wrap=document.createElement('div');wrap.className='pz-select-action';select.before(wrap);wrap.append(select);
  const button=document.createElement('button');button.type='button';button.className='secondary pz-inline-add';button.textContent='+';button.title=kind==='customer'?'Kunde anlegen':'Projekt anlegen';button.setAttribute('aria-label',button.title);button.onclick=event=>{event.preventDefault();event.stopPropagation();if(kind==='customer')window.pzOpenCustomerCreate?.();else window.pzOpenProjectCreate?.({customer_id:select.closest('form,article,.tw-assignment,.tw-bulk-assignment')?.querySelector('[data-tw-customer],[data-bulk-customer],[name="customer_id"]')?.value||''});};wrap.append(button);
 }
 function enhanceCreationActions(root=document){
  for(const select of qa('select[data-tw-customer],select[data-bulk-customer],select[name="customer_id"],#project-customer,[data-work-customer]',root))enhanceSelect(select,'customer');
  for(const select of qa('select[data-tw-project-choice],select[data-bulk-project],select[name="project_id"],#project-select,[data-work-project]',root))enhanceSelect(select,'project');
 }

 function customerViewToggle(){
  const panel=q('#view-customers > .panel'),head=q(':scope > .panel-head',panel);if(!head||q('[data-customer-view-toggle]',head))return;
  const actions=document.createElement('div');actions.className='pz-view-toggle ui-tabs';actions.dataset.customerViewToggle='';actions.innerHTML='<button type="button" data-customer-mode="tiles" title="Kacheln">Kacheln</button><button type="button" data-customer-mode="list" title="Detailliste">Liste</button>';
  head.append(actions);const sync=()=>{let mode='tiles';try{mode=localStorage.getItem('pz-customer-view')==='list'?'list':'tiles';}catch(_){}qa('[data-customer-mode]',actions).forEach(button=>button.className=button.dataset.customerMode===mode?'primary':'secondary');};
  qa('[data-customer-mode]',actions).forEach(button=>button.onclick=()=>{window.pzSetCustomerView?.(button.dataset.customerMode);sync();});document.addEventListener('pz-customer-view-changed',sync);sync();
 }

 function contextTabs(){
  const groups=[
   {views:['settings-profile','settings-connections','settings-client','settings-data','settings-api'],labels:['Profil','Verbindungen','Downloads','Daten','API']},
   {views:['bookkeeping','employee-billing','absence-approvals'],labels:['Projekte','Mitarbeiter','Urlaub & Abwesenheiten']}
  ];
  for(const group of groups)for(const name of group.views){const view=q('#view-'+name);if(!view||q(':scope > [data-context-tabs]',view))continue;const tabs=document.createElement('nav');tabs.className='pz-context-tabs ui-tabs';tabs.dataset.contextTabs='';tabs.setAttribute('aria-label','Untermenü');group.views.forEach((target,index)=>{const button=document.createElement('button');button.type='button';button.textContent=group.labels[index];button.className=target===name?'primary':'secondary';button.setAttribute('aria-current',target===name?'page':'false');button.onclick=()=>openDynamic(target);tabs.append(button);});view.prepend(tabs);}
 }

 /* Keep exactly one assignment dot in each desktop row and one in its mobile summary. */
 function normalizeProviderDots(root=document){for(const tr of qa('.provider-view .raw-provider-table tbody tr',root)){
  const summary=q(':scope > .pz-mobile-summary',tr),cell=qa(':scope > td:not(.pz-mobile-summary)',tr)[0];
  qa('.pz-assignment-dot',summary||document.createElement('span')).forEach(dot=>dot.remove());
  const desktop=qa(':scope > td:not(.pz-mobile-summary) .pz-assignment-dot',tr);desktop.slice(1).forEach(dot=>dot.remove());
  if(!desktop[0]&&cell&&tr.dataset.pzAssigned){const dot=document.createElement('span');dot.className=`pz-assignment-dot ${tr.dataset.pzAssigned}`;cell.prepend(dot);desktop.push(dot);}
  if(desktop[0]&&cell&&desktop[0].parentElement!==cell)cell.prepend(desktop[0]);
  const mobile=qa('.mobile-assignment-dot',summary||tr);mobile.slice(1).forEach(dot=>dot.remove());
 }}

 /* Wheel and two-finger zoom preserve the time underneath the pointer/finger midpoint. */
 const zoomState=new WeakMap();
 function scalable(scroller){return q(':scope > .tw-timeline,:scope > .customer-timeline-layout',scroller);}
 function scaleGeneric(scroller,factor,anchor){
  const content=scalable(scroller);if(!content)return;const oldWidth=content.getBoundingClientRect().width||scroller.clientWidth,position=(scroller.scrollLeft+anchor)/oldWidth;
  const base=Number(content.dataset.zoomBase)||oldWidth,current=Number(content.dataset.zoomWidth)||oldWidth,next=Math.max(Math.max(base,scroller.clientWidth),Math.min(base*48,current*factor));
  content.dataset.zoomBase=String(base);content.dataset.zoomWidth=String(next);content.style.width=next+'px';content.style.minWidth=next+'px';scroller.scrollLeft=position*next-anchor;
 }
 function wheelZoom(event){const scroller=event.target.closest('.tw-timeline-scroll,.customer-timeline-scroll');if(!scroller||!event.deltaY)return;event.preventDefault();event.stopImmediatePropagation();const anchor=event.clientX-scroller.getBoundingClientRect().left,delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?scroller.clientWidth:1);scaleGeneric(scroller,Math.exp(-Math.max(-300,Math.min(300,delta))*.002),anchor);}
 document.addEventListener('wheel',wheelZoom,{capture:true,passive:false});
 function distance(touches){return Math.hypot(touches[0].clientX-touches[1].clientX,touches[0].clientY-touches[1].clientY);}
 function pinchStart(event){if(event.touches.length!==2)return;const scroller=event.target.closest('.timeline-scroll,.tw-timeline-scroll,.customer-timeline-scroll');if(!scroller)return;zoomState.set(scroller,{distance:distance(event.touches)});}
 function pinchMove(event){if(event.touches.length!==2)return;const scroller=event.target.closest('.timeline-scroll,.tw-timeline-scroll,.customer-timeline-scroll'),gesture=zoomState.get(scroller);if(!gesture)return;event.preventDefault();event.stopImmediatePropagation();const next=distance(event.touches),factor=next/Math.max(1,gesture.distance),box=scroller.getBoundingClientRect(),anchor=((event.touches[0].clientX+event.touches[1].clientX)/2)-box.left;gesture.distance=next;if(scroller.classList.contains('timeline-scroll')&&typeof zoomTimeline==='function')zoomTimeline(factor,anchor);else scaleGeneric(scroller,factor,anchor);}
 document.addEventListener('touchstart',pinchStart,{capture:true,passive:true});document.addEventListener('touchmove',pinchMove,{capture:true,passive:false});document.addEventListener('touchend',event=>{if(event.touches.length<2)for(const scroller of qa('.timeline-scroll,.tw-timeline-scroll,.customer-timeline-scroll'))zoomState.delete(scroller);},{capture:true,passive:true});

 let pending=false;function applyEnhancements(root=document){enhanceCreationActions(root);customerViewToggle();contextTabs();normalizeProviderDots(root);syncNavigation();}
 const observer=new MutationObserver(records=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1)applyEnhancements(node);applyEnhancements();});});
 observer.observe(document.body,{childList:true,subtree:true});
 document.addEventListener('pz-provider-rendered',()=>requestAnimationFrame(()=>normalizeProviderDots()));
 document.addEventListener('pz-customers-rendered',()=>{customerViewToggle();window.pzSetCustomerView?.((()=>{try{return localStorage.getItem('pz-customer-view')||'tiles';}catch(_){return'tiles';}})());});
 document.addEventListener('pz-company-ready',()=>{applyEnhancements();applyRoute();});
 document.addEventListener('pz-app-ready',()=>{applyEnhancements();applyRoute();});
 document.addEventListener('pz-auth-ready',()=>setTimeout(()=>{authRedirecting=false;if(location.pathname==='/client/authorize')openAuthorization();},0));
 applyEnhancements();if(typeof state!=='undefined'&&state.user)applyRoute();
})();
