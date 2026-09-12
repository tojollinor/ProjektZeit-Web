(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const notify=(m,l='info',t=4500)=>window.pzToast?window.pzToast(m,l,t):typeof toast==='function'?toast(m):null;
 function applyTheme(theme){if(theme==='dark'||theme==='light')document.documentElement.dataset.theme=theme;else delete document.documentElement.dataset.theme;}

 async function loadProfile(){
  const fold=q('[data-profile-settings]'),form=q('[data-settings-profile]',fold);if(!fold||!form)return;
  try{
   const d=await post('/api/v1/account/context',{}),p=d.profile||{},theme=d.preferences?.theme||'system';
   for(const key of ['first_name','last_name','email','phone'])if(form.elements[key])form.elements[key].value=p[key]||'';
   const radio=q(`input[name="settings-theme"][value="${theme}"]`,fold);if(radio)radio.checked=true;applyTheme(theme);
  }catch(error){notify(error.message,'error');}
 }
 function repairProfile(){
  const fold=q('[data-profile-settings]'),body=q('[data-profile-body]',fold),account=q('#view-account');if(!fold||!body||fold.dataset.profileFixed)return false;
  fold.dataset.profileFixed='1';
  const movedGrid=q('.account-grid',body);if(movedGrid&&account)account.append(movedGrid);
  const grid=document.createElement('div');grid.className='account-grid settings-profile-grid';grid.innerHTML=`<article class="panel"><h3>Profil</h3><form data-settings-profile><div class="field-grid"><label>Vorname<input name="first_name"></label><label>Nachname<input name="last_name"></label></div><div class="field-grid"><label>E-Mail<input type="email" name="email"></label><label>Telefon<input name="phone"></label></div><button class="primary">Speichern</button></form></article><article class="panel"><h3>Darstellung</h3><p class="muted">Systemstandard folgt dem aktuellen Gerät.</p><div class="theme-options"><label><input type="radio" name="settings-theme" value="system"> Systemstandard</label><label><input type="radio" name="settings-theme" value="light"> Heller Modus</label><label><input type="radio" name="settings-theme" value="dark"> Dunkler Modus</label></div></article>`;
  body.prepend(grid);
  const form=q('[data-settings-profile]',grid);form.onsubmit=async event=>{event.preventDefault();try{await post('/api/v1/account/save',Object.fromEntries(new FormData(form)));notify('Profil gespeichert','success');}catch(error){notify(error.message,'error');}};
  qa('input[name="settings-theme"]',grid).forEach(el=>el.onchange=async()=>{applyTheme(el.value);try{await post('/api/v1/account/theme',{theme:el.value});notify('Darstellung gespeichert','success');}catch(error){notify(error.message,'error');}});
  fold.addEventListener('toggle',()=>{if(fold.open)loadProfile();});
  if(fold.open)loadProfile();
  return true;
 }

 function refineAllLogs(){
  for(const row of qa('.log-list .log-row')){
   const copy=q('.log-compact-copy',row);if(!copy||row.dataset.twoLine)continue;
   const head=q(':scope > div',copy),time=q('small',head),message=q(':scope > span',copy);if(!head||!time||!message)continue;
   row.dataset.twoLine='1';const line=document.createElement('div');line.className='log-compact-second';line.append(time,message);copy.append(line);
  }
 }

 // Settle the asynchronously assembled UI for a short bounded period. The old version
 // observed the entire document forever, causing expensive rescans on every DOM mutation.
 let attempts=0;const timer=setInterval(()=>{attempts++;repairProfile();refineAllLogs();if(attempts>=20)clearInterval(timer);},150);
 document.addEventListener('click',event=>{
  if(event.target.closest('[data-pz-nav-target="settings-profile"],[data-view="account"]'))setTimeout(()=>{repairProfile();loadProfile();},80);
  if(event.target.closest('[data-view="logs"],[data-log-refresh]'))setTimeout(refineAllLogs,80);
 });
})();
