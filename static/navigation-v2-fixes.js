(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 function applyChartSizes(){
  const root=q('#view-statistics');if(!root)return;
  for(const el of qa('.pz-stat-bar i[style],.pz-week-bars i[style]',root)){
   const raw=el.getAttribute('style')||'',m=raw.match(/(width|height)\s*:\s*([0-9.]+)%/i);if(!m)continue;
   el.removeAttribute('style');el.style[m[1].toLowerCase()]=`${Math.max(0,Math.min(100,Number(m[2])))}%`;
  }
 }
 function syncWorkPanel(name){const panel=q('.work-panel');if(!panel)return;panel.hidden=name==='statistics'||name.startsWith('settings-')||name.startsWith('workshop-')||['admin-options','logs','bookkeeping','account'].includes(name);}
 const original=window.pzOpenNavTarget;
 if(original)window.pzOpenNavTarget=(name,label)=>{original(name,label);syncWorkPanel(name);requestAnimationFrame(applyChartSizes);};
 const stats=q('#view-statistics');if(stats){let pending=false;new MutationObserver(()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;applyChartSizes();});}).observe(stats,{childList:true,subtree:true});}
 document.addEventListener('click',event=>{const nav=event.target.closest('.sidebar [data-view], [data-go]');if(!nav)return;const name=nav.dataset.view||nav.dataset.go||'';setTimeout(()=>syncWorkPanel(name),0);});
 applyChartSizes();
})();
