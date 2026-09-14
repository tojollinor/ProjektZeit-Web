(()=>{
 const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
 const h=v=>typeof esc==='function'?esc(v):String(v??'');
 const title=q('#page-title');
 const sidebar=q('.sidebar');
 const main=q('main');
 const nav=q('.sidebar nav');
 if(!nav||!main)return;

 const pageTitles={
  'settings-profile':'Persönliches Profil','settings-connections':'Verbindungen','settings-client':'Windows-Client',
  'settings-data':'Import & Export','settings-api':'API','statistics':'Statistiken','workshop-status':'Werkstatt'
 };

 function closeMenu(){sidebar?.classList.remove('open');q('.sidebar-scrim')?.classList.remove('open');}
 function currentView(){return q('.view.active-view')?.id?.replace(/^view-/,'')||'';}
 function createView(name){let section=q(`#view-${name}`);if(section)return section;section=document.createElement('section');section.id=`view-${name}`;section.className='view pz-split-view';main.insertBefore(section,q('#toast'));return section;}
 function makeSub(label,target,titleText=label){const b=document.createElement('button');b.type='button';b.className='pz-subnav';b.dataset.pzNavTarget=target;b.dataset.pzNavTitle=titleText;b.textContent=label;return b;}
 function makeGroup(button,kind){
  const group=document.createElement('div');group.className='pz-nav-group';group.dataset.pzNavGroup=kind;
  button.before(group);group.append(button);button.classList.add('pz-nav-toggle');button.setAttribute('aria-expanded','false');button.removeAttribute('data-view');
  const submenu=document.createElement('div');submenu.className='pz-nav-submenu';submenu.hidden=true;group.append(submenu);return {group,button,submenu};
 }
 function setGroup(group,open){if(!group)return;const submenu=q('.pz-nav-submenu,.admin-nav-submenu',group),toggle=q('.pz-nav-toggle,.admin-nav-toggle',group);if(!submenu||!toggle)return;submenu.hidden=!open;toggle.setAttribute('aria-expanded',String(open));}

 window.pzOpenNavTarget=(name,label='')=>{
  const section=q(`#view-${name}`);if(!section)return;
  if(typeof showView==='function')showView(name);else{qa('.view').forEach(v=>v.classList.remove('active-view'));section.classList.add('active-view');closeMenu();}
  if(title)title.textContent=label||pageTitles[name]||'ProjektZeit';
  if(name==='settings-profile')window.pzLoadAccount?.();
  if(name==='settings-connections'){
   try{typeof loadIntegrations==='function'&&loadIntegrations();}catch(_){}
   setTimeout(fixStarfaceStatus,80);
  }
  if(name==='statistics')renderStatistics();
  if(name==='workshop-status')renderWorkshopStatus();
  closeMenu();setTimeout(window.pzSyncNavigation,0);
 };

 let previousNavView=null;
 window.pzSyncNavigation=()=>{
  const active=currentView();
  const changed=previousNavView!==active;previousNavView=active;
  const admin=q('.admin-nav-group');if(admin&&changed)setGroup(admin,active==='admin-options');
  const bookkeeping=q('[data-pz-nav-group=bookkeeping]');if(bookkeeping&&changed)setGroup(bookkeeping,['bookkeeping','absence-approvals','employee-billing'].includes(active));
  const settings=q('[data-pz-nav-group="settings"]');if(settings&&changed)setGroup(settings,active.startsWith('settings-'));
  const workshop=q('[data-pz-nav-group="workshop"]');if(workshop&&changed)setGroup(workshop,active.startsWith('workshop-'));
  qa('[data-pz-nav-target]').forEach(b=>b.classList.toggle('active',b.dataset.pzNavTarget===active));
  if(active==='admin-options'){
   qa('.admin-subnav[data-admin-open]').forEach(b=>b.classList.toggle('active',Boolean(q(`[data-admin-tab="${b.dataset.adminOpen}"]`)?.classList.contains('primary'))));
  }
 };

 function setupBookkeeping(){const button=q('[data-view="bookkeeping"]',nav)||q('[data-pz-nav-group="bookkeeping"] .pz-nav-toggle',nav);if(!button)return;let submenu=q('[data-pz-nav-group="bookkeeping"] .pz-nav-submenu');if(!submenu){const open=button.onclick;({submenu}=makeGroup(button,'bookkeeping'));button.dataset.bookkeepingToggle='';const overview=makeSub('Projektabrechnung','bookkeeping');overview.onclick=open;submenu.append(overview);button.onclick=e=>{e.stopPropagation();setGroup(button.parentElement,button.getAttribute('aria-expanded')!=='true');};}for(const name of ['employee-billing','absence-approvals']){const child=q('[data-company-nav="'+name+'"]');if(child){child.className='pz-subnav';if(child.parentElement!==submenu)submenu.append(child);}}}
 document.addEventListener('pz-company-ready',()=>{setupBookkeeping();previousNavView=null;window.pzSyncNavigation();});
 function setupSettings(){
  if(q('[data-pz-nav-group="settings"]'))return true;
  const button=q('[data-view="settings"]',nav);if(!button)return false;
  const {submenu}=makeGroup(button,'settings');
  button.innerHTML='<span>⚙</span>Einstellungen';
  submenu.append(makeSub('Persönliches Profil','settings-profile'),makeSub('Verbindungen','settings-connections'),makeSub('Downloads','settings-client'),makeSub('Import & Export','settings-data'),makeSub('API','settings-api'));
  for(const name of ['settings-profile','settings-connections','settings-client','settings-data','settings-api'])createView(name);
  moveSettingsContent();return true;
 }
 function moveSettingsContent(){
  const source=q('#view-settings');if(!source)return;
  const move=(node,target)=>{const parent=q(target);if(node&&parent&&node.parentElement!==parent)parent.append(node);};
  const profile=q('[data-profile-settings]');move(profile,'#view-settings-profile');
  const intro=q('.settings-intro',source),cards=q('#integration-cards');move(intro,'#view-settings-connections');move(cards,'#view-settings-connections');
  const win=qa('article.panel',source).find(x=>/Windows-Client/i.test(x.textContent||''));move(win,'#view-settings-client');
  for(const block of qa('[data-import-export]'))move(block,'#view-settings-data');
  for(const block of qa('[data-user-api-settings]'))move(block,'#view-settings-api');
  for(const [name,label,copy] of [
   ['settings-profile','Persönliches Profil','Profil, Darstellung sowie Geräte und Sitzungen.'],
   ['settings-connections','Verbindungen','Zammad, STARFACE und TeamViewer konfigurieren und prüfen.'],
   ['settings-client','Downloads','Lokalen ProjektZeit-Client herunterladen und verwenden.'],
   ['settings-data','Import & Export','Zeiterfassungsdaten importieren und exportieren.'],
   ['settings-api','API','Persönliche API-Zugänge und Automationen verwalten.']]){
    const sec=q(`#view-${name}`);if(sec&&!q(':scope > .pz-page-intro',sec)){const head=document.createElement('div');head.className='settings-intro pz-page-intro';head.innerHTML=`<p class="eyebrow">EINSTELLUNGEN</p><h3>${h(label)}</h3><p class="muted">${h(copy)}</p>`;sec.prepend(head);}
  }
 }

 function setupWorkshop(){
  if(q('[data-pz-nav-group="workshop"]'))return;
  const settings=q('[data-pz-nav-group="settings"]');const button=document.createElement('button');button.type='button';button.className='nav';button.innerHTML='<span>⌁</span>Werkstatt';
  if(settings)nav.insertBefore(button,settings);else nav.append(button);
  const {submenu}=makeGroup(button,'workshop');
  submenu.append(makeSub('Status','workshop-status','Werkstatt'));
  const reload=document.createElement('button');reload.type='button';reload.className='pz-subnav';reload.dataset.pzHardReload='';reload.textContent='Hard Reload';submenu.append(reload);
  createView('workshop-status');
 }
 function renderWorkshopStatus(){
  const sec=q('#view-workshop-status');if(!sec)return;const version=q('meta[name="pz-frontend-version"]')?.content||'unbekannt';
  sec.innerHTML=`<div class="settings-intro"><p class="eyebrow">WERKSTATT</p><h3>Frontend & Diagnose</h3><p class="muted">Kleine Werkzeuge für die laufende Oberfläche.</p></div><div class="stats pz-tool-stats"><article><span>Frontend-Version</span><strong>${h(version.slice(0,12))}</strong><small>${h(version)}</small></article><article><span>Browserstatus</span><strong>${navigator.onLine?'Online':'Offline'}</strong><small>${h(navigator.userAgent.split(' ').slice(-2).join(' '))}</small></article></div><article class="panel"><div class="panel-head"><div><p class="eyebrow">CACHE</p><h3>Seite vollständig neu laden</h3></div></div><p class="muted">Lädt die Anwendung inklusive aktueller Frontend-Dateien neu.</p><button type="button" class="primary" data-pz-hard-reload>Hard Reload</button></article>`;
 }

 function setupStatistics(){
  if(q('[data-pz-nav-target="statistics"]',nav))return;
  const button=document.createElement('button');button.type='button';button.className='nav';button.dataset.pzNavTarget='statistics';button.dataset.pzNavTitle='Statistiken';button.innerHTML='<span>▥</span>Statistiken';
  const settings=q('[data-pz-nav-group="settings"]');nav.insertBefore(button,settings||null);const sec=createView('statistics');
  sec.innerHTML=`<div class="settings-intro"><p class="eyebrow">AUSWERTUNG</p><h3>Statistiken</h3><p class="muted">Arbeits- und Projektzeiten aus den vorhandenen ProjektZeit-Daten.</p></div><div class="pz-stat-toolbar"><label>Zeitraum<select data-stat-days><option value="7">7 Tage</option><option value="30" selected>30 Tage</option><option value="90">90 Tage</option><option value="365">1 Jahr</option></select></label><button class="secondary" type="button" data-stat-refresh>Aktualisieren</button></div><div data-stat-content></div>`;
  q('[data-stat-days]',sec).onchange=renderStatistics;q('[data-stat-refresh]',sec).onclick=async()=>{try{typeof refresh==='function'&&await refresh();}catch(_){}renderStatistics();};
 }
 function fmtHours(seconds){return `${(seconds/3600).toLocaleString('de-DE',{minimumFractionDigits:1,maximumFractionDigits:1})} h`;}
 function colorIndex(name){let n=0;for(const c of String(name||''))n=(n+c.charCodeAt(0))%6;return n;}
 function barRows(map,limit=7){const rows=[...map.entries()].sort((a,b)=>b[1]-a[1]).slice(0,limit),max=Math.max(1,...rows.map(x=>x[1]));return rows.map(([name,value])=>`<div class="pz-stat-bar-row"><div><strong>${h(name||'Ohne Zuordnung')}</strong><span>${fmtHours(value)}</span></div><div class="pz-stat-bar"><i class="c${colorIndex(name)}" style="width:${Math.max(2,value/max*100)}%"></i></div></div>`).join('')||'<p class="muted">Für diesen Zeitraum liegen noch keine Daten vor.</p>';}
 function lineChart(days,values){
  const w=Math.max(320,Math.round(q('#view-statistics')?.clientWidth||1000)-48),hg=220,p=28,max=Math.max(1,...values),step=(w-p*2)/Math.max(1,days.length-1),points=values.map((v,i)=>`${p+i*step},${hg-p-(v/max)*(hg-p*2)}`).join(' ');
  const labels=days.map((d,i)=>i%Math.max(1,Math.ceil(days.length/Math.max(3,Math.floor(w/100))))===0?`<text x="${p+i*step}" y="${hg-5}" text-anchor="middle">${d.slice(5).split('-').reverse().join('.')}</text>`:'').join('');
  return `<div class="pz-line-chart"><svg viewBox="0 0 ${w} ${hg}" role="img" aria-label="Projektzeit im Zeitverlauf"><line x1="${p}" y1="${hg-p}" x2="${w-p}" y2="${hg-p}" class="axis"/><polyline points="${points}" class="line"/>${values.map((v,i)=>`<circle cx="${p+i*step}" cy="${hg-p-(v/max)*(hg-p*2)}" r="4"><title>${days[i]} · ${fmtHours(v)}</title></circle>`).join('')}${labels}</svg></div>`;
 }
 let statisticsGeneration=0;
 async function renderStatistics(){
  const sec=q('#view-statistics'),host=q('[data-stat-content]',sec);if(!sec||!host)return;const entries=(typeof state!=='undefined'&&state.data?.entries)||[],daysCount=Number(q('[data-stat-days]',sec)?.value||30),now=new Date(),start=new Date(now);start.setHours(0,0,0,0);start.setDate(start.getDate()-daysCount+1);
  const dayKeys=[];for(let i=0;i<daysCount;i++){const d=new Date(start);d.setDate(start.getDate()+i);dayKeys.push(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`);}
  const version=++statisticsGeneration;host.innerHTML='<p class="pz-loading-line">Statistiken werden geladen …</p>';
  let report;try{report=await post('/api/v1/time-workspace/statistics',{day:dayKeys[0],days:daysCount});}catch(e){if(version===statisticsGeneration)host.innerHTML=`<p class="error">${h(e.message)}</p>`;return;}if(version!==statisticsGeneration)return;
  const perDay=new Map(report.per_day),projects=new Map(report.projects),customers=new Map(report.customers),weekdays=new Map(report.weekdays),total=report.total,count=report.count;
  const activeDays=[...perDay.values()].filter(Boolean).length,topProject=[...projects.entries()].sort((a,b)=>b[1]-a[1])[0]?.[0]||'–';
  host.innerHTML=`<div class="stats pz-stat-kpis"><article><span>Erfasste Zeit</span><strong>${fmtHours(total)}</strong><small>${daysCount} Tage</small></article><article><span>Ø je Arbeitstag</span><strong>${activeDays?fmtHours(total/activeDays):'0,0 h'}</strong><small>${activeDays} aktive Tage</small></article><article><span>Stempelungen</span><strong>${count}</strong><small>im Zeitraum</small></article><article><span>Top-Projekt</span><strong>${h(topProject)}</strong><small>${projects.has(topProject)?fmtHours(projects.get(topProject)):'keine Daten'}</small></article></div><div class="pz-stat-grid"><article class="panel pz-stat-wide"><div class="panel-head"><div><p class="eyebrow">VERLAUF</p><h3>Projektzeit nach Tag</h3></div></div>${lineChart(dayKeys,[...perDay.values()])}</article><article class="panel"><div class="panel-head"><div><p class="eyebrow">PROJEKTE</p><h3>Zeit nach Projekt</h3></div></div>${barRows(projects)}</article><article class="panel"><div class="panel-head"><div><p class="eyebrow">KUNDEN</p><h3>Zeit nach Kunde</h3></div></div>${barRows(customers)}</article><article class="panel pz-stat-wide"><div class="panel-head"><div><p class="eyebrow">WOCHENRHYTHMUS</p><h3>Verteilung nach Wochentag</h3></div></div><div class="pz-week-bars">${[...weekdays.entries()].map(([name,value])=>{const max=Math.max(1,...weekdays.values());return `<div><span>${name}</span><i style="height:${Math.max(3,value/max*100)}%" class="c${colorIndex(name)}"></i><small>${fmtHours(value)}</small></div>`;}).join('')}</div></article></div>`;
 }

 function fixStarfaceStatus(){
  const card=q('#integration-cards [data-provider="starface"]');if(!card)return;const missing=q('.missing-secret',card),badge=q('.badge',card),connect=q('[data-pz-starface-connect]',card);if(missing&&/kein client-secret/i.test(missing.textContent||'')){if(badge){if(badge.textContent!=='Nicht eingerichtet')badge.textContent='Nicht eingerichtet';badge.dataset.connectionState='not-configured';}for(const button of qa('button',card)){button.disabled=true;button.title='Client-Secret fehlt. Bitte einen Administrator informieren.';button.style.cursor='not-allowed';}}
 }

 setupSettings();setupWorkshop();setupStatistics();moveSettingsContent();fixStarfaceStatus();window.pzSyncNavigation();
 let attempts=0;const settle=setInterval(()=>{attempts++;setupSettings();setupWorkshop();setupStatistics();moveSettingsContent();fixStarfaceStatus();window.pzSyncNavigation();if(attempts>=20)clearInterval(settle);},150);
 const cards=q('#integration-cards');if(cards){let pending=false;new MutationObserver(()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;fixStarfaceStatus();});}).observe(cards,{childList:true,subtree:true});}
 document.addEventListener('click',e=>{if(e.target.closest('[data-admin-tab]'))setTimeout(window.pzSyncNavigation,20);});
})();
