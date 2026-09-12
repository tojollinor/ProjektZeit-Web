(()=>{
 const nativeFetch=window.fetch.bind(window),DEFAULT_TIMEOUT=30000;
 window.fetch=(input,init={})=>{
  const url=typeof input==='string'?input:input?.url||'';
  const sameApi=typeof url==='string'&&(url.startsWith('/api/')||url.startsWith(location.origin+'/api/'));
  if(!sameApi||init.signal)return nativeFetch(input,init);
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort('timeout'),DEFAULT_TIMEOUT);
  return nativeFetch(input,{...init,signal:controller.signal}).catch(error=>{
    if(controller.signal.aborted)throw new Error('Die Anfrage hat zu lange gedauert. Bitte erneut versuchen.');
    throw error;
  }).finally(()=>clearTimeout(timer));
 };
})();
