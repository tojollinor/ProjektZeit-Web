(()=>{
 const q=(s,r=document)=>r.querySelector(s);
 const names={zammad:'Zammad',starface:'STARFACE',teamviewer:'TeamViewer'};
 let states=new Map(),loading=false,ready=false;
 const dialog=document.createElement('dialog');dialog.className='provider-connect-dialog';dialog.innerHTML='<div class="provider-connect-head"><strong data-provider-connect-title>Verbindung</strong></div><div class="provider-connect-body"><p data-provider-connect-message></p><div class="provider-connect-actions"><button type="button" class="primary" data-provider-connect-yes>Ja</button><button type="button" class="secondary" data-provider-connect-no>Nein</button></div></div>';document.body.append(dialog);
 let pendingProvider='';const yes=q('[data-provider-connect-yes]',dialog),no=q('[data-provider-connect-no]',dialog);
 no.onclick=()=>{pendingProvider='';dialog.close();no.textContent='Nein';if(innerWidth<=900)q('.sidebar')?.classList.add('open');};
 function navTag(provider){const nav=q(`.nav[data-view="${provider}"]`);if(!nav)return null;let tag=q('.provider-nav-tag',nav);if(!tag){tag=document.createElement('small');tag.className='provider-nav-tag';nav.append(tag);}return tag;}
 function decorateLoading(){for(const provider of Object.keys(names)){const tag=navTag(provider);if(!tag)continue;tag.textContent='Status wird geprüft';tag.className='provider-nav-tag loading';tag.dataset.state='loading';tag.title='Verbindungsstatus wird geprüft.';}}
 function decorate(){
  for(const provider of Object.keys(names)){
   const tag=navTag(provider);if(!tag)continue;const s=states.get(provider);
   if(!s||s.reason==='unknown'){tag.textContent='Status unbekannt';tag.className='provider-nav-tag loading';tag.dataset.state='unknown';tag.title='Noch keine aktuelle erfolgreiche Verbindungsprüfung.';continue;}
   tag.textContent=s.connected?'Verbunden':s.reason==='missing'||s.reason==='missing_client_secret'?'Nicht eingerichtet':'Verbindung fehlgeschlagen';
   tag.className='provider-nav-tag '+(s.connected?'connected':'disconnected');tag.dataset.state=s.connected?'connected':'disconnected';tag.title=s.detail||'';
  }
 }
 let loadPromise=null;
 async function load(){
  if(loadPromise)return loadPromise;if(document.hidden||typeof post!=='function'||typeof state==='undefined'||!state.user)return;
  loading=true;if(!ready)decorateLoading();loadPromise=(async()=>{try{const d=await post('/api/v1/provider/navigation-status',{});states=new Map((d.providers||[]).map(x=>[x.provider,x]));ready=true;decorate();}catch(_){states=new Map();ready=false;decorate();}finally{loading=false;}})();try{await loadPromise;}finally{loadPromise=null;}
 }
 function focusSettings(provider,attempt=0){
  const card=q(`#integration-cards [data-provider="${provider}"]`);if(!card&&attempt<12){setTimeout(()=>focusSettings(provider,attempt+1),250);return;}if(!card)return;
  card.classList.add('provider-settings-focus');card.scrollIntoView({behavior:'smooth',block:'center'});setTimeout(()=>card.classList.remove('provider-settings-focus'),2200);q('input,button',card)?.focus?.();
 }
 function goSettings(provider){dialog.close();pendingProvider='';if(window.pzOpenNavTarget)window.pzOpenNavTarget('settings-connections','Verbindungen');else if(typeof showView==='function')showView('settings-connections');setTimeout(()=>focusSettings(provider),180);}
 yes.onclick=()=>{if(pendingProvider)goSettings(pendingProvider);};
 let allowStarface=false,checking=false;
 window.addEventListener('click',async event=>{
  const nav=event.target.closest?.('.nav[data-view="starface"]');if(!nav)return;if(allowStarface){allowStarface=false;return;}
  if(ready&&states.get('starface')?.connected===true)return;
  event.preventDefault();event.stopImmediatePropagation();if(checking)return;checking=true;nav.setAttribute('aria-busy','true');
  try{await load();let s=states.get('starface');
   if(s?.reason==='unknown'){try{const result=await post('/api/v1/integrations/test',{provider:'starface'});if(result.ok===true){s={connected:true};states.set('starface',{provider:'starface',connected:true,reason:'connected'});decorate();}else s={reason:'unavailable',detail:result.error||result.message||'Die Verbindungsprüfung war nicht erfolgreich.'};}catch(error){s={reason:'unavailable',detail:error.message};}}
   if(s?.connected===true){allowStarface=true;nav.click();return;}
   pendingProvider='starface';const missing=s?.reason==='missing_client_secret',expired=['expired','missing'].includes(s?.reason);
   q('[data-provider-connect-title]',dialog).textContent=missing?'STARFACE nicht eingerichtet':expired?'STARFACE-Anmeldung erforderlich':'STARFACE momentan nicht verfügbar';
   q('[data-provider-connect-message]',dialog).textContent=missing?'Für STARFACE wurde kein Client Secret hinterlegt. Bitte informieren Sie einen Administrator, damit er die Zugangsdaten unter Einstellungen → Verbindungen ergänzt. Eine Anmeldung und das Öffnen von STARFACE sind momentan nicht möglich.':expired?'Die STARFACE-Anmeldung fehlt oder ist abgelaufen. Möchten Sie die Verbindungseinstellungen öffnen und sich erneut anmelden?':s?.detail||'Der Verbindungsstatus konnte noch nicht ermittelt werden. Bitte versuchen Sie es erneut oder prüfen Sie Einstellungen → Verbindungen.';
   yes.hidden=!expired;yes.textContent='Ja';no.textContent=expired?'Nein':'OK';dialog.showModal();
  }finally{checking=false;nav.removeAttribute('aria-busy');}
 },true);
 document.addEventListener('click',event=>{if(event.target.closest('[data-integration-action],[data-pz-starface-connect],[data-starface-action],[data-refresh]'))setTimeout(load,500);});
 document.addEventListener('pz-provider-status-changed',()=>setTimeout(load,100));window.addEventListener('starface-connected',()=>setTimeout(load,300));
 decorateLoading();let tries=0;const wait=setInterval(()=>{tries++;if(typeof state!=='undefined'&&state.user){clearInterval(wait);load();}else if(tries>100)clearInterval(wait);},100);setInterval(load,30000);
})();
