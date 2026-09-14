/* One action receipt per dispatched mutation; uncertain requests are never replayed. */
(()=>{
 const original=window.fetch.bind(window),pending=new WeakMap();let activation=null;
 const safe=["/api/v1/admin/user/create","/api/v1/customers", "/api/v1/categories", "/api/v1/projects", "/api/v1/users", "/api/v1/profile/avatar", "/api/v1/sessions/disconnect", "/api/v1/integrations/save", "/api/v1/integrations/remove", "/api/v1/account/save", "/api/v1/account/theme"];
 const eligible=path=>safe.includes(path)||(/\/(save|assign(?:\/(?:customer|project))?|profile|phone|contact-phone|contact|device|delete|action|review|reopen|edit|update|add|archive|begin|end|start|stop|pause|resume|active|approve|reject|submit|cancel|pay|reverse|manual|close|swap|settings|status|clone|merge|roles|preferences|reset-user)$/.test(path)&&!/^\/api\/v1\/(auth|integrations|archive|provider\/refresh|settings|account)\//.test(path)&&path!=='/api/v1/provider/navigation-status');
 function capture(button){activation={button,disabled:button?.disabled};const captured=activation;queueMicrotask(()=>{if(activation===captured)activation=null;});}
 document.addEventListener('click',e=>{const b=e.target.closest('button,input[type=submit]');if(b&&pending.has(b)){e.preventDefault();e.stopImmediatePropagation();return;}if(b)capture(b);},true);
 document.addEventListener('submit',e=>capture(e.submitter||e.target.querySelector('button[type=submit],button:not([type])')),true);
 function paint(b,phase,text){if(!b?.isConnected)return;b.dataset.actionPhase=phase;b.setAttribute('aria-busy',String(phase==='busy'||phase==='uncertain'));if(b.tagName==='INPUT')b.value=text;else b.textContent=text;}
 function begin(b,disabled){if(!b)return null;b.parentElement?.querySelector('[data-action-error]')?.remove();let a=pending.get(b);if(a){a.count++;return a;}a={count:1,html:b.innerHTML,value:b.value,disabled:!!disabled,error:false,uncertain:false};pending.set(b,a);b.disabled=true;paint(b,'busy','Wird gespeichert …');return a;}
 function end(b,a,ok,message,uncertain=false){if(ok&&!uncertain)window.pzUI?.clean(b?.closest('form'));if(!a)return;a.error||=!ok;a.uncertain||=uncertain;if(--a.count)return;
  const phase=a.uncertain?'uncertain':a.error?'error':'success';paint(b,phase,a.uncertain?'Status ungeklärt':a.error?'Fehler':a.successText||'Gespeichert');
  if(a.error&&b.isConnected){let note=b.closest('form')?.querySelector('[data-form-error]')||b.parentElement.querySelector('[data-action-error]');if(!note){note=document.createElement('p');note.dataset.actionError='';note.setAttribute('role','alert');b.after(note);}note.textContent=message||'Speichern fehlgeschlagen. Eingaben bleiben erhalten.';}
  setTimeout(()=>{if(!b.isConnected){pending.delete(b);return;}if(a.uncertain){b.disabled=true;pending.delete(b);return;}
   // Preserve new semantic actions installed by a successful rerender.
   if(['Gespeichert','Gestartet','Beantragt','Fehler'].includes(b.textContent)||b.tagName==='INPUT'){if(b.tagName==='INPUT')b.value=a.value;else b.innerHTML=a.html;}
   b.disabled=b.dataset.actionComplete==='1'||a.disabled;delete b.dataset.actionPhase;b.removeAttribute('aria-busy');pending.delete(b);
  },a.error?4000:3000);
 }
 window.fetch=async(input,init={})=>{
  const url=new URL(typeof input==='string'?input:input.url,location.href),path=url.pathname;
  if(url.origin!==location.origin)return original(input,init);
  if(String(init.method||input?.method||'GET').toUpperCase()!=='POST'||!path.startsWith('/api/')||!eligible(path))return original(input,init);
  const b=activation?.button||document.activeElement?.closest('button[type=submit]'),a=begin(b,activation?.disabled),headers=new Headers(init.headers||input?.headers||{}),key=headers.get('Idempotency-Key')||crypto.randomUUID();headers.set('Idempotency-Key',key);
  let response;
  try{response=await original(input,{...init,headers});const data=await response.clone().json();const uncertain=['pending','uncertain'].includes(data.action_state);if(a)a.successText=data.state==='pending'?'Beantragt':response.status===202||data.state==='running'||data.job?.state==='running'?'Gestartet':'Gespeichert';end(b,a,response.ok&&data.ok!==false,data.error,uncertain);return response;}
  catch(error){
   paint(b,'uncertain','Speicherstatus wird geprüft …');
   // Query the receipt with an independent timeout, never resubmit the mutation.
   try{const control=new AbortController(),timer=setTimeout(()=>control.abort(),10000);let check;try{check=await original('/api/v1/actions/receipt',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':headers.get('X-CSRF-Token')||''},body:JSON.stringify({request_id:key}),signal:control.signal});}finally{clearTimeout(timer);}const receipt=await check.json();
    if(check.ok&&receipt.state==='completed'){end(b,a,receipt.status<400,receipt.payload?.error);return new Response(JSON.stringify(receipt.payload),{status:receipt.status,headers:{'Content-Type':'application/json'}});}
   }catch(_){}
   end(b,a,false,'Speicherstatus ungeklärt. Bitte Daten aktualisieren und den Vorgang prüfen; nicht erneut buchen.',true);throw error;
  }
 };
})();
