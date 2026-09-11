const ticketDialog=document.createElement('dialog');ticketDialog.className='ticket-detail';
ticketDialog.innerHTML='<button>Schließen</button><div></div>';document.body.append(ticketDialog);
ticketDialog.querySelector('button').onclick=()=>ticketDialog.close();
let ticketRequest=0;ticketDialog.addEventListener('close',()=>ticketRequest++);

async function openTicket(id){
 const n=++ticketRequest,box=ticketDialog.querySelector('div');box.textContent='Ticket wird geladen …';ticketDialog.showModal();
 try{
  const d=await post('/api/v1/integrations/ticket',{provider:'zammad',ticket_id:id});if(n!==ticketRequest)return;
  box.innerHTML=`<h2>Ticket ${esc(d.ticket?.number)} · ${esc(d.ticket?.title)}</h2>`;
  const details=document.createElement('pre');details.textContent=JSON.stringify(d,null,2);box.append(details);
 }catch(e){if(n===ticketRequest)box.textContent=e.message;}
}

let customerCache={customers:[],links:{starface:{},zammad:{},teamviewer:{}}};
async function loadCustomerCache(){customerCache=await post('/api/v1/customers/data',{});return customerCache;}

const customerDialog=document.createElement('dialog');customerDialog.className='ticket-detail customer-assign-dialog';
customerDialog.innerHTML=`<form method="dialog"><button value="cancel" class="secondary">Schließen</button></form><div class="customer-assign-body"></div>`;
document.body.append(customerDialog);

function hintValue(h,key,def=''){const value=h?.[key];return typeof value==='string'?value:def;}
async function assignCustomer(provider,row,onDone){
 await loadCustomerCache();
 const hint=row.customer_hint||{},linked=customerCache.links?.[provider]?.[row.external_key];
 const body=customerDialog.querySelector('.customer-assign-body');
 body.innerHTML=`<h2>Kundenzuordnung</h2><p class="muted">${esc(provider.toUpperCase())} · ${esc(row.external_key||'Datensatz')}</p>
 <div class="customer-assignment-grid">
  <section><h3>Bestehenden Kunden zuordnen</h3><label>Kunde<select data-existing><option value="">Kunde wählen …</option>${customerCache.customers.map(c=>`<option value="${c.id}" ${linked?.id===c.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><button type="button" class="primary" data-assign-existing>Zuordnen</button></section>
  <section><h3>Neuen Kunden anlegen</h3><label>Firma / Kunde<input data-new-name value="${attr(hintValue(hint,'name'))}"></label><label>Ansprechpartner<input data-new-contact value="${attr(hintValue(hint,'contact_person'))}"></label><label>E-Mail<input data-new-email value="${attr(hintValue(hint,'email'))}"></label><label>Rufnummern<input data-new-phones value="${attr((hint.phones||[]).join(', '))}" placeholder="mehrere mit Komma trennen"></label><button type="button" class="primary" data-create-assign>Anlegen und zuordnen</button></section>
 </div><p class="integration-status" data-assign-status></p>`;
 const status=body.querySelector('[data-assign-status]');
 const hints=()=>({phones:(body.querySelector('[data-new-phones]').value||'').split(',').map(x=>x.trim()).filter(Boolean),device_id:hintValue(hint,'device_id'),device_name:hintValue(hint,'device_name')});
 async function done(payload){
  status.textContent='Wird gespeichert …';
  try{await post('/api/v1/customers/assign',payload);status.textContent='Gespeichert.';await loadCustomerCache();onDone?.();setTimeout(()=>customerDialog.close(),350);}catch(e){status.textContent=e.message;}
 }
 body.querySelector('[data-assign-existing]').onclick=()=>{const id=+body.querySelector('[data-existing]').value;if(!id){status.textContent='Bitte einen Kunden auswählen.';return;}done({provider,external_key:row.external_key,customer_id:id,label:hintValue(hint,'name'),hints:hints()});};
 body.querySelector('[data-create-assign]').onclick=()=>{const name=body.querySelector('[data-new-name]').value.trim();if(!name){status.textContent='Bitte einen Kundennamen eingeben.';return;}done({provider,external_key:row.external_key,label:name,hints:hints(),new_customer:{name,contact_person:body.querySelector('[data-new-contact]').value.trim(),email:body.querySelector('[data-new-email]').value.trim(),phones:hints().phones.map(number=>({number,source:provider}))}});};
 customerDialog.showModal();
}

function rawValue(value){if(value===null||value===undefined||value==='')return '–';if(typeof value==='object')return JSON.stringify(value);return String(value);}

const providerLoaders={};
for(const section of document.querySelectorAll('.provider-view')){
 const provider=section.dataset.source;
 section.innerHTML=`<article class="panel"><div class="panel-head"><div><p class="eyebrow">ROHDATEN</p><h3>${esc(provider.toUpperCase())}</h3></div></div>${provider==='starface'?'<p class="starface-version" role="status">Version wird geprüft.</p>':''}<div class="provider-toolbar"><input type="search" placeholder="Liste durchsuchen …" aria-label="Liste durchsuchen">${provider==='starface'?'<select data-days aria-label="Zeitraum"><option value="7">7 Tage</option><option value="30" selected>30 Tage</option><option value="90">90 Tage</option><option value="365">365 Tage</option></select>':provider==='teamviewer'?'<select data-days aria-label="Zeitraum"><option value="0">API-Standardzeitraum</option><option value="7">7 Tage</option><option value="30">30 Tage</option><option value="90">90 Tage</option><option value="365">365 Tage</option></select>':''}${provider==='starface'?'<select data-call-type aria-label="Anrufart"><option value="all">Alle Anrufe</option><option value="inbound">Eingehend</option><option value="outbound">Ausgehend</option><option value="missed">Verpasst</option></select>':''}</div><p class="list-status" role="status">Wird beim Öffnen geladen.</p><div class="table-wrap raw-provider-table"><table><thead></thead><tbody></tbody></table></div></article>`;
 let rows=[],columns=[],nextOffset=null,loadedOnce=false,loading=false;
 const more=document.createElement('button');more.className='secondary hidden';more.textContent='Weitere Anrufe laden';if(provider==='starface')section.querySelector('article').append(more);
 async function version(){if(provider!=='starface')return;const label=section.querySelector('.starface-version');try{const info=await post('/api/v1/integrations/list',{provider,info_only:true});label.textContent=info.version?'STARFACE '+info.version:info.version_note;}catch(e){label.textContent=e.message;}}
 function linkedName(row){return customerCache.links?.[provider]?.[row.external_key]?.name||'';}
 function render(){
  const q=section.querySelector('input').value.toLowerCase();
  section.querySelector('thead').innerHTML='<tr><th>Kunde</th><th>Aktion</th>'+columns.map(c=>`<th>${esc(c)}</th>`).join('')+'</tr>';
  const tbody=section.querySelector('tbody');tbody.replaceChildren();
  for(const row of rows.filter(r=>(JSON.stringify(r.raw||r.cells)||'').toLowerCase().includes(q)||linkedName(r).toLowerCase().includes(q))){
   const tr=document.createElement('tr');
   const customer=document.createElement('td');customer.textContent=linkedName(row)||'Nicht zugeordnet';tr.append(customer);
   const actions=document.createElement('td');actions.className='provider-actions';
   const assign=document.createElement('button');assign.type='button';assign.className='secondary subtle';assign.textContent=linkedName(row)?'Kunde ändern':'Kunde zuordnen';assign.onclick=()=>assignCustomer(provider,row,render);actions.append(assign);
   if(provider==='zammad'&&row.ticket_id){const ticket=document.createElement('button');ticket.type='button';ticket.className='secondary subtle';ticket.textContent='Ticket';ticket.onclick=()=>openTicket(row.ticket_id);actions.append(ticket);}
   tr.append(actions);
   for(const name of columns){const td=document.createElement('td');td.textContent=rawValue(row.raw?.[name]);tr.append(td);}tbody.append(tr);
  }
 }
 section.querySelector('input').oninput=render;
 async function loadRows(append=false){
  if(loading)return;loading=true;const status=section.querySelector('.list-status');more.disabled=true;section.querySelectorAll('select').forEach(x=>x.disabled=true);status.textContent='Daten werden geladen …';
  if(!append){rows=[];nextOffset=null;more.classList.add('hidden');render();}
  try{
   await loadCustomerCache();
   const r=await post('/api/v1/integrations/list',{provider,days:Number(section.querySelector('[data-days]')?.value||0),offset:append?nextOffset:0,call_type:section.querySelector('[data-call-type]')?.value||'all'});
   columns=r.raw_columns?.length?r.raw_columns:r.columns;const incoming=r.rows||[];rows=append?[...rows,...incoming]:incoming;nextOffset=r.next_offset??null;more.classList.toggle('hidden',nextOffset===null);loadedOnce=true;status.textContent=`${rows.length} Einträge · ${r.note||''}`;render();
  }catch(error){status.textContent=error.message;}finally{loading=false;more.disabled=false;section.querySelectorAll('select').forEach(x=>x.disabled=false);}
 }
 providerLoaders[provider]=loadRows;more.onclick=()=>loadRows(true);
 section.querySelectorAll('select').forEach(select=>select.addEventListener('change',()=>loadRows(false)));
 document.querySelector(`[data-view="${provider}"]`)?.addEventListener('click',()=>{if(provider==='starface')version();loadRows(false);});
 window.addEventListener('starface-connected',()=>{if(provider==='starface'){version();loadedOnce=false;}});
}

// Kundenbereich dynamisch ergänzen, damit bestehende Layout-Dateien kompatibel bleiben.
const nav=document.querySelector('.sidebar nav');
const settingsButton=nav?.querySelector('[data-view="users"]');
const customersButton=document.createElement('button');customersButton.className='nav';customersButton.dataset.view='customers';customersButton.innerHTML='<span>♧</span>Kunden';
if(nav)nav.insertBefore(customersButton,settingsButton||null);
const customersSection=document.createElement('section');customersSection.id='view-customers';customersSection.className='view';
customersSection.innerHTML=`<div class="panel"><div class="panel-head"><div><p class="eyebrow">STAMMDATEN</p><h3>Kunden</h3></div></div><form class="customer-quick-form inline-form"><input data-customer-name placeholder="Neuer Kundenname" required><button class="secondary">Anlegen</button></form><p class="list-status" data-customer-status></p><div class="customer-cards" data-customer-list></div></div>`;
document.querySelector('main')?.insertBefore(customersSection,document.querySelector('#toast'));
async function renderCustomers(){
 const status=customersSection.querySelector('[data-customer-status]'),list=customersSection.querySelector('[data-customer-list]');status.textContent='Kunden werden geladen …';
 try{await loadCustomerCache();status.textContent=`${customerCache.customers.length} Kunden`;list.replaceChildren();for(const c of customerCache.customers){const card=document.createElement('article');card.className='customer-card';card.innerHTML=`<h3>${esc(c.name)}</h3>${c.contact_person?`<p><strong>Ansprechpartner:</strong> ${esc(c.contact_person)}</p>`:''}${c.email?`<p><strong>E-Mail:</strong> ${esc(c.email)}</p>`:''}<p><strong>Rufnummern:</strong> ${c.phones?.length?c.phones.map(p=>esc(p.number)+(p.label?' ('+esc(p.label)+')':'')).join(', '):'–'}</p><p><strong>TeamViewer / Geräte:</strong> ${c.devices?.length?c.devices.map(d=>esc(d.name||d.external_id)).join(', '):'–'}</p><p><strong>Verknüpfungen:</strong> ${c.provider_links?.length?c.provider_links.map(l=>esc(l.provider.toUpperCase())).join(', '):'–'}</p>`;list.append(card);}}catch(e){status.textContent=e.message;}
}
customersSection.querySelector('.customer-quick-form').onsubmit=async e=>{e.preventDefault();const input=e.currentTarget.querySelector('[data-customer-name]');try{await post('/api/v1/customers/profile',{name:input.value.trim()});input.value='';await refresh();await renderCustomers();}catch(error){customersSection.querySelector('[data-customer-status]').textContent=error.message;}};
customersButton.onclick=()=>{showView('customers');document.querySelector('#page-title').textContent='Kunden';renderCustomers();};
