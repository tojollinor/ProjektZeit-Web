(()=>{
 const panel=document.querySelector('.work-panel');if(!panel)return;
 const q=(s,r=document)=>r.querySelector(s);
 const compact=document.createElement('div');compact.className='work-panel-compact';compact.innerHTML='<div class="work-panel-compact-main"><span data-work-compact-project>Kein Projekt läuft</span><strong data-work-compact-time>00:00:00</strong></div><button type="button" class="primary" data-work-compact-action>Starten</button>';
 panel.append(compact);
 const collapse=document.createElement('button');collapse.type='button';collapse.className='secondary subtle work-panel-collapse';collapse.setAttribute('aria-expanded','true');collapse.textContent='Einklappen';
 q('.panel-head',panel)?.append(collapse);
 const hiddenViews=new Set(['settings','users']);
 function activeView(){const v=document.querySelector('.view.active-view');return v?.id?.replace(/^view-/,'')||'dashboard';}
 function fmt(start){if(!start)return'00:00:00';let s=Math.max(0,Math.floor((Date.now()-new Date(start))/1000));return`${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;}
 function syncVisibility(){panel.hidden=hiddenViews.has(activeView());}
 function syncCompact(){
  const data=typeof state!=='undefined'?state.data:null,running=data?.entries?.find(e=>!e.ended_at),working=!!data?.work;
  q('[data-work-compact-project]',compact).textContent=running&&!running.is_idle?running.project:(running?.is_idle?'Unproduktive Zeit':'Kein Projekt läuft');
  q('[data-work-compact-time]',compact).textContent=running?fmt(running.started_at):'00:00:00';
  const action=q('[data-work-compact-action]',compact);
  if(running&&!running.is_idle){action.textContent='Stoppen';action.dataset.mode='stop';}
  else if(!working){action.textContent='Arbeitsbeginn';action.dataset.mode='begin';}
  else{action.textContent='Starten';action.dataset.mode='start';}
 }
 function setCollapsed(value){panel.classList.toggle('is-collapsed',value);collapse.textContent=value?'Ausklappen':'Einklappen';collapse.setAttribute('aria-expanded',String(!value));try{localStorage.setItem('pz-work-panel-collapsed',value?'1':'0');}catch(_){}}
 collapse.onclick=()=>setCollapsed(!panel.classList.contains('is-collapsed'));
 q('[data-work-compact-action]',compact).onclick=()=>{
  const mode=q('[data-work-compact-action]',compact).dataset.mode;
  if(mode==='stop')return q('#project-pause')?.click();
  if(mode==='begin')return q('#work-begin')?.click();
  setCollapsed(false);q('#project-select')?.focus();
 };
 let stored=false;try{stored=localStorage.getItem('pz-work-panel-collapsed')==='1';}catch(_){}
 setCollapsed(stored);syncVisibility();syncCompact();
 const observer=new MutationObserver(()=>{syncVisibility();syncCompact();});observer.observe(document.body,{attributes:true,attributeFilter:['class'],subtree:true,childList:true});
 setInterval(syncCompact,1000);
 document.addEventListener('click',event=>{if(event.target.closest('.nav,[data-go]'))setTimeout(syncVisibility,0);});
})();
