(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const notify=(m,l='info',t=5000)=>window.pzToast?window.pzToast(m,l,t):typeof toast==='function'?toast(m):null;
 let running=false,customerSort='';

 function decorateRows(){
  const view=q('#view-zammad');if(!view)return;
  for(const row of qa('tbody tr',view)){
   const actions=q('.provider-actions',row);if(actions&&!q('.zammad-cache-badge',actions)){
    const badge=document.createElement('span');badge.className='badge zammad-cache-badge';badge.textContent='Aktuell';badge.title='Im letzten vollständig erfolgreichen Zammad-Abgleich vorhanden';actions.append(badge);
   }
  }
  const first=q('thead tr:first-child th:first-child',view);
  if(first&&!q('[data-zammad-customer-sort]',first)){
   first.replaceChildren();const b=document.createElement('button');b.type='button';b.className='table-sort';b.dataset.zammadCustomerSort='';b.textContent='Kunde';
   b.onclick=()=>{customerSort=customerSort==='asc'?'desc':'asc';sortCustomers();};first.append(b);
  }
  if(customerSort)sortCustomers(false);
 }
 function sortCustomers(update=true){
  const view=q('#view-zammad'),tbody=q('tbody',view);if(!tbody)return;
  const rows=qa(':scope > tr',tbody);rows.sort((a,b)=>{
   const av=(a.children[0]?.textContent||'').trim(),bv=(b.children[0]?.textContent||'').trim();
   const cmp=av.localeCompare(bv,'de',{numeric:true,sensitivity:'base'});return customerSort==='desc'?-cmp:cmp;
  });for(const row of rows)tbody.append(row);
  if(update){const b=q('[data-zammad-customer-sort]',view);if(b)b.textContent='Kunde '+(customerSort==='asc'?'↑':'↓');}
 }
 const view=q('#view-zammad');if(view){
  new MutationObserver(()=>requestAnimationFrame(decorateRows)).observe(view,{childList:true,subtree:true});
  view.addEventListener('click',event=>{const sort=event.target.closest('.table-sort');if(sort&&!sort.matches('[data-zammad-customer-sort]'))customerSort='';},true);
 }

 async function repaint(){try{if(typeof providerLoaders!=='undefined'&&providerLoaders.zammad)await providerLoaders.zammad(false);}catch(_){}}
 function statusChanged(){document.dispatchEvent(new CustomEvent('pz-provider-status-changed',{detail:{provider:'zammad'}}));}
 async function refresh(){
  if(running)return;running=true;const status=q('#view-zammad .list-status');
  try{
   const started=await post('/api/v1/provider/refresh/start',{provider:'zammad'}),id=started.job?.id||'';
   if(status)status.dataset.backgroundRefresh='Vollständiger Zammad-Abgleich läuft …';
   const poll=async()=>{
    try{
     const d=await post('/api/v1/provider/refresh/job',{provider:'zammad'}),job=d.job||{};
     if(id&&job.id&&id!==job.id)return;
     if(job.state==='running'){setTimeout(poll,800);return;}
     running=false;if(status)delete status.dataset.backgroundRefresh;await repaint();decorateRows();statusChanged();
     if(job.state==='success'){
      const r=job.result||{};notify(`Zammad aktualisiert · ${r.total_records||0} Tickets · ${r.removed||0} entfernt`,'success',4500);
     }else notify(job.error||'Zammad konnte nicht vollständig aktualisiert werden. Der bisherige Datenbankstand bleibt erhalten.','warning',7000);
    }catch(error){running=false;if(status)delete status.dataset.backgroundRefresh;statusChanged();notify('Zammad-Status konnte nicht geladen werden. Der lokale Datenbankstand bleibt erhalten.','warning',6000);}
   };setTimeout(poll,350);
  }catch(error){running=false;if(status)delete status.dataset.backgroundRefresh;statusChanged();notify(error.message,'warning',7000);}
 }
 q('[data-view="zammad"]')?.addEventListener('click',()=>setTimeout(refresh,80));
 q('#view-zammad')?.addEventListener('click',event=>{if(event.target.closest('[data-refresh]'))setTimeout(refresh,40);});
 setTimeout(decorateRows,350);
})();
