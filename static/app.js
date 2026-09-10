const state={csrf:'',user:null,data:null,tick:null};
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const dateValue=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
const api=async(path,options={})=>{options.headers={"Content-Type":"application/json",...(state.csrf?{"X-CSRF-Token":state.csrf}:{}),...(options.headers||{})};const r=await fetch(path,options);const j=await r.json();if(!r.ok)throw new Error(j.error||"Unbekannter Fehler");return j};
const post=(path,data={})=>api(path,{method:"POST",body:JSON.stringify(data)});
function toast(text){const el=$("#toast");el.textContent=text;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),2600)}
function duration(start,end){if(!end)return"läuft";let s=Math.max(0,Math.floor((new Date(end)-new Date(start))/1000));return`${String(Math.floor(s/3600)).padStart(2,"0")}:${String(Math.floor(s%3600/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`}
function esc(value){const div=document.createElement("div");div.textContent=value??"";return div.innerHTML}
function attr(value){return esc(value).replaceAll('"','&quot;')}
async function boot(){try{const me=await api("/api/v1/me");state.user=me.user;state.csrf=me.csrf;$("#login").classList.add("hidden");$("#app").classList.remove("hidden");$("#username").textContent=me.user.username;$("#avatar").textContent=me.user.username[0].toUpperCase();$("#role").textContent=me.user.role==="admin"?"Administrator":"Benutzer";$$('.admin-only').forEach(x=>x.style.display=me.user.role==="admin"?"flex":"none");await refresh()}catch{$("#login").classList.remove("hidden");$("#app").classList.add("hidden")}}
async function refresh(){state.data=await api("/api/v1/dashboard");render();renderWork()}
function render(){const d=state.data,active=d.entries.find(e=>!e.ended_at);$("#project-count").textContent=d.projects.length;$("#entry-count").textContent=d.entries.length;const today=new Date().toDateString();let seconds=d.entries.filter(e=>e.ended_at&&new Date(e.started_at).toDateString()===today).reduce((n,e)=>n+(new Date(e.ended_at)-new Date(e.started_at))/1000,0);$("#today-total").textContent=duration(new Date(0),new Date(seconds*1000));$("#entry-table").innerHTML=d.entries.length?d.entries.map(e=>`<tr><td><strong>${esc(e.project)}</strong></td><td>${esc(e.customer||"Ohne Kunde")}</td><td>${esc(e.category)}</td><td>${new Date(e.started_at).toLocaleString("de-DE")}</td><td>${duration(e.started_at,e.ended_at)}</td><td><span class="badge ${e.ended_at?'':'live'}">${e.ended_at?'Gespeichert':'Läuft'}</span></td></tr>`).join(""):`<tr><td colspan="6" class="empty">Noch keine Stempelungen vorhanden.</td></tr>`;renderTimeline(d.entries);fillSelect("#project-select",d.projects,"Projekt wählen");fillSelect("#category-select",d.categories,"Kategorie wählen");fillSelect("#project-customer",d.customers,"Ohne Kunde",true);$("#user-list").innerHTML=d.users.map(u=>`<div class="user-row"><span class="mini-avatar">${esc(u.username[0].toUpperCase())}</span><div><strong>${esc(u.username)}</strong><small>${u.role==='admin'?'Administrator':'Benutzer'} · ${u.active?'Aktiv':'Deaktiviert'}</small></div><span class="badge">${u.role}</span></div>`).join("");setTimer(active)}
function renderTimeline(entries){
  const input=$("#timeline-date"),track=$("#timeline-track");
  if(!input.value)input.value=dateValue(new Date());
  const dayStart=new Date(input.value+"T00:00:00"),dayEnd=new Date(dayStart);
  dayEnd.setDate(dayEnd.getDate()+1);
  const total=dayEnd-dayStart,now=new Date();
  const segments=entries
    .map(e=>({e,start:new Date(e.started_at),end:e.ended_at?new Date(e.ended_at):now}))
    .map(x=>({...x,start:new Date(Math.max(x.start,dayStart)),end:new Date(Math.min(x.end,dayEnd))}))
    .filter(x=>x.end>x.start)
    .sort((a,b)=>a.start-b.start||a.end-b.end);

  // Index dient nur der Kennzeichnung historischer Konflikte.
  segments.forEach((segment,index)=>segment.lane=index);
  const conflicts=new Set();
  for(let i=0;i<segments.length;i++)for(let j=i+1;j<segments.length&&segments[j].start<segments[i].end;j++){
    conflicts.add(i);conflicts.add(j);
  }

  const merged=[];
  for(const x of segments){
    const last=merged.at(-1);
    if(last&&x.start<=last.end)last.end=new Date(Math.max(last.end,x.end));
    else merged.push({start:x.start,end:x.end});
  }

  let cursor=dayStart.getTime();
  const content=document.createDocumentFragment();
  // Einzelne CSS-Eigenschaften sind unter unserer CSP erlaubt. Style-Attribute
  // in HTML-Strings werden dagegen vom Browser blockiert.
  const addGap=(start,end)=>{
    const gap=document.createElement("span");
    gap.className="timeline-gap";
    gap.style.left=`${(start-dayStart)/total*100}%`;
    gap.style.width=`${(end-start)/total*100}%`;
    content.append(gap);
  };
  const colors=["#397bd6","#16a57b","#a76ce8","#dd7846","#3d9db4","#d65f88"];
  for(const span of merged){
    if(span.start.getTime()>cursor)addGap(cursor,span.start);
    cursor=Math.max(cursor,span.end.getTime());
  }
  if(cursor<dayEnd.getTime())addGap(cursor,dayEnd);

  for(const x of segments){
    const left=(x.start-dayStart)/total*100,width=(x.end-x.start)/total*100;
    const color=colors[[...x.e.project].reduce((n,c)=>n+c.charCodeAt(0),0)%colors.length];
    const label=`${x.start.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}–${x.end.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
    const card=document.createElement("button");
    card.type="button";
    card.setAttribute('aria-label',`${x.e.project} · ${label} – Details öffnen`);
    card.setAttribute('aria-haspopup','dialog');
    card.addEventListener('click',()=>showTimelineDetail(x.e,conflicts.has(x.lane)));
    card.className="timeline-segment";
    card.style.left=`${left}%`;
    card.style.width=`${width}%`;
    card.style.top='8px';
    card.style.backgroundColor=color;
    card.title=`${x.e.project} · ${x.e.category} · ${label} · ${duration(x.start,x.end)}`;
    content.append(card);
  }

  track.style.height='66px';
  if(!segments.length){
    const empty=document.createElement("span");
    empty.className="timeline-empty";
    empty.textContent="An diesem Tag wurden keine Aufträge erfasst.";
    content.replaceChildren(empty);
  }
  track.replaceChildren(content);
  const worked=merged.reduce((sum,x)=>sum+(x.end-x.start),0),idle=Math.max(0,total-worked);
  const lanes='';
  const summary=$("#timeline-summary");
  summary.innerHTML=`<span><i></i>Erfasst: ${duration(new Date(0),new Date(worked))}</span><span><i></i>Ohne Erfassung: ${duration(new Date(0),new Date(idle))}</span><span>${segments.length} ${segments.length===1?'Auftrag':'Aufträge'}</span>${lanes}`;
  summary.firstElementChild.style.color="var(--green)";
  if(conflicts.size){const warning=document.createElement('span');warning.className='timeline-conflict';warning.textContent=`${conflicts.size} bestehende Stempelungen überschneiden sich – bitte unter Bearbeiten korrigieren.`;summary.append(warning);}
  updateTimelineScale();
}
function updateTimelineScale(){
  const scroll=$('.timeline-scroll'),layout=$('.timeline-layout'),hours=$('.timeline-hours'),track=$('#timeline-track');
  const width=Math.max(320,scroll.clientWidth-4)*(state.timelineZoom||1);
  layout.style.width=`${width}px`;
  const start=new Date($('#timeline-date').value+'T00:00:00'),end=new Date(start);end.setDate(end.getDate()+1);
  const total=end-start;
  const step=[1,5,15,30,60,120,180,360].find(minutes=>minutes*60000/total*width>=65)||360;
  const ticks=document.createDocumentFragment();
  for(let offset=0;offset<total;offset+=step*60000){
    const tick=document.createElement('span');tick.style.left=`${offset/total*100}%`;
    tick.textContent=new Date(+start+offset).toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});ticks.append(tick);
  }
  const last=document.createElement('span');last.style.left='100%';last.textContent='24:00';last.className='axis-end';ticks.append(last);
  hours.replaceChildren(ticks);
  track.style.backgroundSize=`${step*60000/total*100}% 100%`;
  $('#zoom-reset').textContent=`Ganzer Tag · ${Math.round((state.timelineZoom||1)*100)} %`;
}
function zoomTimeline(factor,anchor){
  const scroll=$('.timeline-scroll'),layout=$('.timeline-layout');
  const oldWidth=layout.getBoundingClientRect().width;
  const position=(scroll.scrollLeft+anchor)/oldWidth;
  state.timelineZoom=Math.max(1,Math.min(96,(state.timelineZoom||1)*factor));
  updateTimelineScale();
  scroll.scrollLeft=position*layout.getBoundingClientRect().width-anchor;
}
function fillSelect(selector,items,placeholder,allowEmpty=false){const el=$(selector),old=el.value;el.innerHTML=`<option value="">${placeholder}</option>`+items.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join("");if([...el.options].some(o=>o.value===old))el.value=old;if(!allowEmpty&&!el.value&&items[0])el.value=items[0].id}
function setTimer(active){clearInterval(state.tick);const pill=$("#live-pill"),button=$("#timer-button"),timer=$("#timer");pill.classList.toggle("running",!!active&&!active.is_idle);pill.querySelector("span").textContent=active?(active.is_idle?"unproduktiv":"Projekt läuft"):"Feierabend";button.textContent="Ausgewähltes Projekt starten / wechseln";button.classList.remove("stop");button.disabled=!state.data.work;const update=()=>{timer.textContent=active?duration(active.started_at,new Date().toISOString()):"00:00:00";if(state.data.work)$("#work-detail").textContent=`Seit ${new Date(state.data.work.started_at).toLocaleTimeString('de-DE')} · ${duration(state.data.work.started_at,new Date())}`};update();if(active)state.tick=setInterval(update,1000)}
function showView(name){$$('.view').forEach(v=>v.classList.remove('active-view'));$("#view-"+name).classList.add('active-view');$$('.nav').forEach(n=>n.classList.toggle('active',n.dataset.view===name));$("#page-title").textContent={dashboard:"Übersicht",tracking:"Zeiterfassung",users:"Benutzerverwaltung",settings:"Einstellungen"}[name];$(".sidebar").classList.remove("open");if(name==='settings'&&!state.integrationsLoaded)loadIntegrations()}
$("#login-form").addEventListener("submit",async e=>{e.preventDefault();$("#login-error").textContent="";try{await post("/api/v1/login",{username:$("#login-user").value,password:$("#login-password").value});await boot()}catch(err){$("#login-error").textContent=err.message}});
$("#logout").addEventListener("click",async()=>{await post("/api/v1/logout");location.reload()});
$("#timeline-date").value=dateValue(new Date());$("#timeline-date").addEventListener("change",()=>state.data&&renderTimeline(state.data.entries));
$('.timeline-scroll').addEventListener('wheel',event=>{
  if(event.ctrlKey||!event.deltaY)return;
  event.preventDefault();
  const scroll=event.currentTarget,anchor=event.clientX-scroll.getBoundingClientRect().left;
  const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?scroll.clientWidth:1);
  zoomTimeline(Math.exp(-Math.max(-300,Math.min(300,delta))*.002),anchor);
},{passive:false});
$('#zoom-reset').addEventListener('click',()=>{state.timelineZoom=1;updateTimelineScale();$('.timeline-scroll').scrollLeft=0;});
window.addEventListener('resize',()=>{if(state.data)updateTimelineScale()});
function moveDay(delta){const value=new Date($("#timeline-date").value+"T12:00:00");value.setDate(value.getDate()+delta);$("#timeline-date").value=dateValue(value);if(state.data)renderTimeline(state.data.entries)}
$("#day-prev").addEventListener("click",()=>moveDay(-1));$("#day-next").addEventListener("click",()=>moveDay(1));$("#day-today").addEventListener("click",()=>{$("#timeline-date").value=dateValue(new Date());state.data&&renderTimeline(state.data.entries)});
$("#csv-export-button").addEventListener("click",async()=>{try{const response=await fetch("/api/v1/export.csv");if(!response.ok){const data=await response.json();throw new Error(data.error||"Export fehlgeschlagen")}const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`ProjektZeit-${dateValue(new Date())}.csv`;document.body.append(link);link.click();link.remove();URL.revokeObjectURL(url);toast("CSV-Export wurde erstellt")}catch(error){toast(error.message)}});
$("#csv-import-button").addEventListener("click",()=>$("#csv-file").click());$("#csv-file").addEventListener("change",async event=>{const file=event.target.files[0];if(!file)return;try{const result=await post("/api/v1/import.csv",{csv:await file.text()});await refresh();const detail=result.errors.length?` · ${result.errors.length} fehlerhafte Zeile(n)`:"";toast(`${result.imported} importiert · ${result.skipped} übersprungen${detail}`)}catch(error){toast(error.message)}finally{event.target.value=""}});
$$('.nav').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.view)));$$('[data-go]').forEach(b=>b.addEventListener('click',()=>showView(b.dataset.go)));$("#menu-toggle").addEventListener("click",()=>$(".sidebar").classList.toggle("open"));
$("#timer-button").addEventListener("click",()=>switchProject(+$("#project-select").value));
function form(id,path,payload){$(id).addEventListener("submit",async e=>{e.preventDefault();try{await post(path,payload());e.target.reset();await refresh();toast("Gespeichert")}catch(err){toast(err.message)}})}
form("#customer-form","/api/v1/customers",()=>({name:$("#customer-name").value}));form("#category-form","/api/v1/categories",()=>({name:$("#category-name").value}));form("#project-form","/api/v1/projects",()=>({name:$("#project-name").value,customer_id:+$("#project-customer").value||null}));form("#user-form","/api/v1/users",()=>({username:$("#new-username").value,password:$("#new-password").value,role:$("#new-role").value}));
function showTimelineDetail(entry,conflict){
  $('#detail-title').textContent=entry.project;
  const fields=$('#detail-fields');fields.replaceChildren();
  const format=value=>new Date(value).toLocaleString('de-DE');
  for(const [label,value] of [['Kunde',entry.customer||'Ohne Kunde'],['Kategorie',entry.category],['Start',format(entry.started_at)],['Ende',entry.ended_at?format(entry.ended_at):'Läuft'],['Dauer',duration(entry.started_at,entry.ended_at||new Date())],['Bemerkung',entry.note||'Keine Bemerkung']]){
    const term=document.createElement('dt'),description=document.createElement('dd');
    term.textContent=label;description.textContent=value;fields.append(term,description);
  }
  $('#detail-conflict').textContent=conflict?'Dieser Eintrag überschneidet sich mit einer bestehenden Stempelung.':'';
  $('#timeline-detail').showModal();
}
$('#detail-close').addEventListener('click',()=>$('#timeline-detail').close());
$('#timeline-detail').addEventListener('click',event=>{if(event.target===$('#timeline-detail')){const box=event.target.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)event.target.close();}});
let editingEntry=null;
function renderWork(){
  const d=state.data,running=d.entries.find(e=>!e.ended_at),working=!!d.work;
  $("#work-status").textContent=working?"Arbeitstag läuft":"Noch nicht begonnen / Feierabend";
  if(!working)$("#work-detail").textContent="Außerhalb der Arbeitszeit wird keine unproduktive Zeit erfasst.";
  $("#work-begin").disabled=working;$("#work-end").disabled=!working;
  $("#project-pause").disabled=!working||!running||!!running.is_idle;
  $("#current-task").textContent=running?`Aktuell: ${running.project}`:"Kein Projekt läuft";
  const active=d.projects.filter(p=>p.active);
  $("#project-count").textContent=active.length;
  $("#quick-projects").innerHTML=active.map(p=>`<button type="button" data-switch="${p.id}" aria-pressed="${!!running&&!running.is_idle&&running.project_id===p.id}" ${!working?'disabled':''}>${esc(p.name)}<small>${esc(d.customers.find(c=>c.id===p.customer_id)?.name||'Ohne Kunde')}</small></button>`).join('')||'<p class="muted">Aktiviere Projekte unter Zeiterfassung.</p>';
  $("#project-activity").innerHTML=d.projects.map(p=>`<label class="activity-row"><input type="checkbox" data-activity="${p.id}" ${p.active?'checked':''}>${esc(p.name)}</label>`).join('');
  fillSelect('#project-select',active,'Projekt wählen');
  $("#entry-table").innerHTML=d.entries.map(e=>`<tr><td><strong class="${e.is_idle?'idle-label':''}">${esc(e.project)}</strong><small class="entry-note">${esc(e.note)}</small></td><td>${esc(e.customer||'Ohne Kunde')}</td><td>${esc(e.category)}</td><td>${new Date(e.started_at).toLocaleString('de-DE')}<small class="entry-end">${e.ended_at?new Date(e.ended_at).toLocaleString('de-DE'):'Läuft'}</small></td><td>${duration(e.started_at,e.ended_at)}</td><td><button class="secondary subtle" data-edit="${e.id}">Bearbeiten</button></td></tr>`).join('')||'<tr><td colspan="6">Noch keine Stempelungen.</td></tr>';
}
async function workAction(path){try{await post(path);await refresh()}catch(error){toast(error.message)}}
async function switchProject(id){try{await post('/api/v1/timer/start',{project_id:id,category_id:+$('#category-select').value,note:$('#note').value});$('#note').value='';await refresh()}catch(error){toast(error.message)}}
$('#work-begin').addEventListener('click',()=>workAction('/api/v1/work/begin'));
$('#work-end').addEventListener('click',()=>workAction('/api/v1/work/end'));
$('#project-pause').addEventListener('click',()=>workAction('/api/v1/timer/stop'));
$('#quick-projects').addEventListener('click',event=>{const button=event.target.closest('[data-switch]');if(button)switchProject(+button.dataset.switch)});
$('#project-activity').addEventListener('change',async event=>{try{await post('/api/v1/projects/active',{id:+event.target.dataset.activity,active:event.target.checked});await refresh()}catch(error){toast(error.message);await refresh()}});
const localStamp=value=>{if(!value)return '';const d=new Date(value);return `${dateValue(d)}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`};
$('#entry-table').addEventListener('click',event=>{
  const button=event.target.closest('[data-edit]');if(!button)return;
  const e=state.data.entries.find(row=>row.id===+button.dataset.edit);editingEntry=e;
  fillSelect('#edit-project',state.data.projects,'Projekt wählen');fillSelect('#edit-category',state.data.categories,'Kategorie wählen');
  if(e.is_idle){$('#edit-project').options[0].textContent='unproduktiv';$('#edit-project').value='';}else $('#edit-project').value=e.project_id;
  $('#edit-category').value=e.category_id;
  $('#edit-start').value=localStamp(e.started_at);$('#edit-end').value=localStamp(e.ended_at);$('#edit-note').value=e.note;
  const locked=!!e.is_idle||!e.ended_at;
  for(const id of ['#edit-project','#edit-category','#edit-start','#edit-end'])$(id).disabled=locked;
  if(e.is_idle&&e.ended_at)$('#edit-project').disabled=false;
  $('#edit-hint').textContent=e.is_idle?'Unproduktive Zeit wird automatisch berechnet. Nach dem Stoppen kannst du hier auch ein Projekt nachtragen; verbleibende Lücken bleiben unproduktiv.':!e.ended_at?'Bei laufenden Stempelungen kannst du die Bemerkung ändern. Zeiten und Projekt lassen sich nach dem Stoppen bearbeiten.':'Freie Zeit innerhalb des Arbeitstags wird nach dem Speichern automatisch als unproduktiv erfasst.';
  $('#edit-error').textContent='';$('#entry-dialog').showModal();
});
$('#edit-cancel').addEventListener('click',()=>$('#entry-dialog').close());
$('#edit-project').addEventListener('change',()=>{if(editingEntry?.is_idle&&editingEntry.ended_at){for(const id of ['#edit-category','#edit-start','#edit-end'])$(id).disabled=!$('#edit-project').value;}});
$('#entry-edit-form').addEventListener('submit',async event=>{event.preventDefault();const e=editingEntry;try{
  const originalOrDate=(id,original)=>$(id).value===localStamp(original)?original:new Date($(id).value).toISOString();
  await post('/api/v1/entries/edit',{id:e.id,original_start:e.started_at,original_end:e.ended_at,original_note:e.note,project_id:+$('#edit-project').value,category_id:+$('#edit-category').value,started_at:originalOrDate('#edit-start',e.started_at),ended_at:$('#edit-end').value?originalOrDate('#edit-end',e.ended_at):null,note:$('#edit-note').value});
  $('#entry-dialog').close();await refresh();toast('Stempelung gespeichert');
}catch(error){$('#edit-error').textContent=error.message}});
const integrationInfo={
  teamviewer:{name:'TeamViewer',label:'API-Token',placeholder:'https://webapi.teamviewer.com',note:'TeamViewer unterstützt hier keinen Passwort-Login. Bitte einen Script-Token mit Leserechten für Verbindungsberichte verwenden. Das Benutzerfeld ist optional und dient nur als Kontobezeichnung.',docs:'https://www.teamviewer.com/en-us/global/support/knowledge-base/teamviewer-remote/for-developers/use-the-teamviewer-api/'},
  starface:{name:'STARFACE',label:'Passwort',placeholder:'https://telefon.firma.de',note:'Benutzername = STARFACE-Login-ID (z. B. 0001). Der Test verwendet REST mit X-Version 2 und prüft Anmeldung sowie Benutzerdaten. Gesprächszeiten sind damit noch nicht nachgewiesen.',docs:'https://knowledge.starface.de/x/cpLGAg'},
  zammad:{name:'Zammad',label:'Passwort',placeholder:'https://support.firma.de',note:'HTTP Basic Authentication muss in Zammad aktiviert sein. Der Test liest dein Benutzerprofil und bis zu fünf erreichbare Tickets. Zugriffsrechte gelten weiterhin.',docs:'https://docs.zammad.org/en/latest/api/intro.html'}
};
async function loadIntegrations(){
  const container=$('#integration-cards');container.textContent='Verbindungen werden geladen …';
  try{
    const data=await api('/api/v1/integrations');
    container.innerHTML=data.integrations.map(row=>{
      const p=row.provider,info=integrationInfo[p];
      return `<article class="panel integration-card" data-provider="${p}"><div class="panel-head"><h3>${info.name}</h3><span class="badge">${row.has_secret?'Gespeichert':'Noch nicht eingerichtet'}</span></div><p class="integration-note">${info.note} <a href="${info.docs}" target="_blank" rel="noopener noreferrer">API-Dokumentation</a></p><div class="integration-fields"><label>Domain<input data-field="domain" value="${attr(row.domain)}" placeholder="${info.placeholder}" autocomplete="off" spellcheck="false"></label><label>${p==='starface'?'Login-ID':'Benutzername'+(p==='teamviewer'?' (optional)':'')}<input data-field="username" value="${attr(row.username)}" maxlength="250" autocomplete="off" spellcheck="false"></label><label>${info.label}<input data-field="secret" type="password" maxlength="4096" autocomplete="new-password" placeholder="${row.has_secret?'Gespeichert – leer lassen zum Beibehalten':info.label+' eingeben'}"></label></div><div class="panel-actions"><button type="button" class="primary" data-integration-action="save">Speichern</button><button type="button" class="secondary" data-integration-action="test">Debug · Verbindung testen</button><button type="button" class="secondary subtle" data-integration-action="remove">Verknüpfung entfernen</button></div><div class="integration-status" role="status"></div><div class="debug-output hidden"></div></article>`;
    }).join('');state.integrationsLoaded=true;
  }catch(error){container.textContent=error.message;}
}
$('#integration-cards').addEventListener('input',event=>{
  const card=event.target.closest('[data-provider]');if(!card)return;
  card.querySelector('.debug-output').replaceChildren();card.querySelector('.debug-output').classList.add('hidden');card.querySelector('.integration-status').textContent='Eingaben geändert – noch nicht gespeichert oder getestet.';
});
$('#integration-cards').addEventListener('click',async event=>{
  const button=event.target.closest('[data-integration-action]');if(!button)return;
  const card=button.closest('[data-provider]'),action=button.dataset.integrationAction,provider=card.dataset.provider;
  const field=name=>card.querySelector(`[data-field="${name}"]`),status=card.querySelector('.integration-status'),output=card.querySelector('.debug-output');
  if(action==='remove'&&!confirm(`Gespeicherte ${integrationInfo[provider].name}-Zugangsdaten entfernen?`))return;
  const body={provider,domain:field('domain').value,username:field('username').value,secret:field('secret').value};
  const controls=[...card.querySelectorAll('button,input')];controls.forEach(x=>x.disabled=true);
  status.className='integration-status';status.textContent=action==='test'?'Verbindung wird geprüft …':'Wird gespeichert …';output.replaceChildren();output.classList.add('hidden');
  try{
    const result=await post('/api/v1/integrations/'+action,action==='remove'?{provider}:body);
    if(action==='test'){
      status.textContent=result.ok?'Verbindungstest erfolgreich. Bitte Datenprobe und Hinweise prüfen.':'Verbindungstest unvollständig oder fehlgeschlagen. Details siehe unten.';
      status.classList.add(result.ok?'success':'failure');
      output.classList.remove('hidden');
      const checks=document.createElement('p');checks.className='integration-note';checks.textContent='Relevante Felder in der Datenprobe: '+result.checks.map(check=>`${check.name}: ${check.found?'vorhanden':'nicht nachgewiesen'}`).join(' · ');
      output.innerHTML=`<p class="integration-note">${esc(result.note)}</p><p class="integration-meta">${esc(new Date(result.checked_at).toLocaleString('de-DE'))} · ${result.duration_ms} ms · Test speichert keine Daten</p>`+result.steps.map(step=>`<section class="debug-step"><strong>${step.ok?'✓':'✕'} ${esc(step.name)}${step.status?' · HTTP '+step.status:''}</strong><p class="step-path">${esc(step.path||'')} ${step.duration_ms!==undefined?'· '+step.duration_ms+' ms':''}</p><p>${esc(step.message)}</p>${step.count!==undefined?`<p>${step.count} Datensätze in der Antwort · Vorschau maximal 5</p><p>Felder: ${esc(step.fields.join(', ')||'Keine Datensatzfelder geliefert')}</p><details open><summary>Bereinigte Datenvorschau</summary><pre>${esc(JSON.stringify(step.preview,null,2))}</pre></details>`:''}</section>`).join('');
      output.prepend(checks);
    }else{
      field('secret').value='';
      field('secret').placeholder=action==='save'?'Gespeichert – leer lassen zum Beibehalten':integrationInfo[provider].label+' eingeben';
      card.querySelector('.badge').textContent=action==='save'?'Gespeichert':'Nicht verknüpft';
      status.textContent=action==='save'?'Verbindungskonfiguration gespeichert. Zugangsdaten werden verschlüsselt aufbewahrt.':'Gespeicherte Zugangsdaten entfernt.';status.classList.add('success');
    }
  }catch(error){status.textContent=error.message;status.classList.add('failure');}
  finally{controls.forEach(x=>x.disabled=false);}
});
boot();
