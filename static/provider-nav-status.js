(()=>{
 const q=(s,r=document)=>r.querySelector(s);
 const names={zammad:'Zammad',starface:'STARFACE',teamviewer:'TeamViewer'};
 let states=new Map(),loading=false,ready=false;
 const dialog=document.createElement('dialog');dialog.className='provider-connect-dialog';dialog.innerHTML='<div class="provider-connect-head"><strong data-provider-connect-title>Verbindung</strong></div><div class="provider-connect-body"><p data-provider-connect-message></p><div class="provider-connect-actions"><button type="button" class="primary" data-provider-connect-yes>Ja</button><button type="button" class="secondary" data-provider-connect-no>Nein</button></div></div>';document.body.append(dialog);
 let pendingProvider='';
 q('[data-provider-connect-no]',dialog).onclick=()=>{pendingProvider='';dialog.close();if(innerWidth<=900)q('.sidebar')?.classList.add('open');};
 function decorate(){
  for(const provider of Object.keys(names)){
   const nav=q(`.nav[data-view="${provider}"]`);if(!nav)continue;
   let tag=q('.provider-nav-tag',nav);if(!tag){tag=document.createElement('small');tag.className='provider-nav-tag';nav.append(tag);}
   const s=states.get(provider);tag.textContent=s?.connected?'Verbunden':'Nicht verbunden';tag.classList.toggle('connected',!!s?.connected);tag.classList.toggle('disconnected',!s?.connected);tag.title=s?.detail||'';
  }
 }
 async function load(){
  if(loading||typeof post!=='function'||typeof state==='undefined'||!state.user)return;
  loading=true;try{const d=await post('/api/v1/provider/navigation-status',{});states=new Map((d.providers||[]).map(x=>[x.provider,x]));ready=true;decorate();}catch(_){/* Navigation niemals wegen Statusabruf blockieren. */}finally{loading=false;}
 }
 function focusSettings(provider,attempt=0){
  const card=q(`#integration-cards [data-provider="${provider}"]`);
  if(!card&&attempt<12){setTimeout(()=>focusSettings(provider,attempt+1),250);return;}
  if(!card)return;
  card.classList.add('provider-settings-focus');card.scrollIntoView({behavior:'smooth',block:'center'});
  setTimeout(()=>card.classList.remove('provider-settings-focus'),2200);
  const target=q('[data-pz-starface-connect],input,button',card);target?.focus?.();
 }
 function goSettings(provider){
  dialog.close();pendingProvider='';
  if(window.pzOpenNavTarget)window.pzOpenNavTarget('settings-connections','Verbindungen');
  else if(typeof showView==='function')showView('settings-connections');
  setTimeout(()=>focusSettings(provider),180);
 }
 q('[data-provider-connect-yes]',dialog).onclick=()=>{if(pendingProvider)goSettings(pendingProvider);};
 document.addEventListener('click',event=>{
  const nav=event.target.closest('.nav[data-view="zammad"],.nav[data-view="starface"],.nav[data-view="teamviewer"]');if(!nav||!ready)return;
  const provider=nav.dataset.view,s=states.get(provider);if(!s||s.connected)return;
  event.preventDefault();event.stopImmediatePropagation();pendingProvider=provider;
  q('[data-provider-connect-title]',dialog).textContent=`${names[provider]} nicht verbunden`;
  q('[data-provider-connect-message]',dialog).textContent=s.reason==='missing'?
   `Die ${names[provider]}-Verbindung wurde noch nicht eingerichtet. Möchten Sie sie jetzt einrichten?`:
   `Die ${names[provider]}-Verbindung wurde unterbrochen. Möchten Sie die Verbindung jetzt wiederherstellen?`;
  dialog.showModal();
 },true);
 document.addEventListener('click',event=>{if(event.target.closest('[data-integration-action],[data-pz-starface-connect],[data-refresh]'))setTimeout(load,1600);});
 document.addEventListener('pz-provider-status-changed',()=>setTimeout(load,150));
 window.addEventListener('starface-connected',()=>setTimeout(load,500));
 let tries=0;const wait=setInterval(()=>{tries++;if(typeof state!=='undefined'&&state.user){clearInterval(wait);load();}else if(tries>100)clearInterval(wait);},100);
 setInterval(load,30000);
})();
