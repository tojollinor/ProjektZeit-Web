"""Project grouping, repeatable projects and immutable billing descriptions."""
import json
from collections import defaultdict
from datetime import date,timedelta
import staff_time as st
import time_workspace as tw
import project_catalog as pc

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS project_tags(id INTEGER PRIMARY KEY,owner_id INTEGER NOT NULL,customer_id INTEGER NOT NULL DEFAULT 0,name VARCHAR(120) NOT NULL,active INTEGER NOT NULL DEFAULT 1,UNIQUE(owner_id,customer_id,name));
    CREATE TABLE IF NOT EXISTS project_tag_links(project_id INTEGER NOT NULL,tag_id INTEGER NOT NULL,PRIMARY KEY(project_id,tag_id));
    CREATE TABLE IF NOT EXISTS project_origins(project_id INTEGER PRIMARY KEY,template_id INTEGER NOT NULL,created_at VARCHAR(40) NOT NULL);
    CREATE TABLE IF NOT EXISTS category_locations(category_id INTEGER PRIMARY KEY,location VARCHAR(12) NOT NULL);
    CREATE TABLE IF NOT EXISTS event_work_context(owner_id INTEGER NOT NULL,source VARCHAR(32) NOT NULL,source_key VARCHAR(255) NOT NULL,location VARCHAR(12) NOT NULL,emergency INTEGER NOT NULL,updated_at VARCHAR(40) NOT NULL,PRIMARY KEY(owner_id,source,source_key));
    CREATE TABLE IF NOT EXISTS billing_descriptions(id INTEGER PRIMARY KEY,project_id INTEGER NOT NULL,service_day VARCHAR(10) NOT NULL,employee_id INTEGER NOT NULL,employee_name VARCHAR(255) NOT NULL,bullets LONGTEXT NOT NULL,seconds INTEGER NOT NULL,emergency INTEGER NOT NULL,revision INTEGER NOT NULL,created_by INTEGER NOT NULL,created_at VARCHAR(40) NOT NULL,invoice_reference VARCHAR(120) NOT NULL DEFAULT '',UNIQUE(project_id,service_day,employee_id,revision));
    ''')
    from next_batch_runtime import _columns
    if 'assigned_user_id' not in _columns(c,'projects'):c.execute('ALTER TABLE projects ADD COLUMN assigned_user_id INTEGER')
    first_upgrade='billing_state' not in _columns(c,'billing_descriptions')
    if first_upgrade:
        c.execute("ALTER TABLE billing_descriptions ADD COLUMN billing_state VARCHAR(24) NOT NULL DEFAULT 'pending'")
        c.execute("UPDATE billing_descriptions SET billing_state=COALESCE((SELECT p.billing_state FROM projects p WHERE p.id=billing_descriptions.project_id),'pending')")
    c.execute('CREATE TABLE IF NOT EXISTS billed_evidence(project_id INTEGER NOT NULL,owner_id INTEGER NOT NULL,source VARCHAR(32) NOT NULL,source_key VARCHAR(255) NOT NULL,fingerprint VARCHAR(128) NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(project_id,owner_id,source,source_key))')
    # Existing descriptions retain their original evidence; upgrade never resubmits it.
    if first_upgrade:c.execute("INSERT OR IGNORE INTO billed_evidence(project_id,owner_id,source,source_key,fingerprint,revision) SELECT r.project_id,r.owner_id,r.source,r.source_key,r.fingerprint,b.revision FROM time_reviews r JOIN (SELECT project_id,MAX(revision) revision FROM billing_descriptions GROUP BY project_id) b ON b.project_id=r.project_id WHERE r.billable=1")

def project(c,uid,pid):
    return __import__('project_access').get(c,uid,pid)

tags=pc.save_tag
attach=pc.assign_tags
clone=pc.clone

def tag_merge(c,uid,body):
    st.require(c,uid,'projects.manage_templates');a=int(body['id']);b=int(body['target_id'])
    if a==b:raise ValueError('Verschiedene Tags wählen.')
    rows=list(c.execute('SELECT * FROM project_tags WHERE owner_id=? AND id IN (?,?)',(uid,a,b)))
    if len(rows)!=2 or rows[0]['customer_id']!=rows[1]['customer_id']:raise ValueError('Nur Tags desselben Kundenbereichs zusammenführen.')
    c.execute('INSERT OR IGNORE INTO project_tag_links(project_id,tag_id) SELECT project_id,? FROM project_tag_links WHERE tag_id=?',(b,a))
    c.execute('DELETE FROM project_tag_links WHERE tag_id=?',(a,));c.execute('UPDATE project_tags SET active=0 WHERE id=?',(a,))
    st.audit(c,uid,uid,'tag',a,'merged',{'target':b});return {'ok':True}

def catalog(c,uid,body):
    return {'projects':[dict(r) for r in c.execute('SELECT * FROM projects WHERE (owner_id=? OR assigned_user_id=?) AND is_system=0 ORDER BY name',(uid,uid))],
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
    p=__import__('project_access').get(c,uid,body['project_id'],accounting=True)
    if uid not in (p['owner_id'],p.get('assigned_user_id')):st.require(c,uid,'bookkeeping.manage')
    if c.execute('SELECT 1 FROM entries WHERE project_id=? AND ended_at IS NULL',(p['id'],)).fetchone():raise ValueError('Projekt läuft noch. Zuerst Zeiterfassung beenden.')
    reviews=[dict(r) for r in c.execute('SELECT * FROM time_reviews WHERE project_id=? AND billable=1 ORDER BY started_at',(p['id'],))]
    evidence={(r['owner_id'],r['source'],r['source_key']):dict(r) for r in c.execute('SELECT * FROM billed_evidence WHERE project_id=?',(p['id'],))}
    current={}
    for e in c.execute('SELECT * FROM entries WHERE project_id=? AND is_idle=0',(p['id'],)):current[(e['owner_id'],'manual',str(e['id']))]={'source':'manual','key':str(e['id']),'project_id':e['project_id'],'start':e['started_at'],'end':e['ended_at'] or ''}
    for e in c.execute('SELECT i.*,a.project_id FROM event_intervals i JOIN provider_assignments a ON a.owner_id=i.owner_id AND a.provider=i.provider AND a.external_key=i.external_key WHERE a.project_id=?',(p['id'],)):current[(e['owner_id'],e['provider'],e['external_key'])]={'source':e['provider'],'key':e['external_key'],'project_id':e['project_id'],'start':e['started_at'],'end':e['ended_at']}
    ctx={(r['owner_id'],r['source'],r['source_key']):dict(r) for r in c.execute('SELECT x.* FROM event_work_context x JOIN time_reviews r ON r.owner_id=x.owner_id AND r.source=x.source AND r.source_key=x.source_key WHERE r.project_id=?',(p['id'],))}
    profiles={r['id']:((r['last_name'] or '')+', '+(r['first_name'] or '')).strip(', ') or r['username'] for r in c.execute('SELECT u.id,u.username,p.first_name,p.last_name FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id')}
    grouped=defaultdict(lambda:{'seconds':0,'emergency':False});pending=[]
    for r in reviews:
        key=(r['owner_id'],r['source'],r['source_key']);item=current.get(key)
        if not item or tw.fingerprint(item)!=r['fingerprint']:raise ValueError('Leistung wurde seit Freigabe verändert. Erneut prüfen.')
        if key in evidence:
            if evidence[key]['fingerprint']!=r['fingerprint']:raise ValueError('Bereits übergebene Leistung wurde geändert. Bitte mit der Buchhaltung klären; sie wird nicht doppelt übergeben.')
            continue
        pending.append(r);a,b=st.parse(r['started_at']),st.parse(r['ended_at'])
        for d in st.days(a.astimezone(st.TZ).date(),b.astimezone(st.TZ).date()+timedelta(days=1)):
            n=st.overlap_seconds(a,b,st.midnight(d),st.midnight(d+timedelta(days=1)))
            if n:
                group=grouped[(str(d),r['owner_id'])];group['seconds']+=n;group['emergency']|=bool(ctx.get(key,{}).get('emergency'))
    return {'project':p,'groups':[{'key':d+':'+str(owner),'service_day':d,'employee_id':owner,'employee_name':profiles.get(owner,'Ehemaliger Mitarbeiter'),**v} for (d,owner),v in grouped.items()],'evidence':pending}

def billing_submit(c,uid,body):
    result=billing_preview(c,uid,body);groups=result['groups'];p=result['project'];notes=body.get('descriptions',{})
    if p['status']!='closed':raise ValueError('Projekt zunächst abschließen und anschließend an die Buchhaltung übergeben.')
    if not groups:raise ValueError('Keine neuen geprüften abrechenbaren Leistungen vorhanden.')
    revision=c.execute('SELECT COALESCE(MAX(revision),0)+1 n FROM billing_descriptions WHERE project_id=?',(p['id'],)).fetchone()['n']
    for g in groups:
        text=str(notes.get(g['key']) or (notes.get(g['service_day']) if len([x for x in groups if x['service_day']==g['service_day']])==1 else '') or '').strip();lines=[x.lstrip('•-* ').strip() for x in text.splitlines() if x.strip()]
        if not lines or len(text)>8000:raise ValueError('Für jeden Mitarbeiter und Leistungstag Stichpunkte angeben (maximal 8000 Zeichen).')
        c.execute('INSERT INTO billing_descriptions(project_id,service_day,employee_id,employee_name,bullets,seconds,emergency,revision,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(p['id'],g['service_day'],g['employee_id'],g['employee_name'],json.dumps(lines,ensure_ascii=False),g['seconds'],int(g['emergency']),revision,uid,st.iso(st.now())))
    for r in result['evidence']:c.execute('INSERT INTO billed_evidence VALUES(?,?,?,?,?,?)',(p['id'],r['owner_id'],r['source'],r['source_key'],r['fingerprint'],revision))
    c.execute("UPDATE projects SET active=0,billing_state='pending',status_updated_at=? WHERE id=?",(st.iso(st.now()),p['id']))
    st.audit(c,uid,p['owner_id'],'project',p['id'],'sent_to_billing',{'revision':revision});return {'ok':True}


def billing_list(c,uid,body):
    st.require(c,uid,'bookkeeping.view')
    rows=[dict(r) for r in c.execute('SELECT b.*,p.name project,cu.name customer FROM billing_descriptions b JOIN projects p ON p.id=b.project_id LEFT JOIN customers cu ON cu.id=p.customer_id ORDER BY b.service_day DESC,b.id DESC LIMIT 1000')]
    for r in rows:r['text']=f"{date.fromisoformat(r['service_day']).strftime('%d.%m.%Y')} · {r['employee_name']}"+ (' · Notdienst' if r['emergency'] else '')+'\n'+'\n'.join('• '+x for x in json.loads(r['bullets']))
    return {'descriptions':rows}

def statistics(c,uid,body):
    data=pc.catalog(c,uid,{})
    tags=set(int(x) for x in body.get('tags',[]))
    allowed={r['project_id'] for r in data['links'] if r['tag_id'] in tags}
    result=[p for p in data['projects'] if not tags or p['id'] in allowed]
    return {'projects':result,'total_seconds':sum(p['seconds'] for p in result)}

HANDLERS={'projects/list':catalog,'tags/save':tags,'tags/assign':attach,'tags/merge':tag_merge,'projects/clone':clone,'projects/statistics':statistics,'event/save':context_save,'category/save':category_save,'billing/preview':billing_preview,'billing/submit':billing_submit,'billing/list':billing_list}


def create_assign(c,uid,body):
    st.require(c,uid,'customers.edit');cid=int(body['customer_id']);name=str(body['name']).strip()
    if not name or len(name)>120 or not c.execute('SELECT 1 FROM customers WHERE id=?',(cid,)).fetchone():raise ValueError('Kunde und Projektname erforderlich.')
    ident=c.execute("INSERT INTO projects(owner_id,customer_id,name,active,status) VALUES(?,?,?,1,'open')",(uid,cid,name)).lastrowid
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


def detail(c,uid,body):
    import project_access
    p=project_access.get(c,uid,body['project_id'],accounting=True)
    customer=c.execute('SELECT name FROM customers WHERE id=?',(p['customer_id'],)).fetchone()
    people=[dict(r) for r in c.execute('SELECT u.id,u.username,p.first_name,p.last_name FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.active=1 ORDER BY u.username')]
    history=__import__('system_features').history(c,p['owner_id'],'project',p['id'])
    return {'project':dict(p,customer=customer['name'] if customer else ''),'people':people,'history':history,'can_assign':st.acl.can(c,uid,'bookkeeping.manage'),'can_edit':uid in (p['owner_id'],p.get('assigned_user_id')) or st.acl.can(c,uid,'bookkeeping.manage')}


def assign_employee(c,uid,body):
    st.require(c,uid,'bookkeeping.manage');p=__import__('project_access').get(c,uid,body['project_id'],accounting=True)
    target=int(body.get('user_id') or 0)
    if target:st.person(c,target)
    if body.get('original_user_id')!=p.get('assigned_user_id'):raise ValueError('Zuständigkeit wurde inzwischen geändert. Bitte neu laden.')
    c.execute('UPDATE projects SET assigned_user_id=? WHERE id=?',(target or None,p['id']))
    st.audit(c,uid,p['owner_id'],'project',p['id'],'Mitarbeiter zugewiesen',{'before':p.get('assigned_user_id'),'after':target or None})
    if target:st.notify(c,target,'project','Dir wurde das Projekt „'+p['name']+'“ zugewiesen.',project_id=p['id'])
    return {'ok':True}

HANDLERS.update({'project/read':detail,'project/assign':assign_employee})
