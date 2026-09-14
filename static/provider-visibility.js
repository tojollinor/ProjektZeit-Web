(()=>{
 const q=(selector,root=document)=>root.querySelector(selector);
 const connection=()=>window.pzProviderStates?.get('starface');
 const message=()=>connection()?.detail||'STARFACE ist nicht verbunden. Bitte die Verbindung unter Einstellungen → Verbindungen prüfen.';
 window.pzRequireCallConnection=()=>{if(connection()?.connected)return true;window.pzUI.message('STARFACE nicht verbunden',message());return false;};
 window.addEventListener('click',event=>{const call=event.target.closest?.('a[href^="tel:"],[data-quick-phone],[data-location-phone]');if(!call||connection()?.connected)return;event.preventDefault();event.stopImmediatePropagation();window.pzRequireCallConnection();},true);
 function decorate(){const connected=connection()?.connected===true;for(const call of document.querySelectorAll('a[href^="tel:"],[data-quick-phone],[data-location-phone]')){call.setAttribute('aria-disabled',String(!connected));if(!connected){call.title=message();call.style.cursor='not-allowed';}else{call.removeAttribute('title');call.style.removeProperty('cursor');}}
  if(!connected){q('#view-starface tbody')?.replaceChildren();q('[data-missed-list]')?.replaceChildren();const status=q('[data-missed-status]');if(status&&status.textContent!==message())status.textContent=message();for(const card of document.querySelectorAll('.customer-detail-dialog .activity-list article')){if(q('.provider-label',card)?.textContent.trim().toLowerCase()==='starface')card.remove();}const history=q('.customer-detail-dialog [data-pane="history"]');if(history){let note=q('.provider-disconnected-note',history);if(!note){note=document.createElement('p');note.className='provider-disconnected-note';history.prepend(note);}if(note.textContent!==message())note.textContent=message();}}
 }
 document.addEventListener('pz-connection-visibility',decorate);
 let queued=false;const root=q('.customer-detail-dialog');if(root)new MutationObserver(()=>{if(queued)return;queued=true;setTimeout(()=>{queued=false;decorate();},20);}).observe(root,{childList:true,subtree:true});
})();
