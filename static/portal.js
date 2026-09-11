// Preview rows are separate from recorded work and live API data.
const providerExamples={
  zammad:{title:'Tickets & Support',description:'Tickets zuordnen und später mit Projektzeiten verbinden.',columns:['Ticket','Titel','Kunde','Status'],rows:[['#1042','Drucker im Büro einrichten','Musterkunde Nord','Offen'],['#1043','VPN-Zugang prüfen','Beispiel GmbH','In Bearbeitung'],['#1044','E-Mail-Konto anlegen','Musterkunde Süd','Wartend']]},
  starface:{title:'Telefonie & Gespräche',description:'Vorschau einer Gesprächsliste. Die Live-Probe liest aktuell Benutzer; echte Anruflisten benötigen eine zusätzliche UCI-Anbindung.',columns:['Zeit','Kontakt','Richtung','Dauer'],rows:[['09:10','Musterkunde Nord','Eingehend','00:08:12'],['10:35','Beispiel GmbH','Ausgehend','00:04:36'],['11:50','Musterkunde Süd','Verpasst','–']]},
  teamviewer:{title:'Fernwartung & Verbindungen',description:'Fernwartungsverbindungen mit Beginn, Ende und Gerätebezug prüfen.',columns:['Gerät','Kontakt','Beginn','Ende'],rows:[['BÜRO-PC-01','Musterkunde Nord','09:30','09:55'],['SERVER-02','Beispiel GmbH','10:15','10:45'],['LAPTOP-03','Musterkunde Süd','13:00','13:20']]}
};
for(const section of document.querySelectorAll('.provider-view')){
  const provider=section.dataset.source,info=providerExamples[provider];
  section.innerHTML=`<article class="panel"><p class="eyebrow">${esc(provider.toUpperCase())}</p><h3>${esc(info.title)}</h3><p class="provider-note">${esc(info.description)}</p><span class="provider-label">Beispieldaten · keine echten Aktivitäten</span><div class="provider-toolbar"><input type="search" placeholder="Liste durchsuchen …" aria-label="Liste durchsuchen"><button class="secondary" data-example>Beispiele anzeigen</button><button class="primary admin-only" data-live>Echte Daten laden</button></div><p class="provider-status" role="status"></p><div class="table-wrap"><table><thead></thead><tbody></tbody></table></div></article>`;
  let columns=info.columns,rows=info.rows;
  function render(){
    const q=section.querySelector('input').value.toLocaleLowerCase();
    const filtered=rows.filter(row=>row.join(' ').toLocaleLowerCase().includes(q));
    section.querySelector('thead').innerHTML='<tr>'+columns.map(x=>`<th>${esc(x)}</th>`).join('')+'</tr>';
    section.querySelector('tbody').innerHTML=filtered.length?filtered.map(row=>'<tr>'+row.map(x=>`<td>${esc(x)}</td>`).join('')+'</tr>').join(''):`<tr><td colspan="${Math.max(1,columns.length)}">Keine Einträge vorhanden.</td></tr>`;
  }
  section.querySelector('input').addEventListener('input',render);
  section.querySelector('[data-example]').addEventListener('click',()=>{columns=info.columns;rows=info.rows;section.querySelector('.provider-label').textContent='Beispieldaten · keine echten Aktivitäten';section.querySelector('.provider-status').textContent='';render()});
  section.querySelector('[data-live]').addEventListener('click',async event=>{
    event.target.disabled=true;const status=section.querySelector('.provider-status');status.textContent='Daten werden geladen …';
    rows=[];render();section.querySelector('.provider-label').textContent='Live-Abfrage läuft';
    try{
      const configs=await api('/api/v1/integrations');const config=configs.integrations.find(x=>x.provider===provider);
      const result=await post('/api/v1/integrations/test',{provider,domain:config.domain,username:config.username,secret:''});
      if(!result.ok)throw new Error(result.steps.filter(x=>!x.ok).map(x=>x.message).join(' · '));
      const step=[...result.steps].reverse().find(x=>Array.isArray(x.preview));
      const records=step?.preview||[];columns=[...new Set(records.flatMap(Object.keys))];rows=records.map(row=>columns.map(key=>row[key]??'–'));
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
