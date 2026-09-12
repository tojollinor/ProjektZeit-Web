(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const notify=(m,l='info',t=5000)=>window.pzToast?window.pzToast(m,l,t):typeof toast==='function'?toast(m):null;
 const view=q('#view-zammad');if(!view)return;
 let running=false,statusFilter='all',lastBody=null;
 function statusKey(text){const s=String(text||'').trim().toLowerCase();if(/geschlossen|closed|merged|zusammengeführt|removed|entfernt/.test(s))return'closed';if(/pending[\s_-]*reminder|reminder|erinner/.test(s))return'reminder';if(/pending|wartend|warten auf schließen/.test(s))return'pending';if(/new|neu/.test(s))return'new';return'open';}
 function statusIndex(){const hs=qa('thead tr:first-child th',view).map(x=>(x.textContent||'').trim().toLowerCase());return hs.findIndex(x=>/state|status/.test(x));}
 function applyFilter(){
  const tbody=q('tbody',view);if(!tbody)return;const idx=statusIndex(),rows=qa(':scope > tr',tbody);let visible=0;
  for(const row of rows){const cells=qa(':scope > td',row),key=statusKey(cells[idx]?.textContent||'');const show=statusFilter==='all'||key===statusFilter;row.hidden=!show;if(show)visible++;}
  qa('[data-filter]',view).forEach(b=>b.classList.toggle('active',b.dataset.filter===statusFilter));const status=q('.list-status',view);if(status)status.dataset.filterCount=visible!==rows.length?`${visible} von ${rows.length} sichtbar`:'';
 }
 function controls(){
  if(q('[data-zammad-list-controls]',view))return;const toolbar=q('.provider-toolbar',view);if(!toolbar)return;
  const wrap=document.createElement('div');wrap.dataset.zammadListControls='';wrap.className='zammad-list-controls';wrap.innerHTML='<div class="zammad-status-filters"><button type="button" class="zammad-filter-chip active" data-filter="all">Alle</button><button type="button" class="zammad-filter-chip" data-filter="open">Offen</button><button type="button" class="zammad-filter-chip" data-filter="closed">Geschlossen</button><button type="button" class="zammad-filter-chip" data-filter="new">Neu</button><button type="button" class="zammad-filter-chip" data-filter="pending">Wartend</button><button type="button" class="zammad-filter-chip" data-filter="reminder">Erinnerung</button></div>';
  toolbar.insertAdjacentElement('afterend',wrap);qa('[data-filter]',wrap).forEach(b=>b.onclick=()=>{statusFilter=b.dataset.filter;applyFilter();});
 }
 function loader(on){const panel=q(':scope > article.panel',view);if(!panel)return;let el=q('.zammad-list-loader',panel);if(!el){el=document.createElement('span');el.className='zammad-list-loader';el.innerHTML='<i></i><span>Aktualisierung</span>';q('.panel-head',panel)?.append(el);}el.classList.toggle('active',!!on);}
 function syncRows(){controls();const tbody=q('tbody',view);if(!tbody||tbody===lastBody&&tbody.dataset.pzZammadSeen===String(tbody.childElementCount))return;lastBody=tbody;tbody.dataset.pzZammadSeen=String(tbody.childElementCount);applyFilter();}
 const status=q('.list-status',view);if(status)new MutationObserver(()=>{const text=status.textContent||'';loader(/geladen|aktualisiert|abgleich|läuft/i.test(text)&&!/einträge/i.test(text));queueMicrotask(syncRows);}).observe(status,{childList:true,characterData:true,subtree:true});
 const tbody=q('tbody',view);if(tbody)new MutationObserver(()=>requestAnimationFrame(syncRows)).observe(tbody,{childList:true});
 async function repaint(){try{if(typeof providerLoaders!=='undefined'&&providerLoaders.zammad)await providerLoaders.zammad(false);}catch(_){}syncRows();}
 function statusChanged(){document.dispatchEvent(new CustomEvent('pz-provider-status-changed',{detail:{provider:'zammad'}}));}
 async function refresh(){
  if(running)return;running=true;loader(true);try{const started=await post('/api/v1/provider/refresh/start',{provider:'zammad'}),id=started.job?.id||'';const poll=async()=>{try{const d=await post('/api/v1/provider/refresh/job',{provider:'zammad'}),job=d.job||{};if(id&&job.id&&id!==job.id)return;if(job.state==='running'){setTimeout(poll,800);return;}running=false;loader(false);await repaint();statusChanged();if(job.state==='success'){const r=job.result||{};notify(`Zammad aktualisiert · ${r.total_records||0} Tickets`,'success',3500);}else notify(job.error||'Zammad konnte nicht aktualisiert werden.','warning',6500);}catch(_){running=false;loader(false);statusChanged();}};setTimeout(poll,350);}catch(error){running=false;loader(false);statusChanged();notify(error.message,'warning',6500);}
 }
 q('[data-refresh]',view)?.addEventListener('click',()=>setTimeout(refresh,20));controls();setTimeout(syncRows,100);
})();
