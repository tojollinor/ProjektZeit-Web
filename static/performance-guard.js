(()=>{
 if(window.__pzPerformanceGuard)return;
 window.__pzPerformanceGuard=true;
 const ring=[];
 const MAX=400;
 const record=(type,data={})=>{
  ring.push({at:new Date().toISOString(),type,...data});
  if(ring.length>MAX)ring.splice(0,ring.length-MAX);
 };
 window.pzDiagnostics={record,events:ring};

 const NativeObserver=window.MutationObserver;
 if(NativeObserver){
  class PzMutationObserver{
   constructor(callback){
    this.callback=callback;this.pending=[];this.timer=null;this.global=false;
    this.native=new NativeObserver(records=>{
     if(!this.global)return this.invoke(records);
     this.pending.push(...records.slice(-80));
     if(this.pending.length>160)this.pending.splice(0,this.pending.length-160);
     if(this.timer)return;
     this.timer=setTimeout(()=>{const batch=this.pending.splice(0);this.timer=null;this.invoke(batch);},70);
    });
   }
   invoke(records){
    const start=performance.now();
    try{return this.callback(records,this);}finally{
     const duration=performance.now()-start;
     if(duration>20)record('slow-mutation-callback',{duration_ms:Math.round(duration),records:records.length,global:this.global});
    }
   }
   observe(target,options){this.global=target===document.body&&!!options?.childList&&!!options?.subtree;return this.native.observe(target,options);}
   disconnect(){if(this.timer){clearTimeout(this.timer);this.timer=null;}this.pending.length=0;return this.native.disconnect();}
   takeRecords(){return this.pending.splice(0).concat(this.native.takeRecords());}
  }
  window.MutationObserver=PzMutationObserver;
 }

 const nativeSetInterval=window.setInterval.bind(window);
 window.setInterval=(fn,delay,...args)=>{
  const stack=String(new Error().stack||''),source=String(fn||'');
  if(Number(delay)===1400&&(/next-batch-ui\.js/i.test(stack)||/cleanCustomerRows|providerSettingsStatus|refineLogs/.test(source))){
   record('legacy-poller-suppressed',{source:'next-batch-ui.js',interval_ms:1400});
   return 0;
  }
  return nativeSetInterval(fn,delay,...args);
 };

 const nativeFetch=window.fetch.bind(window);
 window.fetch=(input,init={})=>{
  const url=typeof input==='string'?input:input?.url||'';
  const started=performance.now();
  const path=(()=>{try{return new URL(url,location.href).pathname;}catch(_){return String(url).split('?')[0];}})();
  return nativeFetch(input,init).then(response=>{
   const duration=Math.round(performance.now()-started);
   if(path.startsWith('/api/')&&(duration>=120||!response.ok))record('api',{path,status:response.status,duration_ms:duration});
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
