// Preview rows are separate from recorded work and live API data.
const providerExamples={
  zammad:{title:'Tickets & Support',description:'Tickets mit Organisationsnamen. Live-Tickets lassen sich direkt in Zammad öffnen.',columns:['ID','Ticketnummer','Titel','Organisation','Status'],rows:[['42','1042','Drucker im Büro einrichten','Musterkunde Nord','Offen'],['43','1043','VPN-Zugang prüfen','Beispiel GmbH','In Bearbeitung'],['44','1044','E-Mail-Konto anlegen','Musterkunde Süd','Wartend']]},
  starface:{title:'Telefonie & Gespräche',description:'Vorschau einer Gesprächsliste. Die Live-Probe liest aktuell Benutzer; echte Anruflisten benötigen eine zusätzliche UCI-Anbindung.',columns:['Zeit','Kontakt','Richtung','Dauer'],rows:[['09:10','Musterkunde Nord','Eingehend','00:08:12'],['10:35','Beispiel GmbH','Ausgehend','00:04:36'],['11:50','Musterkunde Süd','Verpasst','–']]},
  teamviewer:{title:'Fernwartung & Verbindungen',description:'Die letzten Fernwartungen mit Gerätenamen, Beginn, Ende und Verbindungsdauer.',columns:['Gerätename','Benutzer','Beginn','Ende','Verbindungsdauer'],rows:[['LAPTOP-03','Beispielbenutzer','13:00','13:20','00:20:00'],['SERVER-02','Beispielbenutzer','10:15','10:45','00:30:00'],['BÜRO-PC-01','Beispielbenutzer','09:30','09:55','00:25:00']]}
};
for(const section of document.querySelectorAll('.provider-view')){
  const provider=section.dataset.source,info=providerExamples[provider];
  section.innerHTML=`<article class="panel"><p class="eyebrow">${esc(provider.toUpperCase())}</p><h3>${esc(info.title)}</h3><p class="provider-note">${esc(info.description)}</p><span class="provider-label">Beispieldaten · keine echten Aktivitäten</span><div class="provider-toolbar"><input type="search" placeholder="Liste durchsuchen …" aria-label="Liste durchsuchen"><button class="secondary" data-example>Beispiele anzeigen</button><button class="primary admin-only" data-live>Echte Daten laden</button></div><p class="provider-status" role="status"></p><div class="table-wrap"><table><thead></thead><tbody></tbody></table></div></article>`;
  let columns=info.columns,rows=info.rows.map(cells=>({cells}));
  function render(){
    const q=section.querySelector('input').value.toLocaleLowerCase();
    const filtered=rows.filter(row=>row.cells.join(' ').toLocaleLowerCase().includes(q));
    section.querySelector('thead').innerHTML='<tr>'+columns.map(x=>`<th>${esc(x)}</th>`).join('')+'</tr>';
    section.querySelector('tbody').innerHTML=filtered.length?filtered.map((row,index)=>`<tr ${row.url?'class="ticket-link-row" tabindex="0" role="link" aria-label="Ticket in Zammad öffnen"':''} data-index="${index}">`+row.cells.map((x,col)=>`<td>${row.url&&col===2?`<a href="${attr(row.url)}" target="_blank" rel="noopener noreferrer">${esc(x)}</a>`:esc(x)}</td>`).join('')+'</tr>').join(''):`<tr><td colspan="${Math.max(1,columns.length)}">Keine Einträge vorhanden.</td></tr>`;
    for(const tr of section.querySelectorAll('.ticket-link-row')){
      const open=()=>window.open(filtered[Number(tr.dataset.index)].url,'_blank','noopener,noreferrer');
      tr.addEventListener('click',event=>{if(!event.target.closest('a'))open()});
      tr.addEventListener('keydown',event=>{if(event.target===tr&&(event.key==='Enter'||event.key===' ')){event.preventDefault();open()}});
    }
  }
  section.querySelector('input').addEventListener('input',render);
  section.querySelector('[data-example]').addEventListener('click',()=>{columns=info.columns;rows=info.rows.map(cells=>({cells}));section.querySelector('.provider-label').textContent='Beispieldaten · keine echten Aktivitäten';section.querySelector('.provider-status').textContent='';render()});
  section.querySelector('[data-live]').addEventListener('click',async event=>{
    event.target.disabled=true;const status=section.querySelector('.provider-status');status.textContent='Daten werden geladen …';
    rows=[];render();section.querySelector('.provider-label').textContent='Live-Abfrage läuft';
    try{
      if(provider==='teamviewer'||provider==='zammad'){
        const result=await post('/api/v1/integrations/list',{provider});
        columns=result.columns;
        rows=result.rows.map(row=>({url:row.url,cells:row.cells.map((value,index)=>result.date_columns.includes(index)?(value?new Date(value).toLocaleString('de-DE'):'–'):value)}));
        section.querySelector('.provider-label').textContent=`Live-Daten · ${rows.length} Einträge`;
        status.textContent=result.note;render();return;
      }
      const configs=await api('/api/v1/integrations');const config=configs.integrations.find(x=>x.provider===provider);
      const result=await post('/api/v1/integrations/test',{provider,domain:config.domain,username:config.username,secret:''});
      if(!result.ok)throw new Error(result.steps.filter(x=>!x.ok).map(x=>x.message).join(' · '));
      const step=[...result.steps].reverse().find(x=>Array.isArray(x.preview));
      const records=step?.preview||[],keys=[...new Set(records.flatMap(Object.keys))];
      const labels={id:'ID',userId:'Benutzer-ID',userid:'Benutzer-ID',login:'Login-ID',loginId:'Login-ID',firstName:'Vorname',firstname:'Vorname',lastName:'Nachname',lastname:'Nachname',name:'Name',email:'E-Mail',number:'Nummer',username:'Benutzername'};
      columns=keys.map(key=>labels[key]||'Weitere Angabe');rows=records.map(row=>({cells:keys.map(key=>row[key]??'–')}));
      if(!columns.length)columns=['Daten'];
      section.querySelector('.provider-label').textContent='Live-Datenprobe · maximal 5 Einträge';status.textContent=result.note;render();
    }catch(error){section.querySelector('.provider-label').textContent='Keine Live-Daten geladen';status.textContent=error.message;}
    finally{event.target.disabled=false;}
  });render();
}
if(new URLSearchParams(location.search).get('starface')==='connected'){
  history.replaceState(null,'',location.pathname);
  toast('STARFACE erfolgreich verknüpft. Einstellungen zum Verbindungstest öffnen.');
}
