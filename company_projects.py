"""Project grouping, repeatable projects and immutable billing descriptions."""
import json
from collections import defaultdict
from datetime import date,timedelta
import staff_time as st
import time_workspace as tw

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS project_tags(id INTEGER PRIMARY KEY,owner_id INTEGER NOT NULL,customer_id INTEGER NOT NULL DEFAULT 0,name VARCHAR(120) NOT NULL,active INTEGER NOT NULL DEFAULT 1,UNIQUE(owner_id,customer_id,name));
    CREATE TABLE IF NOT EXISTS project_tag_links(project_id INTEGER NOT NULL,tag_id INTEGER NOT NULL,PRIMARY KEY(project_id,tag_id));
    CREATE TABLE IF NOT EXISTS project_origins(project_id INTEGER PRIMARY KEY,template_id INTEGER NOT NULL,created_at VARCHAR(40) NOT NULL);
    CREATE TABLE IF NOT EXISTS category_locations(category_id INTEGER PRIMARY KEY,location VARCHAR(12) NOT NULL);
    CREATE TABLE IF NOT EXISTS event_work_context(owner_id INTEGER NOT NULL,source VARCHAR(32) NOT NULL,source_key VARCHAR(255) NOT NULL,location VARCHAR(12) NOT NULL,emergency INTEGER NOT NULL,updated_at VARCHAR(40) NOT NULL,PRIMARY KEY(owner_id,source,source_key));
    CREATE TABLE IF NOT EXISTS billing_descriptions(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL,service_day VARCHAR(10) NOT NULL,employee_id INTEGER NOT NULL,employee_name VARCHAR(255) NOT NULL,bullets LONGTEXT NOT NULL,seconds INTEGER NOT NULL,emergency INTEGER NOT NULL,revision INTEGER NOT NULL,created_by INTEGER NOT NULL,created_at VARCHAR(40) NOT NULL,invoice_reference VARCHAR(120) NOT NULL DEFAULT '',UNIQUE(project_id,service_day,employee_id,revision));
    ''')

def project(c,uid,pid):
    r=c.execute('SELECT * FROM projects WHERE id=? AND owner_id=? AND is_system=0',(int(pid),uid)).fetchone()
    if not r:raise PermissionError('Projekt nicht zugänglich.')
    return dict(r)

def tags(c,uid,body):
    st.require(c,uid,'projects.manage_templates');ident=int(body.get('id') or 0);cid=int(body.get('customer_id') or 0);name=str(body.get('name') or '').strip()
    if cid and not c.execute('SELECT 1 FROM customers WHERE owner_id=? AND id=?',(uid,cid)).fetchone():raise PermissionError('Kunde nicht zugänglich.')
    if not name or len(name)>120:raise ValueError('Tagname mit maximal 120 Zeichen angeben.')
    if ident:
        r=c.execute('SELECT * FROM project_tags WHERE id=? AND owner_id=?',(ident,uid)).fetchone()
        if not r:raise PermissionError('Tag nicht zugänglich.')
        if cid!=r['customer_id']:raise ValueError('Kundenzuordnung eines bestehenden Tags bleibt erhalten.')
        c.execute('UPDATE project_tags SET name=?,active=? WHERE id=?',(name,int(body.get('active',True) is True),ident))
    else:ident=c.execute('INSERT INTO project_tags(owner_id,customer_id,name) VALUES(?,?,?)',(uid,cid,name)).lastrowid
    st.audit(c,uid,uid,'tag',ident,'saved',body);return {'ok':True,'id':ident}

def attach(c,uid,body):
    p=project(c,uid,body['project_id']);ids=list(set(int(x) for x in body.get('tags',[])))
    if len(ids)>50:raise ValueError('Höchstens 50 Tags je Projekt.')
    for ident in ids:
        r=c.execute('SELECT * FROM project_tags WHERE id=? AND owner_id=? AND active=1',(ident,uid)).fetchone()
        if not r or r['customer_id'] not in (0,p['customer_id']):raise ValueError('Tag gehört zu einem anderen Kunden oder ist archiviert.')
    c.execute('DELETE FROM project_tag_links WHERE project_id=?',(p['id'],))
    for ident in ids:c.execute('INSERT INTO project_tag_links VALUES(?,?)',(p['id'],ident))
    st.audit(c,uid,uid,'project',p['id'],'tags_changed',ids);return {'ok':True}

def clone(c,uid,body):
    p=project(c,uid,body['project_id']);name=str(body['name']).strip()
    if not name or len(name)>120:raise ValueError('Projektname erforderlich (maximal 120 Zeichen).')
    ident=c.execute("INSERT INTO projects(owner_id,customer_id,name,active,status) VALUES(?,?,?,1,'active')",(uid,p['customer_id'],name)).lastrowid
    c.execute('INSERT INTO project_origins VALUES(?,?,?)',(ident,p['id'],st.iso(st.now())))
    c.execute('INSERT INTO project_tag_links(project_id,tag_id) SELECT ?,tag_id FROM project_tag_links WHERE project_id=?',(ident,p['id']))
    st.audit(c,uid,uid,'project',ident,'created_from_project',{'template':p['id']});return {'ok':True,'project_id':ident}

def tag_merge(c,uid,body):
    st.require(c,uid,'projects.manage_templates');a=int(body['id']);b=int(body['target_id'])
    if a==b:raise ValueError('Verschiedene Tags wählen.')
    rows=list(c.execute('SELECT * FROM project_tags WHERE owner_id=? AND id IN (?,?)',(uid,a,b)))
    if len(rows)!=2 or rows[0]['customer_id']!=rows[1]['customer_id']:raise ValueError('Nur Tags desselben Kundenbereichs zusammenführen.')
    c.execute('INSERT OR IGNORE INTO project_tag_links(project_id,tag_id) SELECT project_id,? FROM project_tag_links WHERE tag_id=?',(b,a))
    c.execute('DELETE FROM project_tag_links WHERE tag_id=?',(a,));c.execute('UPDATE project_tags SET active=0 WHERE id=?',(a,))
    st.audit(c,uid,uid,'tag',a,'merged',{'target':b});return {'ok':True}

def catalog(c,uid,body):
    return {'projects':[dict(r) for r in c.execute('SELECT * FROM projects WHERE owner_id=? AND is_system=0 ORDER BY name',(uid,))],
      'tags':[dict(r) for r in c.execute('SELECT * FROM project_tags WHERE owner_id=? ORDER BY name',(uid,))],
      'links':[dict(r) for r in c.execute('SELECT l.* FROM project_tag_links l JOIN projects p ON p.id=l.project_id WHERE p.owner_id=?',(uid,))],
      'categories':[dict(r) for r in c.execute("SELECT c.id,c.name,COALESCE(l.location,'unknown') location FROM categories c LEFT JOIN category_locations l ON l.category_id=c.id WHERE c.owner_id=?",(uid,))]}

def context_save(c,uid,body):
    source=str(body['source']);key=str(body['key']);location=body['location']
    if location not in ('office','outside','unknown'):raise ValueError('Ort ungültig.')
    if source=='manual':found=c.execute('SELECT 1 FROM entries WHERE owner_id=? AND id=?',(uid,key)).fetchone()
    else:found=c.execute('SELECT 1 FROM provider_events WHERE owner_id=? AND provider=? AND external_key=?',(uid,source,key)).fetchone()
    if not found:raise PermissionError('Leistung nicht zugänglich.')
    c.execute('DELETE FROM event_work_context WHERE owner_id=? AND source=? AND source_key=?',(uid,source,key))
    c.execute('INSERT INTO event_work_context VALUES(?,?,?,?,?,?)',(uid,source,key,location,int(body.get('emergency') is True),st.iso(st.now())))
    st.audit(c,uid,uid,'event_context',source+':'+key,'saved',body);return {'ok':True}

def category_save(c,uid,body):
    st.require(c,uid,'staff.policy');ident=int(body['id']);location=body['location']
    if location not in ('office','outside','unknown') or not c.execute('SELECT 1 FROM categories WHERE id=? AND owner_id=?',(ident,uid)).fetchone():raise ValueError('Zeitkategorie nicht zugänglich oder Ort ungültig.')
    c.execute('DELETE FROM category_locations WHERE category_id=?',(ident,));c.execute('INSERT INTO category_locations VALUES(?,?)',(ident,location))
    st.audit(c,uid,uid,'category',ident,'location_changed',body);return {'ok':True}

def contexts(c,uid):return {(r['source'],r['source_key']):dict(r) for r in c.execute('SELECT * FROM event_work_context WHERE owner_id=?',(uid,))}

def billing_preview(c,uid,body):
    p=project(c,uid,body['project_id']);rows=list(c.execute('SELECT * FROM time_reviews WHERE project_id=? AND owner_id=? AND billable=1 ORDER BY started_at',(p['id'],uid)))
    if c.execute('SELECT 1 FROM entries WHERE project_id=? AND ended_at IS NULL',(p['id'],)).fetchone():raise ValueError('Projekt läuft noch. Zuerst Zeiterfassung beenden.')
    grouped=defaultdict(lambda:{'seconds':0,'emergency':False});ctx=contexts(c,uid)
    current_events={}
    for e in c.execute('SELECT id,project_id,started_at,ended_at FROM entries WHERE owner_id=? AND project_id=? AND is_idle=0',(uid,p['id'])):current_events[('manual',str(e['id']))]={'source':'manual','key':str(e['id']),'project_id':e['project_id'],'start':e['started_at'],'end':e['ended_at'] or ''}
    for e in c.execute('SELECT i.*,a.project_id FROM event_intervals i JOIN provider_assignments a ON a.owner_id=i.owner_id AND a.provider=i.provider AND a.external_key=i.external_key WHERE i.owner_id=? AND a.project_id=?',(uid,p['id'])):current_events[(e['provider'],e['external_key'])]={'source':e['provider'],'key':e['external_key'],'project_id':e['project_id'],'start':e['started_at'],'end':e['ended_at']}
    for r in rows:
        a=st.parse(r['started_at']);b=st.parse(r['ended_at'])
        # Revalidate evidence before handing it to accounting.
        current=current_events.get((r['source'],r['source_key']))
        if not current or tw.fingerprint(current)!=r['fingerprint']:raise ValueError('Leistung wurde seit Freigabe verändert. Erneut prüfen.')
        for d in st.days(a.astimezone(st.TZ).date(),b.astimezone(st.TZ).date()+timedelta(days=1)):
            n=st.overlap_seconds(a,b,st.midnight(d),st.midnight(d+timedelta(days=1)))
            if n:
                group=grouped[str(d)];group['seconds']+=n;group['emergency']|=bool(ctx.get((r['source'],r['source_key']),{}).get('emergency'))
    profile=c.execute('SELECT u.username,p.first_name,p.last_name FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.id=?',(uid,)).fetchone()
    name=((profile['last_name'] or '')+', '+(profile['first_name'] or '')).strip(', ') or profile['username']
    return {'project':p,'groups':[{'service_day':d,'employee_id':uid,'employee_name':name,**v} for d,v in grouped.items()]}

def billing_submit(c,uid,body):
    result=billing_preview(c,uid,body);groups=result['groups'];p=result['project'];notes=body.get('descriptions',{})
    if not groups:raise ValueError('Keine geprüften abrechenbaren Leistungen vorhanden.')
    if p['billing_state']=='billed':raise ValueError('Projekt ist bereits abgerechnet.')
    revision=c.execute('SELECT COALESCE(MAX(revision),0)+1 n FROM billing_descriptions WHERE project_id=?',(p['id'],)).fetchone()['n']
    for g in groups:
        text=str(notes.get(g['service_day']) or '').strip();lines=[x.lstrip('•-* ').strip() for x in text.splitlines() if x.strip()]
        if not lines or len(text)>8000:raise ValueError('Für jeden Leistungstag Stichpunkte angeben (maximal 8000 Zeichen).')
        c.execute('INSERT INTO billing_descriptions(project_id,service_day,employee_id,employee_name,bullets,seconds,emergency,revision,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(p['id'],g['service_day'],uid,g['employee_name'],json.dumps(lines,ensure_ascii=False),g['seconds'],int(g['emergency']),revision,uid,st.iso(st.now())))
    c.execute("UPDATE projects SET status='closed',active=0,billing_state='pending',status_updated_at=? WHERE id=?",(st.iso(st.now()),p['id']))
    st.audit(c,uid,uid,'project',p['id'],'sent_to_billing',{'revision':revision});return {'ok':True}

def billing_list(c,uid,body):
    st.require(c,uid,'bookkeeping.view')
    rows=[dict(r) for r in c.execute('SELECT b.*,p.name project,cu.name customer FROM billing_descriptions b JOIN projects p ON p.id=b.project_id LEFT JOIN customers cu ON cu.id=p.customer_id WHERE b.revision=(SELECT MAX(v.revision) FROM billing_descriptions v WHERE v.project_id=b.project_id) ORDER BY b.service_day DESC,b.id DESC LIMIT 1000')]
    for r in rows:r['text']=f"{date.fromisoformat(r['service_day']).strftime('%d.%m.%Y')} · {r['employee_name']}"+ (' · Notdienst' if r['emergency'] else '')+'\n'+'\n'.join('• '+x for x in json.loads(r['bullets']))
    return {'descriptions':rows}

def statistics(c,uid,body):
    tags=sorted(set(int(x) for x in body.get('tags',[])));projects=catalog(c,uid,{})['projects']
    if tags:
        allowed={r['project_id'] for r in c.execute('SELECT l.project_id FROM project_tag_links l JOIN project_tags t ON t.id=l.tag_id WHERE t.owner_id=? AND t.id IN ('+','.join('?' for _ in tags)+')',(uid,*tags))};projects=[p for p in projects if p['id'] in allowed]
    result=[]
    for p in projects:
        spans=[{'start':r['started_at'],'end':r['ended_at']} for r in c.execute('SELECT started_at,ended_at FROM entries WHERE project_id=? AND owner_id=? AND is_idle=0 AND ended_at IS NOT NULL',(p['id'],uid))]
        result.append({'project_id':p['id'],'name':p['name'],'seconds':tw.union_seconds(spans)})
    return {'projects':result,'total_seconds':sum(r['seconds'] for r in result)}

HANDLERS={'projects/list':catalog,'tags/save':tags,'tags/assign':attach,'tags/merge':tag_merge,'projects/clone':clone,'projects/statistics':statistics,'event/save':context_save,'category/save':category_save,'billing/preview':billing_preview,'billing/submit':billing_submit,'billing/list':billing_list}


def create_assign(c,uid,body):
    st.require(c,uid,'customers.edit');cid=int(body['customer_id']);name=str(body['name']).strip()
    if not name or len(name)>120 or not c.execute('SELECT 1 FROM customers WHERE id=? AND owner_id=?',(cid,uid)).fetchone():raise ValueError('Kunde und Projektname erforderlich.')
    ident=c.execute("INSERT INTO projects(owner_id,customer_id,name,active,status) VALUES(?,?,?,1,'active')",(uid,cid,name)).lastrowid
    result=tw.assign(c,uid,{'project_id':ident,'items':body['items'],'confirm_reassign':body.get('confirm_reassign') is True});result['project_id']=ident;return result


def snapshot_entry(c,uid,ident,category):
    r=c.execute('SELECT location FROM category_locations WHERE category_id=?',(category,)).fetchone()
    location=r['location'] if r else 'unknown'
    c.execute("INSERT OR IGNORE INTO event_work_context VALUES(?,'manual',?,?,0,?)",(uid,str(ident),location,st.iso(st.now())))


def outside(c,uid,body):
    target=int(body.get('user_id') or uid)
    if target!=uid:st.require(c,uid,'staff.view')
    a,b=tw.bounds(body);ctx=contexts(c,target)
    rows=[{'source':'manual','key':str(r['id']),'start':r['started_at'],'end':r['ended_at']} for r in c.execute('SELECT * FROM entries WHERE owner_id=? AND is_idle=0 AND started_at<? AND ended_at>?',(target,st.iso(b),st.iso(a)))]
    rows += [{'source':r['provider'],'key':r['external_key'],'start':r['started_at'],'end':r['ended_at']} for r in c.execute('SELECT * FROM event_intervals WHERE owner_id=? AND started_at<? AND ended_at>?',(target,st.iso(b),st.iso(a)))]
    totals=[]
    for d in st.days(a.date(),b.date()):
        start=st.midnight(d);end=st.midnight(d+timedelta(days=1));spans=[];unknown=0
        for e in rows:
            x=max(start,st.parse(e['start']));y=min(end,st.parse(e['end']))
            if y<=x:continue
            location=ctx.get((e['source'],e['key']),{}).get('location','office' if e['source']=='teamviewer' else 'unknown')
            if location=='outside':spans.append((x,y))
            if location=='unknown':unknown+=1
        n=sum(st.overlap_seconds(x,y,start,end) for x,y in st.merge(spans));totals.append({'day':str(d),'outside_seconds':n,'over_eight_hours':n>8*3600,'unclassified_events':unknown})
    return {'days':totals,'notice':'Erfasste Einsatzorte; keine automatische Spesenberechnung.'}

HANDLERS.update({'projects/create-assign':create_assign,'outside/report':outside})


def categories_save(c,uid,body):
    for item in body.get('categories',[]):category_save(c,uid,item)
    return {'ok':True}

HANDLERS.update({'provider/assign':tw.assign,'categories/save':categories_save})
