const ticketDialog=document.createElement('dialog');ticketDialog.className='ticket-detail';
ticketDialog.innerHTML='<button>Schließen</button><div></div>';document.body.append(ticketDialog);
ticketDialog.querySelector('button').onclick=()=>ticketDialog.close();
let ticketRequest=0;ticketDialog.addEventListener('close',()=>ticketRequest++);
async function openTicket(id){
 const n=++ticketRequest,box=ticketDialog.querySelector('div');box.textContent='Ticket wird geladen …';ticketDialog.showModal();
 try{
  const d=await post('/api/v1/integrations/ticket',{provider:'zammad',ticket_id:id});if(n!==ticketRequest)return;
  box.innerHTML=`<h2>Ticket ${esc(d.ticket.number)} · ${esc(d.ticket.title)}</h2>`;
  const labels={organization:'Organisation',customer:'Kunde',owner:'Bearbeiter',group:'Gruppe',state:'Status',priority:'Priorität',created_at:'Erstellt',updated_at:'Aktualisiert'};
  for(const [key,label] of Object.entries(labels)){const p=document.createElement('p');p.textContent=label+': '+(d.ticket[key]??'–');box.append(p);}
  for(const a of d.articles){
   const h=document.createElement('h3'),p=document.createElement('pre');h.textContent=[a.subject||'Nachricht',a.from,a.created_at,a.internal?'Intern':''].filter(Boolean).join(' · ');
   let body=a.body||'';
   if(a.content_type==='text/html'){const doc=new DOMParser().parseFromString(body,'text/html');doc.querySelectorAll('script,style,iframe,object,img').forEach(x=>x.remove());doc.querySelectorAll('br,p,div').forEach(x=>x.append(doc.createTextNode('\n')));body=doc.body.textContent;}
   p.textContent=body;box.append(h,p);
   if(a.attachments?.length){const files=document.createElement('p');files.textContent='Anhänge: '+a.attachments.map(x=>x.filename||x.name||x.id).join(', ')+' (Download noch nicht verfügbar)';box.append(files);}
  }
  const details=document.createElement('details'),summary=document.createElement('summary'),raw=document.createElement('pre');summary.textContent='Alle gelieferten Ticketfelder';raw.textContent=JSON.stringify(d.ticket,null,2);details.append(summary,raw);box.append(details);
 }catch(e){if(n===ticketRequest)box.textContent=e.message;}
}
for(const section of document.querySelectorAll('.provider-view')){
 const provider=section.dataset.source;
 section.innerHTML=`<article class="panel"><h3>${esc(provider.toUpperCase())}</h3>${provider==='starface'?'<p class="starface-version" role="status">Version wird beim Öffnen geprüft.</p>':''}<div class="provider-toolbar"><input type="search" placeholder="Liste durchsuchen …" aria-label="Liste durchsuchen">${provider==='starface'?'<select data-days aria-label="Zeitraum"><option value="7">7 Tage</option><option value="30" selected>30 Tage</option><option value="90">90 Tage</option><option value="365">365 Tage</option></select>':provider==='teamviewer'?'<select data-days aria-label="Zeitraum"><option value="0">API-Standardzeitraum</option><option value="7">7 Tage</option><option value="30">30 Tage</option><option value="90">90 Tage</option><option value="365">365 Tage</option></select>':''}${provider==='starface'?'<select data-call-type aria-label="Anrufart"><option value="all">Alle Anrufe</option><option value="inbound">Eingehend</option><option value="outbound">Ausgehend</option><option value="missed">Verpasst</option></select>':''}<button class="primary admin-only">Daten laden</button></div><p class="list-status" role="status">Noch keine Daten geladen.</p><div class="table-wrap"><table><thead></thead><tbody></tbody></table></div></article>`;
 let rows=[],columns=[],nextOffset=null;
 const more=document.createElement('button');more.className='secondary hidden';more.textContent='Weitere Anrufe laden';
 if(provider==='starface')section.querySelector('article').append(more);
 async function version(){
  if(provider!=='starface')return;
  const label=section.querySelector('.starface-version');
  try{const info=await post('/api/v1/integrations/list',{provider,info_only:true});label.textContent=info.version?'STARFACE '+info.version:info.version_note;}catch(e){label.textContent=e.message;}
 }
 if(provider==='starface'){
  document.querySelector('[data-view="starface"]').addEventListener('click',version);
  window.addEventListener('starface-connected',version);
 }

 function render(){
  const q=section.querySelector('input').value.toLowerCase();section.querySelector('thead').innerHTML='<tr>'+columns.map(c=>`<th>${esc(c)}</th>`).join('')+'</tr>';
  const body=section.querySelector('tbody');body.replaceChildren();
  for(const row of rows.filter(r=>r.cells.join(' ').toLowerCase().includes(q))){const tr=document.createElement('tr');for(const v of row.cells){const td=document.createElement('td');td.textContent=v??'–';tr.append(td);}if(row.ticket_id){tr.className='ticket-link-row';tr.tabIndex=0;tr.setAttribute('role','button');tr.onclick=()=>openTicket(row.ticket_id);tr.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openTicket(row.ticket_id);}};}body.append(tr);}
 }
 section.querySelector('input').oninput=render;
 async function loadRows(append=false){
  const status=section.querySelector('.list-status'),button=section.querySelector('.provider-toolbar button');button.disabled=true;more.disabled=true;section.querySelectorAll('select').forEach(x=>x.disabled=true);status.textContent='Daten werden geladen …';if(!append){rows=[];nextOffset=null;more.classList.add('hidden');render();}
  try{

   const r=await post('/api/v1/integrations/list',{provider,days:Number(section.querySelector('[data-days]')?.value||0),offset:append?nextOffset:0,call_type:section.querySelector('[data-call-type]')?.value||'all'});columns=r.columns;const loaded=r.rows.map(row=>({...row,cells:row.cells.map((v,i)=>r.date_columns.includes(i)?(v?new Date(v).toLocaleString('de-DE'):'–'):v)}));rows=append?[...rows,...loaded]:loaded;nextOffset=r.next_offset??null;more.classList.toggle('hidden',nextOffset===null);status.textContent=`${rows.length} Einträge · ${r.note}`;render();
  }catch(error){status.textContent=error.message;}finally{button.disabled=false;more.disabled=false;section.querySelectorAll('select').forEach(x=>x.disabled=false);}
 }
 section.querySelector('.provider-toolbar button').onclick=()=>loadRows();
 more.onclick=()=>loadRows(true);
 section.querySelectorAll('select').forEach(select=>select.addEventListener('change',()=>{nextOffset=null;more.classList.add('hidden');rows=[];render();section.querySelector('.list-status').textContent='Filter geändert – Daten neu laden.';}));
}
