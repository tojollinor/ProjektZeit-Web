(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const dialog=()=>q('.ticket-thread-dialog');
 function firstLine(text){return String(text||'').split(/\r?\n/).map(x=>x.trim()).find(Boolean)||'Keine Textvorschau';}
 function enhance(){
  const root=dialog();if(!root||root.dataset.collapseReady==='1')return;
  const box=q('[data-ticket-body]',root),head=q('.ticket-thread-head',box),thread=q('.ticket-thread',box);
  if(!head||!thread)return;
  root.dataset.collapseReady='1';
  const toolbar=document.createElement('div');toolbar.className='ticket-thread-controls';
  toolbar.innerHTML='<button type="button" class="secondary subtle" data-ticket-collapse-all>Alle Antworten einklappen</button><button type="button" class="secondary subtle" data-ticket-expand-all>Alle Antworten ausklappen</button>';
  head.append(toolbar);
  const cards=qa('.ticket-article',thread);
  for(const card of cards){
   const body=q('.ticket-article-body',card),articleHead=q('.ticket-article-head',card);if(!body||!articleHead)continue;
   const preview=document.createElement('small');preview.className='ticket-collapsed-preview';preview.textContent=firstLine(body.textContent);q('div',articleHead)?.append(preview);
   const toggle=document.createElement('button');toggle.type='button';toggle.className='secondary subtle ticket-article-toggle';toggle.textContent='Mehr anzeigen';articleHead.append(toggle);
   requestAnimationFrame(()=>{
    const style=getComputedStyle(body),line=parseFloat(style.lineHeight)||22,max=line*7.2;
    if(body.scrollHeight>max+2){card.classList.add('ticket-article-long','ticket-body-clamped');toggle.hidden=false;}
    else{toggle.hidden=true;}
   });
   toggle.onclick=()=>{
    if(card.classList.contains('ticket-overview-collapsed')){
      card.classList.remove('ticket-overview-collapsed');
      if(card.classList.contains('ticket-article-long'))card.classList.add('ticket-body-clamped');
      toggle.textContent=card.classList.contains('ticket-article-long')?'Mehr anzeigen':'Einklappen';
      if(!card.classList.contains('ticket-article-long'))toggle.hidden=false;
      return;
    }
    if(card.classList.contains('ticket-article-long')){
      const clamped=card.classList.toggle('ticket-body-clamped');toggle.textContent=clamped?'Mehr anzeigen':'Weniger anzeigen';
    }else{
      card.classList.add('ticket-overview-collapsed');toggle.textContent='Antwort öffnen';
    }
   };
  }
  q('[data-ticket-collapse-all]',toolbar).onclick=()=>{
   for(const card of cards){card.classList.add('ticket-overview-collapsed');const b=q('.ticket-article-toggle',card);if(b){b.hidden=false;b.textContent='Antwort öffnen';}}
  };
  q('[data-ticket-expand-all]',toolbar).onclick=()=>{
   for(const card of cards){card.classList.remove('ticket-overview-collapsed');const b=q('.ticket-article-toggle',card);if(card.classList.contains('ticket-article-long')){card.classList.add('ticket-body-clamped');if(b){b.hidden=false;b.textContent='Mehr anzeigen';}}else if(b)b.hidden=true;}
  };
  const external=qa('a.ticket-open-zammad',box)[0];if(external)external.textContent='In Zammad öffnen';
 }
 if(typeof openTicket==='function'){
  const original=openTicket;
  openTicket=async function(id){const root=dialog();if(root)delete root.dataset.collapseReady;const result=await original(id);requestAnimationFrame(()=>requestAnimationFrame(enhance));return result;};
 }
 const observer=new MutationObserver(()=>{const root=dialog();if(root&&q('.ticket-thread',root)&&root.dataset.collapseReady!=='1')requestAnimationFrame(enhance);});
 observer.observe(document.body,{childList:true,subtree:true});
})();
