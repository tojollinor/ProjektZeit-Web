(() => {
  const container=document.querySelector('#integration-cards');
  if(!container)return;
  let pollTimer=null;

  async function starfaceData(){
    const data=await api('/api/v1/integrations');
    return data.integrations.find(row=>row.provider==='starface');
  }

  window.renderStarfaceCard = row => {
    const configured=!!row.username;
    return '<article class="panel integration-card" data-provider="starface">' + `<div class="panel-head"><h3>STARFACE</h3><span class="badge">${row.has_secret?'Verbunden':configured?'Konfiguriert':'Nicht eingerichtet'}</span></div>
        <p class="integration-note">Adresse und OAuth-Client werden zentral auf dem ProjektZeit-Server gespeichert. Der Windows-Client wird nur für Browser-Anmeldung und lokalen STARFACE-Rücksprung benötigt. Danach kann er beendet werden.</p>
        <div class="integration-fields">
          <label>STARFACE-Adresse<input data-field="domain" value="${attr(row.domain)}" placeholder="https://telefon.firma.de" autocomplete="off" spellcheck="false"></label>
          <label>Client-ID<input data-field="client_id" value="${attr(row.username||'rest-client')}" maxlength="250" autocomplete="off" spellcheck="false"></label>
          <label>Client-Secret<input data-field="client_secret" type="password" maxlength="4096" autocomplete="new-password" placeholder="${configured?'Gespeichert – leer lassen zum Beibehalten':'Client-Secret eingeben'}"></label>
        </div>
        <div class="panel-actions">
          <button type="button" class="secondary" data-starface-action="save">Konfiguration speichern</button>
          <button type="button" class="primary" data-starface-action="connect">STARFACE verbinden</button>
          <button type="button" class="secondary" data-starface-action="test">Verbindung testen</button>
          <button type="button" class="secondary subtle" data-starface-action="remove">Verknüpfung entfernen</button>
        </div>
        <p class="integration-note">Die aktuelle Windows-EXE zuerst einmal manuell starten. Weboberfläche und Client müssen mit demselben ProjektZeit-Benutzer angemeldet sein.</p><div class="desktop-launch hidden"></div><div class="integration-status" role="status"></div><div class="debug-output hidden"></div>` + '</article>';
  };

  async function saveConfig(card){
    const domain=normalizeStarfaceAddress(card.querySelector('[data-field="domain"]').value);
    const clientId=card.querySelector('[data-field="client_id"]').value.trim()||'rest-client';
    const clientSecret=card.querySelector('[data-field="client_secret"]').value;
    const result=await post('/api/v1/integrations/starface/start',{
      configure_only:true,domain,client_id:clientId,client_secret:clientSecret
    });
    card.querySelector('[data-field="domain"]').value=result.domain;
    card.querySelector('[data-field="client_id"]').value=result.client_id;
    const secret=card.querySelector('[data-field="client_secret"]');
    secret.value='';secret.placeholder='Gespeichert – leer lassen zum Beibehalten';
    card.querySelector('.badge').textContent='Konfiguriert';
    return result;
  }

  async function pollConnected(card){
    clearInterval(pollTimer);
    let remaining=200;
    pollTimer=setInterval(async()=>{
      if(!card.isConnected){clearInterval(pollTimer);return;}
      if(--remaining<=0){clearInterval(pollTimer);card.querySelector('.integration-status').textContent='Zeitlimit erreicht. Falls die Anmeldung noch offen ist, erneut „STARFACE verbinden“ wählen.';return;}
      try{
        const row=await starfaceData();
        if(row?.has_secret){
          clearInterval(pollTimer);
          card.querySelector('.desktop-launch').classList.add('hidden');
          card.querySelector('.badge').textContent='Verbunden';
          window.dispatchEvent(new Event('starface-connected'));
          const status=card.querySelector('.integration-status');status.className='integration-status success';status.textContent='STARFACE ist verbunden. Die Verbindung liegt jetzt auf dem ProjektZeit-Server und funktioniert auch ohne laufenden Windows-Client.';
        }
      }catch{}
    },1500);
  }

  container.addEventListener('click',async event=>{
    const button=event.target.closest('[data-starface-action]');
    if(!button)return;
    const card=button.closest('[data-provider="starface"]');
    if(!card)return;
    event.preventDefault();event.stopImmediatePropagation();
    const action=button.dataset.starfaceAction,status=card.querySelector('.integration-status'),output=card.querySelector('.debug-output');
    const controls=[...card.querySelectorAll('button,input')];
    if(action==='remove'&&!confirm('Gespeicherte STARFACE-Konfiguration und OAuth-Verknüpfung entfernen?'))return;
    controls.forEach(x=>x.disabled=true);status.className='integration-status';output.replaceChildren();output.classList.add('hidden');
    clearInterval(pollTimer);
    card.querySelector('.desktop-launch').replaceChildren();
    card.querySelector('.desktop-launch').classList.add('hidden');
    try{
      if(action==='save'){
        status.textContent='Konfiguration wird gespeichert …';await saveConfig(card);status.classList.add('success');status.textContent='STARFACE-Konfiguration verschlüsselt gespeichert.';
      }else if(action==='connect'){
        status.textContent='Konfiguration wird geprüft …';await saveConfig(card);
        const start=await post('/api/v1/integrations/starface/start',{desktop_prepare:true});
        status.textContent='ProjektZeit-Client wird geöffnet … Im Client bzw. Browser die STARFACE-Anmeldung abschließen.';
        const launch=card.querySelector('.desktop-launch');
        const link=document.createElement('a');
        link.href=start.uri;link.className='secondary';link.textContent='Windows-Client öffnen';
        const hint=document.createElement('p');
        hint.textContent='Falls kein Fenster erscheint: aktuelle EXE herunterladen, einmal starten und diesen Link anklicken. Die Browser-Abfrage zum Öffnen bestätigen.';
        launch.replaceChildren(link,hint);launch.classList.remove('hidden');
        window.location.href=start.uri;
        pollConnected(card);
      }else if(action==='test'){
        status.textContent='Verbindung wird geprüft …';
        const domain=normalizeStarfaceAddress(card.querySelector('[data-field="domain"]').value);
        const result=await post('/api/v1/integrations/test',{provider:'starface',domain,username:'',secret:''});
        status.textContent=result.ok?'Verbindungstest erfolgreich.':'Verbindungstest unvollständig oder fehlgeschlagen.';
        status.classList.add(result.ok?'success':'failure');
        output.classList.remove('hidden');
        output.innerHTML=`<p class="integration-note">${esc(result.note)}</p><p class="integration-meta">${esc(new Date(result.checked_at).toLocaleString('de-DE'))} · ${result.duration_ms} ms</p>`+result.steps.map(step=>`<section class="debug-step"><strong>${step.ok?'✓':'✕'} ${esc(step.name)}${step.status?' · HTTP '+step.status:''}</strong><p>${esc(step.message)}</p></section>`).join('');
      }else if(action==='remove'){
        await post('/api/v1/integrations/remove',{provider:'starface'});clearInterval(pollTimer);
        card.dataset.desktopUi='';await loadIntegrations();
      }
    }catch(error){status.textContent=error.message;status.classList.add('failure');}
    finally{controls.forEach(x=>x.disabled=false);}
  },true);
})();
