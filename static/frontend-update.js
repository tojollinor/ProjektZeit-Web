(()=>{
 const q=(s,r=document)=>r.querySelector(s);
 const loadedVersion=q('meta[name="pz-frontend-version"]')?.content||'';
 let serverVersion='',checking=false,timer=null;

 function banner(){
  let el=q('[data-pz-update-banner]');
  if(el)return el;
  el=document.createElement('aside');
  el.className='pz-update-banner';el.dataset.pzUpdateBanner='';el.hidden=true;
  el.setAttribute('role','status');el.setAttribute('aria-live','polite');
  el.innerHTML='<div><strong>Neue Weboberfläche verfügbar</strong><span>Eine aktualisierte Version von ProjektZeit ist verfügbar.</span></div><button type="button" class="primary" data-pz-update-now>Aktualisieren</button>';
  document.body.append(el);
  q('[data-pz-update-now]',el).onclick=()=>hardReload(serverVersion);
  return el;
 }

 function showUpdate(version){serverVersion=version||serverVersion;banner().hidden=false;}

 async function getServerVersion(){
  const response=await fetch(`/api/v1/frontend/version?_=${Date.now()}`,{cache:'no-store',credentials:'same-origin',headers:{'Cache-Control':'no-cache'}});
  if(!response.ok)throw new Error('Frontend-Version nicht erreichbar');
  const data=await response.json();return String(data.version||'');
 }

 async function check(){
  if(checking||!loadedVersion)return;checking=true;
  try{const current=await getServerVersion();if(current&&current!==loadedVersion)showUpdate(current);}catch(_){/* Update checks must never disturb normal work. */}
  finally{checking=false;}
 }

 async function hardReload(version=''){
  try{version=version||await getServerVersion();}catch(_){version=String(Date.now());}
  const url=new URL(location.href);url.searchParams.set('_pz_reload',version||String(Date.now()));
  location.replace(url.toString());
 }
 window.pzHardReload=hardReload;

 function ensureWorkshopButton(){
  const section=q('#view-workshop');if(!section||q('[data-pz-hard-reload-panel]',section))return;
  const panel=document.createElement('article');panel.className='panel pz-hard-reload-panel';panel.dataset.pzHardReloadPanel='';
  panel.innerHTML='<div class="panel-head"><div><p class="eyebrow">WEB-OBERFLÄCHE</p><h3>Oberfläche neu laden</h3></div></div><p class="muted">Falls neue Änderungen nicht erscheinen, lädt diese Funktion die Weboberfläche mit einer frischen Versionskennung neu. Die Anmeldung bleibt erhalten.</p><div class="panel-actions"><button type="button" class="secondary" data-pz-hard-reload>Weboberfläche hart neu laden</button></div>';
  section.append(panel);q('[data-pz-hard-reload]',panel).onclick=()=>hardReload();
 }

 banner();ensureWorkshopButton();
 new MutationObserver(ensureWorkshopButton).observe(document.body,{childList:true,subtree:true});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
 window.addEventListener('focus',check);window.addEventListener('online',check);
 setTimeout(check,4000);timer=setInterval(check,60000);
 window.addEventListener('beforeunload',()=>{if(timer)clearInterval(timer);},{once:true});
})();
