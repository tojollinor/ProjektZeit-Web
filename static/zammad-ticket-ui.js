(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const dialog=()=>q('.ticket-thread-dialog');
 function firstLine(text){return String(text||'').split(/\r?\n/).map(x=>x.trim()).find(Boolean)||'Keine Textvorschau';}
 function enhance(){
  const root=dialog();if(!root||root.dataset.collapseReady==='1')return;
  const box=q('[data-ticket-body]',root),head=q('.ticket-thread-head',box),thread=q('.ticket-thread',box);if(!head||!thread)return;
  root.dataset.collapseReady='1';const toolbar=document.createElement('div');toolbar.className='ticket-thread-controls';toolbar.innerHTML='<button type="button" class="secondary subtle" data-ticket-collapse-all>Alle Antworten einklappen</button><button type="button" class="secondary subtle" data-ticket-expand-all>Alle Antworten ausklappen</button>';head.append(toolbar);
  const cards=qa('.ticket-article',thread);for(const card of cards){const body=q('.ticket-article-body',card),articleHead=q('.ticket-article-head',card);if(!body||!articleHead)continue;const preview=document.createElement('small');preview.className='ticket-collapsed-preview';preview.textContent=firstLine(body.textContent);q('div',articleHead)?.append(preview);}
  q('[data-ticket-collapse-all]',toolbar).onclick=()=>cards.forEach(card=>card.classList.add('ticket-overview-collapsed'));
  q('[data-ticket-expand-all]',toolbar).onclick=()=>cards.forEach(card=>card.classList.remove('ticket-overview-collapsed','ticket-body-clamped'));
  const external=q('a.ticket-open-zammad',box);if(external)external.textContent='In Zammad öffnen';
 }
 if(typeof openTicket==='function'){const original=openTicket;openTicket=async function(id){const root=dialog();if(root)delete root.dataset.collapseReady;const result=await original(id);requestAnimationFrame(()=>requestAnimationFrame(enhance));return result;};}
 const observer=new MutationObserver(()=>{const root=dialog();if(root&&q('.ticket-thread',root)&&root.dataset.collapseReady!=='1')requestAnimationFrame(enhance);});observer.observe(document.body,{childList:true,subtree:true});
})();
