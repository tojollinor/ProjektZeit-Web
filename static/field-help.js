(()=>{
 function attach(label,text){
  if(!label||!text||label.dataset.helpReady)return;label.dataset.helpReady='1';
  const button=document.createElement('button');button.type='button';button.className='field-help-button';button.textContent='?';button.setAttribute('aria-label','Hilfe: '+label.textContent.trim());
  button.onclick=e=>{e.preventDefault();e.stopPropagation();window.pzUI.message('Hilfe',text);};
  const control=[...label.children].find(child=>child.matches?.('input,select,textarea'));
  if(control?.matches('input[type="checkbox"],input[type="radio"]')){
   label.classList.add('field-help-checkbox');label.append(button);return;
  }
  const line=document.createElement('span');line.className='field-label-line';
  if(control){for(const node of [...label.childNodes]){if(node===control)break;line.append(node);}label.insertBefore(line,control);}
  else{while(label.firstChild)line.append(label.firstChild);label.append(line);}
  line.append(button);label.classList.add('field-help-label');
 }
 window.pzHelp={attach};
})();
