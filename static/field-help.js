(()=>{
 let nextId=0;
 function attach(label,text){
  if(!label||!text||label.dataset.helpReady)return;label.dataset.helpReady='1';
  const wrapper=document.createElement('div');wrapper.className='field-with-help';label.replaceWith(wrapper);wrapper.append(label);
  const button=document.createElement('button');button.type='button';button.className='field-help-button';button.textContent='?';button.setAttribute('aria-label','Hilfe: '+label.textContent.trim());
  const tip=document.createElement('span');tip.id='field-help-'+(++nextId);tip.className='field-help-text';tip.setAttribute('role','tooltip');tip.textContent=text;tip.hidden=true;button.setAttribute('aria-describedby',tip.id);label.querySelector('input,select')?.setAttribute('aria-describedby',tip.id);
  const show=()=>tip.hidden=false,hide=()=>tip.hidden=true;wrapper.onpointerenter=show;wrapper.onpointerleave=()=>{if(!wrapper.contains(document.activeElement))hide();};wrapper.onfocusin=show;wrapper.onfocusout=e=>{if(!wrapper.contains(e.relatedTarget))hide();};button.onclick=e=>{e.preventDefault();e.stopPropagation();window.pzUI.message('Hilfe',text);};wrapper.onkeydown=e=>{if(e.key==='Escape'){hide();e.stopPropagation();}};wrapper.append(button,tip);
 }
 window.pzHelp={attach};
})();
