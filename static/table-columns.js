/* Shared, local per-user table preferences; editing never fetches provider data. */
(()=>{
 const clamp=value=>Math.max(80,Math.min(720,Number(value)||160));
 function create(section,provider,onChange){
  let schema=[],preference=null;
  const storageKey=()=>`pz-table-v1:${state.user?.id||'anonymous'}:${provider}`;
  function read(){if(preference)return;try{preference=JSON.parse(localStorage.getItem(storageKey()))||{};}catch(_){preference={};}}
  function write(){try{localStorage.setItem(storageKey(),JSON.stringify(preference));}catch(_){}onChange();}
  function all(){read();const known=new Map(schema.map(c=>[c.key,c]));const order=[...new Set([...(Array.isArray(preference.order)?preference.order:[]),...known.keys()])];return order.filter(k=>known.has(k)).map(key=>({...known.get(key),width:clamp(preference.widths?.[key]??known.get(key).width),visible:preference.visible?.[key]??known.get(key).default!==false}));}
  function visible(){const list=all();return list.filter(c=>c.visible).length?list.filter(c=>c.visible):list.slice(0,1);}
  function setWidth(key,width){read();preference.widths={...preference.widths,[key]:clamp(width)};write();}
  function open(){
   const d=document.createElement('dialog');d.className='ui-dialog table-column-dialog';d.setAttribute('aria-label','Tabellenspalten bearbeiten');
   d.innerHTML='<div class="panel-head"><h3>Spalten bearbeiten</h3><button type="button" class="secondary" data-close>Schließen</button></div><p>Spalten einblenden, ausblenden, verschieben und ihre Breite ändern. Gilt für dieses Benutzerkonto auf diesem Gerät.</p><div data-columns></div><button type="button" class="secondary" data-reset>Standard wiederherstellen</button>';
   document.body.append(d);d.querySelector('[data-close]').onclick=()=>d.close();d.addEventListener('close',()=>d.remove(),{once:true});
   function draw(){const host=d.querySelector('[data-columns]');host.replaceChildren();const list=all();list.forEach((column,index)=>{
    const row=document.createElement('div');row.className='table-column-editor-row';const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=!!column.visible;label.append(check,document.createTextNode(column.label));
    check.onchange=()=>{if(!check.checked&&visible().length===1){check.checked=true;return;}preference.visible={...preference.visible,[column.key]:check.checked};write();};
    const widthLabel=document.createElement('label');widthLabel.textContent='Breite (px)';const width=document.createElement('input');width.type='number';width.min='80';width.max='720';width.step='10';width.value=column.width;width.setAttribute('aria-label','Breite: '+column.label);width.onchange=()=>{setWidth(column.key,width.value);width.value=clamp(width.value);};widthLabel.append(width);row.append(label,widthLabel);
    const actions=document.createElement('div');actions.className='panel-actions';for(const [offset,text] of [[-1,'↑'],[1,'↓']]){const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent=text;button.setAttribute('aria-label',column.label+(offset<0?' nach oben':' nach unten'));button.disabled=index+offset<0||index+offset>=list.length;button.onclick=()=>{const order=list.map(c=>c.key);[order[index],order[index+offset]]=[order[index+offset],order[index]];preference.order=order;write();draw();};actions.append(button);}row.append(actions);host.append(row);
   });}
   d.querySelector('[data-reset]').onclick=()=>{preference={};write();draw();};draw();d.showModal();
  }
  const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent='Spalten';button.onclick=open;section.querySelector('.provider-toolbar').append(button);
  function headerResize(th,column){
   th.style.width=column.width+'px';const handle=document.createElement('span');handle.className='table-column-resize';handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');handle.setAttribute('aria-label','Spaltenbreite: '+column.label);handle.setAttribute('aria-valuemin','80');handle.setAttribute('aria-valuemax','720');handle.setAttribute('aria-valuenow',column.width);
   handle.onkeydown=e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();setWidth(column.key,column.width+(e.key==='ArrowLeft'?-10:10));};
   handle.onpointerdown=e=>{e.preventDefault();e.stopPropagation();handle.setPointerCapture(e.pointerId);const start=e.clientX,original=column.width;let next=original;handle.onpointermove=move=>{next=clamp(original+move.clientX-start);th.style.width=next+'px';const col=section.querySelector('col[data-column-key="'+CSS.escape(column.key)+'"]');if(col)col.style.width=next+'px';};handle.onpointerup=()=>{handle.onpointermove=null;setWidth(column.key,next);};handle.onpointercancel=()=>{handle.onpointermove=null;onChange();};};th.append(handle);
  }
  return {update:columns=>{schema=columns;},visible,headerResize};
 }
 window.pzTableColumns={create};
})();
