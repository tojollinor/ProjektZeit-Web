(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const h=v=>typeof esc==='function'?esc(v):String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const a=v=>h(v).replaceAll('"','&quot;');
 const notify=(message,level='info',timeout=4500)=>window.pzToast?window.pzToast(message,level,timeout):typeof toast==='function'?toast(message):null;
 let profileRequest=null,sessionsRequest=null,connectionRequest=0,connectionLoading=false,lastConnectionStates=new Map();
 let navObserver=null,cardsObserver=null,arranging=false;

 function fmtDate(value){if(!value)return '–';const d=new Date(value);return Number.isNaN(+d)?String(value):d.toLocaleString('de-DE',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'});}
 function activeName(){return q('.view.active-view')?.id?.replace(/^view-/,'')||'';}
 function systemView(name=activeName()){
  return name==='settings'||name==='account'||name==='admin-options'||name==='logs'||name==='workshop'||name.startsWith('settings-')||name.startsWith('workshop-');
 }
 function syncWorkPanel(name=activeName()){const panel=q('.work-panel');if(panel)panel.hidden=systemView(name);}

 function arrangeNav(){
  const nav=q('.sidebar nav');if(!nav||arranging)return;
  const settings=q('[data-pz-nav-group="settings"]',nav)||q('[data-view="settings"]',nav);
  const admin=q('.admin-nav-group',nav)||q('[data-view="admin-options"]',nav);
  const workshop=q('[data-pz-nav-group="workshop"]',nav)||q('[data-view="workshop"]',nav);
  const desired=[
   q('[data-view="dashboard"]',nav),q('[data-pz-nav-target="statistics"]',nav),q('[data-view="tracking"]',nav),q('[data-pz-nav-target="projects"]',nav),
   q('[data-view="bookkeeping"]',nav),q('[data-view="customers"]',nav),q('[data-view="zammad"]',nav),q('[data-view="starface"]',nav),q('[data-view="teamviewer"]',nav),
   q('[data-view="logs"]',nav),settings,admin,workshop
  ].filter(Boolean);
  const current=[...nav.children].filter(x=>desired.includes(x));
  if(current.length===desired.length&&current.every((x,i)=>x===desired[i]))return;
  arranging=true;for(const item of desired)nav.append(item);queueMicrotask(()=>{arranging=false;});
 }

 function ensureWorkshopLog(){
  const group=q('[data-pz-nav-group="workshop"]');if(!group)return false;
  const submenu=q('.pz-nav-submenu,.admin-nav-submenu',group);if(!submenu)return false;
  let button=q('[data-pz-copy-diagnostic]',submenu);if(button)return true;
  button=document.createElement('button');button.type='button';button.className='admin-subnav pz-subnav pz-diagnostic-copy';button.dataset.pzCopyDiagnostic='';button.textContent='Log kopieren';
  const reload=q('[data-pz-hard-reload]',submenu);submenu.insertBefore(button,reload||null);button.onclick=copyDiagnostics;return true;
 }

 async function copyText(text){
  try{await navigator.clipboard.writeText(text);return true;}catch(_){}
  try{const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.append(area);area.select();const ok=document.execCommand('copy');area.remove();return ok;}catch(_){return false;}
 }
 async function copyDiagnostics(event){
  const button=event?.currentTarget||q('[data-pz-copy-diagnostic]');if(button){button.disabled=true;button.dataset.oldText=button.textContent;button.textContent='Log wird erstellt …';}
  window.pzDiagnostics?.record?.('diagnostic-copy',{view:activeName()});
  let backend=null,backendError='';
  try{backend=await post('/api/v1/diagnostics/snapshot',{});}catch(error){backendError=String(error?.message||error);}
  const resources=performance.getEntriesByType?.('resource')?.slice(-100).map(entry=>{let path='';try{path=new URL(entry.name,location.href).pathname;}catch(_){path=String(entry.name);}return {path,duration_ms:Math.round(entry.duration),transfer_size:entry.transferSize||0,initiator:entry.initiatorType||''};})||[];
  const payload={
   exported_at:new Date().toISOString(),frontend_version:q('meta[name="pz-frontend-version"]')?.content||'',current_view:activeName(),online:navigator.onLine,
   viewport:{width:innerWidth,height:innerHeight,device_pixel_ratio:devicePixelRatio},user_agent:navigator.userAgent,
   backend:backend||{error:backendError||'Diagnose-Endpunkt nicht verfügbar'},client_events:[...(window.pzDiagnostics?.events||[])],resources
  };
  const text='ProjektZeit Diagnose-Log\n'+JSON.stringify(payload,null,2),ok=await copyText(text);
  if(ok)notify('Diagnose-Log in die Zwischenablage kopiert','success',5000);else notify('Diagnose-Log konnte nicht kopiert werden','error',6000);
  if(button){button.disabled=false;button.textContent=button.dataset.oldText||'Log kopieren';delete button.dataset.oldText;}
 }

 function ensureProfile(){
  const view=q('#view-settings-profile');if(!view)return false;
  const legacy=q('[data-profile-settings]',view);if(legacy)legacy.hidden=true;
  if(q('[data-pz-profile-main]',view))return true;
  const intro=q(':scope > .pz-page-intro',view);
  const main=document.createElement('div');main.className='pz-profile-main';main.dataset.pzProfileMain='';
  main.innerHTML=`
   <article class="panel"><div class="panel-head"><div><p class="eyebrow">STAMMDATEN</p><h3>Persönliche Daten</h3></div></div>
    <form data-pz-profile-form><label>Benutzername<input name="username" readonly></label><div class="field-grid"><label>Vorname<input name="first_name" autocomplete="given-name"></label><label>Nachname<input name="last_name" autocomplete="family-name"></label></div><div class="field-grid"><label>E-Mail<input type="email" name="email" autocomplete="email"></label><label>Telefon<input name="phone" autocomplete="tel"></label></div><div class="pz-profile-actions"><button class="primary">Stammdaten speichern</button></div><p class="integration-status" data-pz-save-status></p></form>
   </article>
   <article class="panel"><div class="panel-head"><div><p class="eyebrow">DARSTELLUNG</p><h3>Darstellung</h3></div></div><p class="muted">Systemstandard folgt dem aktuellen Gerät.</p><div class="theme-options"><label><input type="radio" name="pz-theme" value="system"> Systemstandard</label><label><input type="radio" name="pz-theme" value="light"> Heller Modus</label><label><input type="radio" name="pz-theme" value="dark"> Dunkler Modus</label></div><p class="integration-status" data-pz-theme-status></p></article>
   <article class="panel pz-session-panel"><div class="panel-head"><div><p class="eyebrow">SITZUNGEN</p><h3>Aktive Sitzungen &amp; Sitzungsverlauf</h3></div><button type="button" class="secondary subtle" data-pz-sessions-refresh>Aktualisieren</button></div><div class="pz-session-columns"><section class="pz-session-section"><h4>Aktive Sitzungen</h4><div class="pz-session-list" data-pz-active-sessions><p class="pz-loading-line">Aktive Sitzungen werden geladen …</p></div></section><section class="pz-session-section"><h4>Sitzungsverlauf</h4><div class="pz-session-list" data-pz-session-history><p class="pz-loading-line">Sitzungsverlauf wird geladen …</p></div></section></div></article>`;
  if(intro)intro.after(main);else view.prepend(main);
  const form=q('[data-pz-profile-form]',main);form.onsubmit=async e=>{e.preventDefault();const status=q('[data-pz-save-status]',main);status.textContent='Stammdaten werden gespeichert …';const data=Object.fromEntries(new FormData(form));delete data.username;try{await post('/api/v1/account/save',data);status.textContent='Stammdaten gespeichert.';notify('Persönliche Daten gespeichert','success');}catch(error){status.textContent=error.message;}};
  qa('input[name="pz-theme"]',main).forEach(input=>input.onchange=async()=>{const status=q('[data-pz-theme-status]',main),theme=input.value;if(theme==='dark'||theme==='light')document.documentElement.dataset.theme=theme;else delete document.documentElement.dataset.theme;status.textContent='Darstellung wird gespeichert …';try{await post('/api/v1/account/theme',{theme});status.textContent='Darstellung gespeichert.';}catch(error){status.textContent=error.message;}});
  q('[data-pz-sessions-refresh]',main).onclick=()=>loadSessions(true);
  main.addEventListener('click',async e=>{const button=e.target.closest('[data-pz-session-disconnect]');if(!button)return;const current=button.dataset.current==='1',label=current?'Diese aktuelle Sitzung wirklich abmelden?':'Diese Sitzung wirklich abmelden?';if(!confirm(label))return;button.disabled=true;try{const result=await post('/api/v1/sessions/disconnect',{token_hash:button.dataset.pzSessionDisconnect});if(result.current){location.reload();return;}await loadSessions(true);notify('Sitzung abgemeldet','success');}catch(error){notify(error.message,'error');button.disabled=false;}});
  return true;
 }

 function applyTheme(theme){if(theme==='dark'||theme==='light')document.documentElement.dataset.theme=theme;else delete document.documentElement.dataset.theme;}
 async function loadProfile(force=false){
  if(!ensureProfile())return;
  if(profileRequest&&!force)return profileRequest;
  const view=q('#view-settings-profile'),form=q('[data-pz-profile-form]',view),status=q('[data-pz-save-status]',view);if(status&&!form.dataset.loaded)status.innerHTML='<span class="pz-loading-line">Stammdaten werden geladen …</span>';
  profileRequest=(async()=>{try{const d=await post('/api/v1/account/context',{}),p=d.profile||{},theme=d.preferences?.theme||'system';form.elements.username.value=typeof state!=='undefined'&&state.user?.username?state.user.username:'';for(const key of ['first_name','last_name','email','phone'])form.elements[key].value=p[key]||'';const radio=q(`input[name="pz-theme"][value="${theme}"]`,view);if(radio)radio.checked=true;applyTheme(theme);form.dataset.loaded='1';if(status)status.textContent='';}catch(error){if(status)status.textContent=error.message;}finally{profileRequest=null;}})();return profileRequest;
 }
 function sessionName(s){return s.client_type==='windows'?'Windows-Client':s.client_type==='app'?'App':'Browser';}
 function activeSessionRow(s){return `<article class="pz-session-row"><div><div class="pz-session-title"><strong>${h(sessionName(s))}</strong>${s.current?'<span class="badge">Diese Sitzung</span>':''}<span class="pz-session-state ${h(s.activity||'inactive')}">${s.activity==='active'?'Aktiv':'Inaktiv'}</span></div><small>${h(s.client_name||'Unbekanntes Gerät')}</small><div class="pz-session-meta"><span>IP ${h(s.ip_address||'–')}</span><span>Angemeldet ${h(fmtDate(s.created_at))}</span><span>Zuletzt aktiv ${h(fmtDate(s.last_active_at))}</span></div></div><button type="button" class="secondary subtle danger" data-pz-session-disconnect="${a(s.token_hash)}" data-current="${s.current?'1':'0'}">${s.current?'Diese Sitzung abmelden':'Abmelden'}</button></article>`;}
 function historySessionRow(s){return `<article class="pz-session-row"><div><div class="pz-session-title"><strong>${h(sessionName(s))}</strong><span class="pz-session-state">Beendet</span></div><small>${h(s.client_name||'Unbekanntes Gerät')}</small><div class="pz-session-meta"><span>IP ${h(s.ip_address||'–')}</span><span>Start ${h(fmtDate(s.created_at))}</span><span>Letzte Aktivität ${h(fmtDate(s.last_active_at))}</span><span>Ende ${h(fmtDate(s.ended_at))}</span>${s.end_reason?`<span>Grund: ${h(s.end_reason)}</span>`:''}</div></div></article>`;}
 async function loadSessions(force=false){
  if(!ensureProfile())return;
  if(sessionsRequest&&!force)return sessionsRequest;
  const view=q('#view-settings-profile'),active=q('[data-pz-active-sessions]',view),history=q('[data-pz-session-history]',view);active.innerHTML='<p class="pz-loading-line">Aktive Sitzungen werden geladen …</p>';history.innerHTML='<p class="pz-loading-line">Sitzungsverlauf wird geladen …</p>';
  sessionsRequest=(async()=>{try{const d=await post('/api/v1/sessions/list',{}),connected=d.connected||[],ended=d.history||[];active.innerHTML=connected.length?connected.map(activeSessionRow).join(''):'<p class="muted">Keine aktiven Sitzungen.</p>';history.innerHTML=ended.length?ended.map(historySessionRow).join(''):'<p class="muted">Noch keine beendeten Sitzungen.</p>';}catch(error){active.innerHTML=`<p class="error">${h(error.message)}</p>`;history.innerHTML='<p class="muted">Sitzungsverlauf konnte nicht geladen werden.</p>';}finally{sessionsRequest=null;}})();return sessionsRequest;
 }
 async function loadProfilePage(force=false){ensureProfile();await Promise.allSettled([loadProfile(force),loadSessions(force)]);}

 function markConnectionsLoading(){
  const container=q('#integration-cards');if(!container)return;
  for(const card of qa('[data-provider]',container)){const badge=q('.badge',card);if(!badge)continue;badge.textContent='Status wird geprüft';badge.dataset.connectionState='loading';badge.title='Verbindungsstatus wird geprüft.';}
 }
 function applyConnectionStates(){
  const container=q('#integration-cards');if(!container)return;if(connectionLoading){markConnectionsLoading();return;}
  for(const [provider,item] of lastConnectionStates){const card=q(`[data-provider="${provider}"]`,container),badge=q('.badge',card);if(!badge)continue;if(item.connected){badge.textContent='Verbunden';badge.dataset.connectionState='connected';badge.title=item.detail||'Verbunden';}else if(item.reason==='missing'||item.reason==='missing_client_secret'){badge.textContent='Nicht eingerichtet';badge.dataset.connectionState='not-configured';badge.title=item.detail||'Nicht eingerichtet';}else{badge.textContent='Verbindung fehlgeschlagen';badge.dataset.connectionState='configured-failed';badge.title=item.detail||'Verbindung fehlgeschlagen';}}
 }
 async function loadConnectionStates(){
  const request=++connectionRequest;connectionLoading=true;markConnectionsLoading();
  try{const data=await post('/api/v1/provider/navigation-status',{});if(request!==connectionRequest)return;lastConnectionStates=new Map((data.providers||[]).map(item=>[item.provider,item]));connectionLoading=false;applyConnectionStates();}
  catch(error){if(request!==connectionRequest)return;connectionLoading=false;for(const badge of qa('#integration-cards .badge')){badge.textContent='Status nicht verfügbar';badge.dataset.connectionState='unknown';badge.title=error.message;}}
 }
 function wrapLoadIntegrations(){
  if(typeof window.loadIntegrations!=='function'||window.loadIntegrations.__pzWrapped)return false;
  const original=window.loadIntegrations;
  const wrapped=async function(...args){const pending=original.apply(this,args),container=q('#integration-cards');if(container&&!q('[data-provider]',container))container.innerHTML='<div class="pz-loading-line">Verbindungen werden geladen …</div>';connectionLoading=true;markConnectionsLoading();try{return await pending;}finally{applyConnectionStates();}};
  wrapped.__pzWrapped=true;window.loadIntegrations=wrapped;return true;
 }
 function watchCards(){const cards=q('#integration-cards');if(!cards||cardsObserver)return false;cardsObserver=new MutationObserver(()=>{if(connectionLoading)markConnectionsLoading();else applyConnectionStates();});cardsObserver.observe(cards,{childList:true,subtree:true});return true;}

 function providerViewLoading(provider){const status=q(`#view-${provider} .list-status`);if(status&&!q(`#view-${provider} tbody tr`)){status.classList.add('pz-loading-line');status.textContent='Daten werden geladen …';setTimeout(()=>status.classList.remove('pz-loading-line'),5000);}}

 function installHooks(){
  if(window.pzOpenNavTarget&&!window.pzOpenNavTarget.__pzSettingsPolish){const original=window.pzOpenNavTarget;const wrapped=(name,label)=>{original(name,label);syncWorkPanel(name);if(name==='settings-profile')loadProfilePage();if(name==='settings-connections')loadConnectionStates();setTimeout(()=>{arrangeNav();ensureWorkshopLog();},0);};wrapped.__pzSettingsPolish=true;window.pzOpenNavTarget=wrapped;}
  wrapLoadIntegrations();watchCards();
 }
 document.addEventListener('click',event=>{
  const profile=event.target.closest('[data-pz-nav-target="settings-profile"]');if(profile)setTimeout(()=>loadProfilePage(),0);
  const connections=event.target.closest('[data-pz-nav-target="settings-connections"]');if(connections){connectionLoading=true;markConnectionsLoading();loadConnectionStates();}
  const provider=event.target.closest('.nav[data-view="zammad"],.nav[data-view="starface"],.nav[data-view="teamviewer"]');if(provider)providerViewLoading(provider.dataset.view);
  if(event.target.closest('.sidebar [data-view],.sidebar [data-pz-nav-target],.sidebar [data-admin-open]'))setTimeout(()=>{syncWorkPanel();arrangeNav();ensureWorkshopLog();},0);
 });

 function init(){
  arrangeNav();ensureWorkshopLog();ensureProfile();syncWorkPanel();installHooks();
  const nav=q('.sidebar nav');if(nav&&!navObserver){navObserver=new MutationObserver(()=>{arrangeNav();ensureWorkshopLog();});navObserver.observe(nav,{childList:true});}
 }
 init();let tries=0;const settle=setInterval(()=>{tries++;init();if(typeof state!=='undefined'&&state.user&&q('[data-pz-nav-group="workshop"]')&&q('#view-settings-profile')&&tries>20)clearInterval(settle);else if(tries>60)clearInterval(settle);},150);
})();
