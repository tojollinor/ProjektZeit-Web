(()=>{
 if(window.__pzPerformanceGuard)return;
 window.__pzPerformanceGuard=true;
 window.pzApplyRowVisibility=row=>{row.hidden=['statusHidden','dateHidden','assignmentHidden','searchHidden','employeeHidden'].some(k=>row.dataset[k]==='1');};
 const safe=(value,depth=0)=>{if(depth>8)return '[begrenzt]';if(Array.isArray(value))return value.slice(0,1000).map(x=>safe(x,depth+1));if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).slice(0,100).map(([k,v])=>[k,/password|passwd|secret|token|authorization|cookie|api.?key|oauth.?code/i.test(k)?'[entfernt]':safe(v,depth+1)]));if(typeof value==='string')return value.replace(/(Bearer\s+)[^\s,;]+/gi,'$1[entfernt]').replace(/((?:password|client_secret|access_token|refresh_token|api_key|code)\s*[=:]\s*)[^\s&,;]+/gi,'$1[entfernt]').slice(0,2000);return value;};window.pzSanitize=safe;
 const ring=[];
 const MAX=400;
 const record=(type,data={})=>{
  ring.push({at:new Date().toISOString(),type,...safe(data)});
  if(ring.length>MAX)ring.splice(0,ring.length-MAX);
 };
 window.pzDiagnostics={record,events:ring};

 // Keep the native observer API intact for browser integrations.

 const nativeFetch=window.fetch.bind(window);
 window.fetch=(input,init={})=>{
  const url=typeof input==='string'?input:input?.url||'';
  const started=performance.now();
  const path=(()=>{try{return new URL(url,location.href).pathname;}catch(_){return String(url).split('?')[0];}})();
  return nativeFetch(input,init).then(response=>{
   const duration=Math.round(performance.now()-started);
   if(path.startsWith('/api/')&&(duration>=120||!response.ok))record('api',{path,status:response.status,duration_ms:duration,server_timing:response.headers.get('Server-Timing')||''});
   return response;
  },error=>{
   const duration=Math.round(performance.now()-started);
   if(path.startsWith('/api/'))record('api-error',{path,duration_ms:duration,error:String(error?.message||error)});
   throw error;
  });
 };

 window.addEventListener('error',event=>record('javascript-error',{message:String(event.message||'Unbekannter Fehler'),source:String(event.filename||''),line:event.lineno||0,column:event.colno||0}));
 window.addEventListener('unhandledrejection',event=>record('unhandled-rejection',{message:String(event.reason?.message||event.reason||'Unbekannter Fehler')}));
 document.addEventListener('click',event=>{
  const nav=event.target.closest('.sidebar [data-view],.sidebar [data-pz-nav-target],.sidebar [data-admin-open]');
  if(nav)record('navigation',{target:nav.dataset.view||nav.dataset.pzNavTarget||nav.dataset.adminOpen||''});
 },true);
 try{
  if('PerformanceObserver' in window&&PerformanceObserver.supportedEntryTypes?.includes('longtask')){
   const observer=new PerformanceObserver(list=>{for(const item of list.getEntries())record('long-task',{duration_ms:Math.round(item.duration),start_ms:Math.round(item.startTime)});});
   observer.observe({type:'longtask',buffered:true});
  }
 }catch(_){}
})();
