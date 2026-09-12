(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const notify=(m,l='info',t=4200)=>window.pzToast?window.pzToast(m,l,t):typeof toast==='function'?toast(m):null;
 let current='',loaded=false,loading=null;
 function initial(){return ((typeof state!=='undefined'&&state.user?.username)||q('#username')?.textContent||'?').trim().charAt(0).toUpperCase()||'?';}
 function paint(el,image){
  if(!el)return;
  if(image){el.textContent='';el.style.backgroundImage=`url(${JSON.stringify(image).slice(1,-1)})`;el.style.backgroundSize='cover';el.style.backgroundPosition='center';el.classList.add('has-profile-image');}
  else{el.style.backgroundImage='';el.classList.remove('has-profile-image');el.textContent=initial();}
 }
 function sync(){paint(q('#avatar'),current);qa('[data-pz-profile-avatar]').forEach(el=>paint(el,current));q('[data-profile-image-panel]')?.remove();}
 function apply(image){current=image||'';loaded=true;sync();}
 async function load(force=false){if(typeof post!=='function')return;if(loading&&!force)return loading;if(loaded&&!force){sync();return current;}loading=(async()=>{try{const d=await post('/api/v1/profile/avatar',{action:'get'});apply(d.image||'');return current;}catch(_){sync();return current;}finally{loading=null;}})();return loading;}
 function imageData(file){return new Promise((resolve,reject)=>{if(!file||!/^image\/(png|jpeg|webp)$/.test(file.type)){reject(new Error('Bitte PNG, JPEG oder WebP auswählen.'));return;}const img=new Image(),url=URL.createObjectURL(file);img.onload=()=>{try{const max=320,scale=Math.min(1,max/Math.max(img.width,img.height)),w=Math.max(1,Math.round(img.width*scale)),h=Math.max(1,Math.round(img.height*scale)),canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;canvas.getContext('2d').drawImage(img,0,0,w,h);URL.revokeObjectURL(url);resolve(canvas.toDataURL('image/jpeg',.82));}catch(e){URL.revokeObjectURL(url);reject(e);}};img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('Bild konnte nicht gelesen werden.'));};img.src=url;});}

 const dialog=document.createElement('dialog');dialog.className='pz-avatar-dialog';dialog.innerHTML=`<div class="pz-avatar-dialog-card"><div class="panel-head"><div><p class="eyebrow">PROFILBILD</p><h3>Profilbild bearbeiten</h3></div></div><p class="muted">PNG, JPEG oder WebP. Das Bild wird vor dem Speichern automatisch verkleinert.</p><input type="file" accept="image/png,image/jpeg,image/webp" hidden data-pz-avatar-file><div class="pz-avatar-dialog-actions"><button type="button" class="primary" data-pz-avatar-upload>Profilbild hochladen</button><button type="button" class="danger-button" data-pz-avatar-remove>Profilbild löschen</button><button type="button" class="secondary subtle" data-pz-avatar-cancel>Abbrechen</button></div><p class="integration-status" data-pz-avatar-status></p></div>`;document.body.append(dialog);
 const file=q('[data-pz-avatar-file]',dialog),status=q('[data-pz-avatar-status]',dialog),remove=q('[data-pz-avatar-remove]',dialog);
 function open(){status.textContent='';remove.disabled=!current;dialog.showModal();}
 q('[data-pz-avatar-cancel]',dialog).onclick=()=>dialog.close();q('[data-pz-avatar-upload]',dialog).onclick=()=>file.click();
 file.onchange=async()=>{try{status.textContent='Bild wird verarbeitet …';const image=await imageData(file.files?.[0]);status.textContent='Bild wird gespeichert …';const d=await post('/api/v1/profile/avatar',{action:'save',image});apply(d.image||image);status.textContent='Profilbild gespeichert.';notify('Profilbild gespeichert','success');setTimeout(()=>dialog.close(),350);}catch(e){status.textContent=e.message;notify(e.message,'error');}finally{file.value='';}};
 remove.onclick=async()=>{if(!current){dialog.close();return;}try{remove.disabled=true;status.textContent='Profilbild wird gelöscht …';await post('/api/v1/profile/avatar',{action:'remove'});apply('');status.textContent='Profilbild gelöscht.';notify('Profilbild gelöscht','success');setTimeout(()=>dialog.close(),300);}catch(e){status.textContent=e.message;notify(e.message,'error');}finally{remove.disabled=!current;}};
 document.addEventListener('click',e=>{if(e.target.closest('[data-pz-profile-avatar-edit],[data-pz-profile-avatar-button]')){e.preventDefault();open();}if(e.target.closest('[data-pz-nav-target="settings-profile"]'))setTimeout(()=>{sync();load();},50);});
 window.pzProfileAvatar={load,apply,sync,open,get current(){return current;}};
 let tries=0;const timer=setInterval(()=>{tries++;sync();if(typeof state!=='undefined'&&state.user){load();if(tries>20)clearInterval(timer);}else if(tries>100)clearInterval(timer);},150);
})();
