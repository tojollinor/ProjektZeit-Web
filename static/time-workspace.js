/* Local event workspace: one renderer, one request lifecycle per visible panel. */
(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const h=v=>esc(String(v??''));
 const hours=s=>`${Math.floor(s/3600)}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;
 const today=()=>new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Berlin'});
 const sources={manual:'Projektzeit',starface:'Telefonat',teamviewer:'Fernwartung',zammad:'Ticket'};
 const instances=new Set();
 function layout(events,start,end){
  const groups=new Map();
  for(const e of events){const a=Math.max(+new Date(e.start),start),b=Math.min(e.end?+new Date(e.end):e.running?Date.now():a,end);if(!Number.isFinite(a)||b<a||a>=end)continue;const label=`${e.employee} · ${sources[e.source]||e.source}`;if(!groups.has(label))groups.set(label,[]);groups.get(label).push({e,a,b});}
  const out=[];
  for(const [label,items] of groups){const lanes=[];for(const item of items.sort((a,b)=>a.a-b.a||a.b-b.b)){let lane=lanes.findIndex(x=>x<=item.a);if(lane<0)lane=lanes.length;lanes[lane]=item.b;out.push({...item,label,lane});}}
  return out;
 }
 window.pzTimeLayout=layout;
 function mount(host,scope={}){
  if(q(':scope > [data-time-workspace]',host))return;
  const panel=document.createElement('article');panel.className='panel time-workspace';panel.dataset.timeWorkspace='';
  panel.innerHTML=`<div class="panel-head"><div><p class="eyebrow">ZEITEN PRÜFEN UND ZUORDNEN</p><h3>${scope.customer_id?'Kundenzeitstrahl':scope.projectView?'Projektzeitstrahl':'Mein Arbeitstag'}</h3></div><button class="secondary" data-tw-refresh aria-label="Zeiten aktualisieren">↻</button></div><div class="tw-toolbar"><label>Datum<input type="date" data-tw-day></label><label>Zeitraum<select data-tw-days><option value="1">Ein Tag</option><option value="7">7 Tage ab Datum</option><option value="30">30 Tage ab Datum</option></select></label><label>Projekt<select data-tw-project><option value="">Alle Projekte</option></select></label><label data-tw-team-label hidden><input type="checkbox" data-tw-team> Team anzeigen</label></div><div class="tw-tabs" role="tablist" aria-label="Zeitansicht"><button class="secondary" data-tw-mode="timeline">Zeitstrahl</button><button class="secondary" data-tw-mode="inbox">Zuordnungseingang</button><button class="secondary" data-tw-mode="review">Tagesabschluss</button><button class="secondary" data-tw-mode="bookings">Geprüfte Buchungen</button></div><p data-tw-status role="status"></p><div data-tw-summary class="tw-summary"></div><div data-tw-content></div>`;
  host.prepend(panel);q('[data-tw-day]',panel).value=today();
  let data=null,mode=window.pzUI?.get('time-tab','timeline')||'timeline',controller=null,generation=0,loaded=false,saving=false;
  const selected=new Map();
  const visible=()=>panel.isConnected&&!!panel.getBoundingClientRect().height&&!document.hidden;
  const body=()=>({day:q('[data-tw-day]',panel).value,days:Number(q('[data-tw-days]',panel).value),customer_id:scope.customer_id||0,project_id:Number(q('[data-tw-project]',panel).value)||scope.project_id||0,team:q('[data-tw-team]',panel).checked});
  const status=message=>{q('[data-tw-status]',panel).textContent=message;};
  async function load(){
   if(!visible())return;const version=++generation;controller?.abort();controller=new AbortController();status('Lokale Zeiten werden geladen …');q('[data-tw-refresh]',panel).disabled=true;const timer=setTimeout(()=>{if(version===generation){controller.abort();status('Zeitabfrage dauert zu lange. Bitte erneut versuchen.');}},15000);
   try{const r=await api('/api/v1/time-workspace/read',{method:'POST',body:JSON.stringify(body()),signal:controller.signal});if(version!==generation)return;data=r;loaded=true;selected.clear();const select=q('[data-tw-project]',panel),value=select.value;select.innerHTML='<option value="">Alle Projekte</option>'+r.projects.filter(p=>!scope.customer_id||p.customer_id===scope.customer_id).map(p=>`<option value="${p.id}">${h(p.name)}</option>`).join('');select.value=value;q('[data-tw-team-label]',panel).hidden=!r.can_view_team||!(scope.customer_id||Number(value));status(r.truncated?'Mehr als 1.000 Ereignisse: Bitte Zeitraum oder Projekt eingrenzen. Summen beziehen sich auf die angezeigten Ereignisse.':'Lokaler Datenbestand · '+new Date().toLocaleTimeString('de-DE'));render();}
   catch(e){if(version===generation&&e.name!=='AbortError')status(e.message);}
   finally{clearTimeout(timer);if(version===generation)q('[data-tw-refresh]',panel).disabled=false;}
  }
  async function mutate(action,payload){if(saving)return;saving=true;status('Wird gespeichert …');try{await post('/api/v1/time-workspace/'+action,{...body(),...payload});await load();if(typeof refresh==='function')await refresh();}catch(e){status(e.message);}finally{saving=false;}}
  function row(e){const article=document.createElement('article');article.className='tw-event-card';const key=`${e.source}:${e.key}`;
   article.innerHTML=`<div class="tw-event-title"><input type="checkbox" data-tw-select aria-label="Ereignis auswählen" ${e.owner_id!==state.user.id?'disabled':''}><strong>${h(e.title)}</strong><span class="badge">${h(sources[e.source]||e.source)}</span></div><p>${h(e.employee)} · ${h(new Date(e.start).toLocaleString('de-DE'))} – ${e.end?h(new Date(e.end).toLocaleTimeString('de-DE')):e.running?'läuft':'keine Zeitmessung'} · ${hours(e.seconds)}</p><p>${h(data.projects.find(p=>p.id===e.project_id)?.name||'Projekt fehlt')}${e.overlap?' · Überschneidung':''}${e.reviewed?e.billable?' · Abrechenbar geprüft':' · Ohne Abrechnung geprüft':' · Ungeprüft'}</p><div class="panel-actions" data-tw-actions></div>`;
   q('[data-tw-select]',article).onchange=ev=>ev.target.checked?selected.set(key,{source:e.source,key:e.key}):selected.delete(key);
   const actions=q('[data-tw-actions]',article);
   if(e.owner_id===state.user.id&&e.project_id&&e.end&&!e.running&&!e.reviewed){for(const [label,billable] of [['Ohne Abrechnung prüfen',false],['Abrechenbar freigeben',true]]){const b=document.createElement('button');b.className='secondary';b.textContent=label;b.onclick=()=>mutate('review',{source:e.source,key:e.key,billable});actions.append(b);}}
   if(e.owner_id===state.user.id){
    const place=document.createElement('button');place.className='secondary';place.textContent='Einsatzort / Notdienst';place.onclick=()=>window.pzCompany?.eventDialog(e);actions.append(place);
    if(e.reviewed){const b=document.createElement('button');b.className='secondary';b.textContent='Prüfung wieder öffnen';b.onclick=()=>mutate('reopen',{source:e.source,key:e.key});actions.append(b);}
    for(const p of e.suggestions||[]){const b=document.createElement('button');b.className='secondary';b.textContent='Vorschlag übernehmen: '+p.name;b.onclick=()=>mutate('assign',{items:[{source:e.source,key:e.key}],project_id:p.id});actions.append(b);}
   }
   return article;
  }
  function render(){if(!data)return;const s=data.summary;q('[data-tw-summary]',panel).innerHTML=`<span>${s.unassigned} ohne Projekt</span><span>${s.unreviewed} ungeprüft</span><span>${s.overlaps} überlappend</span><span>${s.running} laufende Zeiten</span><span>Abrechenbar: ${hours(s.billable_seconds)}</span>`;
   qa('[data-tw-mode]',panel).forEach(b=>(b.classList.toggle('primary',b.dataset.twMode===mode),b.setAttribute('aria-selected',String(b.dataset.twMode===mode)),b.setAttribute('role','tab')));const content=q('[data-tw-content]',panel);content.replaceChildren();
   if(mode==='timeline'){
    const scroll=document.createElement('div');scroll.className='tw-timeline-scroll';const chart=document.createElement('div');chart.className='tw-timeline';scroll.append(chart);content.append(scroll);
    const start=+new Date(data.start),end=+new Date(data.end),axis=document.createElement('div');axis.className='tw-axis';for(let i=0;i<=8;i++){const tick=document.createElement('span');tick.style.left=`${i/8*100}%`;tick.textContent=new Date(start+(end-start)*i/8).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});axis.append(tick);}chart.append(axis);
    const tracks=new Map();const add=(label,lane,a,b,title,event,kind)=>{const key=label+':'+lane;let track=tracks.get(key);if(!track){track=document.createElement('div');track.className='tw-track';const cap=document.createElement('span');cap.textContent=label+(lane?' · '+(lane+1):'');track.append(cap);chart.append(track);tracks.set(key,track);}const bar=document.createElement('button');bar.type='button';bar.className='tw-bar '+kind;bar.style.left=`${Math.max(0,(a-start)/(end-start)*100)}%`;bar.style.width=`${Math.max(.3,(b-a)/(end-start)*100)}%`;bar.title=title;bar.setAttribute('aria-label',title);bar.onclick=()=>{const dialog=document.createElement('dialog');dialog.className='tw-detail';const close=document.createElement('button');close.className='secondary';close.textContent='Schließen';close.onclick=()=>dialog.close();dialog.append(close);if(event)dialog.append(row(event));else{const text=document.createElement('p');text.textContent=title;dialog.append(text);}dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();};track.append(bar);};
    if(!scope.customer_id&&!scope.projectView){for(const [items,label,kind] of [[data.work,'Meine Arbeitszeit','work'],[data.pauses,'Meine Pausen','pause']])for(const e of items){const a=Math.max(start,+new Date(e.started_at)),b=Math.min(end,e.ended_at?+new Date(e.ended_at):Date.now());if(b>a)add(label,0,a,b,`${label}: ${hours((b-a)/1000)}`,null,kind);}}
    for(const item of layout(data.events,start,end))add(item.label,item.lane,item.a,item.b,`${item.e.title} · ${hours(item.e.seconds)}`,item.e,item.e.source);
    if(!tracks.size){const empty=document.createElement('p');empty.textContent='Keine Ereignisse im ausgewählten Zeitraum.';content.append(empty);}
   }
   if(mode==='review'){const notice=document.createElement('p');notice.textContent='Prüfe Zuordnungen, Überschneidungen und laufende Timer. Eine Freigabe beendet den Arbeitstag nicht automatisch. Tickets ohne gemessene Dauer sind Hinweise und keine abrechenbare Zeit.';content.append(notice);}
   if(mode!=='timeline'){
    const controls=document.createElement('div');controls.className='tw-toolbar';controls.innerHTML=`<label>Auswahl zuordnen<select data-tw-assignment><option value="">Projekt wählen</option>${data.projects.filter(p=>p.customer_id).map(p=>`<option value="${p.id}">${h(p.name)} · ${h(data.customers.find(c=>c.id===p.customer_id)?.name||'')}</option>`).join('')}</select></label><button class="primary" data-tw-assign>Ausgewählte zuordnen</button>`;content.append(controls);q('[data-tw-assign]',controls).onclick=()=>{if(!selected.size){status('Bitte Ereignisse auswählen.');return;}mutate('assign',{items:[...selected.values()],project_id:Number(q('[data-tw-assignment]',controls).value)});};
    const list=document.createElement('div');list.className='tw-event-list';const entries=data.events.filter(e=>mode==='inbox'?!e.project_id:mode==='bookings'?e.reviewed:true);for(const e of entries)list.append(row(e));if(!entries.length)list.textContent=mode==='inbox'?'Alle angezeigten Ereignisse sind einem Projekt zugeordnet.':'Keine passenden Ereignisse.';content.append(list);
   }
  }
  q('[data-tw-refresh]',panel).onclick=load;for(const selector of ['[data-tw-day]','[data-tw-days]','[data-tw-project]','[data-tw-team]'])q(selector,panel).onchange=()=>{if(!scope.customer_id&&!Number(q('[data-tw-project]',panel).value))q('[data-tw-team]',panel).checked=false;load();};
  qa('[data-tw-mode]',panel).forEach(b=>b.onclick=()=>{mode=b.dataset.twMode;window.pzUI?.set('time-tab',mode);selected.clear();render();});
  const instance={panel,load,invalidate:()=>{loaded=false;if(!saving&&visible())load();},stop:()=>{controller?.abort();generation++;},isLoaded:()=>loaded};instances.add(instance);load();return instance;
 }
 function sync(){for(const x of instances){if(!x.panel.isConnected){x.stop();instances.delete(x);}else if(!x.panel.getBoundingClientRect().height||document.hidden)x.stop();else if(!x.isLoaded())x.load();}
  const view=q('.view.active-view');if(!view)return;if(view.id==='view-projects')mount(view,{projectView:true});if(view.id==='view-bookkeeping')mount(view);}
 function attachCustomer(box,id){if(q('[data-tab="timeline"]',box))return;const b=document.createElement('button');b.className='secondary';b.dataset.tab='timeline';b.textContent='Zeitstrahl';q('.customer-tabs',box)?.append(b);const pane=document.createElement('section');pane.dataset.pane='timeline';pane.className='hidden';box.append(pane);b.onclick=()=>{qa('[data-pane]',box).forEach(p=>p.classList.toggle('hidden',p!==pane));qa('[data-tab]',box).forEach(t=>t.classList.toggle('primary',t===b));mount(pane,{customer_id:id});};}
 document.addEventListener('pz-project-select',async e=>{const host=q('#view-projects');if(!host)return;const x=[...instances].find(x=>x.panel.closest('#view-projects'))||mount(host,{projectView:true});await x.load();const select=q('[data-tw-project]',host);if(select){select.value=e.detail.id;select.dispatchEvent(new Event('change'));}});
 window.pzTimeWorkspace={mount,attachCustomer};
 document.addEventListener('pz-view-changed',()=>requestAnimationFrame(sync));document.addEventListener('visibilitychange',sync);
 document.addEventListener('pz-data-changed',()=>{for(const x of instances)x.invalidate();});
 const dashboard=q('#view-dashboard');if(dashboard){const button=document.createElement('button');button.className='secondary';button.textContent='Tagesabschluss prüfen';button.onclick=()=>{showView('projects');requestAnimationFrame(()=>q('[data-tw-mode="review"]',q('#view-projects'))?.click());};dashboard.prepend(button);}
 sync();
})();
