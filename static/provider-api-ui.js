(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const escText=v=>typeof esc==='function'?esc(v):String(v??'');
 const notify=(m,l='info',t=5000)=>window.pzToast?window.pzToast(m,l,t):typeof toast==='function'?toast(m):null;

 // Zammad rows always open the ProjektZeit ticket detail view. The external jump stays inside that detail view.
 function wireZammadRows(){
  for(const row of qa('#view-zammad tbody tr')){
   if(row.dataset.pzTicketOpen)return;row.dataset.pzTicketOpen='1';
   row.addEventListener('click',event=>{
    if(event.target.closest('button,a,input,select,textarea,label'))return;
    const ticket=qa('button',row).find(b=>/^ticket$/i.test(b.textContent.trim()));
    if(ticket){event.preventDefault();event.stopPropagation();ticket.click();}
   });
  }
  for(const link of qa('.ticket-open-zammad'))link.textContent='In Zammad öffnen';
 }
 const zammadView=q('#view-zammad');if(zammadView)new MutationObserver(wireZammadRows).observe(zammadView,{childList:true,subtree:true});
 new MutationObserver(wireZammadRows).observe(document.body,{childList:true,subtree:true});setTimeout(wireZammadRows,300);

 // STARFACE and TeamViewer: render local cache first, refresh provider in parallel, then repaint from cache.
 const refreshState=new Map();
 function pLabel(p){return p==='starface'?'STARFACE':'TeamViewer';}
 async function repaint(provider){try{if(typeof providerLoaders!=='undefined'&&providerLoaders[provider])await providerLoaders[provider](false);}catch(_){}}
 async function startProviderRefresh(provider){
  if(!['starface','teamviewer'].includes(provider)||refreshState.get(provider)==='running')return;
  refreshState.set(provider,'running');const section=q(`#view-${provider}`),status=q('.list-status',section);
  const days=Number(q('[data-days]',section)?.value||0);
  try{
   const started=await post('/api/v1/provider/refresh/start',{provider,days});
   let id=started.job?.id||'';let attempts=0;
   const poll=async()=>{
    try{
     const data=await post('/api/v1/provider/refresh/job',{provider}),job=data.job||{};
     if(id&&job.id&&job.id!==id)return;
     if(job.state==='running'){if(status)status.dataset.backgroundRefresh='Aktualisierung im Hintergrund …';setTimeout(poll,900);return;}
     refreshState.delete(provider);if(status)delete status.dataset.backgroundRefresh;
     await repaint(provider);
     if(job.state==='success'){
      const r=job.result||{};notify(`${pLabel(provider)} aktualisiert · ${r.new||0} neu`,'success',3500);
     }else if(job.access==='invalid'){
      notify(`${pLabel(provider)}-Zugang ist nicht gültig. Gespeicherte Einträge bleiben erhalten, sind aber ausgeblendet.`,'warning',7000);
     }else if(job.error){
      notify(`${pLabel(provider)} konnte nicht aktualisiert werden. Lokale Daten bleiben erhalten.`,'warning',6000);
     }
    }catch(error){attempts++;if(attempts<6){setTimeout(poll,1200);return;}refreshState.delete(provider);notify(`${pLabel(provider)}-Status konnte nicht geladen werden. Lokale Daten bleiben sichtbar.`,'warning',5500);}
   };
   setTimeout(poll,400);
  }catch(error){refreshState.delete(provider);await repaint(provider);notify(error.message,'warning',6000);}
 }
 for(const provider of ['starface','teamviewer']){
  q(`[data-view="${provider}"]`)?.addEventListener('click',()=>setTimeout(()=>startProviderRefresh(provider),80));
  q(`#view-${provider}`)?.addEventListener('click',event=>{if(event.target.closest('[data-refresh]'))setTimeout(()=>startProviderRefresh(provider),60);});
 }
 window.addEventListener('starface-connected',()=>setTimeout(()=>startProviderRefresh('starface'),250));

 const tokenLabels={
  'customers.read':'Kunden lesen','projects.read':'Projekte lesen','time.read':'Zeiterfassung lesen','tickets.read':'Zammad-Tickets lesen',
  'starface.read':'STARFACE-Historie lesen','teamviewer.read':'TeamViewer-Historie lesen','admin.users.read':'Benutzer lesen',
  'admin.integrations.read':'Integrationsstatus lesen','admin.logs.read':'System-/Provider-Logs lesen'
 };
 function tokenDate(v){if(!v)return 'Nie';const d=new Date(v);return Number.isNaN(+d)?v:d.toLocaleString('de-DE');}
 async function copyValue(value){try{await navigator.clipboard.writeText(value);notify('API-Token kopiert','success');}catch(_){notify('Kopieren nicht möglich','error');}}
 function endpoint(kind,action){return kind==='admin'?`/api/v1/admin/api/tokens/${action}`:`/api/v1/api/tokens/${action}`;}
 async function renderTokens(kind,root){
  const body=q('[data-api-body]',root);if(!body)return;body.innerHTML='<p class="muted">API-Tokens werden geladen …</p>';
  try{
   const data=await post(endpoint(kind,'list'),{}),scopes=data.scopes||{},tokens=data.tokens||[];
   body.innerHTML=`<div class="api-intro"><p>${kind==='admin'?'Administrative API-Tokens können ausdrücklich freigegebene Admin-Funktionen verwenden.':'Persönliche API-Tokens sind an deinen Benutzer gebunden und sehen nur deine freigegebenen Daten.'}</p><p class="muted">OpenAPI: <code>/api/v1/external/openapi.json</code> · Tokens werden nur einmal vollständig angezeigt.</p></div><form data-api-create><div class="field-grid"><label>Name<input name="name" maxlength="120" placeholder="z. B. Mein ChatGPT" required></label><label>Gültigkeit<select name="expires_days"><option value="0">Unbegrenzt</option><option value="30">30 Tage</option><option value="90">90 Tage</option><option value="365">365 Tage</option></select></label></div><div class="api-scope-grid">${Object.entries(scopes).map(([key,label])=>`<label><input type="checkbox" name="scope" value="${escText(key)}"> <span>${escText(label)}</span><small>${escText(key)}</small></label>`).join('')||'<p class="muted">Für deinen Benutzer sind aktuell keine API-Berechtigungen verfügbar.</p>'}</div><button class="primary" ${Object.keys(scopes).length?'':'disabled'}>API-Token generieren</button></form><div data-api-once></div><div class="api-token-list">${tokens.length?tokens.map(t=>`<article class="api-token-row ${t.active?'':'revoked'}" data-token-id="${t.id}"><div><strong>${escText(t.name)}</strong><small>${escText(t.prefix)} · erstellt ${tokenDate(t.created_at)}${t.last_used_at?' · zuletzt '+tokenDate(t.last_used_at):''}${t.expires_at?' · gültig bis '+tokenDate(t.expires_at):''}</small><div class="api-token-scopes">${(t.permissions||[]).map(x=>`<span>${escText(tokenLabels[x]||x)}</span>`).join('')}</div></div>${t.active?'<button type="button" class="secondary subtle danger" data-api-revoke>Widerrufen</button>':'<span class="badge">Widerrufen</span>'}</article>`).join(''):'<p class="muted">Noch keine API-Tokens vorhanden.</p>'}</div>`;
   const form=q('[data-api-create]',body);if(form)form.onsubmit=async e=>{e.preventDefault();const permissions=qa('input[name="scope"]:checked',form).map(x=>x.value);try{const created=await post(endpoint(kind,'create'),{name:form.name.value,expires_days:Number(form.expires_days.value),permissions});const once=q('[data-api-once]',body);once.innerHTML=`<div class="api-token-once"><strong>Diesen Token jetzt kopieren. Er wird danach nicht mehr vollständig angezeigt.</strong><code>${escText(created.token)}</code><button type="button" class="secondary" data-copy-token>Kopieren</button></div>`;q('[data-copy-token]',once).onclick=()=>copyValue(created.token);form.reset();await renderTokensKeepOnce(kind,root,created.token);}catch(error){notify(error.message,'error');}};
   qa('[data-api-revoke]',body).forEach(button=>button.onclick=async()=>{const id=button.closest('[data-token-id]')?.dataset.tokenId;if(!id||!confirm('API-Token wirklich widerrufen?'))return;try{await post(endpoint(kind,'revoke'),{id:Number(id)});notify('API-Token widerrufen','success');renderTokens(kind,root);}catch(error){notify(error.message,'error');}});
  }catch(error){body.innerHTML=`<p class="error">${escText(error.message)}</p>`;}
 }
 async function renderTokensKeepOnce(kind,root,token){await renderTokens(kind,root);const body=q('[data-api-body]',root),once=q('[data-api-once]',body);if(once&&token){once.innerHTML=`<div class="api-token-once"><strong>Diesen Token jetzt kopieren. Er wird danach nicht mehr vollständig angezeigt.</strong><code>${escText(token)}</code><button type="button" class="secondary" data-copy-token>Kopieren</button></div>`;q('[data-copy-token]',once).onclick=()=>copyValue(token);}}

 function ensureUserApi(){
  const settings=q('#view-settings');if(!settings||q('[data-user-api-settings]',settings))return;
  const details=document.createElement('details');details.className='panel settings-fold api-settings';details.dataset.userApiSettings='';
  details.innerHTML='<summary><span>API</span><span class="fold-status">ChatGPT & Automationen</span></summary><div class="fold-body" data-api-body></div>';
  settings.append(details);details.addEventListener('toggle',()=>{if(details.open)renderTokens('user',details);});
 }
 function ensureAdminApi(){
  const section=q('#view-admin-options');if(!section||q('[data-admin-tab="api"]',section))return;const tabs=q('.admin-tabs',section);if(!tabs)return;
  const button=document.createElement('button');button.className='secondary';button.dataset.adminTab='api';button.textContent='API';tabs.append(button);
  const pane=document.createElement('div');pane.className='hidden';pane.dataset.adminPane='api';pane.innerHTML='<article class="panel api-admin-panel"><div class="panel-head"><div><p class="eyebrow">ADMIN-API</p><h3>Administrative API-Tokens</h3></div></div><div data-api-body></div></article>';section.append(pane);
  button.onclick=()=>{qa('[data-admin-tab]',section).forEach(b=>b.className=b===button?'primary':'secondary');qa('[data-admin-pane]',section).forEach(p=>p.classList.toggle('hidden',p!==pane));renderTokens('admin',pane);};
 }
 ensureUserApi();ensureAdminApi();new MutationObserver(()=>{ensureUserApi();ensureAdminApi();}).observe(document.body,{childList:true,subtree:true});
})();
