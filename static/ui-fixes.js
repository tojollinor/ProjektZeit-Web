(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 function beta(el){if(el&&!el.querySelector('.beta-tag'))el.insertAdjacentHTML('beforeend',' <span class="beta-tag">Beta</span>');}
 function apply(){
  const isAdmin=typeof state!=='undefined'&&state.user?.role==='admin';
  qa('[data-starface-admin]').forEach(el=>el.style.display=isAdmin?'':'none');
  for(const sel of ['[data-admin-tab="roles"]','[data-admin-tab="policies"]','[data-admin-tab="smtp"]','[data-admin-tab="notifications"]','[data-admin-tab="super"]'])beta(q(sel));
  qa('[data-history-load],[data-async-history]').forEach(el=>{if(!el.querySelector('.beta-tag'))el.insertAdjacentHTML('beforeend',' <span class="beta-tag">Beta</span>');});
 }
 const observer=new MutationObserver(apply);observer.observe(document.body,{childList:true,subtree:true});
 let tries=0;const wait=setInterval(()=>{tries++;apply();if((typeof state!=='undefined'&&state.user)||tries>80)clearInterval(wait);},100);
 const sidebar=q('.sidebar');function syncScrim(){if(!sidebar)return;const scrim=q('.sidebar-scrim');if(scrim)scrim.classList.toggle('open',sidebar.classList.contains('open'));}
 if(sidebar){new MutationObserver(syncScrim).observe(sidebar,{attributes:true,attributeFilter:['class']});document.addEventListener('click',event=>{if(event.target.closest('.nav,[data-go],#menu-toggle,.sidebar-scrim'))setTimeout(syncScrim,0);});window.addEventListener('resize',()=>{if(innerWidth>900){sidebar.classList.remove('open');syncScrim();}});syncScrim();}
 const build=q('meta[name="pz-frontend-version"]')?.content||'';
 function versioned(url){if(!build||/([?&])pzv=/.test(url))return url;return `${url}${url.includes('?')?'&':'?'}pzv=${encodeURIComponent(build)}`;}
 function stylesheet(href,key){if(document.querySelector(`link[data-${key}]`))return;const link=document.createElement('link');link.rel='stylesheet';link.href=versioned(href);link.dataset[key]='';document.head.append(link);}
 function script(src,key){if(document.querySelector(`script[data-${key}]`))return;const el=document.createElement('script');el.src=versioned(src);el.defer=true;el.dataset[key]='';document.body.append(el);}
 stylesheet('/ux-batch.css?v=0.7.0-2','uxBatch');script('/ux-batch.js?v=0.7.0-2','uxBatch');
 stylesheet('/provider-api-ui.css?v=0.7.0-1','providerApiUi');script('/provider-api-ui.js?v=0.7.0-1','providerApiUi');script('/network-guard.js?v=0.7.0-1','networkGuard');
 stylesheet('/work-panel-ui.css?v=0.7.0-2','workPanelUi');script('/work-panel-ui.js?v=0.7.0-2','workPanelUi');
 stylesheet('/zammad-ticket-ui.css?v=0.7.0-2','zammadTicketUi');script('/zammad-ticket-ui.js?v=0.7.0-1','zammadTicketUi');script('/zammad-cache-ui.js?v=0.7.0-4','zammadCacheUi');
 stylesheet('/provider-nav-status.css?v=0.7.0-1','providerNavStatus');script('/provider-nav-status.js?v=0.7.0-1','providerNavStatus');
 stylesheet('/customer-extra-ui.css?v=0.7.0-1','customerExtraUi');script('/customer-extra-ui.js?v=0.7.0-1','customerExtraUi');
 stylesheet('/ux-round2.css?v=0.7.0-1','uxRound2');script('/ux-round2.js?v=0.7.0-1','uxRound2');
 stylesheet('/next-batch-ui.css?v=0.7.0-1','nextBatchUi');script('/next-batch-ui.js?v=0.7.0-2','nextBatchUi');script('/next-batch-fixes.js?v=0.7.0-1','nextBatchFixes');
})();
