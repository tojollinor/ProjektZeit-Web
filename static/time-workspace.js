/* Project workday, provider timeline and assignment inbox. */
(()=>{
 const q=(s,r=document)=>r?.querySelector?.(s),qa=(s,r=document)=>[...(r?.querySelectorAll?.(s)||[])];
 const h=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Berlin'}).format(new Date());
 const clock=v=>v?new Date(v).toLocaleTimeString('de-DE',{timeZone:'Europe/Berlin',hour:'2-digit',minute:'2-digit'}):'–';
 const dateTime=v=>v?new Date(v).toLocaleString('de-DE',{timeZone:'Europe/Berlin'}):'–';
 const hours=s=>`${s<0?'−':''}${Math.floor(Math.abs(Number(s)||0)/3600)}:${String(Math.floor(Math.abs(Number(s)||0)%3600/60)).padStart(2,'0')}:${String(Math.floor(Math.abs(Number(s)||0)%60)).padStart(2,'0')}`;
 const sourceNames={manual:'Meine Projekte',starface:'Meine Telefonate',zammad:'Meine Tickets',teamviewer:'Meine Verbindungen'};
 const sourceBadges={manual:'Projekt',starface:'Telefonat',zammad:'Ticket',teamviewer:'TeamViewer'};
 const icon={
  refresh:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17.7 6.3A8 8 0 1 0 20 12h-2a6 6 0 1 1-1.8-4.3L13 11h8V3l-3.3 3.3Z"/></svg>',
  pin:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7Zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5Z"/></svg>',
  close:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6.4 5 5.6 5.6L17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4-5.6-5.6L6.4 19 5 17.6l5.6-5.6L5 6.4 6.4 5Z"/></svg>'
 };
 const instances=new Set();

 function layout(events,start,end){
  const groups=new Map();
  for(const e of events){
   const parsedStart=+new Date(e.start),parsedEnd=e.end?+new Date(e.end):e.running?Date.now():parsedStart;
   const a=Math.max(parsedStart,start),b=Math.min(parsedEnd,end);
   if(!Number.isFinite(a)||!Number.isFinite(b)||b<a||a>=end)continue;
   const label=`${e.employee} · ${sourceNames[e.source]||e.source}`;
   if(!groups.has(label))groups.set(label,[]);groups.get(label).push({e,a,b});
  }
  const out=[];
  for(const [label,items] of groups){
   const lanes=[];
   for(const item of items.sort((a,b)=>a.a-b.a||a.b-b.b)){
    let lane=lanes.findIndex(x=>x<=item.a);if(lane<0)lane=lanes.length;lanes[lane]=item.b;out.push({...item,label,lane});
   }
  }
  return out;
 }
 window.pzTimeLayout=layout;

 function horizontalNavigation(scroller){
  let dragging=false,startX=0,startLeft=0;
  scroller.addEventListener('wheel',event=>{
   if(scroller.scrollWidth<=scroller.clientWidth)return;
   const delta=Math.abs(event.deltaX)>Math.abs(event.deltaY)?event.deltaX:event.deltaY;
   if(!delta)return;
   const next=Math.max(0,Math.min(scroller.scrollWidth-scroller.clientWidth,scroller.scrollLeft+delta));
   if(next===scroller.scrollLeft)return;
   event.preventDefault();scroller.scrollLeft=next;
  },{passive:false});
  scroller.addEventListener('pointerdown',event=>{
   if(event.pointerType!=='mouse'||event.button!==0||event.target.closest('button,input,select,label'))return;
   dragging=true;startX=event.clientX;startLeft=scroller.scrollLeft;scroller.classList.add('is-dragging');scroller.setPointerCapture(event.pointerId);
  });
  scroller.addEventListener('pointermove',event=>{if(dragging)scroller.scrollLeft=startLeft-(event.clientX-startX);});
  const stop=()=>{dragging=false;scroller.classList.remove('is-dragging');};scroller.addEventListener('pointerup',stop);scroller.addEventListener('pointercancel',stop);
 }

 function mount(host,scope={}){
  if(!host||q(':scope > [data-time-workspace]',host))return;
  const panel=document.createElement('article');panel.className='panel time-workspace';panel.dataset.timeWorkspace='';
  panel.innerHTML=`<div class="panel-head"><div><p class="eyebrow">ZEITEN PRÜFEN UND ZUORDNEN</p><h3>${scope.customer_id?'Kundenzeitstrahl':'Mein Arbeitstag'}</h3></div><button type="button" class="secondary tw-icon-button" data-tw-refresh aria-label="Zeiten aktualisieren" title="Neu laden">${icon.refresh}</button></div>
   <div class="tw-toolbar"><label>Datum<input type="date" data-tw-day></label><label>Zeitraum<select data-tw-days><option value="1">Ein Tag</option><option value="7">7 Tage ab Datum</option><option value="30">30 Tage ab Datum</option></select></label><label>Projekt<select data-tw-project><option value="">Alle Projekte</option></select></label><label class="tw-team-toggle" data-tw-team-label hidden><input type="checkbox" data-tw-team> Team anzeigen</label></div>
   <div class="tw-tabs" role="tablist" aria-label="Zeitansicht"><button type="button" class="secondary" data-tw-mode="timeline">Zeitstrahl</button><button type="button" class="secondary" data-tw-mode="inbox">Zuordnungseingang</button><button type="button" class="secondary" data-tw-mode="review">Tagesabschluss</button><button type="button" class="secondary" data-tw-mode="bookings">Geprüfte Buchungen</button></div>
   <p data-tw-status role="status"></p><div data-tw-summary class="tw-summary"></div><div data-tw-content></div>`;
  const intro=q(':scope > .pz-page-intro',host),work=q(':scope > .tracking-grid',host);if(work)work.after(panel);else if(intro)intro.after(panel);else host.prepend(panel);
  q('[data-tw-day]',panel).value=today();
  let data=null,mode=window.pzUI?.get('time-tab','timeline')||'timeline',controller=null,generation=0,loaded=false,saving=false;
  const selected=new Map();
  const visible=()=>panel.isConnected&&!!panel.getBoundingClientRect().height&&!document.hidden;
  const requestBody=()=>({day:q('[data-tw-day]',panel).value,days:Number(q('[data-tw-days]',panel).value),customer_id:scope.customer_id||0,project_id:Number(q('[data-tw-project]',panel).value)||scope.project_id||0,team:q('[data-tw-team]',panel).checked});
  const status=message=>{q('[data-tw-status]',panel).textContent=message;};
  function customerName(id){return data?.customers.find(c=>Number(c.id)===Number(id))?.name||'';}
  function projectName(id){return data?.projects.find(p=>Number(p.id)===Number(id))?.name||'';}
  function projectOptions(customerId,current=0){return '<option value="">Projekt wählen …</option>'+data.projects.filter(p=>!customerId||Number(p.customer_id)===Number(customerId)).map(p=>`<option value="${p.id}" ${Number(p.id)===Number(current)?'selected':''}>${h(p.name)}</option>`).join('');}

  async function load(){
   if(!visible())return;const version=++generation;controller?.abort();controller=new AbortController();status('Lokale Zeiten werden geladen …');q('[data-tw-refresh]',panel).disabled=true;
   const timer=setTimeout(()=>{if(version===generation){controller.abort();status('Zeitabfrage dauert zu lange. Bitte erneut versuchen.');}},15000);
   try{
    const r=await api('/api/v1/time-workspace/read',{method:'POST',body:JSON.stringify(requestBody()),signal:controller.signal});if(version!==generation)return;
    data=r;loaded=true;selected.clear();const select=q('[data-tw-project]',panel),value=select.value;select.innerHTML='<option value="">Alle Projekte</option>'+r.projects.filter(p=>!scope.customer_id||Number(p.customer_id)===Number(scope.customer_id)).map(p=>`<option value="${p.id}">${h(p.name)}</option>`).join('');select.value=value;
    q('[data-tw-team-label]',panel).hidden=!r.can_view_team||!(scope.customer_id||Number(value));status(r.truncated?'Mehr als 1.000 Ereignisse: Zeitraum oder Projekt bitte eingrenzen.':'Lokaler Datenbestand · '+new Date().toLocaleTimeString('de-DE'));render();
   }catch(error){if(version===generation&&error.name!=='AbortError')status(error.message);}finally{clearTimeout(timer);if(version===generation)q('[data-tw-refresh]',panel).disabled=false;}
  }
  async function mutate(action,payload){if(saving)return;saving=true;status('Wird gespeichert …');try{await post('/api/v1/time-workspace/'+action,{...requestBody(),...payload});await load();if(typeof refresh==='function')await refresh();}catch(error){status(error.message);}finally{saving=false;}}

  async function assignEvent(e,customerId,projectId){
   if(!projectId&&e.source==='manual'){status('Projektzeiten benötigen eine Projektzuordnung.');return;}
   try{
    if(customerId&&e.source!=='manual'&&!projectId){await post('/api/v1/provider/assign/customer',{provider:e.source,external_key:e.key,customer_id:Number(customerId),bulk:false,match_type:e.match_type||'',match_value:e.match_value||''});await load();document.dispatchEvent(new CustomEvent('pz-data-changed'));}
    else await mutate('assign',{items:[{source:e.source,key:e.key}],project_id:Number(projectId),confirm_reassign:true});
   }catch(error){status(error.message);}
  }

  function assignmentControls(e,compact=false){
   const box=document.createElement('div');box.className=compact?'tw-assignment tw-assignment-compact':'tw-assignment';
   box.innerHTML=`<label>Kunde<select data-tw-customer ${e.source==='manual'?'disabled':''}><option value="">Kunde wählen …</option>${data.customers.map(c=>`<option value="${c.id}" ${Number(c.id)===Number(e.customer_id)?'selected':''}>${h(c.name)}</option>`).join('')}</select></label><label>Projekt<select data-tw-project-choice>${projectOptions(e.customer_id,e.project_id)}</select></label><button type="button" class="primary" data-tw-save-assignment>Zuordnen</button>`;
   const customer=q('[data-tw-customer]',box),project=q('[data-tw-project-choice]',box);customer.onchange=()=>{project.innerHTML=projectOptions(customer.value);};q('[data-tw-save-assignment]',box).onclick=()=>assignEvent(e,customer.value,project.value);
   return box;
  }

  function openDetail(e){
   const d=document.createElement('dialog');d.className='tw-detail';const duration=e.seconds!=null?hours(e.seconds):'–';
   d.innerHTML=`<div class="tw-detail-head"><div><p class="eyebrow">${h(sourceBadges[e.source]||e.type||'ZEIT')}</p><h3>${h(e.title||'Zeitdetail')}</h3></div><button type="button" class="secondary tw-icon-button" data-close aria-label="Schließen" title="Schließen">${icon.close}</button></div><dl class="tw-detail-facts"><dt>Mitarbeiter</dt><dd>${h(e.employee||state.user?.username||'–')}</dd><dt>Datum</dt><dd>${h(dateTime(e.start))}</dd><dt>Zeitraum</dt><dd>${h(clock(e.start))} – ${h(e.end?clock(e.end):e.running?'läuft':'keine Zeitmessung')}</dd><dt>Dauer</dt><dd>${h(duration)}</dd><dt>Kunde</dt><dd>${h(customerName(e.customer_id)||'Nicht zugeordnet')}</dd><dt>Projekt</dt><dd>${h(projectName(e.project_id)||'Nicht zugeordnet')}</dd><dt>Status</dt><dd>${h(e.reviewed?(e.billable?'Abrechenbar geprüft':'Ohne Abrechnung geprüft'):'Ungeprüft')}${e.overlap?' · Überschneidung':''}</dd></dl>${e.note?`<section class="tw-detail-note"><strong>Bemerkung</strong><p>${h(e.note)}</p></section>`:''}<div data-detail-assignment></div>`;
   q('[data-close]',d).onclick=()=>d.close();d.addEventListener('close',()=>d.remove(),{once:true});if(e.owner_id===state.user.id&&sourceNames[e.source])q('[data-detail-assignment]',d).append(assignmentControls(e));document.body.append(d);d.showModal();
  }

  function eventRow(e){
   const article=document.createElement('article');article.className='tw-event-card';const key=`${e.source}:${e.key}`;
   article.innerHTML=`<div class="tw-event-main"><div class="tw-event-title"><input type="checkbox" data-tw-select aria-label="Ereignis auswählen" ${e.owner_id!==state.user.id?'disabled':''}><button type="button" class="tw-event-open" data-open-detail><strong>${h(e.title)}</strong><span class="badge">${h(sourceBadges[e.source]||e.source)}</span></button></div><div class="tw-event-meta"><span>${h(e.employee)}</span><span>${h(dateTime(e.start))} – ${h(e.end?clock(e.end):e.running?'läuft':'ohne Messdauer')}</span><span>${h(hours(e.seconds))}</span><span>${h(projectName(e.project_id)||'Projekt fehlt')}</span><span>${h(customerName(e.customer_id)||'Kunde fehlt')}</span><span>${e.reviewed?(e.billable?'Abrechenbar geprüft':'Geprüft'):'Ungeprüft'}${e.overlap?' · Überschneidung':''}</span></div></div><div class="tw-event-actions" data-tw-actions></div>`;
   q('[data-tw-select]',article).onchange=ev=>ev.target.checked?selected.set(key,{source:e.source,key:e.key}):selected.delete(key);q('[data-open-detail]',article).onclick=()=>openDetail(e);
   const actions=q('[data-tw-actions]',article);
   if(e.owner_id===state.user.id){
    actions.append(assignmentControls(e,true));
    const place=document.createElement('button');place.type='button';place.className='secondary tw-icon-button';place.title='Einsatzort und Notdienst';place.setAttribute('aria-label','Einsatzort und Notdienst');place.innerHTML=icon.pin;place.onclick=()=>window.pzCompany?.eventDialog(e);actions.append(place);
    if(e.project_id&&e.end&&!e.running&&!e.reviewed)for(const [label,billable] of [['Ohne Abrechnung prüfen',false],['Abrechenbar freigeben',true]]){const b=document.createElement('button');b.type='button';b.className='secondary';b.textContent=label;b.onclick=()=>mutate('review',{source:e.source,key:e.key,billable});actions.append(b);}
    if(e.reviewed){const reopen=document.createElement('button');reopen.type='button';reopen.className='secondary';reopen.textContent='Prüfung öffnen';reopen.onclick=()=>mutate('reopen',{source:e.source,key:e.key});actions.append(reopen);}
    if((e.suggestions||[]).length){const suggestions=document.createElement('div');suggestions.className='tw-suggestions';suggestions.innerHTML='<small>Vorschläge</small>';for(const p of e.suggestions){const b=document.createElement('button');b.type='button';b.className='secondary subtle';b.textContent=p.name;b.onclick=()=>mutate('assign',{items:[{source:e.source,key:e.key}],project_id:p.id,confirm_reassign:true});suggestions.append(b);}actions.append(suggestions);}
   }
   return article;
  }

  function addAxis(chart,start,end){const axis=document.createElement('div');axis.className='tw-axis';const hoursTotal=Math.max(1,(end-start)/3600000),steps=Math.min(9,Math.max(3,Math.ceil(hoursTotal/3)));for(let i=0;i<steps;i++){const ratio=i/(steps-1),value=start+(end-start)*ratio,label=document.createElement('span');label.style.left=(ratio*100)+'%';label.textContent=new Date(value).toLocaleString('de-DE',{timeZone:'Europe/Berlin',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});axis.append(label);}chart.append(axis);}
  function renderTimeline(content){
   const start=+new Date(data.start),end=+new Date(data.end),scroll=document.createElement('div');scroll.className='tw-timeline-scroll';scroll.tabIndex=0;scroll.setAttribute('aria-label','Zeitstrahl – horizontal scrollbar');const chart=document.createElement('div');chart.className='tw-timeline';chart.style.minWidth=Math.max(960,Number(q('[data-tw-days]',panel).value)*820)+'px';scroll.append(chart);content.append(scroll);horizontalNavigation(scroll);addAxis(chart,start,end);
   const work=data.work.map(w=>({source:'work',key:w.id,title:'Arbeitszeit',employee:state.user.username,start:w.started_at,end:w.ended_at||new Date().toISOString(),seconds:Math.max(0,(+new Date(w.ended_at||Date.now())-+new Date(w.started_at))/1000),owner_id:state.user.id}));
   const groups=[{key:'work',label:'Meine Arbeitszeit',items:work},{key:'manual',label:'Meine Projekte',items:data.events.filter(e=>e.source==='manual')},{key:'zammad',label:'Meine Tickets',items:data.events.filter(e=>e.source==='zammad')},{key:'starface',label:'Meine Telefonate',items:data.events.filter(e=>e.source==='starface')},{key:'teamviewer',label:'Meine Verbindungen',items:data.events.filter(e=>e.source==='teamviewer')}];
   for(const group of groups){const track=document.createElement('section');track.className='tw-track';track.dataset.source=group.key;track.innerHTML=`<strong>${group.label}</strong>`;const laid=layout(group.items,start,end);let maxLane=0;for(const item of laid){maxLane=Math.max(maxLane,item.lane);const bar=document.createElement('button');bar.type='button';bar.className=`tw-bar ${group.key}`;bar.style.left=((item.a-start)/(end-start)*100)+'%';bar.style.width=Math.max(.35,(item.b-item.a)/(end-start)*100)+'%';bar.style.top=(30+item.lane*28)+'px';bar.title=`${item.e.title} · ${hours(item.e.seconds)}`;bar.setAttribute('aria-label',bar.title);bar.onclick=()=>openDetail(item.e);track.append(bar);}track.style.height=(72+maxLane*28)+'px';if(!group.items.length){const empty=document.createElement('span');empty.className='tw-track-empty';empty.textContent='Keine Einträge';track.append(empty);}chart.append(track);}
  }

  function bulkControls(content){
   const controls=document.createElement('div');controls.className='tw-bulk-assignment';controls.innerHTML=`<label>Kunde<select data-bulk-customer><option value="">Kunde wählen …</option>${data.customers.map(c=>`<option value="${c.id}">${h(c.name)}</option>`).join('')}</select></label><label>Projekt<select data-bulk-project>${projectOptions(0)}</select></label><button type="button" class="primary" data-bulk-save>Ausgewählte zuordnen</button>`;const customer=q('[data-bulk-customer]',controls),project=q('[data-bulk-project]',controls);customer.onchange=()=>project.innerHTML=projectOptions(customer.value);q('[data-bulk-save]',controls).onclick=()=>{if(!selected.size){status('Bitte mindestens ein Ereignis auswählen.');return;}if(!project.value){status('Bitte ein Projekt auswählen.');return;}mutate('assign',{items:[...selected.values()],project_id:Number(project.value),confirm_reassign:true});};content.append(controls);
  }

  function render(){
   if(!data)return;qa('[data-tw-mode]',panel).forEach(b=>{b.classList.toggle('primary',b.dataset.twMode===mode);b.classList.toggle('secondary',b.dataset.twMode!==mode);b.setAttribute('aria-selected',String(b.dataset.twMode===mode));});const s=data.summary;q('[data-tw-summary]',panel).innerHTML=`<span>${s.unassigned} ohne Projekt</span><span>${s.unreviewed} ungeprüft</span><span>${s.overlaps} überlappend</span><span>${s.running} laufende Zeiten</span><span>Abrechenbar ${hours(s.billable_seconds)}</span>`;
   const content=q('[data-tw-content]',panel);content.replaceChildren();if(mode==='timeline'){renderTimeline(content);return;}bulkControls(content);if(mode==='review'){const notice=document.createElement('p');notice.className='tw-review-note';notice.textContent='Zuordnungen, Überschneidungen und laufende Timer prüfen. Tickets ohne Messdauer bleiben Hinweise und werden nicht automatisch abgerechnet.';content.append(notice);}const entries=data.events.filter(e=>mode==='inbox'?!e.project_id:mode==='bookings'?e.reviewed:true),list=document.createElement('div');list.className='tw-event-list';for(const e of entries)list.append(eventRow(e));if(!entries.length)list.innerHTML=`<p class="tw-empty">${mode==='inbox'?'Alle angezeigten Ereignisse sind zugeordnet.':'Keine passenden Ereignisse.'}</p>`;content.append(list);
  }

  q('[data-tw-refresh]',panel).onclick=load;for(const selector of ['[data-tw-day]','[data-tw-days]','[data-tw-project]','[data-tw-team]'])q(selector,panel).onchange=()=>{if(!scope.customer_id&&!Number(q('[data-tw-project]',panel).value))q('[data-tw-team]',panel).checked=false;load();};qa('[data-tw-mode]',panel).forEach(b=>b.onclick=()=>{mode=b.dataset.twMode;window.pzUI?.set('time-tab',mode);selected.clear();render();});
  const instance={panel,load,invalidate:()=>{loaded=false;if(!saving&&visible())load();},stop:()=>{controller?.abort();generation++;},isLoaded:()=>loaded};instances.add(instance);load();return instance;
 }

 function sync(){for(const x of instances){if(!x.panel.isConnected){x.stop();instances.delete(x);}else if(!x.panel.getBoundingClientRect().height||document.hidden)x.stop();else if(!x.isLoaded())x.load();}const view=q('.view.active-view');if(view?.id==='view-projects')mount(view,{projectView:true});}
 function attachCustomer(box,id){if(q('[data-tab="timeline"]',box))return;const b=document.createElement('button');b.className='secondary';b.dataset.tab='timeline';b.textContent='Zeitstrahl';q('.customer-tabs',box)?.append(b);const pane=document.createElement('section');pane.dataset.pane='timeline';pane.className='hidden';box.append(pane);b.onclick=()=>{qa('[data-pane]',box).forEach(p=>p.classList.toggle('hidden',p!==pane));qa('[data-tab]',box).forEach(t=>t.classList.toggle('primary',t===b));mount(pane,{customer_id:id});};}
 document.addEventListener('pz-project-select',async event=>{const host=q('#view-projects');if(!host)return;const instance=[...instances].find(x=>x.panel.closest('#view-projects'))||mount(host,{projectView:true});await instance?.load();const select=q('[data-tw-project]',host);if(select){select.value=event.detail.id;select.dispatchEvent(new Event('change'));}});
 window.pzTimeWorkspace={mount,attachCustomer};document.addEventListener('pz-view-changed',()=>requestAnimationFrame(sync));document.addEventListener('visibilitychange',sync);document.addEventListener('pz-data-changed',()=>{for(const x of instances)x.invalidate();});
 const dashboard=q('#view-dashboard');if(dashboard&&!q('[data-open-day-review]',dashboard)){const button=document.createElement('button');button.type='button';button.className='secondary';button.dataset.openDayReview='';button.textContent='Tagesabschluss prüfen';button.onclick=()=>{showView('projects');requestAnimationFrame(()=>q('[data-tw-mode="review"]',q('#view-projects'))?.click());};dashboard.prepend(button);}sync();
})();
