(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const h=v=>typeof esc==='function'?esc(v):String(v??'');
 const a=v=>typeof attr==='function'?attr(v):h(v).replaceAll('"','&quot;');
 const notify=(m,l='info',t=5000)=>window.pzToast?window.pzToast(m,l,t):null;
 const providerRows={zammad:[],starface:[],teamviewer:[]};
 let context=null,customers=null,lastCustomerRetry=0;

 async function pzPost(path,body={}){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  try{
   const r=await fetch(path,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json',...(typeof state!=='undefined'&&state.csrf?{'X-CSRF-Token':state.csrf}:{})},body:JSON.stringify(body)});
   const data=await r.json();if(!r.ok)throw new Error(data.error||`HTTP ${r.status}`);return data;
  }catch(e){if(e?.name==='AbortError')throw new Error('Die Anfrage hat zu lange gedauert. Bitte erneut versuchen.');throw e;}finally{clearTimeout(timer);}
 }

 /* Network watchdog and provider-response capture. Existing app fetches now get a timeout too. */
 const nativeFetch=window.fetch.bind(window);
 window.fetch=(input,init={})=>{
  const url=typeof input==='string'?input:input?.url||'';
  const own=!init.signal,controller=own?new AbortController():null;
  const next=own?{...init,signal:controller.signal}:init;
  const timer=own?setTimeout(()=>controller.abort(),15000):null;
  const promise=nativeFetch(input,next);
  promise.then(response=>{
   if(/\/api\/v1\/integrations\/list/.test(url)){
    try{const body=JSON.parse(init.body||'{}'),provider=body.provider;if(providerRows[provider])response.clone().json().then(data=>{if(Array.isArray(data.rows)){providerRows[provider]=data.rows;setTimeout(()=>decorateProvider(provider),0);}}).catch(()=>{});}catch(_){}
   }
  }).catch(()=>{}).finally(()=>{if(timer)clearTimeout(timer);});
  return promise;
 };

 function spinner(text='Seite wird geladen') {return `<div class="pz-page-loader"><i></i><strong>${h(text)}</strong></div>`;}
 function loading(section,on,text='Seite wird geladen'){
  if(!section)return;let el=q(':scope > .pz-page-loader',section);
  if(on&&!el){section.insertAdjacentHTML('afterbegin',spinner(text));el=q(':scope > .pz-page-loader',section);}
  if(el)el.hidden=!on;
 }
 function compactRefresh(root=document){
  for(const b of qa('button',root)){
   if(b.dataset.pzCompactRefresh||!/^(Aktualisieren|Vorschläge aktualisieren)$/i.test((b.textContent||'').trim()))continue;
   b.dataset.pzCompactRefresh='1';b.classList.add('pz-refresh-icon');b.title='Aktualisieren';b.setAttribute('aria-label','Aktualisieren');b.textContent='↻';
  }
 }

 function customerIcon(){
  const btn=q('[data-view="customers"]');if(!btn)return;const span=q('span',btn);if(span&&span.dataset.pzCustomerIcon)return;
  const svg='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8c.5-4.1 3-6.2 7-6.2s6.5 2.1 7 6.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  if(span){span.innerHTML=svg;span.dataset.pzCustomerIcon='1';}
 }
 function dashboardPencil(){const b=q('[data-dashboard-edit]');if(!b)return;b.textContent='✎';b.title='Dashboard bearbeiten';b.setAttribute('aria-label','Dashboard bearbeiten');b.classList.add('pz-dashboard-pencil');}

 /* Customer lifecycle watchdog. One controlled retry instead of a request/render storm. */
 function customersStuck(){const sec=q('#view-customers');if(!sec?.classList.contains('active-view'))return false;const st=q('[data-customer-status]',sec)?.textContent||'';return /werden geladen|wird geladen/i.test(st);}
 function triggerCustomerReload(reason='watchdog'){
  const now=Date.now();if(now-lastCustomerRetry<10000)return;lastCustomerRetry=now;
  const btn=q('[data-view="customers"]');if(!btn)return;
  notify(reason==='resume'?'Kundenansicht wird wiederhergestellt …':'Kunden laden dauert ungewöhnlich lange. Neuer Versuch …','warning',3500);btn.click();
 }
 q('[data-view="customers"]')?.addEventListener('click',()=>{
  const sec=q('#view-customers');loading(sec,true,'Kunden werden geladen');
  const stamp=Date.now();setTimeout(()=>{if(stamp<=lastCustomerRetry)return;if(customersStuck())triggerCustomerReload();},12000);
  setTimeout(()=>loading(sec,customersStuck()),250);
 });
 document.addEventListener('visibilitychange',()=>{if(!document.hidden&&customersStuck())setTimeout(()=>triggerCustomerReload('resume'),350);});

 /* Strong admin accordion state, no obsolete horizontal/super-admin navigation. */
 const adminViews=new Set(['admin-options']);
 function fixAdminNav(){
  const section=q('#view-admin-options');if(section){q('.admin-tabs',section)?.classList.add('pz-obsolete-admin-tabs');qa('[data-admin-tab="super"],[data-admin-pane="super"],[data-admin-tab="api"],[data-admin-pane="api"]',section).forEach(x=>x.remove());}
  const group=q('.admin-nav-group'),toggle=q('.admin-nav-toggle'),submenu=q('.admin-nav-submenu');if(!group||!toggle||!submenu)return;
  const active=q('.view.active-view')?.id?.replace('view-','')||'';const onAdmin=adminViews.has(active);
  if(onAdmin){submenu.hidden=false;toggle.setAttribute('aria-expanded','true');}
  qa('.admin-subnav',submenu).forEach(b=>b.classList.toggle('active',onAdmin&&q(`[data-admin-tab="${b.dataset.adminOpen}"]`)?.classList.contains('primary')));
 }
 document.addEventListener('click',e=>{const nav=e.target.closest('[data-view],[data-go]');if(nav&&!(nav.dataset.view||nav.dataset.go||'').startsWith('admin'))setTimeout(()=>{const s=q('.admin-nav-submenu'),t=q('.admin-nav-toggle');if(s){s.hidden=true;t?.setAttribute('aria-expanded','false');}},0);setTimeout(fixAdminNav,100);},true);

 const deps={
  'users.create':['users.view','admin.options.view'],'users.edit':['users.view','admin.options.view'],'users.disable':['users.view','admin.options.view'],'users.roles.assign':['users.view','roles.view','admin.options.view'],
  'roles.view':['admin.options.view'],'roles.create':['roles.view','admin.options.view'],'roles.edit':['roles.view','admin.options.view'],'roles.clone':['roles.view','admin.options.view'],'roles.delete':['roles.view','admin.options.view'],'roles.reset_user':['roles.view','admin.options.view'],
  'security.policies.view':['admin.options.view'],'security.policies.edit':['security.policies.view','admin.options.view'],'security.2fa.reset_user':['users.view','admin.options.view'],'security.sessions.end':['users.view','admin.options.view'],
  'smtp.view':['admin.options.view'],'smtp.edit':['smtp.view','admin.options.view'],'smtp.test':['smtp.view','admin.options.view'],'notifications.edit':['admin.options.view'],
  'integrations.edit':['integrations.view','admin.options.view'],'integrations.sync':['integrations.view'],'integrations.debug':['integrations.view','admin.options.view'],'system.options.edit':['admin.options.view'],
  'bookkeeping.manage':['bookkeeping.view'],'logs.view_team':['logs.view_own'],'logs.view_all':['logs.view_own'],
  'customers.view_contacts':['customers.view_basic'],'customers.view_links':['customers.view_basic'],'customers.view_history':['customers.view_basic'],'customers.create':['customers.view_basic'],'customers.edit':['customers.view_basic'],'customers.archive':['customers.view_basic'],'customers.delete':['customers.view_basic']
 };
 function permissionDependencies(){
  const pane=q('[data-admin-pane="roles"]')||q('#view-admin-options');if(!pane)return;
  const boxes=qa('input[type="checkbox"]',pane).filter(x=>(x.value||x.dataset.permission||'').includes('.'));
  const map=new Map(boxes.map(x=>[x.value||x.dataset.permission,x]));if(!map.size)return;
  const required=new Map();
  for(const [strong,needs] of Object.entries(deps))if(map.get(strong)?.checked)for(const key of needs){map.get(key)&&(map.get(key).checked=true);required.set(key,strong);}
  for(const [key,box] of map){const by=required.get(key);box.disabled=!!by;const label=box.closest('label');if(label){label.classList.toggle('pz-required-permission',!!by);if(by)label.title=`Durch ${by} erforderlich`;else label.removeAttribute('title');}}
  for(const box of boxes)if(!box.dataset.pzDep){box.dataset.pzDep='1';box.addEventListener('change',permissionDependencies);}
 }

 /* Settings status comes from one fresh source and starts in a loading state. */
 async function providerStatus(){
  const cards=qa('#integration-cards [data-provider]');for(const c of cards){const b=q('.badge',c);if(b){b.textContent='Wird geprüft …';b.dataset.connectionState='loading';}}
  try{const d=await pzPost('/api/v1/provider/navigation-status',{});for(const item of d.providers||[]){const card=q(`#integration-cards [data-provider="${item.provider}"]`),b=q('.badge',card);if(!b)continue;if(item.connected){b.textContent='Verbunden';b.dataset.connectionState='connected';}else if(item.reason==='missing'){b.textContent='Nicht eingerichtet';b.dataset.connectionState='not-configured';}else{b.textContent='Eingerichtet · Verbindung fehlgeschlagen';b.dataset.connectionState='configured-failed';b.title=item.detail||'';}}}catch(e){for(const b of qa('#integration-cards .badge')){b.textContent='Status nicht verfügbar';b.dataset.connectionState='configured-failed';b.title=e.message;}}
 }
 q('[data-view="settings"]')?.addEventListener('click',()=>setTimeout(providerStatus,80));

 /* Provider row assignment status and detail dialog. */
 const detail=document.createElement('dialog');detail.className='pz-provider-detail';detail.innerHTML='<div class="panel-head"><h3 data-pz-detail-title>Details</h3><button type="button" class="secondary" data-pz-detail-close>Schließen</button></div><div data-pz-detail-body></div>';document.body.append(detail);q('[data-pz-detail-close]',detail).onclick=()=>detail.close();
 const assign=document.createElement('dialog');assign.className='pz-assign-dialog';assign.innerHTML='<div class="panel-head"><h3>Kunden zuordnen</h3><button type="button" class="secondary" data-pz-assign-close>Schließen</button></div><div data-pz-assign-body></div>';document.body.append(assign);q('[data-pz-assign-close]',assign).onclick=()=>assign.close();
 async function getContext(){if(!context)context=await pzPost('/api/v1/next/context',{});return context;}
 async function getCustomers(){const d=await pzPost('/api/v1/customers/data',{});customers=d.customers||[];return customers;}
 function can(key){return !!context?.is_superadmin||(context?.permissions||[]).includes(key);}
 function assignmentState(row){return row?.assignment?.project_id?'green':row?.assignment?.customer_id?'blue':'red';}
 async function chooseCustomer(provider,row){
  const list=await getCustomers(),body=q('[data-pz-assign-body]',assign);body.innerHTML=`<p>Zuordnungsmerkmal: <strong>${h(row.assignment?.match_value||'wird aus dem Eintrag ermittelt')}</strong></p><label>Kunde<select data-pz-customer><option value="">Kunde wählen …</option>${list.map(c=>`<option value="${c.id}">${h(c.name)}</option>`).join('')}</select></label><div class="panel-actions"><button type="button" class="primary" data-pz-assign-one>Nur diesen Eintrag</button><button type="button" class="secondary" data-pz-assign-all>Alle passenden zuordnen</button></div><p class="list-status" data-pz-assign-status></p>`;
  async function go(bulk){const cid=Number(q('[data-pz-customer]',body).value),status=q('[data-pz-assign-status]',body);if(!cid){status.textContent='Bitte einen Kunden auswählen.';return;}try{status.textContent='Zuordnung wird gespeichert …';const r=await pzPost('/api/v1/provider/assign/customer',{provider,external_key:row.external_key,customer_id:cid,bulk});status.textContent=bulk?`${r.matched||1} passende Einträge zugeordnet.`:'Eintrag zugeordnet.';notify('Kundenzuordnung gespeichert','success');setTimeout(()=>{assign.close();q(`#view-${provider} [data-refresh]`)?.click();},450);}catch(e){status.textContent=e.message;}}
  q('[data-pz-assign-one]',body).onclick=()=>go(false);q('[data-pz-assign-all]',body).onclick=()=>go(true);assign.showModal();
 }
 async function chooseProject(provider,row){
  await getContext();const projects=(context.projects||[]).filter(p=>!p.customer_id||p.customer_id===row.assignment?.customer_id);const body=q('[data-pz-assign-body]',assign);q('h3',assign).textContent='Projekt zuordnen';body.innerHTML=`<label>Projekt<select data-pz-project><option value="">Projekt wählen …</option>${projects.map(p=>`<option value="${p.id}">${h(p.name)}</option>`).join('')}</select></label><button type="button" class="primary" data-pz-project-save>Zuordnen</button><p class="list-status"></p>`;q('[data-pz-project-save]',body).onclick=async()=>{const id=Number(q('[data-pz-project]',body).value);if(!id)return;try{await pzPost('/api/v1/provider/assign/project',{provider,external_key:row.external_key,project_id:id});notify('Projektzuordnung gespeichert','success');assign.close();q(`#view-${provider} [data-refresh]`)?.click();}catch(e){q('.list-status',body).textContent=e.message;}};assign.showModal();
 }
 async function openProviderDetail(provider,row){
  await getContext().catch(()=>{});q('[data-pz-detail-title]',detail).textContent=`${provider==='starface'?'STARFACE':provider==='teamviewer'?'TeamViewer':'Zammad'} · Details`;const body=q('[data-pz-detail-body]',detail),as=row.assignment||{};
  const customer=as.customer_name?`<div class="pz-assignment-fact"><small>Kunde</small>${can('customers.view_basic')?`<button type="button" class="pz-customer-link" data-open-customer="${as.customer_id}">${h(as.customer_name)}</button>`:`<strong>${h(as.customer_name)}</strong>`}${as.match_value?`<span>über ${h(as.match_value)}</span>`:''}</div>`:'';
  body.innerHTML=`<div class="pz-detail-assignment"><span class="pz-assignment-dot ${assignmentState(row)}"></span>${customer}${as.project_name?`<div class="pz-assignment-fact"><small>Projekt</small><strong>${h(as.project_name)}</strong></div>`:''}<div class="panel-actions">${!as.customer_id?'<button class="primary" data-detail-customer>Kunden zuordnen</button>':'<button class="secondary" data-detail-project>Projekt zuordnen</button>'}</div></div><dl class="pz-raw-fields">${Object.entries(row.raw||{}).sort(([x],[y])=>x.localeCompare(y)).map(([k,v])=>`<dt>${h(k)}</dt><dd>${h(typeof v==='object'?JSON.stringify(v):v)}</dd>`).join('')}</dl>`;
  q('[data-detail-customer]',body)?.addEventListener('click',()=>chooseCustomer(provider,row));q('[data-detail-project]',body)?.addEventListener('click',()=>chooseProject(provider,row));q('[data-open-customer]',body)?.addEventListener('click',e=>{detail.close();typeof openCustomer==='function'&&openCustomer(Number(e.currentTarget.dataset.openCustomer));});detail.showModal();
 }
 function decorateProvider(provider){
  const sec=q(`#view-${provider}`),trs=qa('tbody tr',sec),rows=providerRows[provider]||[];if(!sec)return;
  trs.forEach((tr,i)=>{const row=rows[i];if(!row)return;tr.dataset.pzAssigned=assignmentState(row);let dot=q('.pz-assignment-dot',tr);if(!dot){dot=document.createElement('span');dot.className='pz-assignment-dot';tr.firstElementChild?.prepend(dot);}dot.className=`pz-assignment-dot ${assignmentState(row)}`;
   if(!tr.dataset.pzDetail){tr.dataset.pzDetail='1';tr.addEventListener('click',e=>{if(e.target.closest('button,a,input,select,label'))return;if(provider!=='zammad')openProviderDetail(provider,row);});}
   let actions=q('.provider-actions',tr)||tr.lastElementChild;if(actions&&!q('[data-pz-assign-button]',tr)){const b=document.createElement('button');b.type='button';b.dataset.pzAssignButton='';b.className='secondary subtle pz-assign-mini';b.textContent=row.assignment?.customer_id?'Projekt zuordnen':'Kunden zuordnen';b.onclick=e=>{e.stopPropagation();row.assignment?.customer_id?chooseProject(provider,row):chooseCustomer(provider,row);};actions.append(b);}
  });
  assignmentFilter(sec);
 }
 function assignmentFilter(sec){const toolbar=q('.provider-toolbar',sec);if(!toolbar||q('[data-pz-assignment-filter]',toolbar))return;const s=document.createElement('select');s.dataset.pzAssignmentFilter='';s.innerHTML='<option value="all">Alle Zuordnungen</option><option value="green">Projekt zugeordnet</option><option value="blue">Kunde, Projekt fehlt</option><option value="red">Kunde fehlt</option>';toolbar.append(s);s.onchange=()=>qa('tbody tr',sec).forEach(tr=>tr.hidden=s.value!=='all'&&tr.dataset.pzAssigned!==s.value);}

 /* Customer detail: stable provider identity links, history, archive/delete. */
 const history=document.createElement('dialog');history.className='audit-dialog';history.innerHTML='<div class="audit-head"><strong>Historie</strong><button type="button" class="secondary">Schließen</button></div><div class="audit-list"></div>';document.body.append(history);q('button',history).onclick=()=>history.close();
 async function showHistory(type,id,title){q('.audit-head strong',history).textContent=title;q('.audit-list',history).innerHTML=spinner('Historie wird geladen');history.showModal();try{const d=await pzPost('/api/v1/history/object',{entity_type:type,entity_id:id});q('.audit-list',history).innerHTML=(d.history||[]).map(x=>`<article><strong>${h(new Date(x.created_at).toLocaleString('de-DE'))} · ${h(x.actor)}</strong><span>${h(x.action)}</span>${Object.keys(x.changes||{}).length?`<details><summary>Details</summary><pre>${h(JSON.stringify(x.changes,null,2))}</pre></details>`:''}</article>`).join('')||'<p class="muted">Noch keine Historieneinträge.</p>';}catch(e){q('.audit-list',history).innerHTML=`<p class="error">${h(e.message)}</p>`;}}
 async function augmentCustomer(id){
  const box=q('.customer-detail-dialog [data-detail]');if(!box)return;await getContext().catch(()=>{});
  if(!q('[data-pz-customer-history]',box)){const b=document.createElement('button');b.type='button';b.dataset.pzCustomerHistory='';b.className='secondary subtle pz-history-button';b.textContent='◴';b.title='Historie';b.setAttribute('aria-label','Historie anzeigen');q('h2',box)?.insertAdjacentElement('afterend',b);b.onclick=()=>showHistory('customer',id,'Kundenhistorie');}
  const pane=q('[data-pane="master"]',box);if(!pane||q('[data-pz-links]',pane)||!can('customers.view_links'))return;
  const card=document.createElement('article');card.dataset.pzLinks='';card.className='customer-master-card pz-links-card';pane.append(card);
  async function renderLinks(){try{const d=await pzPost('/api/v1/customers/links',{customer_id:id}),groups={zammad:[],starface:[],teamviewer:[]};for(const x of d.links||[])groups[x.provider]?.push(x);card.innerHTML=`<div class="panel-head"><div><p class="eyebrow">VERKNÜPFUNGEN</p><h3>Automatische Zuordnung</h3></div></div>${[['zammad','Zammad'],['starface','STARFACE'],['teamviewer','TeamViewer']].map(([p,label])=>`<section class="pz-link-group"><div class="pz-link-group-head"><strong>${label}</strong><button type="button" class="secondary subtle pz-link-add" data-add-link="${p}">+</button></div>${groups[p].length?groups[p].map(x=>`<div class="pz-link-row"><span>${h(x.display_name&&p==='teamviewer'?`${x.display_name} · ${x.link_value}`:x.link_value)}</span><button type="button" class="secondary subtle danger pz-trash" data-delete-link="${x.id}" title="Verknüpfung entfernen" aria-label="Verknüpfung entfernen">⌫</button></div>`).join(''):'<small class="muted">Keine Verknüpfung</small>'}</section>`).join('')}<div class="panel-actions pz-customer-life"><button type="button" class="secondary" data-archive-customer>Kunde archivieren</button><button type="button" class="secondary subtle danger" data-delete-customer>Kunde löschen</button></div>`;
    qa('[data-delete-link]',card).forEach(b=>b.onclick=async()=>{if(!confirm('Verknüpfung entfernen? Alle darüber zugeordneten Einträge werden wieder gelöst.'))return;await pzPost('/api/v1/customers/link/delete',{id:Number(b.dataset.deleteLink)});notify('Verknüpfung entfernt','success');renderLinks();});
    qa('[data-add-link]',card).forEach(b=>b.onclick=()=>addLink(b.dataset.addLink));q('[data-archive-customer]',card).onclick=async()=>{if(!confirm('Kunden archivieren? Die Daten und Historie bleiben erhalten.'))return;await pzPost('/api/v1/customers/archive',{customer_id:id,archived:true});notify('Kunde archiviert','success');};q('[data-delete-customer]',card).onclick=async()=>{if(!confirm('Kunden wirklich löschen? Alle Zammad-, STARFACE- und TeamViewer-Verknüpfungen werden aufgehoben. Externe Einträge bleiben erhalten.'))return;await pzPost('/api/v1/customers/delete',{customer_id:id});notify('Kunde gelöscht','success');q('.customer-detail-dialog')?.close();q('[data-view="customers"]')?.click();};
   }catch(e){card.innerHTML=`<p class="error">${h(e.message)}</p>`;}}
   async function addLink(provider){const type=provider==='zammad'?'email':provider==='starface'?'phone':'teamviewer_id',value=prompt(provider==='teamviewer'?'TeamViewer-ID eingeben':provider==='zammad'?'Zammad-E-Mail-Adresse eingeben':'STARFACE-Rufnummer eingeben');if(!value)return;let display='';if(provider==='teamviewer')display=prompt('Gerätename (optional)')||'';try{const c=await pzPost('/api/v1/customers/link/candidates',{customer_id:id,provider,link_type:type,link_value:value}),bulk=c.count?confirm(`${c.count} passende Einträge gefunden. Sollen diese jetzt dem Kunden zugeordnet werden?`):true;const r=await pzPost('/api/v1/customers/link/add',{customer_id:id,provider,link_type:type,link_value:value,display_name:display,bulk});notify(`${r.matched||0} Einträge zugeordnet`,'success');renderLinks();}catch(e){notify(e.message,'error');}}
   renderLinks();
  }
  if(typeof openCustomer==='function'&&!window.pzCustomerHistoryWrapped){const original=openCustomer;openCustomer=async function(id){await original(id);setTimeout(()=>augmentCustomer(id),0);};window.pzCustomerHistoryWrapped=true;}

 /* Manual STARFACE callback button. */
 function missedButtons(){for(const row of qa('.missed-call-row')){if(q('[data-pz-callback]',row))continue;const call=(providerRows.starface||[]).find(r=>{const raw=r.raw||{};return String(raw.callerNumber||'')===String(q('small',row)?.textContent||'').split(' · ')[0];});if(!call)continue;const b=document.createElement('button');b.type='button';b.className='secondary subtle pz-callback';b.dataset.pzCallback='';b.title='Als zurückgerufen markieren';b.setAttribute('aria-label','Zurückgerufen');b.textContent='↩☎';b.onclick=async()=>{try{await pzPost('/api/v1/starface/callback/manual',{external_key:call.external_key});row.remove();notify('Als zurückgerufen markiert','success');}catch(e){notify(e.message,'error');}};row.append(b);}}

 function whiteNames(){qa('.customer-card h3,.compact-customer strong,.compact-contact strong,#view-teamviewer tbody strong,#view-teamviewer .pz-mobile-summary strong').forEach(x=>x.classList.add('pz-primary-text'));}
 function settingsOrder(){const s=q('#view-settings');if(!s)return;const profile=q('[data-profile-settings]',s),cards=q('#integration-cards',s),win=[...s.children].find(x=>x.matches?.('article.panel')&&/Windows-Client/.test(x.textContent||'')),api=q('[data-user-api-settings]',s);if(profile)s.prepend(profile);if(cards){profile?.after(cards);if(win)cards.after(win);if(api)win?.after(api);}}

 function autoLoad(){
  const view=q('.view.active-view');if(!view)return;compactRefresh(view);
  const id=view.id?.replace('view-','');if(id==='customers'&&q('[data-customer-list]',view)?.children.length===0)q('[data-view="customers"]')?.click();
  if(id==='settings'){loading(view,true,'Einstellungen werden geladen');providerStatus().finally(()=>loading(view,false));settingsOrder();}
  if(id==='admin-options'){fixAdminNav();permissionDependencies();}
 }
 const observer=new MutationObserver(()=>requestAnimationFrame(()=>{customerIcon();dashboardPencil();compactRefresh();whiteNames();fixAdminNav();permissionDependencies();missedButtons();settingsOrder();for(const p of ['zammad','starface','teamviewer'])decorateProvider(p);const sec=q('#view-customers');if(sec&&!customersStuck())loading(sec,false);}));observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
 document.addEventListener('click',e=>{if(e.target.closest('[data-view],[data-go]'))setTimeout(autoLoad,80);},true);
 setTimeout(async()=>{try{context=await getContext();}catch(_){}customerIcon();dashboardPencil();compactRefresh();whiteNames();fixAdminNav();permissionDependencies();settingsOrder();providerStatus();autoLoad();},600);
})();
