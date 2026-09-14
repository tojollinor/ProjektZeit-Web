/* A single, permission-scoped inbox. Reading a message never decides a request. */
(()=>{
 const q=(s,r=document)=>r.querySelector(s),h=v=>attr(String(v??''));
 let data=null,loading=null,timer=null,mode='action',ready=false;
 const safely=fn=>async()=>{try{await fn();}catch(e){window.pzToast?.(e.message,'error');}};
 const api=(action,body={})=>post('/api/v1/company/notifications/'+action,body);
 const date=x=>new Date(x).toLocaleString('de-DE',{timeZone:'Europe/Berlin'});
 function draw(){
  const bell=q('#notification-bell');if(!bell)return;
  if(!data){bell.textContent='…';bell.setAttribute('aria-busy','true');bell.title='Benachrichtigungen werden geprüft';return;}bell.removeAttribute('aria-busy');
  bell.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a6 6 0 0 0-6 6v5l-2 3v2h16v-2l-2-3V8a6 6 0 0 0-6-6M9 20a3 3 0 0 0 6 0z"/></svg><span>'+data.action_count+' offen · '+data.unread+' neu'+'</span>';
  bell.title=data.action_count+' zu bestätigen · '+data.unread+' ungelesen';bell.setAttribute('aria-label','Benachrichtigungen: '+bell.title);
  const root=q('#view-notifications');if(!root?.classList.contains('active-view'))return;
  root.innerHTML='<article class="panel"><div class="panel-head"><h3>Benachrichtigungen</h3><button class="primary" data-inbox-refresh>Aktualisieren</button></div><div class="panel-actions" role="tablist" aria-label="Benachrichtigungen">'+[['action','Zu bestätigen ('+data.action_count+')'],['unread','Ungelesen ('+data.unread+')'],['all','Alle']].map(([key,label])=>'<button role="tab" aria-selected="'+(mode===key)+'" class="'+(mode===key?'primary':'secondary')+'" data-inbox-mode="'+key+'">'+label+'</button>').join('')+'</div><p>Entscheidungen und Nachrichten für dein Konto. Als gelesen markieren verändert keine Genehmigung.</p><div data-inbox-list role="tabpanel"></div></article>';
  q('[data-inbox-refresh]',root).onclick=refresh;root.querySelectorAll('[data-inbox-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.inboxMode;draw();});const list=q('[data-inbox-list]',root);
  function row(title,detail,label,action){const el=document.createElement('article');el.className='notification-row';el.innerHTML='<div><strong>'+h(title)+'</strong><p>'+h(detail)+'</p></div><button class="secondary">'+h(label)+'</button>';q('button',el).onclick=safely(action);list.append(el);return el;}
  if(mode!=='unread'){
   for(const r of data.requests)row(r.state==='awaiting_employee'?'Deine Bestätigung erforderlich':'Abwesenheitsantrag prüfen',(r.username||'')+' · '+date(r.start_at)+' – '+date(r.end_at),'Antrag öffnen',()=>window.pzCompany.requestDetail(r));
   for(const r of data.swaps)row('Notdiensttausch prüfen',date(r.starts)+' – '+date(r.ends),'Tausch öffnen',()=>{const d=window.pzCompany.dialog('Notdiensttausch','<p>'+h(date(r.starts))+' – '+h(date(r.ends))+'</p>',null);for(const [label,approve] of [['Bestätigen',true],['Ablehnen',false]]){const b=document.createElement('button');b.type='button';b.className=approve?'primary':'danger';b.textContent=label;b.onclick=async()=>{try{await post('/api/v1/company/duty/approve',{id:r.id,approve});d.close();await refresh();}catch(e){q('.error',d).textContent=e.message;}};q('form',d).append(b);}});
  }
  if(mode!=='action')for(const n of data.notifications.filter(n=>mode==='all'||!n.read_at)){
   const el=row(n.message,date(n.created_at)+(n.read_at?' · Gelesen':' · Ungelesen'),'Öffnen',async()=>{const detail=await api('detail',{id:n.id});await api('seen',{id:n.id});if(detail.request)window.pzCompany.requestDetail(detail.request);else if(n.project_id)await window.pzProjects.open(null,n.project_id);else window.pzCompany.dialog('Benachrichtigung','<p>'+h(n.message)+'</p><p>'+h(date(n.created_at))+'</p>',null);await refresh();});
   if(!n.read_at){const b=document.createElement('button');b.className='secondary';b.textContent='Als gelesen markieren';b.onclick=safely(async()=>{await api('seen',{id:n.id});await refresh();});el.append(b);}
  }
  if(!list.children.length)list.innerHTML='<p>Hier ist aktuell nichts offen.</p>';
 }
 async function refresh(){if(!state.user||document.hidden)return;clearTimeout(timer);if(loading)return loading;loading=api('list').then(r=>{data=r;draw();}).catch(e=>{const bell=q('#notification-bell');if(bell)bell.title='Benachrichtigungen konnten nicht geladen werden: '+e.message;const root=q('#view-notifications');if(root?.classList.contains('active-view'))root.innerHTML='<article class="panel"><p role="alert">'+h(e.message)+'</p><button class="primary" data-inbox-retry>Erneut laden</button></article>';q('[data-inbox-retry]',root||document)?.addEventListener('click',refresh);}).finally(()=>{loading=null;if(!document.hidden)timer=setTimeout(refresh,60000);});return loading;}
 function boot(){if(ready||!state.user)return;ready=true;const root=document.createElement('section');root.id='view-notifications';root.className='view';root.innerHTML='<article class="panel"><p>Benachrichtigungen werden geladen …</p></article>';q('main').append(root);const bell=document.createElement('button');bell.id='notification-bell';bell.className='secondary';bell.type='button';bell.setAttribute('aria-label','Benachrichtigungen öffnen');bell.onclick=()=>{showView('notifications');q('#page-title').textContent='Benachrichtigungen';draw();refresh();};q('#live-pill').before(bell);draw();refresh();}
 document.addEventListener('pz-company-ready',boot);document.addEventListener('pz-company-changed',refresh);document.addEventListener('pz-view-changed',()=>{if(q('#view-notifications.active-view')){draw();refresh();}});document.addEventListener('visibilitychange',()=>{clearTimeout(timer);if(!document.hidden)refresh();});document.addEventListener('pz-auth-ready',boot);boot();
})();
