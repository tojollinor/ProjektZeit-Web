"""Normalized local events, daily review and explicit billable bookings.

Provider events remain evidence. Only an explicit review creates a booking;
assignment never silently starts a timer or bills an overlapping event.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Berlin')
LIMIT = 1000


def parse(value):
    if not value: return None
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError): return None


def iso(d):
    return d.astimezone(timezone.utc).isoformat(timespec='seconds') if d else ''


def identifier(provider, raw, hint):
    from final_batch_runtime import _provider_identifier
    kind, value = _provider_identifier(provider, raw, hint)
    if kind == 'phone': value = re.sub(r'\D', '', value)
    return kind, value.casefold() if kind == 'email' else value


def normalize(provider, raw, occurred='', captured=''):
    start = parse(raw.get('startTime') or raw.get('start_date') or raw.get('started_at') or occurred)
    end = parse(raw.get('endTime') or raw.get('end_date') or raw.get('ended_at'))
    seconds = raw.get('duration')
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0 and start and not end:
        end = start + timedelta(seconds=seconds)
    # Ticket creation is an event, not measured work. Never invent ticket duration.
    if provider == 'zammad' and not raw.get('started_at'):
        start = parse(raw.get('created_at') or occurred)
        end = None
    return start, end


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS event_organizations (
      owner_id INTEGER NOT NULL, provider VARCHAR(32) NOT NULL, external_key VARCHAR(255) NOT NULL,
      organization_id VARCHAR(255) NOT NULL, PRIMARY KEY(owner_id,provider,external_key)
    );
    CREATE INDEX IF NOT EXISTS idx_event_organizations ON event_organizations(owner_id,organization_id);
    CREATE TABLE IF NOT EXISTS event_intervals (
      owner_id INTEGER NOT NULL, provider VARCHAR(32) NOT NULL, external_key VARCHAR(255) NOT NULL,
      started_at VARCHAR(40) NOT NULL, ended_at VARCHAR(40) NOT NULL,
      match_type VARCHAR(32) NOT NULL, match_value VARCHAR(500) NOT NULL,
      PRIMARY KEY(owner_id,provider,external_key)
    );
    CREATE INDEX IF NOT EXISTS idx_intervals_time ON event_intervals(owner_id,started_at);
    CREATE INDEX IF NOT EXISTS idx_intervals_identity ON event_intervals(owner_id,provider,match_type,match_value);
    CREATE TABLE IF NOT EXISTS time_reviews (
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      source VARCHAR(32) NOT NULL, source_key VARCHAR(255) NOT NULL,
      fingerprint VARCHAR(64) NOT NULL, project_id INTEGER REFERENCES projects(id),
      started_at VARCHAR(40) NOT NULL, ended_at VARCHAR(40) NOT NULL,
      seconds INTEGER NOT NULL, billable INTEGER NOT NULL DEFAULT 0,
      reviewed_at VARCHAR(40) NOT NULL,
      PRIMARY KEY(owner_id,source,source_key)
    );
    CREATE INDEX IF NOT EXISTS idx_time_reviews_day ON time_reviews(owner_id,started_at);
    ''')
    # Incremental legacy backfill, only events not yet indexed; never rerun JSON parsing for all rows.
    for r in c.execute('''SELECT e.* FROM provider_events e LEFT JOIN event_intervals i
                          ON i.owner_id=e.owner_id AND i.provider=e.provider AND i.external_key=e.external_key
                          WHERE i.external_key IS NULL'''):
        try: index_event(c, r['owner_id'], r['provider'], r['external_key'], json.loads(r['raw_json']), json.loads(r['hint_json']), r['occurred_at'], r['captured_at'])
        except (ValueError, TypeError): continue


def index_event(c, uid, provider, key, raw, hint, occurred='', captured=''):
    organization=str(raw.get('organization_id') or raw.get('organizationId') or '')
    c.execute('DELETE FROM event_organizations WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key))
    if organization:c.execute('INSERT INTO event_organizations VALUES(?,?,?,?)',(uid,provider,key,organization))
    start, end = normalize(provider, raw, occurred, captured)
    kind, value = identifier(provider, raw, hint)
    c.execute('DELETE FROM event_intervals WHERE owner_id=? AND provider=? AND external_key=?', (uid, provider, key))
    c.execute('INSERT INTO event_intervals VALUES(?,?,?,?,?,?,?)', (uid, provider, key, iso(start), iso(end), kind, value))


def bounds(body):
    day = str(body.get('day') or datetime.now(TZ).date())
    try: start = datetime.combine(datetime.strptime(day, '%Y-%m-%d').date(), datetime.min.time(), TZ)
    except ValueError: raise ValueError('Ungültiger Tag.') from None
    days = max(1, min(int(body.get('days') or 1), 366))
    return start, start + timedelta(days=days)


def fingerprint(event):
    return hashlib.sha256(json.dumps([event.get(k) for k in ('source', 'key', 'project_id', 'start', 'end')], separators=(',', ':')).encode()).hexdigest()


def union_seconds(events):
    spans = sorted((parse(e['start']), parse(e['end'])) for e in events if parse(e.get('start')) and parse(e.get('end')) and parse(e['end']) > parse(e['start']))
    merged = []
    for a,b in spans:
        if merged and a <= merged[-1][1]: merged[-1][1] = max(b, merged[-1][1])
        else: merged.append([a,b])
    return int(sum((b-a).total_seconds() for a,b in merged))


def events(c, uid, body, allow_team=False):
    start, end = bounds(body)
    cid = int(body.get('customer_id') or 0); pid = int(body.get('project_id') or 0)
    team = bool(body.get('team')) and allow_team and bool(cid or pid)
    if body.get('team') and not team: raise PermissionError('Teamansicht ist nur für Administratoren in einem Kunden oder Projekt verfügbar.')
    if cid and not c.execute('SELECT id FROM customers WHERE id=?'+('' if team else ' AND owner_id=?'), (cid,) if team else (cid,uid)).fetchone(): raise PermissionError('Kunde nicht zugänglich.')
    if pid and not c.execute('SELECT id FROM projects WHERE id=?'+('' if team else ' AND owner_id=?'), (pid,) if team else (pid,uid)).fetchone(): raise PermissionError('Projekt nicht zugänglich.')
    result = []
    args = [iso(end), iso(start)]
    where = 'e.is_idle=0 AND e.started_at<? AND (e.ended_at IS NULL OR e.ended_at>?)'
    if not team: where += ' AND e.owner_id=?'; args.append(uid)
    if cid: where += ' AND p.customer_id=?'; args.append(cid)
    if pid: where += ' AND p.id=?'; args.append(pid)
    rows = c.execute('''SELECT e.*,p.name project,p.customer_id,u.username FROM entries e
                        JOIN projects p ON p.id=e.project_id JOIN users u ON u.id=e.owner_id
                        WHERE '''+where+' ORDER BY e.started_at,e.id LIMIT 1001',tuple(args))
    now = datetime.now(timezone.utc)
    for r in rows:
        if r['is_idle']: continue
        result.append({'source':'manual','key':str(r['id']),'owner_id':r['owner_id'],'employee':r['username'],
                       'project_id':r['project_id'],'customer_id':r['customer_id'],'title':r['project'],
                       'start':r['started_at'],'end':r['ended_at'] or '', 'running':not r['ended_at'],'note':r['note']})
    args = [iso(end), iso(start), iso(start)]
    where = "i.started_at<? AND (i.ended_at>? OR (i.ended_at='' AND i.started_at>=?))"
    if not team: where += ' AND i.owner_id=?'; args.append(uid)
    if cid:
        matches=[key for key,ids in customer_identities(c,uid).items() if cid in ids]
        clauses=[];match_args=[]
        for provider,kind,value in matches:
            clauses.append('(i.owner_id=? AND i.provider=? AND i.match_type=? AND i.match_value=?)')
            match_args.extend((uid,provider,kind,value))
        clauses.append("(i.owner_id=? AND EXISTS (SELECT 1 FROM event_organizations o JOIN customer_provider_links ol ON ol.owner_id=o.owner_id AND ol.provider=o.provider AND ol.external_key=CONCAT_PLACEHOLDER WHERE o.owner_id=i.owner_id AND o.provider=i.provider AND o.external_key=i.external_key AND ol.customer_id=?))")
        # SQL concatenation differs between SQLite and MariaDB; both paths stay parameterized.
        concat="CONCAT('zammad:organization:',o.organization_id)" if getattr(c,'dialect','')=='mariadb' else "('zammad:organization:' || o.organization_id)"
        clauses[-1]=clauses[-1].replace('CONCAT_PLACEHOLDER',concat);match_args.extend((uid,cid))
        where+=' AND (COALESCE(a.customer_id,l.customer_id)=? OR (a.customer_id IS NULL AND l.customer_id IS NULL AND ('+' OR '.join(clauses)+')))'
        args.extend([cid,*match_args])
    if pid: where += ' AND a.project_id=?'; args.append(pid)
    rows = c.execute('''SELECT e.owner_id,e.provider,e.external_key,e.summary,i.started_at,i.ended_at,
                        a.project_id,COALESCE(a.customer_id,l.customer_id) customer_id,u.username,i.match_type,i.match_value
                        FROM event_intervals i JOIN provider_events e
                        ON e.owner_id=i.owner_id AND e.provider=i.provider AND e.external_key=i.external_key
                        JOIN users u ON u.id=e.owner_id LEFT JOIN provider_assignments a
                        ON a.owner_id=e.owner_id AND a.provider=e.provider AND a.external_key=e.external_key
                        LEFT JOIN customer_provider_links l
                        ON l.owner_id=e.owner_id AND l.provider=e.provider AND l.external_key=e.external_key
                        WHERE '''+where+' ORDER BY i.started_at,e.external_key LIMIT 1001',tuple(args))
    for r in rows:
        result.append({'source':r['provider'],'key':r['external_key'],'owner_id':r['owner_id'],'employee':r['username'],
                       'project_id':r['project_id'],'customer_id':r['customer_id'],'title':r['summary'] or r['provider'],
                       'start':r['started_at'],'end':r['ended_at'],'running':False,'match_type':r['match_type'],'match_value':r['match_value']})
    truncated = len(result)>LIMIT
    result.sort(key=lambda e:(e['start'],e['source'],e['key']))
    result=result[:LIMIT]
    reviews={(r['owner_id'],r['source'],r['source_key']):dict(r) for r in c.execute('SELECT * FROM time_reviews WHERE started_at<? AND ended_at>?'+('' if team else ' AND owner_id=?'),(iso(end),iso(start)) if team else (iso(end),iso(start),uid))}
    for e in result:
        a=parse(e['start']); b=parse(e['end']) or (now if e['running'] else a)
        e['seconds']=max(0,int((min(b,end).astimezone(timezone.utc)-max(a,start).astimezone(timezone.utc)).total_seconds())) if a and b else 0
        review=reviews.get((e['owner_id'],e['source'],e['key']))
        e['reviewed']=bool(review and review['fingerprint']==fingerprint(e))
        e['billable']=bool(e['reviewed'] and review['billable'])
    return result,truncated,start,end


def workspace(c,uid,body,allow_team=False):
    rows,truncated,start,end=events(c,uid,body,allow_team)
    work=[dict(r) for r in c.execute('SELECT id,started_at,ended_at FROM work_sessions WHERE owner_id=? AND started_at<? AND (ended_at IS NULL OR ended_at>?) ORDER BY started_at',(uid,iso(end),iso(start)))]
    pauses=[dict(r) for r in c.execute('SELECT id,started_at,ended_at FROM work_pauses WHERE owner_id=? AND started_at<? AND (ended_at IS NULL OR ended_at>?) ORDER BY started_at',(uid,iso(end),iso(start)))]
    overlaps=set(); active=[]
    for e in rows:
        a=parse(e['start']);b=parse(e['end'])
        if not a or not b:continue
        active=[x for x in active if x[0]>a]
        for old_end,old in active:
            if old['owner_id']==e['owner_id']:
                overlaps.add((e['source'],e['key'],e['owner_id']));overlaps.add((old['source'],old['key'],old['owner_id']))
        active.append((b,e))
    identities=customer_identities(c,uid)
    projects=[dict(r) for r in c.execute('SELECT id,name,customer_id FROM projects WHERE owner_id=? AND is_system=0 ORDER BY name',(uid,))]
    for e in rows:
        e['overlap']=(e['source'],e['key'],e['owner_id']) in overlaps
        matches=identities.get((e['source'],e.get('match_type'),e.get('match_value')),set())
        if e.get('customer_id'):matches={e['customer_id']}
        a=parse(e['start']);b=parse(e['end']) or a
        concurrent={x['project_id'] for x in rows if x['source']=='manual' and x['owner_id']==uid and parse(x['start']) and parse(x['end']) and a and b and parse(x['start'])<=b and parse(x['end'])>=a}
        e['suggestions']=[p for p in projects if p['customer_id'] in matches and p['id'] in concurrent] if not e['project_id'] and e['owner_id']==uid else []
    return {'events':rows,'work':work,'pauses':pauses,'truncated':truncated,'start':iso(start),'end':iso(end),
            'summary':{'unassigned':sum(not e['project_id'] for e in rows),'unreviewed':sum(not e['reviewed'] for e in rows),
                       'overlaps':len(overlaps),'running':sum(e['running'] for e in rows)+sum(not w['ended_at'] for w in work),
                       'event_seconds':sum(e['seconds'] for e in rows),'billable_seconds':sum(e['seconds'] for e in rows if e['billable'])},
            'customers':[dict(r) for r in c.execute('SELECT id,name FROM customers WHERE owner_id=? AND archived=0 ORDER BY name',(uid,))],
            'projects':projects,
            'can_view_team':allow_team}


def assign(c,uid,body):
    import admin_controls
    admin_controls.require_permission(c,uid,'customers.edit')
    pid=int(body.get('project_id') or 0)
    project=c.execute('SELECT id,customer_id FROM projects WHERE owner_id=? AND id=? AND is_system=0',(uid,pid)).fetchone()
    if not project or not project['customer_id']:raise ValueError('Bitte ein eigenes Projekt mit Kunde auswählen.')
    selections=body.get('items') or []
    if not isinstance(selections,list) or not 1<=len(selections)<=100:raise ValueError('Bitte 1 bis 100 Ereignisse auswählen.')
    for item in selections:
        source=str(item.get('source') or '');key=str(item.get('key') or '')
        if source=='manual':
            if not c.execute('SELECT id FROM entries WHERE owner_id=? AND id=?',(uid,key)).fetchone():raise ValueError('Stempelung nicht gefunden.')
            c.execute('UPDATE entries SET project_id=? WHERE owner_id=? AND id=?',(pid,uid,key))
        else:
            if not c.execute('SELECT 1 FROM provider_events WHERE owner_id=? AND provider=? AND external_key=?',(uid,source,key)).fetchone():raise ValueError('Providerereignis nicht gefunden.')
            previous=c.execute('SELECT customer_id FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,source,key)).fetchone()
            if previous and previous['customer_id'] and previous['customer_id']!=project['customer_id'] and body.get('confirm_reassign') is not True:raise ValueError('Das Projekt gehört zu einem anderen Kunden. Kundenzuordnung ausdrücklich bestätigen.')
            c.execute('DELETE FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,source,key))
            c.execute('INSERT INTO provider_assignments(owner_id,provider,external_key,customer_id,project_id,match_type,match_value,assigned_by,assigned_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid,source,key,project['customer_id'],pid,'manual','',uid,iso(datetime.now(timezone.utc))))
        c.execute('DELETE FROM time_reviews WHERE owner_id=? AND source=? AND source_key=?',(uid,source,key))
    import system_features
    system_features.audit(c,uid,uid,'project',pid,'time_events_assigned',{'count':len(selections)})
    return {'ok':True,'assigned':len(selections)}


def review(c,uid,body):
    # Re-read authoritative local data, never trust client durations/ownership.
    rows,_,_,_=events(c,uid,body)
    source=str(body.get('source') or '');key=str(body.get('key') or '')
    e=next((e for e in rows if e['source']==source and e['key']==key),None)
    if not e:raise ValueError('Ereignis nicht im ausgewählten Zeitraum gefunden.')
    if e['running'] or not e['end']:raise ValueError('Nur abgeschlossene Zeiten können freigegeben werden. Tickets ohne Zeitmessung zuerst manuell stempeln.')
    if not e['project_id']:raise ValueError('Bitte zuerst ein Projekt zuordnen.')
    billable=body.get('billable') is True
    if billable:
        conflict=c.execute('''SELECT 1 FROM time_reviews WHERE owner_id=? AND billable=1 AND started_at<? AND ended_at>?
                              AND NOT (source=? AND source_key=?) LIMIT 1''',(uid,e['end'],e['start'],source,key)).fetchone()
        if conflict:raise ValueError('Überschneidung mit bereits abrechenbarer Zeit. Bitte ohne Abrechnung prüfen oder die Zeitintervalle zuerst korrigieren.')
    seconds=max(0,int((parse(e['end'])-parse(e['start'])).total_seconds()))
    if seconds<=0:raise ValueError('Eine Buchung benötigt eine positive gemessene Dauer.')
    c.execute('DELETE FROM time_reviews WHERE owner_id=? AND source=? AND source_key=?',(uid,source,key))
    c.execute('INSERT INTO time_reviews VALUES(?,?,?,?,?,?,?,?,?,?)',(uid,source,key,fingerprint(e),e['project_id'],e['start'],e['end'],seconds,int(billable),iso(datetime.now(timezone.utc))))
    import system_features
    system_features.audit(c,uid,uid,'time_review',source+':'+key,'reviewed',{'billable':billable,'seconds':seconds})
    return {'ok':True}


def handle(app,handler,session,body,action):
    try:
        with app.db(read_only=action in ('read','statistics')) as c:
            if action=='read':result=workspace(c,session['id'],body,session['role']=='admin')
            elif action=='statistics':result=statistics(c,session['id'],body)
            elif action=='assign':result=assign(c,session['id'],body)
            elif action=='review':result=review(c,session['id'],body)
            elif action=='reopen':
                c.execute('DELETE FROM time_reviews WHERE owner_id=? AND source=? AND source_key=?',(session['id'],str(body.get('source') or ''),str(body.get('key') or '')))
                import system_features
                system_features.audit(c,session['id'],session['id'],'time_review',str(body.get('key') or ''),'reopened',{})
                result={'ok':True}
            else:return handler.send_json(404,{'error':'Nicht gefunden'})
        return handler.send_json(200,result)
    except PermissionError as e:return handler.send_json(403,{'error':str(e)})
    except (ValueError,TypeError,KeyError) as e:return handler.send_json(400,{'error':str(e)})


def statistics(c,uid,body):
    start,end=bounds(body);now=datetime.now(timezone.utc);end=min(end,now)
    per_day={};cursor=start
    while cursor<end:
        per_day[cursor.date().isoformat()]=0;cursor+=timedelta(days=1)
    projects={};customers={};weekdays={x:0 for x in ['Mo','Di','Mi','Do','Fr','Sa','So']};total=0;count=0
    for r in c.execute('''SELECT e.started_at,e.ended_at,p.name project,cu.name customer FROM entries e
                          JOIN projects p ON p.id=e.project_id LEFT JOIN customers cu ON cu.id=p.customer_id
                          WHERE e.owner_id=? AND e.is_idle=0 AND e.started_at<? AND (e.ended_at IS NULL OR e.ended_at>?)''',(uid,iso(end),iso(start))):
        a=parse(r['started_at']);b=parse(r['ended_at']) or now
        if not a or b<=a:continue
        a=max(a,start);b=min(b,end)
        if b<=a:continue
        seconds=int((b.astimezone(timezone.utc)-a.astimezone(timezone.utc)).total_seconds());total+=seconds;count+=1
        projects[r['project']]=projects.get(r['project'],0)+seconds
        name=r['customer'] or 'Ohne Kunde';customers[name]=customers.get(name,0)+seconds
        cursor=a.astimezone(TZ)
        while cursor<b:
            boundary=datetime.combine(cursor.date()+timedelta(days=1),datetime.min.time(),TZ)
            part_end=min(b,boundary);part=int((part_end.astimezone(timezone.utc)-cursor.astimezone(timezone.utc)).total_seconds())
            key=cursor.date().isoformat();per_day[key]=per_day.get(key,0)+part;weekdays[['Mo','Di','Mi','Do','Fr','Sa','So'][cursor.weekday()]]+=part;cursor=part_end.astimezone(TZ)
    return {'per_day':list(per_day.items()),'projects':list(projects.items()),'customers':list(customers.items()),'weekdays':list(weekdays.items()),'total':total,'count':count}


def customer_identities(c,uid):
    """Small customer identity catalog; no scan or JSON decode of provider history."""
    out={}
    def add(provider,kind,value,cid):
        value=str(value or '').strip()
        if kind=='phone':value=re.sub(r'\D','',value)
        if kind=='email':value=value.casefold()
        if value:out.setdefault((provider,kind,value),set()).add(cid)
    for r in c.execute('SELECT provider,link_type,link_value,customer_id FROM customer_identity_links WHERE owner_id=?',(uid,)):add(r['provider'],r['link_type'],r['link_value'],r['customer_id'])
    for r in c.execute('SELECT customer_id,number FROM customer_phones WHERE owner_id=? UNION SELECT x.customer_id,p.number FROM customer_contact_phones p JOIN customer_contacts x ON x.id=p.contact_id WHERE p.owner_id=?',(uid,uid)):add('starface','phone',r['number'],r['customer_id'])
    for r in c.execute('SELECT customer_id,email FROM customer_profiles WHERE owner_id=? UNION SELECT customer_id,email FROM customer_contacts WHERE owner_id=?',(uid,uid)):add('zammad','email',r['email'],r['customer_id'])
    for r in c.execute('SELECT customer_id,external_id FROM customer_devices WHERE owner_id=? AND provider=?',(uid,'teamviewer')):add('teamviewer','teamviewer_id',r['external_id'],r['customer_id'])
    return out
