(()=>{
 let users=[],directory=new Map(),loading=null,lastAuto=null;
 const digits=value=>String(value||'').replace(/\D/g,'');
 const internal=value=>{const d=digits(value);return d&&d.length<=5?d:'';};
 function rebuild(){directory=new Map(users.map(u=>[String(u.extension),u.name]));}
 async function loadDirectory(force=false){
  if(loading&&!force)return loading;
  loading=post('/api/v1/starface/users',{}).then(data=>{users=data.users||[];lastAuto=data.auto||null;rebuild();renderPanel();decorateHistory(document);return data;}).finally(()=>{loading=null;});
  return loading;
 }
 function employee(value){const ext=internal(value);return ext&&directory.has(ext)?directory.get(ext):String(value||'–');}
 function decorateHistory(root){
  const scope=root?.querySelectorAll?root:document;
  scope.querySelectorAll('.activity-list article').forEach(article=>{
   const provider=article.querySelector('.provider-label');if(provider?.textContent.trim()!=='STARFACE')return;
   const strong=article.querySelector('strong');if(!strong)return;
   const raw=strong.dataset.rawCall||strong.textContent.trim();strong.dataset.rawCall=raw;
   const match=raw.match(/^(Eingehend|Ausgehend)\s*·\s*(.*?)\s*→\s*(.*?)\s*·\s*(.*)$/);if(!match)return;
   const inbound=match[1]==='Eingehend';
   strong.replaceChildren();
   const icon=document.createElement('span');icon.className='call-direction-icon '+(inbound?'incoming':'outgoing');icon.textContent='☎';icon.title=inbound?'Eingehender Anruf':'Ausgehender Anruf';
   const text=document.createElement('span');text.textContent=`${match[1]} · ${employee(match[2])} → ${employee(match[3])} · ${match[4]}`;
   strong.append(icon,text);
  });
 }
 function ensurePanel(){
  const section=document.querySelector('#view-starface');if(!section||section.querySelector('[data-starface-directory]'))return;
  const panel=document.createElement('article');panel.className='panel starface-directory-panel';panel.dataset.starfaceDirectory='';
  panel.innerHTML=`<div class="panel-head"><div><p class="eyebrow">MITARBEITER</p><h3>STARFACE-Benutzer &amp; interne Nummern</h3></div><button type="button" class="secondary" data-sf-users-refresh>Aktualisieren</button></div><p class="muted">Interne Nummern werden, sofern STARFACE sie über die REST-Schnittstelle freigibt, automatisch Benutzern zugeordnet. Manuelle Einträge haben immer Vorrang.</p><div class="provider-toolbar"><input type="search" data-sf-user-search placeholder="Mitarbeiter oder interne Nummer suchen …"></div><p class="list-status" data-sf-user-status></p><div class="table-wrap"><table><thead><tr><th>Interne Nummer</th><th>Mitarbeiter</th><th>Quelle</th></tr></thead><tbody data-sf-user-body></tbody></table></div><form class="inline-form starface-user-form" data-sf-user-form><input name="extension" inputmode="numeric" maxlength="5" placeholder="z. B. 31" required><input name="name" placeholder="Mitarbeitername" required><button class="secondary">Zuordnung speichern</button></form>`;
  section.append(panel);
  panel.querySelector('[data-sf-user-search]').oninput=renderPanel;
  panel.querySelector('[data-sf-users-refresh]').onclick=()=>loadDirectory(true).catch(error=>{panel.querySelector('[data-sf-user-status]').textContent=error.message;});
  panel.querySelector('[data-sf-user-form]').onsubmit=async event=>{
   event.preventDefault();const form=event.currentTarget,status=panel.querySelector('[data-sf-user-status]');status.textContent='Zuordnung wird gespeichert …';
   try{const data=await post('/api/v1/starface/users/save',{extension:form.extension.value,name:form.name.value});users=data.users||[];rebuild();form.reset();status.textContent='Zuordnung gespeichert.';renderPanel();decorateHistory(document);}catch(error){status.textContent=error.message;}
  };
 }
 function renderPanel(){
  ensurePanel();const panel=document.querySelector('[data-starface-directory]');if(!panel)return;
  const query=(panel.querySelector('[data-sf-user-search]')?.value||'').trim().toLocaleLowerCase('de-DE');
  const body=panel.querySelector('[data-sf-user-body]');if(!body)return;body.replaceChildren();
  const filtered=users.filter(u=>`${u.extension} ${u.name}`.toLocaleLowerCase('de-DE').includes(query));
  for(const user of filtered){const tr=document.createElement('tr');for(const value of [user.extension,user.name,user.source==='manual'?'Manuell':'STARFACE']){const td=document.createElement('td');td.textContent=value;tr.append(td);}body.append(tr);}
  if(!filtered.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=3;td.textContent=query?'Keine passenden Zuordnungen.':'Noch keine internen Nummern zugeordnet.';tr.append(td);body.append(tr);}
  const status=panel.querySelector('[data-sf-user-status]');
  if(lastAuto){const errors=(lastAuto.errors||[]).filter(Boolean);status.textContent=errors.length?`${users.length} Zuordnungen · Automatisches Einlesen nicht vollständig möglich: ${errors.join(' | ')} · Manuelle Zuordnung bleibt verfügbar.`:`${users.length} Zuordnungen · ${lastAuto.imported||0} Treffer automatisch aus STARFACE erkannt.`;}
  else status.textContent=`${users.length} Zuordnungen`;
 }
 document.querySelector('[data-view="starface"]')?.addEventListener('click',()=>{ensurePanel();loadDirectory(true).catch(error=>{const status=document.querySelector('[data-sf-user-status]');if(status)status.textContent=error.message;});});
 const observer=new MutationObserver(mutations=>{
  if(!mutations.some(m=>[...m.addedNodes].some(n=>n.nodeType===1&&(n.matches?.('.activity-list')||n.querySelector?.('.activity-list')))))return;
  loadDirectory(false).then(()=>decorateHistory(document)).catch(()=>decorateHistory(document));
 });
 observer.observe(document.body,{childList:true,subtree:true});
 ensurePanel();
})();
