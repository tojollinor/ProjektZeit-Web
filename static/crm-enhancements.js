(()=>{
 const $q=(s,r=document)=>r.querySelector(s),$qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const e=v=>typeof esc==='function'?esc(v):String(v??'');
 const a=v=>typeof attr==='function'?attr(v):e(v).replaceAll('"','&quot;');

 /* Stackable Komodo-style toasts. */
 let stack=$q('#toast-stack');
 if(!stack){stack=document.createElement('div');stack.id='toast-stack';stack.setAttribute('aria-live','polite');document.body.append(stack);}
 function pzToast(text,level='info',timeout=3600){
  const item=document.createElement('div');item.className=`pz-toast ${level}`;
  const dot=document.createElement('i'),msg=document.createElement('span'),close=document.createElement('button');msg.textContent=text;close.type='button';close.className='pz-toast-dismiss';close.textContent='×';close.setAttribute('aria-label','Benachrichtigung schließen');item.append(dot,msg,close);stack.append(item);
  let timer;const dismiss=()=>{clearTimeout(timer);item.remove();};close.onclick=event=>{event.preventDefault();event.stopPropagation();dismiss();};item.onpointerenter=()=>clearTimeout(timer);item.onfocusin=()=>clearTimeout(timer);item.onpointerleave=()=>{if(!item.contains(document.activeElement))timer=setTimeout(dismiss,timeout);};item.onfocusout=()=>{timer=setTimeout(dismiss,timeout);};
  requestAnimationFrame(()=>item.classList.add('show'));timer=setTimeout(dismiss,timeout);
  return item;
 }
 try{toast=pzToast}catch(_){/* global toast may be lexical in some browsers */}
 window.pzToast=pzToast;

 const labelProvider=p=>p==='starface'?'STARFACE':p==='teamviewer'?'TeamViewer':p==='zammad'?'Zammad':p;

 /* Main Logs view. */
 const nav=$q('.sidebar nav'),settingsButton=$q('[data-view="settings"]',nav);
 const logsButton=document.createElement('button');logsButton.className='nav';logsButton.dataset.view='logs';logsButton.innerHTML='<span>≡</span>Logs';
 if(nav&&!$q('[data-view="logs"]',nav))nav.insertBefore(logsButton,settingsButton||null);
 const logsSection=document.createElement('section');logsSection.id='view-logs';logsSection.className='view';
 logsSection.innerHTML=`<article class="panel logs-panel"><div class="panel-head"><div><p class="eyebrow">BETRIEBSJOURNAL</p><h3>Logs</h3></div><button class="secondary" data-log-refresh>Aktualisieren</button></div><div class="provider-toolbar"><select data-log-category><option value="">Alle Kategorien</option><option value="starface">STARFACE</option><option value="teamviewer">TeamViewer</option><option value="zammad">Zammad</option><option value="system">System</option></select><select data-log-level><option value="">Alle Status</option><option value="info">Info</option><option value="success">Erfolg</option><option value="warning">Warnung</option><option value="error">Fehler</option></select></div><p class="list-status" data-log-status></p><div class="log-list" data-log-list></div></article>`;
 $q('main')?.insertBefore(logsSection,$q('#toast'));
 async function renderLogs(){
  const category=$q('[data-log-category]',logsSection).value,level=$q('[data-log-level]',logsSection).value,status=$q('[data-log-status]',logsSection),list=$q('[data-log-list]',logsSection);
  status.textContent='Logs werden geladen …';
  try{const data=await post('/api/v1/logs/list',{category,level,limit:500});list.replaceChildren();for(const row of data.logs||[]){const card=document.createElement('article');card.className=`log-row ${row.level}`;card.innerHTML=`<i></i><div><strong>${e(labelProvider(row.category))} · ${e(row.action)}</strong><p>${e(row.message)}</p><small>${e(new Date(row.created_at).toLocaleString('de-DE',{timeZone:'Europe/Berlin'}))}</small>${row.details&&Object.keys(row.details).length?`<details><summary>Technische Details</summary><pre>${e(JSON.stringify(row.details,null,2))}</pre></details>`:''}</div>`;list.append(card);}status.textContent=`${(data.logs||[]).length} Einträge`;}catch(error){status.textContent=error.message;pzToast(error.message,'error');}
 }
 logsButton.onclick=()=>{showView('logs');$q('#page-title').textContent='Logs';renderLogs();};
 $q('[data-log-refresh]',logsSection).onclick=renderLogs;$q('[data-log-category]',logsSection).onchange=renderLogs;$q('[data-log-level]',logsSection).onchange=renderLogs;

 /* Workshop raw-debug console. */
 function ensureDebugPanel(){
  const section=$q('#view-workshop');if(!section||$q('[data-raw-debug]',section))return;
  const panel=document.createElement('article');panel.className='panel raw-debug-panel';panel.dataset.rawDebug='';
  panel.innerHTML=`<div class="panel-head"><div><p class="eyebrow">ROHDATEN</p><h3>Debug-Ausgabe</h3></div></div><p class="muted">Bereinigte Rohantworten der Schnittstellen. Zugangsdaten, OAuth-Tokens und Auth-Header werden nicht ausgegeben.</p><div class="provider-toolbar"><select data-debug-provider><option value="starface">STARFACE</option><option value="teamviewer">TeamViewer</option><option value="zammad">Zammad</option></select><button class="primary" data-debug-load>Daten holen</button><button class="secondary" data-debug-copy>Kopieren</button></div><p class="list-status" data-debug-status>Noch keine Daten geladen.</p><textarea class="debug-raw-text" data-debug-text readonly spellcheck="false" placeholder="Hier erscheinen die Rohdaten …"></textarea>`;
  section.append(panel);
  const text=$q('[data-debug-text]',panel),status=$q('[data-debug-status]',panel);
  $q('[data-debug-load]',panel).onclick=async()=>{const provider=$q('[data-debug-provider]',panel).value;status.textContent=`${labelProvider(provider)} wird abgefragt …`;pzToast(`${labelProvider(provider)} · Debug-Daten werden geholt`,'info');try{const data=await post('/api/v1/debug/raw',{provider});text.value=JSON.stringify(data,null,2);status.textContent=`${labelProvider(provider)} · ${data.fetched_at||''} · HTTP ${Array.isArray(data.http_status)?data.http_status.join('/'):data.http_status}`;pzToast(`${labelProvider(provider)} · Debug-Daten erfolgreich geladen`,'success');}catch(error){status.textContent=error.message;pzToast(`${labelProvider(provider)} · ${error.message}`,'error');}};
  $q('[data-debug-copy]',panel).onclick=async()=>{if(!text.value)return;try{await navigator.clipboard.writeText(text.value);pzToast('Debug-Ausgabe kopiert','success');}catch(_){text.select();document.execCommand('copy');pzToast('Debug-Ausgabe kopiert','success');}};
 }
 ensureDebugPanel();
 $q('[data-view="workshop"]')?.addEventListener('click',ensureDebugPanel);

 /* History buttons in settings cards. */
 async function archiveStatus(card,provider){
  let line=$q('[data-archive-state]',card);if(!line){line=document.createElement('p');line.className='integration-meta archive-state';line.dataset.archiveState='';card.append(line);}
  try{const data=await post('/api/v1/archive/status',{}),s=(data.states||[]).find(x=>x.provider===provider);if(!s)return;line.textContent=s.total_records?`${s.total_records} archivierte Datensätze · ältester: ${window.pzDate.dateTime(s.oldest_at)} · neuester: ${window.pzDate.dateTime(s.newest_at)} · Sync: ${window.pzDate.dateTime(s.last_sync_at)}`:'Noch keine History archiviert.';}catch(_){line.textContent='History-Status derzeit nicht verfügbar.';}
 }
 function enhanceIntegrationCards(){
  for(const provider of ['starface','teamviewer']){
   const card=$q(`[data-provider="${provider}"]`);if(!card)continue;
   const actions=$q('.panel-actions',card);if(actions&&!$q('[data-history-load]',card)){
    const button=document.createElement('button');button.type='button';button.className='secondary';button.dataset.historyLoad=provider;button.textContent='History laden';if(provider==='starface'&&$q('.missing-secret',card)){button.disabled=true;button.title='Client-Secret fehlt. Bitte einen Administrator informieren.';}actions.append(button);
    button.onclick=async()=>{button.disabled=true;pzToast(`${labelProvider(provider)} · Vollständiger History-Import gestartet`,'info',5000);const status=$q('.integration-status',card);if(status)status.textContent='History wird so weit wie möglich geladen. Das kann etwas dauern …';try{const r=await post('/api/v1/archive/sync',{provider,full:true});const message=`${labelProvider(provider)} History · ${r.received} geprüft · ${r.new} neu · ${r.total_records} gespeichert`;pzToast(message,'success',6500);if(status){status.className='integration-status success';status.textContent=message;}archiveStatus(card,provider);}catch(error){pzToast(`${labelProvider(provider)} · ${error.message}`,'error',7000);if(status){status.className='integration-status failure';status.textContent=error.message;}}finally{button.disabled=false;}};
   }
   if(!card.dataset.archiveStatusReady){card.dataset.archiveStatusReady='1';archiveStatus(card,provider);}
  }
 }
 const settingsObserver=new MutationObserver(enhanceIntegrationCards);const integrationCards=$q('#integration-cards');if(integrationCards)settingsObserver.observe(integrationCards,{childList:true,subtree:true});
 $q('[data-view="settings"]')?.addEventListener('click',()=>setTimeout(enhanceIntegrationCards,100));setTimeout(enhanceIntegrationCards,300);

 /* Provider refresh notifications. */
 for(const section of $qa('.provider-view')){
  const button=$q('[data-refresh]',section),provider=section.dataset.source;if(!button)continue;
  button.addEventListener('click',()=>{pzToast(`${labelProvider(provider)} · Aktualisierung gestartet`,'info');let tries=0;const timer=setInterval(()=>{tries++;const status=$q('.list-status',section);if((!button.disabled&&status&&!/werden geladen/i.test(status.textContent))||tries>80){clearInterval(timer);if(tries>80)return;const failed=/fehler|nicht erreichbar|abgewiesen|ungültig/i.test(status.textContent);pzToast(`${labelProvider(provider)} · ${status.textContent}`,failed?'error':'success',5500);}},250);});
 }

 /* Phone editor. */
 const phoneDialog=document.createElement('dialog');phoneDialog.className='phone-edit-dialog';phoneDialog.innerHTML=`<form data-phone-edit><h3>Rufnummer bearbeiten</h3><label>Rufnummer<input name="number" required></label><label>Typ<select name="label"></select></label><div class="panel-actions"><button type="button" class="secondary" data-phone-cancel>Abbrechen</button><button class="primary">Speichern</button></div></form>`;document.body.append(phoneDialog);$q('[data-phone-cancel]',phoneDialog).onclick=()=>phoneDialog.close();
 const kinds=['Festnetz','Mobil','Privat','Zentrale','Durchwahl','Fax','Sonstige'];
 function editPhone(phone,scope,customerId){const form=$q('[data-phone-edit]',phoneDialog);form.number.value=phone.number||'';form.label.innerHTML=kinds.map(k=>`<option ${k===(phone.label||'Sonstige')?'selected':''}>${e(k)}</option>`).join('');form.onsubmit=async ev=>{ev.preventDefault();try{await post('/api/v1/customers/phone/update',{id:phone.id,scope,number:form.number.value,label:form.label.value});phoneDialog.close();pzToast('Rufnummer gespeichert','success');openCustomer(customerId);}catch(error){pzToast(error.message,'error');}};phoneDialog.showModal();}
 async function deletePhone(phone,scope,customerId){try{await post('/api/v1/customers/phone/delete',{id:phone.id,scope});pzToast('Rufnummer gelöscht','success');openCustomer(customerId);}catch(error){pzToast(error.message,'error');}}
 function phoneRows(phones,scope,customerId){const wrap=document.createElement('div');wrap.className='phone-rows';for(const phone of phones||[]){const row=document.createElement('div');row.className='phone-row';const digits=String(phone.number||'').replace(/[^+\d]/g,'');row.innerHTML=`<div><small>${e(phone.label||'Rufnummer')}</small><strong>${e(phone.number)}</strong></div><div class="phone-actions"><a class="secondary phone-call" href="tel:${a(digits)}">☎ Anrufen</a><button class="secondary subtle" type="button" data-edit>Bearbeiten</button><button class="secondary subtle danger" type="button" data-delete aria-label="Rufnummer löschen">×</button></div>`;$q('[data-edit]',row).onclick=()=>editPhone(phone,scope,customerId);$q('[data-delete]',row).onclick=()=>deletePhone(phone,scope,customerId);wrap.append(row);}if(!(phones||[]).length){const p=document.createElement('p');p.className='muted';p.textContent='Keine Rufnummern hinterlegt.';wrap.append(p);}return wrap;}

 let sfUsers=null;
 async function starfaceUsers(){if(sfUsers)return sfUsers;try{const data=await post('/api/v1/starface/users',{});sfUsers=new Map((data.users||[]).map(x=>[String(x.extension),x.name]));}catch(_){sfUsers=new Map();}return sfUsers;}
 function party(value,map){const raw=String(value||'–'),digits=raw.replace(/\D/g,'');return digits&&digits.length<=5&&map.has(digits)?map.get(digits):raw;}
 function callKind(raw){const direction=String(raw.direction||'').toUpperCase(),result=String(raw.result||'').toUpperCase(),seconds=Number(raw.duration);if(direction==='OUTBOUND'&&/REJECT|DECLIN|BUSY/.test(result))return ['rejected','Anruf abgelehnt','⊘'];if(direction==='OUTBOUND'&&Number.isFinite(seconds)&&seconds<3)return ['not-reached','Nicht erreicht','×'];if(direction==='INBOUND'&&/MISS|NO_ANSWER/.test(result))return ['missed','Verpasster Anruf','↙'];if(direction==='OUTBOUND')return ['outgoing','Ausgehender Anruf','↗'];return ['incoming','Eingehender Anruf','↘'];}
 function formatDuration(raw){const s=Number(raw.duration);if(!Number.isFinite(s))return '–';return s<60?`${s} s`:`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')} min`;}
 async function rebuildHistory(box,data){const history=$q('[data-pane="history"]',box);if(!history)return;const map=data.starface_status?.connected?await starfaceUsers():new Map(),events=data.activity||[];const list=document.createElement('div');list.className='activity-list';for(const event of events){const r=event.raw||{},article=document.createElement('article');if(event.provider==='starface'){const [kind,title,mark]=callKind(r);article.innerHTML=`<span class="provider-label">STARFACE</span><div class="call-line"><span class="call-status ${kind}" title="${a(title)}" aria-label="${a(title)}"><b>☎</b><i>${e(mark)}</i></span><strong>${e(party(r.callerNumber,map))} → ${e(party(r.calledNumber,map))}</strong><span>${e(formatDuration(r))}</span></div><small>${e(event.occurred_at?new Date(event.occurred_at).toLocaleString('de-DE',{timeZone:'Europe/Berlin'}):'Zeitpunkt unbekannt')}</small>`;}else if(event.provider==='teamviewer'){article.innerHTML=`<span class="provider-label">TEAMVIEWER</span><strong>${e(r.devicename||r.device_name||'Gerät')} · ${e(r.username||'–')}</strong><small>${e(window.pzDate.dateTime(r.start_date||event.occurred_at))}</small>`;}else{article.innerHTML=`<span class="provider-label">ZAMMAD</span><strong>${e(r.number||r.id||'')} · ${e(r.title||event.summary||'')}</strong><small>${e(window.pzDate.dateTime(r.updated_at||event.occurred_at))}</small>`;}list.append(article);}if(!events.length){list.innerHTML='<p class="muted">Noch kein zuordenbarer Verlauf vorhanden.</p>';}history.replaceChildren(list);if(data.starface_status&&!data.starface_status.connected){const note=document.createElement('p');note.className='provider-disconnected-note';note.textContent=data.starface_status.detail||'STARFACE ist nicht verbunden.';history.prepend(note);}}

 /* Customer 24h timeline. */
 function ensureTimelineTab(box,customerId){window.pzTimeWorkspace?.attachCustomer(box,customerId);}

 async function enhanceCustomer(customerId){const box=$q('.customer-detail-dialog [data-detail]');if(!box)return;let data;try{data=await loadCustomerDetail(customerId);}catch(_){return;}const c=data.customer||{};const master=$q('[data-pane="master"]',box);if(master){const companyList=$q('.customer-detail-grid>article:first-child .phone-list',master);if(companyList)companyList.replaceWith(phoneRows(c.phones||[],'company',customerId));const contactCards=$qa('.contact-card',master);(c.contacts||[]).forEach((contact,index)=>{const list=$q('.phone-list',contactCards[index]);if(list)list.replaceWith(phoneRows(contact.phones||[],'contact',customerId));});}
  const deviceForm=$q('[data-add-device]',box),deviceSelect=$q('select[name="device"]',deviceForm);if(deviceForm&&deviceSelect&&!$q('.customer-device-search',deviceForm)){const input=document.createElement('input');input.type='search';input.className='customer-device-search';input.placeholder='TeamViewer-Gerät oder ID suchen …';deviceForm.prepend(input);input.oninput=()=>{const q=input.value.trim().toLocaleLowerCase('de-DE');for(const option of deviceSelect.options){if(!option.value){option.hidden=false;continue;}option.hidden=!option.textContent.toLocaleLowerCase('de-DE').includes(q);}if(deviceSelect.selectedOptions[0]?.hidden)deviceSelect.value='';};}
  ensureTimelineTab(box,customerId);await rebuildHistory(box,data);
 }
 if(typeof openCustomer==='function'){const original=openCustomer;openCustomer=async function(id){await original(id);await enhanceCustomer(id);};}
})();
