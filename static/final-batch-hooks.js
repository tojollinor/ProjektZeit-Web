(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const notify=(m,l='info',t=5000)=>window.pzToast?window.pzToast(m,l,t):null;
 async function postJson(path,body={}){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);try{const r=await fetch(path,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json',...(typeof state!=='undefined'&&state.csrf?{'X-CSRF-Token':state.csrf}:{})},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`);return d;}finally{clearTimeout(timer);}}

 async function askLink(customerId,provider,type,value,label){
  value=String(value||'').trim();if(!value)return;
  try{const c=await postJson('/api/v1/customers/link/candidates',{customer_id:customerId,provider,link_type:type,link_value:value});if(!c.count)return;const yes=await window.pzUI.confirm(`${c.count} ${label} zu ${value} gefunden. Sollen diese dem Kunden zugeordnet werden?`);await postJson('/api/v1/customers/link/add',{customer_id:customerId,provider,link_type:type,link_value:value,bulk:yes});notify(yes?`${c.count} Einträge zugeordnet`:'Verknüpfung für zukünftige Einträge gespeichert','success');}catch(e){notify(e.message,'warning');}
 }

 /* After customer profile save/create, offer to connect cached Zammad/STARFACE data. */
 const native=window.fetch.bind(window);
 window.fetch=(input,init={})=>{
  const url=typeof input==='string'?input:input?.url||'',promise=native(input,init);
  if(/\/api\/v1\/customers\/profile$/.test(url)&&String(init.method||'GET').toUpperCase()==='POST'){
   let body={};try{body=JSON.parse(init.body||'{}');}catch(_){}
   promise.then(r=>r.ok?r.clone().json():null).then(d=>{const cid=d?.customer_id||body.id;if(!cid)return;setTimeout(()=>{if(body.email)askLink(cid,'zammad','email',body.email,'Zammad-Tickets');for(const p of body.phones||[])if(p?.number)askLink(cid,'starface','phone',p.number,'STARFACE-Anrufe');},250);}).catch(()=>{});
  }
  return promise;
 };

 /* Customer edit forms have phone operations separate from profile save. Ask after successful phone add/update too. */
 document.addEventListener('submit',e=>{
  const box=e.target.closest('.customer-detail-dialog [data-detail]');if(!box)return;const cid=Number(box.dataset.pzCustomerId||0);if(!cid)return;
  const email=e.target.querySelector('input[name="email"]')?.value||'';const phone=e.target.querySelector('input[name="number"],input[data-new-phone]')?.value||'';
  if(email)setTimeout(()=>askLink(cid,'zammad','email',email,'Zammad-Tickets'),700);if(phone)setTimeout(()=>askLink(cid,'starface','phone',phone,'STARFACE-Anrufe'),700);
 },true);

 /* Tag the currently open customer so save hooks know which stable customer ID they belong to. */
 if(typeof openCustomer==='function'&&!window.pzCustomerIdWrapped){const original=openCustomer;openCustomer=async function(id){const r=await original(id);const box=q('.customer-detail-dialog [data-detail]');if(box)box.dataset.pzCustomerId=String(id);return r;};window.pzCustomerIdWrapped=true;}
})();
