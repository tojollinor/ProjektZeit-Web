/* The project page owns its filters and dialogs; no background polling. */
(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const h=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const hours=n=>(n/3600).toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2})+' h';
 const api=(route,body={})=>post('/api/v1/project-catalog/'+route,body);
 let data=null,tagFilter='',customerFilter='',generation=0;
 const tagLabel=t=>t.name+' · '+(t.customer_id?(t.customer||'Gelöschter Kunde'):'Allgemein')+(t.active?'':' (archiviert)');
 const projectTags=p=>data.links.filter(l=>l.project_id===p.id).map(l=>data.tags.find(t=>t.id===l.tag_id)).filter(Boolean);
 function visible(){return data.projects.filter(p=>(!customerFilter||String(p.customer_id)===customerFilter)&&(!tagFilter||projectTags(p).some(t=>String(t.id)===tagFilter)));}
 function draw(){
  const host=q('[data-project-page-list]');if(!host||!data)return;
  const projects=visible(),groups={open:[],active:[],parked:[],closed:[]},labels={open:'Offen',active:'Aktiv',parked:'Geparkt',closed:'Abgeschlossen'};
  projects.forEach(p=>(groups[p.status]||groups.active).push(p));
  host.innerHTML=`<section class="panel pc-wide"><div class="pc-toolbar"><label>Kunde<select data-pc-customer><option value="">Alle Kunden</option>${data.customers.map(c=>`<option value="${c.id}" ${String(c.id)===customerFilter?'selected':''}>${h(c.name)}</option>`).join('')}</select></label><label>Tag<select data-pc-tag><option value="">Alle Tags</option>${data.tags.filter(t=>!customerFilter||!t.customer_id||String(t.customer_id)===customerFilter).map(t=>`<option value="${t.id}" ${String(t.id)===tagFilter?'selected':''}>${h(tagLabel(t))}</option>`).join('')}</select></label><button type="button" class="secondary" data-pc-manage>Tags verwalten</button><button type="button" class="secondary" data-pc-reload>Aktualisieren</button></div><h3>Zeitvergleich</h3><p class="muted">Abgeschlossene Zeitabschnitte aus Zeiterfassung und zugeordneten Anbieterleistungen. Überschneidungen zählen innerhalb eines Projekts einmal. Laufende Zeiten sind noch nicht enthalten. Keine Abrechnungssumme.</p><p data-pc-total>${projects.length} Projekte · ${hours(projects.reduce((n,p)=>n+p.seconds,0))}</p><details><summary>Einzelne Projekte vergleichen</summary><div class="pc-comparison">${projects.map(p=>`<div><span>${h(p.name)}</span><strong>${hours(p.seconds)}</strong></div>`).join('')||'<p>Keine Projekte für diese Auswahl.</p>'}</div></details></section>`+
  '<section class="panel pc-wide pc-list"><h3>Projekte</h3>'+projects.map(p=>`<button type="button" class="pz-project-row pc-project-link" data-pc-detail="${p.id}"><span class="project-state-dot ${p.status}" aria-label="${h(labels[p.status])}"></span><span><strong>${h(p.name)}</strong><small>${h(p.customer||'Ohne Kunde')}</small></span><span>${h(labels[p.status]||p.status)}</span><span>${hours(p.seconds)}</span><span aria-hidden="true">›</span></button>`).join('')+(projects.length?'':'<p>Keine Projekte für diese Auswahl.</p>')+'</section>';
  qa('[data-pc-detail]',host).forEach(b=>b.onclick=()=>detail(Number(b.dataset.pcDetail)));
  q('[data-pc-customer]',host).onchange=e=>{customerFilter=e.target.value;tagFilter='';draw();};
  q('[data-pc-tag]',host).onchange=e=>{tagFilter=e.target.value;draw();};
  q('[data-pc-manage]',host).onclick=manage;
  q('[data-pc-reload]',host).onclick=render;
  qa('[data-pc-copy]',host).forEach(b=>b.onclick=()=>copy(Number(b.dataset.pcCopy)));
  qa('[data-pc-assign]',host).forEach(b=>b.onclick=()=>assign(Number(b.dataset.pcAssign)));
  qa('[data-pc-status]',host).forEach(b=>b.onclick=async()=>{try{await post('/api/v1/projects/status',{project_id:Number(b.dataset.pcId),status:b.dataset.pcStatus,send_to_billing:false});await render();if(typeof refresh==='function')await refresh();}catch(e){window.pzToast?.(e.message,'error');}});
 }
 async function render(){
  const host=q('[data-project-page-list]');if(!host)return;
  const version=++generation;host.innerHTML='<p role="status">Projekte werden geladen …</p>';
  try{const result=await api('list');if(version!==generation)return;data=result;draw();}
  catch(e){if(version!==generation)return;host.innerHTML=`<p role="alert">${h(e.message)}</p><button type="button" class="secondary" data-pc-retry>Erneut versuchen</button>`;q('[data-pc-retry]',host).onclick=render;}
 }
 function dialog(title,content,save){
  q('#pc-dialog')?.remove();const el=document.createElement('dialog');el.id='pc-dialog';el.className='pc-dialog';el.setAttribute('aria-labelledby','pc-title');
  el.innerHTML=`<form><h2 id="pc-title">${h(title)}</h2>${content}<p role="alert" data-pc-error></p><p role="status" data-pc-success></p><div class="panel-actions"><button type="button" class="secondary" data-pc-close>Schließen</button>${save?'<button type="submit" class="primary">Speichern</button>':''}</div></form>`;
  document.body.append(el);const form=q('form',el);let saving=false,done=false;
  q('[data-pc-close]',el).onclick=()=>el.close();el.addEventListener('close',()=>el.remove());el.addEventListener('cancel',e=>{if(saving)e.preventDefault();});
  form.onsubmit=async e=>{e.preventDefault();if(!save||saving||done)return;saving=true;const button=q('[type=submit]',form),close=q('[data-pc-close]',form);button.disabled=true;close.disabled=true;q('[data-pc-error]',el).textContent='';
   try{await save(new FormData(form));done=true;button.dataset.actionComplete='1';button.textContent='Gespeichert';q('[data-pc-success]',el).textContent='Erfolgreich gespeichert.';qa('input,select',form).forEach(x=>x.disabled=true);document.dispatchEvent(new CustomEvent('pz-data-changed'));await render();if(typeof refresh==='function')refresh().catch(()=>{});}
   catch(error){q('[data-pc-error]',el).textContent=error.message;}
   finally{saving=false;button.disabled=done;close.disabled=false;}
  };el.showModal();return el;
 }
 function copy(id){const p=data.projects.find(p=>p.id===id);dialog('Projekt kopieren',`<p>Kunde und aktive Tags werden übernommen. Das neue Projekt startet ohne Zeiten, Anbieterzuordnungen und Abrechnung.</p><label>Neuer Projektname<input name="name" required maxlength="120" value="${h((p.name+' – Kopie').slice(0,120))}"></label>`,f=>api('clone',{project_id:id,name:f.get('name')}));}
 function assign(id){const p=data.projects.find(p=>p.id===id),current=new Set(projectTags(p).map(t=>t.id));const tags=data.tags.filter(t=>(!t.customer_id||t.customer_id===p.customer_id)&&(t.active||current.has(t.id)));
  dialog('Tags: '+p.name,`<p>Allgemeine Tags und Tags dieses Kunden sind auswählbar.</p><div class="pc-tag-options">${tags.map(t=>`<label><input type="checkbox" name="tags" value="${t.id}" ${current.has(t.id)?'checked':''}>${h(tagLabel(t))}</label>`).join('')||'<p>Noch keine passenden Tags. Bitte zuerst unter „Tags verwalten“ anlegen.</p>'}</div>`,f=>api('tags/assign',{project_id:id,tags:f.getAll('tags').map(Number)}));
 }
 function editTag(tag){dialog(tag?'Tag bearbeiten':'Tag anlegen',`<label>Name<input name="name" required maxlength="120" value="${h(tag?.name||'')}"></label><label>Kundenbereich<select name="customer_id" ${tag?'disabled':''}><option value="0">Allgemein</option>${data.customers.map(c=>`<option value="${c.id}" ${c.id===tag?.customer_id?'selected':''}>${h(c.name)}</option>`).join('')}</select></label>${tag?`<label class="pc-check"><input name="active" type="checkbox" ${tag.active?'checked':''}>Aktiv (archivierte Tags bleiben für Auswertungen erhalten)</label>`:''}`,f=>api('tags/save',{id:tag?.id||0,name:f.get('name'),customer_id:tag?.customer_id||Number(f.get('customer_id')),active:tag?f.has('active'):true}));}
 function manage(){const el=dialog('Tags verwalten',`<p>Tags gelten für deine Projekte. Kundenspezifische Tags können nur diesem Kunden zugeordnet werden.</p><button type="button" class="secondary" data-pc-new>Tag anlegen</button><div class="pc-tag-options">${data.tags.map(t=>`<button type="button" class="secondary" data-pc-edit="${t.id}">${h(tagLabel(t))}</button>`).join('')||'<p>Noch keine Tags vorhanden.</p>'}</div>`);q('[data-pc-new]',el).onclick=()=>editTag();qa('[data-pc-edit]',el).forEach(b=>b.onclick=()=>editTag(data.tags.find(t=>t.id===Number(b.dataset.pcEdit))));}
 async function detail(id){
  let root=q('#view-project-detail');if(!root){root=document.createElement('section');root.id='view-project-detail';root.className='view';q('main').append(root);}showView('project-detail');q('#page-title').textContent='Projektdetails';root.innerHTML='<article class="panel"><p role="status">Projekt wird geladen …</p></article>';
  try{const result=await post('/api/v1/company/project/read',{project_id:id}),p=result.project,labels={open:'Offen',active:'Aktiv',parked:'Geparkt',closed:'Abgeschlossen'};const person=x=>((x.last_name||'')+', '+(x.first_name||'')).replace(/^, |, $/g,'')||x.username;
   root.innerHTML='<article class="panel"><button class="secondary" data-pc-back>‹ Projektliste</button><h3><span class="project-state-dot '+p.status+'"></span> '+h(p.name)+'</h3><p>'+h(p.customer||'Ohne Kunde')+'</p><p>Zuständig: '+h(person(result.people.find(x=>x.id===(p.assigned_user_id||p.owner_id))||{username:'Ehemaliger Mitarbeiter'}))+'</p><div class="pc-toolbar"><label>Status<select data-detail-status '+(!result.can_edit?'disabled':'')+'>'+Object.entries(labels).map(([key,label])=>'<option value="'+key+'" '+(p.status===key?'selected':'')+'>'+label+'</option>').join('')+'</select></label><button class="primary" data-detail-save '+(!result.can_edit?'disabled':'')+'>Status speichern</button></div><div class="panel-actions"><button class="secondary" data-detail-tags>Tags</button><button class="secondary" data-detail-copy>Neues Projekt aus diesem Projekt</button>'+(result.can_assign?'<button class="secondary" data-detail-employee>Mitarbeiter zuweisen</button>':'')+(p.status==='closed'&&result.can_edit?'<button class="primary" data-detail-billing>Ab in die Abrechnung</button>':'')+'</div><p data-detail-message role="status"></p><p>Abrechnung: '+h({'':'Noch nicht übergeben',pending:'Zur Abrechnung',in_progress:'In Bearbeitung',billed:'Abgerechnet'}[p.billing_state]||p.billing_state)+'. Frühere Leistungsbeschreibungen bleiben beim Wiederöffnen erhalten.</p></article><article class="panel"><h3>Projektverlauf</h3>'+result.history.map(e=>'<p><strong>'+h(e.action)+'</strong> · '+h(new Date(e.created_at).toLocaleString('de-DE'))+' · '+h(e.actor||'')+'</p>').join('')+'</article>';
   q('[data-pc-back]',root).onclick=()=>{showView('projects');render();};q('[data-detail-save]',root).onclick=async()=>{try{await post('/api/v1/projects/status',{project_id:id,original_status:p.status,status:q('[data-detail-status]',root).value});await detail(id);if(typeof refresh==='function')await refresh();}catch(e){q('[data-detail-message]',root).textContent=e.message;}};
   const own=typeof state==='undefined'||p.owner_id===state.user.id;q('[data-detail-tags]',root).disabled=!own;q('[data-detail-copy]',root).disabled=!own;
   q('[data-detail-tags]',root).onclick=()=>assign(id);q('[data-detail-copy]',root).onclick=()=>copy(id);
   q('[data-detail-billing]',root)?.addEventListener('click',()=>window.pzCompany.closeForBilling(id));
   q('[data-detail-employee]',root)?.addEventListener('click',()=>window.pzCompany.dialog('Mitarbeiter zuweisen','<p>Die aufgezeichneten Zeiten bleiben beim jeweiligen Mitarbeiter.</p><label>Mitarbeiter<select name="user_id"><option value="">Projektinhaber</option>'+result.people.map(x=>'<option value="'+x.id+'" '+(p.assigned_user_id===x.id?'selected':'')+'>'+h(person(x))+'</option>').join('')+'</select></label>',async values=>{await post('/api/v1/company/project/assign',{project_id:id,user_id:values.user_id,original_user_id:p.assigned_user_id});await detail(id);}));
  }catch(e){root.innerHTML='<article class="panel"><p role="alert">'+h(e.message)+'</p><button class="secondary" data-pc-back>Zur Projektliste</button></article>';q('[data-pc-back]',root).onclick=()=>showView('projects');}
 }
 async function open(customerId,projectId){customerFilter=customerId?String(customerId):'';tagFilter='';if(!data)data=await api('list');await detail(projectId);}
 window.pzProjects={render,open,detail};
})();
