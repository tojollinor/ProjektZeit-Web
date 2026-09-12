(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const h=v=>typeof esc==='function'?esc(v):String(v??'');
 const a=v=>typeof attr==='function'?attr(v):h(v).replaceAll('"','&quot;');
 const notify=(m,l='info',t=4500)=>window.pzToast?window.pzToast(m,l,t):typeof toast==='function'?toast(m):null;
 let context=null;

 function fmtDate(value,withSeconds=false){
  if(!value)return '–';const d=new Date(value);if(Number.isNaN(+d))return String(value);
  return d.toLocaleString('de-DE',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',...(withSeconds?{second:'2-digit'}:{})});
 }
 function fmtLastUpdate(value){
  if(!value)return '';const d=new Date(value);if(Number.isNaN(+d))return '';
  const now=new Date(),same=d.getFullYear()===now.getFullYear()&&d.getMonth()===now.getMonth()&&d.getDate()===now.getDate();
  return same?d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'})+' Uhr':d.toLocaleString('de-DE',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})+' Uhr';
 }
 async function loadContext(){context=await post('/api/v1/next/context',{});return context;}
 function can(key){return !!context?.is_superadmin||(context?.permissions||[]).includes(key);}

 function renameDashboard(){
  const b=q('[data-view="dashboard"]');if(b)b.childNodes.forEach(n=>{if(n.nodeType===3&&/Übersicht/.test(n.nodeValue||''))n.nodeValue='Dashboard';});
  if(q('#view-dashboard')?.classList.contains('active-view'))q('#page-title').textContent='Dashboard';
 }

 const systemViews=new Set(['settings','account','admin-options','logs','bookkeeping']);
 function syncWorkPanel(){const active=q('.view.active-view'),name=active?.id?.replace(/^view-/,'')||'';const panel=q('.work-panel');if(panel)panel.hidden=systemViews.has(name);}
 document.addEventListener('click',e=>{const nav=e.target.closest('[data-view],[data-go]');if(nav)setTimeout(()=>{syncWorkPanel();if((nav.dataset.view||nav.dataset.go)==='dashboard')q('#page-title').textContent='Dashboard';},0);},true);
 new MutationObserver(syncWorkPanel).observe(q('main')||document.body,{subtree:true,attributes:true,attributeFilter:['class']});

 function viewport(){const meta=q('meta[name="viewport"]');if(!meta)return;meta.content=innerWidth<=900?'width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no':'width=device-width,initial-scale=1';}
 viewport();window.addEventListener('resize',viewport);

 function moveProfile(){
  const settings=q('#view-settings'),account=q('#view-account'),accountNav=q('[data-view="account"]');if(!settings||!account)return;
  accountNav?.remove();if(q('[data-profile-settings]',settings))return;
  const fold=document.createElement('details');fold.className='panel settings-fold';fold.dataset.profileSettings='';
  fold.innerHTML='<summary><span>Profil</span><span class="fold-status">Persönliche Einstellungen</span></summary><div class="fold-body" data-profile-body></div>';
  const body=q('[data-profile-body]',fold),grid=q('.account-grid',account);if(grid)body.append(grid);
  settings.prepend(fold);fold.addEventListener('toggle',()=>{if(fold.open)window.pzLoadAccount?.();});
 }
 function csvLast(){const settings=q('#view-settings'),csv=q('[data-import-export]',settings);if(settings&&csv&&csv!==settings.lastElementChild)settings.append(csv);}

 function providerSettingsStatus(){
  for(const card of qa('#integration-cards [data-provider]')){
   const fold=q('.settings-fold',card)||card,badge=q('.badge',fold);if(!badge)continue;const text=(badge.textContent||'').trim().toLowerCase();
   let state='configured-failed',label='Eingerichtet, aber nicht verbunden';
   if(/verbunden/.test(text)){state='connected';label='Verbunden';}
   else if(/nicht eingerichtet|kein client-secret|nicht konfiguriert/.test(text)){state='not-configured';label='Nicht eingerichtet';}
   else if(/fehl|ungültig|nicht verbunden/.test(text)){state='configured-failed';label=/fehl/.test(text)?'Verbindung fehlgeschlagen':'Eingerichtet, aber nicht verbunden';}
   badge.textContent=label;badge.dataset.connectionState=state;
  }
 }

 async function refreshProviderSettingsStatus(){
  try{
   const d=await post('/api/v1/provider/navigation-status',{});
   for(const item of d.providers||[]){
    const card=q(`#integration-cards [data-provider="${item.provider}"]`),badge=q('.badge',card);if(!badge)continue;
    if(item.connected){badge.textContent='Verbunden';badge.dataset.connectionState='connected';}
    else if(item.reason==='missing'){badge.textContent='Nicht eingerichtet';badge.dataset.connectionState='not-configured';}
    else{badge.textContent=item.detail&&/fehl|ungültig|abgewiesen/i.test(item.detail)?'Verbindung fehlgeschlagen':'Eingerichtet, aber nicht verbunden';badge.dataset.connectionState='configured-failed';}
   }
  }catch(_){}
 }

 function adminAccordion(){
  const nav=q('.sidebar nav'),admin=q('[data-view="admin-options"]',nav);if(!nav||!admin||q('.admin-nav-group',nav))return;
  if(!can('admin.options.view')){admin.remove();return;}admin.classList.remove('admin-only');admin.style.display='flex';
  const group=document.createElement('div');group.className='admin-nav-group';admin.before(group);group.append(admin);admin.classList.add('admin-nav-toggle');admin.setAttribute('aria-expanded','false');
  const submenu=document.createElement('div');submenu.className='admin-nav-submenu';submenu.hidden=true;
  const items=[
   ['users','Benutzer',false,'users.view'],['roles','Rollen & Rechte',true,'roles.view'],['policies','Richtlinien',false,'security.policies.view'],
   ['smtp','E-Mail / SMTP',true,'smtp.view'],['notifications','Benachrichtigungen',true,'notifications.edit'],['integrations','Integrationen',true,'integrations.view'],['api','API',false,'admin.options.view'],['super','Systemschutz',true,'system.options.edit']
  ];
  for(const [tab,label,beta,permission] of items){
   if(!can(permission))continue;const b=document.createElement('button');b.type='button';b.className='admin-subnav';b.dataset.adminOpen=tab;
   b.innerHTML=`<span>${h(label)}</span>${beta?'<small class="beta-tag">Beta</small>':''}`;submenu.append(b);
   b.onclick=e=>{e.stopPropagation();showView('admin-options');q('#page-title').textContent='Admin-Optionen';setTimeout(()=>q(`[data-admin-tab="${tab}"]`)?.click(),80);};
  }
  group.append(submenu);admin.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();const open=submenu.hidden;submenu.hidden=!open;admin.setAttribute('aria-expanded',String(open));},true);
 }

 const customerCreate=document.createElement('dialog');customerCreate.className='customer-create-dialog';
 customerCreate.innerHTML=`<form data-customer-create><div class="panel-head"><div><p class="eyebrow">STAMMDATEN</p><h3>Kunde anlegen</h3></div><button type="button" class="secondary subtle" data-customer-create-close>Schließen</button></div><label>Firma / Kundenname<input name="name" maxlength="120" required></label><div class="field-grid"><label>E-Mail<input name="email" type="email"></label><label>Telefon<input name="phone"></label></div><div class="field-grid"><label>Straße<input name="street"></label><label>Hausnummer<input name="house_number"></label></div><div class="field-grid"><label>PLZ<input name="zip_code"></label><label>Ort<input name="city"></label></div><label>Land<input name="country" value="Deutschland"></label><div class="panel-actions"><button class="primary">Kunde speichern</button></div></form>`;document.body.append(customerCreate);
 q('[data-customer-create-close]',customerCreate).onclick=()=>customerCreate.close();
 q('[data-customer-create]',customerCreate).onsubmit=async e=>{e.preventDefault();const f=e.currentTarget,values=Object.fromEntries(new FormData(f));try{const phones=values.phone.trim()?[{number:values.phone,label:'Festnetz',source:'manual'}]:[];const created=await post('/api/v1/customers/profile',{name:values.name,email:values.email,phones});await post('/api/v1/customers/master',{customer_id:created.customer_id,save:true,street:values.street,house_number:values.house_number,zip_code:values.zip_code,city:values.city,country:values.country});notify('Kunde angelegt','success');customerCreate.close();f.reset();f.country.value='Deutschland';await (typeof refresh==='function'?refresh():Promise.resolve());q('[data-view="customers"]')?.click();}catch(error){notify(error.message,'error');}};
 function customerCreateButton(){const section=q('#view-customers'),form=q('.customer-quick-form',section);if(!section||!form||q('[data-customer-create-button]',section))return;const button=document.createElement('button');button.type='button';button.className='primary customer-add-button';button.dataset.customerCreateButton='';button.textContent='+';button.title='Kunde anlegen';button.setAttribute('aria-label','Kunde anlegen');form.replaceWith(button);button.onclick=()=>customerCreate.showModal();}
 function cleanCustomerRows(){for(const row of qa('.compact-customer-row')){const sub=q('.customer-row-sub',row),bits=qa(':scope > span',sub);if(bits.length>1)bits.at(-1).remove();}}

 function projectManager(){const host=q('#project-activity')?.closest('article');if(!host||q('[data-project-manager]',host))return;const wrap=document.createElement('div');wrap.dataset.projectManager='';wrap.className='project-manager';host.append(wrap);renderProjects();}
 async function renderProjects(){const wrap=q('[data-project-manager]');if(!wrap)return;try{await loadContext();const groups={active:[],parked:[],closed:[]};for(const p of context.projects||[])groups[p.status||'active']?.push(p);wrap.innerHTML=`<div class="project-status-groups">${projectGroup('Aktive Projekte',groups.active)}${projectGroup('Geparkt',groups.parked)}${projectGroup('Geschlossene Projekte',groups.closed)}</div>`;qa('[data-project-status]',wrap).forEach(b=>b.onclick=()=>changeProjectStatus(Number(b.dataset.projectId),b.dataset.projectStatus));}catch(error){wrap.innerHTML=`<p class="error">${h(error.message)}</p>`;}}
 function projectGroup(title,items){return `<section class="project-status-group"><h4>${h(title)}</h4>${items.length?items.map(p=>`<article class="project-status-row"><div><strong>${h(p.name)}</strong><small>${h(p.customer||'Ohne Kunde')}${p.billing_state?` · ${h({pending:'Zur Abrechnung',in_progress:'In Bearbeitung',billed:'Abgerechnet'}[p.billing_state]||p.billing_state)}`:''}</small></div><div class="project-status-actions">${p.status!=='active'?`<button class="secondary subtle" data-project-id="${p.id}" data-project-status="active">Aktiv</button>`:''}${p.status!=='parked'?`<button class="secondary subtle" data-project-id="${p.id}" data-project-status="parked">Parken</button>`:''}${p.status!=='closed'?`<button class="secondary subtle" data-project-id="${p.id}" data-project-status="closed">Schließen</button>`:''}</div></article>`).join(''):'<p class="muted">Keine Projekte.</p>'}</section>`;}
 async function changeProjectStatus(id,status){let send=false;if(status==='closed')send=confirm('Projekt schließen und direkt zur Abrechnung übergeben?\n\nOK = schließen und zur Abrechnung\nAbbrechen = nur schließen');try{await post('/api/v1/projects/status',{project_id:id,status,send_to_billing:send});notify(status==='active'?'Projekt aktiviert':status==='parked'?'Projekt geparkt':send?'Projekt geschlossen und zur Abrechnung übergeben':'Projekt geschlossen','success');await refresh();await renderProjects();}catch(error){notify(error.message,'error');}}

 function bookkeeping(){const nav=q('.sidebar nav');if(!nav||q('[data-view="bookkeeping"]')||!can('bookkeeping.view'))return;const settings=q('[data-view="settings"]',nav),button=document.createElement('button');button.className='nav';button.dataset.view='bookkeeping';button.innerHTML='<span>€</span>Buchhaltung';nav.insertBefore(button,settings||null);const section=document.createElement('section');section.id='view-bookkeeping';section.className='view';section.innerHTML=`<div class="panel"><div class="panel-head"><div><p class="eyebrow">BUCHHALTUNG</p><h3>Projektabrechnung</h3></div><button class="secondary" data-bookkeeping-refresh>Aktualisieren</button></div><div data-bookkeeping-list></div></div>`;q('main')?.insertBefore(section,q('#toast'));button.onclick=()=>{showView('bookkeeping');q('#page-title').textContent='Buchhaltung';loadBookkeeping();};q('[data-bookkeeping-refresh]',section).onclick=loadBookkeeping;}
 async function loadBookkeeping(){const list=q('[data-bookkeeping-list]');if(!list)return;list.innerHTML='<p class="muted">Buchhaltung wird geladen …</p>';try{const d=await post('/api/v1/bookkeeping/list',{}),groups={pending:[],in_progress:[],billed:[]};for(const p of d.projects||[])groups[p.billing_state]?.push(p);list.innerHTML=['pending','in_progress','billed'].map(key=>`<section class="billing-group"><h4>${{pending:'Zur Abrechnung',in_progress:'In Bearbeitung',billed:'Abgerechnet'}[key]}</h4>${groups[key].length?groups[key].map(p=>`<article class="billing-row"><div><strong>${h(p.name)}</strong><small>${h(p.customer||'Ohne Kunde')}</small></div>${can('bookkeeping.manage')?`<select data-billing-project="${p.id}"><option value="pending" ${key==='pending'?'selected':''}>Zur Abrechnung</option><option value="in_progress" ${key==='in_progress'?'selected':''}>In Bearbeitung</option><option value="billed" ${key==='billed'?'selected':''}>Abgerechnet</option></select>`:''}</article>`).join(''):'<p class="muted">Keine Projekte.</p>'}</section>`).join('');qa('[data-billing-project]',list).forEach(s=>s.onchange=async()=>{try{await post('/api/v1/bookkeeping/status',{project_id:Number(s.dataset.billingProject),billing_state:s.value});await loadBookkeeping();}catch(e){notify(e.message,'error');}});}catch(error){list.innerHTML=`<p class="error">${h(error.message)}</p>`;}}

 function sessionsUi(){const body=q('[data-profile-body]');if(!body||q('[data-session-settings]',body))return;const panel=document.createElement('article');panel.className='panel session-settings';panel.dataset.sessionSettings='';panel.innerHTML=`<div class="panel-head"><div><p class="eyebrow">SITZUNGEN</p><h3>Geräte & Sitzungen</h3></div><button type="button" class="secondary" data-sessions-refresh>Aktualisieren</button></div><div class="session-tabs"><button class="primary" data-session-tab="connected">Verbundene Sitzungen</button><button class="secondary" data-session-tab="history">Sitzungsverlauf</button></div><div data-session-pane="connected"></div><div class="hidden" data-session-pane="history"></div>`;body.append(panel);q('[data-sessions-refresh]',panel).onclick=loadSessions;qa('[data-session-tab]',panel).forEach(b=>b.onclick=()=>{qa('[data-session-tab]',panel).forEach(x=>x.className=x===b?'primary':'secondary');qa('[data-session-pane]',panel).forEach(x=>x.classList.toggle('hidden',x.dataset.sessionPane!==b.dataset.sessionTab));});loadSessions();}
 async function loadSessions(){const panel=q('[data-session-settings]');if(!panel)return;try{const d=await post('/api/v1/sessions/list',{});q('[data-session-pane="connected"]',panel).innerHTML=(d.connected||[]).length?(d.connected||[]).map(s=>sessionCard(s,true)).join(''):'<p class="muted">Keine verbundenen Sitzungen.</p>';q('[data-session-pane="history"]',panel).innerHTML=(d.history||[]).length?(d.history||[]).map(s=>sessionCard(s,false)).join(''):'<p class="muted">Noch keine beendeten Sitzungen.</p>';qa('[data-session-disconnect]',panel).forEach(b=>b.onclick=async()=>{if(!confirm('Diese Sitzung wirklich trennen?'))return;try{const r=await post('/api/v1/sessions/disconnect',{token_hash:b.dataset.sessionDisconnect});if(r.current){location.reload();return;}await loadSessions();notify('Sitzung getrennt','success');}catch(e){notify(e.message,'error');}});}catch(error){q('[data-session-pane="connected"]',panel).innerHTML=`<p class="error">${h(error.message)}</p>`;}}
 function sessionCard(s,connected){const name=s.client_type==='windows'?'Windows-Client':s.client_type==='app'?'App':'Browser';return `<article class="session-row"><div><div class="session-title"><strong>${h(name)}</strong>${s.current?'<span class="badge">Diese Sitzung</span>':''}<span class="session-state ${s.activity}">${s.activity==='active'?'Aktiv':'Inaktiv'}</span></div><small>${h(s.client_name||'')} · verbunden seit ${h(fmtDate(s.created_at))}</small><small>Zuletzt aktiv: ${h(fmtDate(s.last_active_at))}${!connected&&s.ended_at?` · beendet ${h(fmtDate(s.ended_at))}`:''}${!connected&&s.end_reason?` · ${h(s.end_reason)}`:''}</small></div>${connected?`<button type="button" class="secondary subtle danger" data-session-disconnect="${a(s.token_hash)}">Trennen</button>`:''}</article>`;}

 const widgetEditor=document.createElement('dialog');widgetEditor.className='dashboard-editor';widgetEditor.innerHTML=`<div class="panel-head"><div><p class="eyebrow">DASHBOARD</p><h3>Dashboard bearbeiten</h3></div><button type="button" class="secondary" data-dashboard-editor-close>Schließen</button></div><p class="muted">Widgets auswählen und mit den Pfeilen anordnen.</p><div data-widget-editor-list></div><button type="button" class="primary" data-widget-editor-save>Speichern</button>`;document.body.append(widgetEditor);q('[data-dashboard-editor-close]',widgetEditor).onclick=()=>widgetEditor.close();
 function dashboardUi(){const dash=q('#view-dashboard');if(!dash||q('[data-dashboard-edit]',dash))return;const edit=document.createElement('button');edit.type='button';edit.className='secondary subtle dashboard-edit';edit.dataset.dashboardEdit='';edit.textContent='Dashboard bearbeiten';dash.prepend(edit);const stats=q('.stats',dash);if(stats)stats.dataset.dashboardWidget='stats';const missed=document.createElement('article');missed.className='panel missed-calls-widget';missed.dataset.dashboardWidget='missed_calls';missed.innerHTML=`<div class="panel-head"><div><p class="eyebrow">STARFACE</p><h3>Verpasste Anrufe</h3></div><button type="button" class="secondary" data-missed-refresh>Aktualisieren</button></div><p class="muted" data-missed-status>Lokaler Stand</p><div data-missed-list></div>`;stats?.after(missed);q('[data-missed-refresh]',missed).onclick=()=>refreshMissed(true);edit.onclick=openWidgetEditor;refreshMissed(false);applyDashboard();}
 async function applyDashboard(){const dash=q('#view-dashboard');if(!dash)return;try{if(!context)await loadContext();const widgets=context.dashboard?.widgets||['stats','missed_calls'];const edit=q('[data-dashboard-edit]',dash);let anchor=edit;for(const key of widgets){const el=q(`[data-dashboard-widget="${key}"]`,dash);if(el){anchor.after(el);anchor=el;el.hidden=false;}}for(const el of qa('[data-dashboard-widget]',dash))el.hidden=!widgets.includes(el.dataset.dashboardWidget);}catch(_){}}
 function openWidgetEditor(){const all=[['stats','Kennzahlen'],['missed_calls','Verpasste Anrufe']],selected=[...(context?.dashboard?.widgets||['stats','missed_calls'])];const list=q('[data-widget-editor-list]',widgetEditor);function paint(){list.innerHTML=all.map(([key,label])=>{const pos=selected.indexOf(key);return `<div class="widget-editor-row"><label><input type="checkbox" data-widget-check="${key}" ${pos>=0?'checked':''}> ${h(label)}</label><div><button type="button" class="secondary subtle" data-widget-up="${key}" ${pos<=0?'disabled':''}>↑</button><button type="button" class="secondary subtle" data-widget-down="${key}" ${pos<0||pos===selected.length-1?'disabled':''}>↓</button></div></div>`;}).join('');qa('[data-widget-check]',list).forEach(x=>x.onchange=()=>{const key=x.dataset.widgetCheck;if(x.checked&&!selected.includes(key))selected.push(key);if(!x.checked)selected=selected.filter(v=>v!==key);paint();});qa('[data-widget-up]',list).forEach(b=>b.onclick=()=>{const i=selected.indexOf(b.dataset.widgetUp);if(i>0)[selected[i-1],selected[i]]=[selected[i],selected[i-1]];paint();});qa('[data-widget-down]',list).forEach(b=>b.onclick=()=>{const i=selected.indexOf(b.dataset.widgetDown);if(i>=0&&i<selected.length-1)[selected[i+1],selected[i]]=[selected[i],selected[i+1]];paint();});}paint();q('[data-widget-editor-save]',widgetEditor).onclick=async()=>{try{const d=await post('/api/v1/dashboard/preferences',{widgets:selected});context.dashboard={widgets:d.widgets};await applyDashboard();widgetEditor.close();notify('Dashboard gespeichert','success');}catch(e){notify(e.message,'error');}};widgetEditor.showModal();}
 async function refreshMissed(syncServer){const status=q('[data-missed-status]'),list=q('[data-missed-list]');if(!list)return;try{if(syncServer){status.textContent='STARFACE wird vollständig abgeglichen …';const started=await post('/api/v1/archive/start',{provider:'starface'}),id=started.job?.id;await new Promise((resolve,reject)=>{let tries=0;const poll=async()=>{try{const d=await post('/api/v1/archive/job',{provider:'starface'}),j=d.job||{};if(id&&j.id&&j.id!==id){if(++tries<300)return setTimeout(poll,1000);}if(j.state==='running')return setTimeout(poll,1000);if(j.state==='success')resolve();else reject(new Error(j.error||'STARFACE-Abgleich fehlgeschlagen'));}catch(e){reject(e);}};poll();});}const d=await post('/api/v1/starface/missed',{}),calls=d.calls||[];status.textContent=`${calls.length} nicht zurückgerufene ${calls.length===1?'Anruf':'Anrufe'}`;list.innerHTML=calls.length?calls.map(c=>`<article class="missed-call-row"><div><strong>${h(c.name||c.number||'Unbekannt')}</strong><small>${h(c.number||'')} · ${h(fmtDate(c.occurred_at))}</small></div><a class="secondary subtle" href="tel:${a(String(c.number||'').replace(/[^+\d]/g,''))}">Anrufen</a></article>`).join(''):'<p class="muted">Keine offenen Rückrufe.</p>';if(!d.server_write_supported){const note=document.createElement('small');note.className='muted callback-write-note';note.textContent='Der STARFACE-Rückrufstatus wird beim Aktualisieren vollständig vom Server abgeglichen.';list.append(note);}}catch(error){status.textContent=error.message;}}

 function refineLogs(){for(const row of qa('.log-list .log-row')){const copy=q('.log-compact-copy',row);if(!copy||row.dataset.twoLine)return;row.dataset.twoLine='1';const head=q(':scope > div',copy),time=q('small',head),message=q(':scope > span',copy);if(!head||!time||!message)continue;const line=document.createElement('div');line.className='log-compact-second';line.append(time,message);copy.append(line);}}
 new MutationObserver(()=>requestAnimationFrame(refineLogs)).observe(document.body,{childList:true,subtree:true});

 function providerStatus(){for(const sec of qa('.provider-view')){const status=q('.list-status',sec);if(!status)continue;const text=status.textContent||'';if(/lädt|werden geladen|fehler|abgleich läuft/i.test(text))continue;const match=text.match(/zuletzt(?: vollständig)? aktualisiert\s+([^·\s]+(?:T[^·\s]+)?)/i);const last=status.dataset.lastSyncAt||match?.[1]||'';if(last)status.dataset.lastSyncAt=last;const count=qa('tbody tr',sec).length;status.textContent=last?`${count} Einträge · zuletzt aktualisiert ${fmtLastUpdate(last)}`:`${count} Einträge`;}}

 async function init(){
  if(typeof state==='undefined'||!state.user){setTimeout(init,120);return;}
  try{await loadContext();}catch(_){context={permissions:[],dashboard:{widgets:['stats','missed_calls']}};}
  renameDashboard();moveProfile();customerCreateButton();cleanCustomerRows();projectManager();bookkeeping();adminAccordion();dashboardUi();sessionsUi();csvLast();providerSettingsStatus();refreshProviderSettingsStatus();syncWorkPanel();refineLogs();
  q('[data-view="settings"]')?.addEventListener('click',()=>setTimeout(()=>{moveProfile();sessionsUi();csvLast();providerSettingsStatus();refreshProviderSettingsStatus();window.pzLoadAccount?.();},160));
  q('[data-view="customers"]')?.addEventListener('click',()=>setTimeout(()=>{customerCreateButton();cleanCustomerRows();},200));
  q('[data-view="tracking"]')?.addEventListener('click',()=>setTimeout(renderProjects,180));
  setInterval(()=>{cleanCustomerRows();providerSettingsStatus();csvLast();providerStatus();refineLogs();},1400);
 }
 init();
})();