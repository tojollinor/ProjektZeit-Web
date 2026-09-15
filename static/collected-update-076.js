/* Collected 0.7.6 UI refinements: provider ownership, mail branding and compact actions. */
(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const h=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const svg={
  edit:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 16.5V20h3.5L18.1 9.4l-3.5-3.5L4 16.5Zm16.7-9.7a1 1 0 0 0 0-1.4l-2.1-2.1a1 1 0 0 0-1.4 0l-1.6 1.6 3.5 3.5 1.6-1.6Z"/></svg>',
  history:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4a8 8 0 1 1-7.4 4.9l-2.2-.1L5.5 5l.1 2A10 10 0 1 0 12 2v2Zm-1 3h2v5.2l3.3 2-1 1.7-4.3-2.6V7Z"/></svg>',
  eye:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5c-7 0-10 7-10 7s3 7 10 7 10-7 10-7-3-7-10-7Zm0 12a5 5 0 1 1 0-10 5 5 0 0 1 0 10Zm0-8a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/></svg>'
 };
 function message(text,type='success'){if(typeof window.pzToast==='function')window.pzToast(text,type);else if(typeof notify==='function')notify(text,type);}
 function iconize(button,type,label){if(!button||button.dataset.iconized076)return;button.dataset.iconized076='1';button.classList.add('icon-action');button.innerHTML=svg[type];button.title=label;button.setAttribute('aria-label',label);}
 function normalizeActions(root=document){
  for(const button of qa('button',root)){
   const text=(button.textContent||'').trim();
   if(text==='Bearbeiten')iconize(button,'edit','Bearbeiten');
   else if(text==='History'||text==='Historie')iconize(button,'history','Verlauf anzeigen');
   else if(text==='Anzeigen'&&button.closest('#view-logs,[data-log-list],.log-list'))iconize(button,'eye','Log anzeigen');
  }
 }

 let syncData=null,syncBlocked=false,syncPromise=null;
 async function getSync(force=false){
  if(syncBlocked)return null;if(syncData&&!force)return syncData;if(syncPromise)return syncPromise;
  syncPromise=post('/api/v1/company/sync/status',{}).then(data=>(syncData=data)).catch(error=>{if(/Berechtigung|403/i.test(error.message))syncBlocked=true;return null;}).finally(()=>syncPromise=null);
  return syncPromise;
 }
 function providerName(provider){return provider==='zammad'?'Zammad':provider==='teamviewer'?'TeamViewer':'STARFACE';}
 function syncDialog(setting,budget,onSaved){
  const d=document.createElement('dialog');d.className='company-dialog integration-sync-dialog';
  d.innerHTML=`<form><div class="dialog-title-row"><div><p class="eyebrow">${h(providerName(setting.provider))}</p><h3>Automatischer Abgleich</h3></div><button type="button" class="icon-action secondary" data-close aria-label="Schließen">×</button></div><label class="checkbox-field"><input type="checkbox" name="enabled" ${setting.enabled?'checked':''}> Automatischen Abgleich aktivieren</label><div class="field-grid"><label>Intervall tagsüber (Sekunden)<input type="number" name="day_seconds" min="60" max="86400" value="${Number(setting.day_seconds)}" required></label><label>Intervall nachts (Sekunden)<input type="number" name="night_seconds" min="60" max="86400" value="${Number(setting.night_seconds)}" required></label><label>Tagesbeginn<input type="number" name="day_start" min="0" max="23" value="${Number(setting.day_start)}" required></label><label>Tagesende<input type="number" name="day_end" min="1" max="24" value="${Number(setting.day_end)}" required></label><label>24-Stunden-Budget<input type="number" name="cap" min="1" max="${setting.provider==='teamviewer'?3600:50000}" value="${Number(budget?.cap||3600)}" required></label></div><p class="muted">Budget und Zeitplan gehören ausschließlich zu ${h(providerName(setting.provider))}.</p><p role="alert" class="error" data-error></p><div class="panel-actions"><button type="button" class="secondary" data-cancel>Abbrechen</button><button class="primary">Speichern</button></div></form>`;
  document.body.append(d);const close=()=>d.close();q('[data-close]',d).onclick=close;q('[data-cancel]',d).onclick=close;d.addEventListener('close',()=>d.remove(),{once:true});
  q('form',d).onsubmit=async event=>{event.preventDefault();const form=event.currentTarget,values=Object.fromEntries(new FormData(form));q('[data-error]',d).textContent='';try{await post('/api/v1/company/sync/save',{provider:setting.provider,enabled:form.elements.enabled.checked,day_seconds:Number(values.day_seconds),night_seconds:Number(values.night_seconds),day_start:Number(values.day_start),day_end:Number(values.day_end),cap:Number(values.cap)});syncData=null;message('Abgleich für '+providerName(setting.provider)+' gespeichert');close();await onSaved();}catch(error){q('[data-error]',d).textContent=error.message;}};
  d.showModal();
 }
 function targetsFor(provider){
  const targets=[];
  for(const details of qa('[data-admin-pane="integrations"] details.service-fold'))if((q('summary',details)?.textContent||'').toLowerCase().includes(provider))targets.push(details);
  return [...new Set(targets)];
 }
 async function decorateSync(force=false){
  qa('[data-company-sync]').forEach(node=>node.remove());
  qa('#integration-cards [data-integration-sync],#view-settings-connections [data-integration-sync]').forEach(node=>node.remove());
  const hasTarget=qa('[data-admin-pane="integrations"] details.service-fold').length;if(!hasTarget)return;
  const data=await getSync(force);if(!data)return;
  for(const setting of data.settings||[]){
   const budget=(data.budget||[]).find(row=>row.provider===setting.provider),jobs=(data.jobs||[]).filter(row=>row.provider===setting.provider),job=jobs.sort((a,b)=>String(b.started_at).localeCompare(String(a.started_at)))[0];
   for(const target of targetsFor(setting.provider)){
    let block=q(':scope > [data-integration-sync]',target);if(!block){block=document.createElement('section');block.dataset.integrationSync='';block.className='integration-sync-settings';target.append(block);}
    block.innerHTML=`<div><small>AUTOMATISCHER ABGLEICH</small><strong>${setting.enabled?'Aktiv':'Ausgeschaltet'}</strong><span>${h(budget?.used??'–')} / ${h(budget?.cap??'–')} Anfragen in 24 Stunden${job?' · letzter Status: '+h(job.state):''}</span></div><button type="button" class="icon-action secondary" aria-label="Abgleich konfigurieren" title="Abgleich konfigurieren">${svg.edit}</button>`;
    q('button',block).onclick=()=>syncDialog(setting,budget,()=>decorateSync(true));
   }
  }
 }

 let mailLoading=false;
 function templateFrom(form){return {company_name:form.elements.company_name.value,logo_url:form.elements.logo_url.value,primary_color:form.elements.primary_color.value,accent_color:form.elements.accent_color.value,footer_text:form.elements.footer_text.value};}
 async function mountMailTemplate(){
  const pane=q('[data-admin-pane="smtp"]');if(!pane||q('[data-email-template-panel]',pane)||mailLoading)return;mailLoading=true;
  try{
   const data=await post('/api/v1/admin/email-template/context',{}),t=data.template||{},panel=document.createElement('article');panel.className='panel email-template-panel';panel.dataset.emailTemplatePanel='';
   panel.innerHTML=`<div class="panel-head"><div><p class="eyebrow">DARSTELLUNG</p><h3>Zentrale E-Mail-Vorlage</h3><p>Ein einheitliches Erscheinungsbild für Sicherheitscodes, Passwortänderungen und Benachrichtigungen.</p></div></div><div class="email-template-layout"><form data-email-template><div class="field-grid"><label>Unternehmensname<input name="company_name" maxlength="120" value="${h(t.company_name||'ProjektZeit')}" required></label><label>Logo-URL (optional)<input type="url" name="logo_url" maxlength="1000" value="${h(t.logo_url||'')}" placeholder="https://…"></label><label>Primärfarbe<input type="color" name="primary_color" value="${h(t.primary_color||'#3275d1')}"></label><label>Akzentfarbe<input type="color" name="accent_color" value="${h(t.accent_color||'#20c997')}"></label></div><label>Fußzeile<textarea name="footer_text" rows="3" maxlength="1000" required>${h(t.footer_text||'')}</textarea></label><p role="alert" class="error" data-template-error></p><div class="panel-actions"><button type="button" class="secondary" data-template-preview>Vorschau aktualisieren</button><button class="primary compact-save">Vorlage speichern</button></div></form><div class="email-template-preview"><div><strong>Vorschau</strong><span>Desktop & Mobil</span></div><iframe title="Vorschau der E-Mail-Vorlage" sandbox></iframe></div></div><form class="email-template-test inline-form" data-template-test><label>Testempfänger<input type="email" name="recipient" placeholder="name@unternehmen.de" required></label><button class="secondary">Testmail senden</button></form>`;
   pane.append(panel);const form=q('[data-email-template]',panel),frame=q('iframe',panel),error=q('[data-template-error]',panel);
   const show=html=>{frame.srcdoc=html;};show(data.html||'');
   const preview=async()=>{error.textContent='';try{const out=await post('/api/v1/admin/email-template/preview',{template:templateFrom(form)});show(out.html);}catch(e){error.textContent=e.message;}};
   q('[data-template-preview]',panel).onclick=preview;let timer;form.oninput=()=>{clearTimeout(timer);timer=setTimeout(preview,350);};form.onsubmit=async event=>{event.preventDefault();error.textContent='';try{const out=await post('/api/v1/admin/email-template/save',{template:templateFrom(form)});show(out.html);window.pzUI?.clean?.(form);message('E-Mail-Vorlage gespeichert');}catch(e){error.textContent=e.message;}};
   q('[data-template-test]',panel).onsubmit=async event=>{event.preventDefault();const button=q('button',event.currentTarget);button.disabled=true;try{await post('/api/v1/admin/email-template/test',{recipient:event.currentTarget.elements.recipient.value});message('Testmail wurde in die Versandwarteschlange aufgenommen');}catch(e){message(e.message,'error');}finally{button.disabled=false;}};
  }catch(_){/* SMTP view without template permission remains unchanged. */}finally{mailLoading=false;}
 }

 let watchedAdminPane=null;
 function watchAdminIntegrations(){const pane=q('[data-admin-pane="integrations"]');if(!pane||pane===watchedAdminPane)return;watchedAdminPane=pane;new MutationObserver(()=>{clearTimeout(pane._sync076);pane._sync076=setTimeout(()=>decorateSync(),50);}).observe(pane,{childList:true});}
 function apply(){normalizeActions();mountMailTemplate();watchAdminIntegrations();decorateSync();}
 const previous=window.pzRenderCompanySync;window.pzRenderCompanySync=async root=>{q('[data-company-sync]',root)?.remove();await decorateSync();};
 document.addEventListener('pz-admin-context',()=>setTimeout(apply,0));document.addEventListener('pz-admin-pane-ready',()=>{setTimeout(apply,0);setTimeout(()=>decorateSync(),350);});document.addEventListener('pz-view-changed',()=>setTimeout(apply,80));document.addEventListener('pz-provider-rendered',()=>normalizeActions());
 const cards=q('#integration-cards');if(cards)new MutationObserver(()=>{clearTimeout(cards._sync076);cards._sync076=setTimeout(apply,40);}).observe(cards,{childList:true});
 let tries=0;const settle=setInterval(()=>{apply();if(++tries>=30)clearInterval(settle);},180);apply();
})();
