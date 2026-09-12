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

 // Keep the mobile navigation scrim strictly in sync with the sidebar.
 // showView() closes the sidebar after selecting a destination, so the
 // scrim must be cleared there as well or it remains as a dark overlay.
 const sidebar=q('.sidebar');
 function syncScrim(){
  if(!sidebar)return;
  const scrim=q('.sidebar-scrim');
  if(scrim)scrim.classList.toggle('open',sidebar.classList.contains('open'));
 }
 if(sidebar){
  new MutationObserver(syncScrim).observe(sidebar,{attributes:true,attributeFilter:['class']});
  document.addEventListener('click',event=>{
   if(event.target.closest('.nav,[data-go],#menu-toggle,.sidebar-scrim'))setTimeout(syncScrim,0);
  });
  window.addEventListener('resize',()=>{if(innerWidth>900){sidebar.classList.remove('open');syncScrim();}});
  syncScrim();
 }
})();
