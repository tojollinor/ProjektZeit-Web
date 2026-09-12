(()=>{
 const panel=document.querySelector('.work-panel');if(!panel)return;
 const q=(s,r=document)=>r.querySelector(s),notify=(m,l='info')=>window.pzToast?.(m,l,4500);
 const compact=document.createElement('div');compact.className='work-panel-compact';compact.innerHTML='<div class="work-panel-compact-main"><span data-work-compact-project>Kein Projekt läuft</span><strong data-work-compact-time>00:00:00</strong></div><div class="work-panel-compact-actions"><button type="button" class="primary" data-workday-toggle>Arbeit starten</button><button type="button" class="secondary" data-work-pause>Pause</button></div>';
 panel.append(compact);
 const collapse=document.createElement('button');collapse.type='button';collapse.className='work-panel-chevron';collapse.setAttribute('aria-label','Arbeitszeitleiste ein- oder ausklappen');collapse.innerHTML='⌃';q('.panel-head',panel)?.append(collapse);
 const hiddenViews=new Set(['settings','users']);let workState={state:'stopped',work:null,pause:null},busy=false;
 function activeView(){const v=document.querySelector('.view.active-view');return v?.id?.replace(/^view-/,'')||'dashboard';}
 function fmt(start){if(!start)return'00:00:00';let s=Math.max(0,Math.floor((Date.now()-new Date(start))/1000));return`${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;}
 function setText(el,value){if(el&&el.textContent!==value)el.textContent=value;}
 function syncVisibility(){panel.hidden=hiddenViews.has(activeView());}
 function setCollapsed(value){panel.classList.toggle('is-collapsed',value);collapse.innerHTML=value?'⌄':'⌃';collapse.setAttribute('aria-expanded',String(!value));}
 function syncCompact(){
  const data=typeof state!=='undefined'?state.data:null,running=data?.entries?.find(e=>!e.ended_at&&!e.is_idle),working=workState.state!=='stopped',paused=workState.state==='pause';
  setText(q('[data-work-compact-project]',compact),paused?'Pause':running?.project||(!working?'Arbeitstag nicht gestartet':'Kein Projekt läuft'));
  setText(q('[data-work-compact-time]',compact),paused?fmt(workState.pause?.started_at):(working?fmt(workState.work?.started_at):'00:00:00'));
  const toggle=q('[data-workday-toggle]',compact),pause=q('[data-work-pause]',compact);
  if(paused){toggle.hidden=true;pause.hidden=false;pause.className='primary work-pause-end';pause.textContent='Pause beenden';}
  else{toggle.hidden=false;toggle.textContent=working?'Arbeit beenden':'Arbeit starten';pause.hidden=false;pause.className='secondary';pause.textContent='Pause';pause.disabled=!working;}
  panel.classList.toggle('work-is-paused',paused);
 }
 async function refreshState(){if(typeof post!=='function'||typeof state==='undefined'||!state.user)return;try{workState=await post('/api/v1/worktime/state',{});syncCompact();}catch(_){}}
 async function action(name){if(busy)return;busy=true;try{workState=await post('/api/v1/worktime/action',{action:name});await (typeof loadData==='function'?loadData():Promise.resolve());syncCompact();}catch(e){notify(e.message,'error');}finally{busy=false;}}
 q('[data-workday-toggle]',compact).onclick=e=>{e.stopPropagation();action(workState.state==='stopped'?'begin':'end');};
 q('[data-work-pause]',compact).onclick=e=>{e.stopPropagation();action(workState.state==='pause'?'resume':'pause');};
 collapse.onclick=e=>{e.stopPropagation();if(workState.state!=='pause')setCollapsed(!panel.classList.contains('is-collapsed'));};
 panel.addEventListener('click',e=>{if(workState.state==='pause')return;if(e.target.closest('button,a,input,select,textarea,label,[role="button"],details,summary'))return;setCollapsed(!panel.classList.contains('is-collapsed'));});
 setCollapsed(true);syncVisibility();syncCompact();refreshState();
 const observer=new MutationObserver(syncVisibility);for(const view of document.querySelectorAll('.view'))observer.observe(view,{attributes:true,attributeFilter:['class']});
 setInterval(()=>{syncCompact();if(!busy)refreshState();},5000);
 document.addEventListener('click',event=>{if(event.target.closest('.nav,[data-go]')){setCollapsed(true);setTimeout(syncVisibility,0);}});

 const prompt=document.createElement('dialog');prompt.className='workday-start-dialog';prompt.innerHTML='<div><h3>Arbeitstag starten?</h3><p>Möchten Sie den Arbeitstag jetzt beginnen?</p><div class="panel-actions"><button type="button" class="primary" data-workday-yes>Ja</button><button type="button" class="secondary" data-workday-no>Nein</button></div></div>';document.body.append(prompt);
 q('[data-workday-no]',prompt).onclick=()=>prompt.close();q('[data-workday-yes]',prompt).onclick=async()=>{await action('begin');prompt.close();};
 async function maybePrompt(){if(typeof state==='undefined'||!state.user)return;await refreshState();let shown=false;try{shown=sessionStorage.getItem('pz-workday-prompted')==='1';}catch(_){}if(!shown&&workState.state==='stopped'){try{sessionStorage.setItem('pz-workday-prompted','1');}catch(_){}prompt.showModal();}}
 let tries=0;const timer=setInterval(()=>{tries++;if(typeof state!=='undefined'&&state.user){clearInterval(timer);setTimeout(maybePrompt,250);}else if(tries>100)clearInterval(timer);},100);
})();
