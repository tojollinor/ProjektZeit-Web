(()=>{
 const q=(s,r=document)=>r.querySelector(s);
 const loadedVersion=q('meta[name="pz-frontend-version"]')?.content||'';
 let serverVersion='',checking=false,timer=null;

 function cleanReloadMarker(){
  const url=new URL(location.href);if(!url.searchParams.has('_pz_reload'))return;
  url.searchParams.delete('_pz_reload');history.replaceState(history.state,'',url.pathname+(url.searchParams.size?'?'+url.searchParams.toString():'')+url.hash);
 }

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
  if(checking||!loadedVersion||document.hidden)return;checking=true;
  try{const current=await getServerVersion();if(current&&current!==loadedVersion)showUpdate(current);}catch(_){/* Update checks must never disturb normal work. */}
  finally{checking=false;}
 }

 async function hardReload(version=''){
  try{version=version||await getServerVersion();}catch(_){version=String(Date.now());}
  const url=new URL(location.href);url.searchParams.set('_pz_reload',version||String(Date.now()));
  location.replace(url.toString());
 }
 window.pzHardReload=hardReload;

 function releaseFooter(){
  const host=q('.sidebar-bottom .user-chip');if(!host||q('[data-release-info]'))return;
  const info=document.createElement('div');info.dataset.releaseInfo='';info.className='release-info';
  const release=q('meta[name="pz-release-version"]')?.content||'',build=q('meta[name="pz-build-revision"]')?.content||'';
  info.innerHTML='<button type="button" class="release-check" data-release-status role="status">Aktuellste Version</button>';
  host.after(info);
  const button=q('button',info);
  async function updateStatus(){if(button.disabled)return;button.disabled=true;button.setAttribute('aria-busy','true');
   const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),8000);
   try{const response=await fetch('/api/v1/system/update',{credentials:'same-origin',cache:'no-store',signal:controller.signal});if(!response.ok)throw new Error('Prüfung nicht verfügbar');const data=await response.json();button.textContent=data.state==='available'?'Update verfügbar':'Aktuellste Version';button.dataset.state=data.state==='available'?'available':'current';button.title=data.message||button.textContent;}
   catch(_){button.textContent='Aktuellste Version';button.dataset.state='current';button.title='Aktualisierungsprüfung momentan nicht möglich.';}
   finally{clearTimeout(timeout);button.disabled=false;button.removeAttribute('aria-busy');}
  }
  button.onclick=updateStatus;updateStatus();
 }
 releaseFooter();
 cleanReloadMarker();banner();
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
 window.addEventListener('focus',check);window.addEventListener('online',check);
 setTimeout(check,4000);timer=setInterval(check,60000);
 window.addEventListener('beforeunload',()=>{if(timer)clearInterval(timer);},{once:true});
})();
