"""Employee time models, absence requests and audited account movements.

All calculations use Europe/Berlin dates and integer seconds. No future credit.
"""
import calendar
import csv
import io
import json
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction
from functools import lru_cache
from zoneinfo import ZoneInfo
import holidays
import admin_controls as acl
import system_features
import work_models as wm

TZ=ZoneInfo('Europe/Berlin')
PERMISSIONS={
 'staff.view':'Arbeitszeit anderer Mitarbeiter ansehen',
 'staff.manage':'Urlaubskonten verwalten',
 'staff.policy':'Arbeitszeit- und Abwesenheitsrichtlinien verwalten',
 'absence.review':'Urlaubsanträge genehmigen',
 'absence.review_unpaid':'Unbezahlte Abwesenheit und Zeitausgleich genehmigen',
 'absence.review_self':'Eigene Abwesenheitsanträge genehmigen',
 'absence.enter_other':'Abwesenheiten für andere eintragen',
 'correction.review':'Arbeitszeiten anderer Mitarbeiter korrigieren',
 'correction.review_self':'Eigene Stempelkorrekturen genehmigen',
 'payroll.manage':'Stunden auszahlen und Monate abschließen',
 'calendar.work_team':'Arbeits- und Projektzeiten im Teamkalender sehen',
 'duty.manage':'Notdienstplan verwalten',
 'sync.manage':'Unternehmensweiten Providerabgleich verwalten',
 'sync.diagnostics':'Isolierte Schnittstellentests durchführen',
 'projects.manage_templates':'Projektvorlagen und Tags verwalten',
}
DEFAULT_POLICY={'approval_paid':True,'approval_unpaid':True,'hourly_paid':False,'minimum_minutes':30,'correction_mode':'direct','self_approval':False}
KINDS=[('vacation','Bezahlter Urlaub','paid',1,'#62a5fa'),('sick','Krank','paid',0,'#c58be2'),('unpaid','Unbezahlte Abwesenheit','debit',0,'#b8a36a'),('timeoff','Freizeitausgleich','debit',0,'#64bfa9'),('release','Unbezahlte Freistellung (Soll reduzieren)','reduce',0,'#a7a7a7')]

def iso(x):return x.astimezone(timezone.utc).isoformat(timespec='seconds')
def parse(x):
    d=datetime.fromisoformat(str(x).replace('Z','+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=TZ)
def now():return datetime.now(timezone.utc)
def midnight(day):return datetime.combine(day,time.min,TZ)
def days(a,b):
    while a<b:yield a;a+=timedelta(days=1)
def audit(c,actor,uid,kind,key,action,detail):system_features.audit(c,uid,actor,kind,str(key),action,detail)
def require(c,uid,key):acl.require_permission(c,uid,key)
def person(c,uid):
    if not c.execute('SELECT id FROM users WHERE id=? AND active=1',(uid,)).fetchone():raise ValueError('Mitarbeiter nicht aktiv.')
def seconds(value):
    n=Fraction(str(value))*3600
    if n.denominator!=1 or n<0 or n>744*3600:raise ValueError('Ungültiger Stundenwert.')
    return int(n)

def migrate(c):
    wm.migrate(c)
    c.executescript('''
    CREATE TABLE IF NOT EXISTS staff_policy_versions(id INTEGER PRIMARY KEY,valid_from VARCHAR(10) NOT NULL,settings_json LONGTEXT NOT NULL,created_by INTEGER NOT NULL,created_at VARCHAR(40) NOT NULL);
    CREATE TABLE IF NOT EXISTS absence_kinds(code VARCHAR(64) PRIMARY KEY,name VARCHAR(120) NOT NULL,rule VARCHAR(12) NOT NULL,vacation INTEGER NOT NULL,color VARCHAR(20) NOT NULL,active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS staff_requests(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,created_by INTEGER NOT NULL,kind VARCHAR(64) NOT NULL,start_at VARCHAR(40) NOT NULL,end_at VARCHAR(40) NOT NULL,whole_day INTEGER NOT NULL,state VARCHAR(24) NOT NULL,version INTEGER NOT NULL DEFAULT 1,policy_json LONGTEXT NOT NULL,note TEXT NOT NULL,decision_note TEXT NOT NULL,created_at VARCHAR(40) NOT NULL,decided_at VARCHAR(40),decided_by INTEGER,parent_id INTEGER,payload_json LONGTEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_staff_requests_dates ON staff_requests(user_id,start_at,end_at,state);
    CREATE TABLE IF NOT EXISTS vacation_accounts(user_id INTEGER NOT NULL,year INTEGER NOT NULL,entitlement INTEGER NOT NULL,carry INTEGER NOT NULL DEFAULT 0,carry_until VARCHAR(10) NOT NULL DEFAULT '',PRIMARY KEY(user_id,year));
    CREATE TABLE IF NOT EXISTS staff_movements(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,day VARCHAR(10) NOT NULL,seconds INTEGER NOT NULL,kind VARCHAR(32) NOT NULL,note TEXT NOT NULL,created_by INTEGER NOT NULL,created_at VARCHAR(40) NOT NULL,source_key VARCHAR(100) NOT NULL UNIQUE);
    CREATE TABLE IF NOT EXISTS staff_month_closures(user_id INTEGER NOT NULL,month VARCHAR(7) NOT NULL,snapshot_json LONGTEXT NOT NULL,created_by INTEGER NOT NULL,created_at VARCHAR(40) NOT NULL,PRIMARY KEY(user_id,month));
    CREATE TABLE IF NOT EXISTS staff_month_revisions(user_id INTEGER NOT NULL,month VARCHAR(7) NOT NULL,seconds INTEGER NOT NULL,PRIMARY KEY(user_id,month));
    CREATE TABLE IF NOT EXISTS staff_holiday_overrides(subdivision VARCHAR(8) NOT NULL,day VARCHAR(10) NOT NULL,name VARCHAR(120) NOT NULL,enabled INTEGER NOT NULL,PRIMARY KEY(subdivision,day));
    CREATE TABLE IF NOT EXISTS notification_links(notification_id INTEGER PRIMARY KEY,request_id INTEGER,project_id INTEGER);
    CREATE TABLE IF NOT EXISTS notification_reads(user_id INTEGER NOT NULL,notification_id INTEGER NOT NULL,read_at VARCHAR(40) NOT NULL,PRIMARY KEY(user_id,notification_id));
    ''')
    for code,name,rule,vacation,color in KINDS:c.execute('INSERT OR IGNORE INTO absence_kinds(code,name,rule,vacation,color) VALUES(?,?,?,?,?)',(code,name,rule,vacation,color))
    for r in list(c.execute("SELECT id,user_id FROM staff_requests WHERE kind='correction' AND state='pending'")):
        c.execute("UPDATE staff_requests SET state='superseded',version=version+1,decision_note=? WHERE id=?",('Direkte Korrekturen verfügbar. Bitte Stempelung prüfen und erneut speichern.',r['id']))
        notify(c,r['user_id'],'correction','Eine frühere Zeitkorrektur wurde nicht angewendet. Bitte unter Zeiterfassung erneut prüfen und direkt speichern.')

def register():
    acl.PERMISSION_CATEGORIES['Arbeitszeit & Abwesenheiten']=list(PERMISSIONS.items())
    acl.ALL_PERMISSIONS.update(PERMISSIONS)
    # Self-approval is never implicit in ordinary admin role defaults.
    acl.DEFAULT_ADMIN_PERMISSIONS.update(set(PERMISSIONS)-{'absence.review_self','correction.review_self'})
    acl.ALL_PERMISSIONS.add(wm.PERMISSION)
    import final_batch_runtime
    for key in ('staff.manage','staff.policy','sync.manage','sync.diagnostics','duty.manage'):
        final_batch_runtime.DEPENDENCIES[key]={'admin.options.view'}
    final_batch_runtime.DEPENDENCIES['staff.manage'].add('users.view')
    final_batch_runtime.DEPENDENCIES['payroll.manage']={'bookkeeping.view','staff.view'}

def policy(c,day=None):
    day=day or now().astimezone(TZ).date()
    r=c.execute('SELECT settings_json FROM staff_policy_versions WHERE valid_from<=? ORDER BY valid_from DESC,id DESC LIMIT 1',(str(day),)).fetchone()
    result={**DEFAULT_POLICY,**(json.loads(r['settings_json']) if r else {})}
    result['correction_mode']='none' if result['correction_mode']=='none' else 'direct'
    return result

def model_list(c,uid):return [dict(m,weights=[int(i in m['weekdays']) for i in range(7)],opening_seconds=0) for m in wm.models(c,uid)]
def model_on(models,day):return next((x for x in reversed(models) if x['valid_from']<=str(day)),None)
def daily_target(model,day):
    if not model:return None
    weights=model['weights'];w=weights[day.weekday()]
    if not w:return 0
    if model['mode']=='daily':return model['target_seconds']*w//max(weights)
    if model['mode']=='weekly':period=list(range(7));index=day.weekday();ww=weights
    else:
        period=list(days(day.replace(day=1),day.replace(day=calendar.monthrange(day.year,day.month)[1])+timedelta(days=1)))
        index=day.day-1;ww=[weights[d.weekday()] for d in period]
    target=model['target_seconds'];den=sum(ww)
    # Cumulative apportionment conserves the exact monthly/weekly total.
    return target*sum(ww[:index+1])//den-target*sum(ww[:index])//den

@lru_cache(maxsize=256)
def holiday_calendar(year,subdivision):return wm.holiday_calendar(year,subdivision)
def holiday_name(model,day,overrides):
    if not model:return ''
    key=(model['subdivision'],str(day))
    if key in overrides:return overrides[key]['name'] if overrides[key]['enabled'] else ''
    return holiday_calendar(day.year,model['subdivision']).get(day,'')

def overlap_seconds(a,b,c,d):return max(0,int((min(b,d).astimezone(timezone.utc)-max(a,c).astimezone(timezone.utc)).total_seconds()))
def merge(spans):
    out=[]
    for a,b in sorted(spans):
        if b<=a:continue
        if out and a<=out[-1][1]:out[-1][1]=max(b,out[-1][1])
        else:out.append([a,b])
    return out
def subtract(spans,cuts):
    for ca,cb in merge(cuts):
        out=[]
        for a,b in spans:
            if cb<=a or ca>=b:out.append([a,b]);continue
            if a<ca:out.append([a,ca])
            if cb<b:out.append([cb,b])
        spans=out
    return spans

def dataset(c,uid,start,end):
    rows=[dict(r) for r in c.execute('SELECT * FROM staff_requests WHERE user_id=? AND start_at<? AND end_at>? ORDER BY id',(uid,iso(midnight(end)),iso(midnight(start))))]
    for r in rows:r['policy']=json.loads(r['policy_json']);r['payload']=json.loads(r['payload_json'])
    return {'models':model_list(c,uid),'requests':rows,
      'work':[dict(r) for r in c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND started_at<? AND (ended_at IS NULL OR ended_at>?)',(uid,iso(midnight(end)),iso(midnight(start))))],
      'pauses':[dict(r) for r in c.execute('SELECT * FROM work_pauses WHERE owner_id=? AND started_at<? AND (ended_at IS NULL OR ended_at>?)',(uid,iso(midnight(end)),iso(midnight(start))))],
      'overrides':{(r['subdivision'],r['day']):dict(r) for r in c.execute('SELECT * FROM staff_holiday_overrides WHERE day>=? AND day<?',(str(start),str(end)))}}

def request_spans(r,requests):
    cuts=[(parse(x['start_at']),parse(x['end_at'])) for x in requests if x['kind']=='cancel' and x['parent_id']==r['id'] and x['state']=='approved']
    return subtract([[parse(r['start_at']),parse(r['end_at'])]],cuts)

def daily(data,day,clock=None):
    clock=clock or now();a=midnight(day);b=midnight(day+timedelta(days=1));model=model_on(data['models'],day);target=daily_target(model,day)
    holiday=holiday_name(model,day,data['overrides']);requests=data['requests'];spans=[];unclosed=False
    gross=[]
    for w in data['work']:
        x=parse(w['started_at']);y=min(parse(w['ended_at']),clock) if w['ended_at'] else clock
        if x<b and y>a:
            clipped=(max(x,a),min(y,b));gross.append(clipped);unclosed|=not w['ended_at']
            pauses=[(parse(p['started_at']),min(parse(p['ended_at']),clock) if p['ended_at'] else clock) for p in data['pauses'] if p['work_session_id']==w['id']]
            spans.extend(subtract([clipped],pauses))
    worked=sum(int((y.astimezone(timezone.utc)-x.astimezone(timezone.utc)).total_seconds()) for x,y in merge(spans))
    amounts={'paid':[],'reduce':[],'vacation':[],'sick':[]};labels=[]
    for r in requests:
        if r['state']!='approved' or r['kind'] in ('cancel','correction'):continue
        rs=request_spans(r,requests)
        hits=[(max(x,a),min(y,b)) for x,y in rs if x<b and y>a]
        if not hits:continue
        meta=r['payload']['kind'];labels.append(meta['name'])
        for x,y in hits:
            amount=(target or 0) if r['whole_day'] else overlap_seconds(x,y,a,b)
            amounts.setdefault(meta['rule'],[]).append((x,y,amount))
            if meta['vacation']:amounts['vacation'].append((x,y,amount))
            if r['kind']=='sick':amounts['sick'].append((x,y,amount))
    def sum_amount(key):
        # Full-day compensation is capped at target; overlapping sick/vacation
        # credits are unioned and never stack.
        items=amounts[key]
        if any(n==(target or 0) and x==a and y==b for x,y,n in items):return target or 0
        return min(target or 0,sum(int((y.astimezone(timezone.utc)-x.astimezone(timezone.utc)).total_seconds()) for x,y in merge([(x,y) for x,y,n in items])))
    credit=(target or 0) if holiday else sum_amount('paid')
    reduction=0 if holiday else min(max(0,(target or 0)-credit),sum_amount('reduce'))
    vacation=0
    if not holiday and target:
        cuts=[(x,y) for x,y,n in amounts['sick']]
        for x,y,n in amounts['vacation']:
            remaining=subtract([[x,y]],cuts)
            removed=sum(overlap_seconds(u,v,x,y) for u,v in merge(cuts))
            vacation+=int(Fraction(max(0,n-removed),target)*1_000_000)
        vacation=min(vacation,1_000_000)
    # Missing historical work with no full-day explanation is a clarification,
    # not an automatically finalized debit. Explicit zero-work day can be confirmed.
    confirmed=any(r['state']=='approved' and r['kind']=='correction' and r['payload'].get('day')==str(day) for r in requests)
    absent=bool(holiday or credit+reduction>=(target or 0) or any(r['state']=='approved' and r['whole_day'] and r['kind'] not in ('cancel','correction') and any(x<=a and y>=b for x,y in request_spans(r,requests)) for r in requests))
    unresolved=bool(target and day<clock.astimezone(TZ).date() and unclosed)
    complete=b<=clock and not unresolved and target is not None
    delta=worked+credit+reduction-(target or 0)
    return {'day':str(day),'target_seconds':target,'worked_seconds':worked,'pause_seconds':max(0,sum(overlap_seconds(x,y,a,b) for x,y in merge(gross))-worked),'credit_seconds':credit if b<=clock else 0,'planned_credit_seconds':credit,'reduction_seconds':reduction if b<=clock else 0,'delta_seconds':delta if b<=clock and target is not None else None,'posted_seconds':delta if complete else 0,'state':'closed' if complete else 'unresolved' if unresolved else 'unconfigured' if target is None else 'planned' if a>clock else 'provisional','holiday':holiday,'labels':labels,'vacation_units':vacation}

def month_report(c,uid,month):
    start=date.fromisoformat(month+'-01');end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    data=dataset(c,uid,start,end);rows=[daily(data,d) for d in days(start,end)]
    closure=c.execute('SELECT * FROM staff_month_closures WHERE user_id=? AND month=?',(uid,month)).fetchone()
    movements=[dict(r) for r in c.execute('SELECT * FROM staff_movements WHERE user_id=? AND day>=? AND day<? ORDER BY id',(uid,str(start),str(end)))]
    closed=json.loads(closure['snapshot_json']) if closure else None
    projects=[dict(r) for r in c.execute('SELECT e.*,p.name project_name FROM entries e JOIN projects p ON p.id=e.project_id WHERE e.owner_id=? AND e.is_idle=0 AND e.started_at<? AND (e.ended_at IS NULL OR e.ended_at>?) ORDER BY e.started_at',(uid,iso(midnight(end)),iso(midnight(start))))]
    return {'projects':projects,'days':rows,'month':month,'requests':[dict(r,can_decide=can_decide(c,uid,r)) for r in data['requests']],'work':data['work'],'models':data['models'],'movements':movements,'closure':closed,'posted_seconds':closed['posted_seconds'] if closed else sum(x['posted_seconds'] for x in rows),'movement_seconds':sum(x['seconds'] for x in movements if x['day']<=str(now().astimezone(TZ).date())),'revision_seconds':sum(x['posted_seconds'] for x in rows)-(closed['posted_seconds'] if closed else sum(x['posted_seconds'] for x in rows))}

def vacation_balance(c,uid,year,extra_requests=None):
    start=date(year,1,1);end=date(year+1,1,1);data=dataset(c,uid,start,end);data['work']=[];data['pauses']=[]
    if extra_requests:data['requests'].extend(extra_requests)
    rows={d:daily(data,d)['vacation_units'] for d in days(start,end)}
    approved=sum(rows.values());taken=sum(v for d,v in rows.items() if d<now().astimezone(TZ).date())
    account=c.execute('SELECT * FROM vacation_accounts WHERE user_id=? AND year=?',(uid,year)).fetchone()
    entitlement=account['entitlement'] if account else 0;carry=account['carry'] if account else 0
    expiry=date.fromisoformat(account['carry_until']) if account and account['carry_until'] else None
    pending=[r for r in data['requests'] if r['state'] in ('pending','awaiting_employee') and r['kind'] not in ('cancel','correction')]
    hypothetical={**data,'requests':[dict(r,state='approved') if r in pending else r for r in data['requests']]}
    planned_rows={d:daily(hypothetical,d)['vacation_units'] for d in days(start,end)};planned=sum(planned_rows.values())
    used_carry=min(carry,sum(v for d,v in rows.items() if not expiry or d<=expiry))
    planned_carry=min(carry,sum(v for d,v in planned_rows.items() if not expiry or d<=expiry))
    shown_carry=used_carry if expiry and now().astimezone(TZ).date()>expiry else carry
    available=entitlement+shown_carry-approved
    # Expiring carry cannot fund leave after its deadline, even when requested early.
    after_pending=min(entitlement+shown_carry-planned,entitlement+planned_carry-planned) if expiry else entitlement+carry-planned
    return {'year':year,'configured':bool(account),'entitlement':entitlement,'carry':shown_carry,'taken':taken,'approved':approved,'pending':max(0,planned-approved),'available':available,'after_pending':after_pending}


def save_model(c,actor,body):
    if body.get('opening_hours') and Fraction(str(body['opening_hours'])):raise ValueError('Startsaldo über eine Korrekturbuchung der Buchhaltung eintragen.')
    return wm.save(c,actor,{**body,'weekdays':body.get('weekdays',[i for i,w in enumerate(body.get('weights',[])) if w])})

def save_policy(c,actor,body):
    require(c,actor,'staff.policy');d=date.fromisoformat(body['valid_from'])
    if d<now().astimezone(TZ).date():raise ValueError('Neue Richtlinien gelten frühestens ab heute.')
    p={k:body.get(k,v) for k,v in DEFAULT_POLICY.items()}
    if p['correction_mode'] not in ('none','request','direct'):raise ValueError('Korrekturmodus ungültig.')
    p['minimum_minutes']=int(p['minimum_minutes'])
    if not 1<=p['minimum_minutes']<=480:raise ValueError('Mindestdauer muss zwischen 1 und 480 Minuten liegen.')
    for k in ('approval_paid','approval_unpaid','hourly_paid','self_approval'):
        if not isinstance(p[k],bool):raise ValueError('Ungültige Richtlinie.')
    c.execute('INSERT INTO staff_policy_versions(valid_from,settings_json,created_by,created_at) VALUES(?,?,?,?)',(str(d),json.dumps(p),actor,iso(now())))
    audit(c,actor,actor,'staff_policy',str(d),'created',p);return {'ok':True}

def request_range(body):
    whole=body.get('whole_day') is True
    if whole:
        a=midnight(date.fromisoformat(body['from']));b=midnight(date.fromisoformat(body['to'])+timedelta(days=1))
    else:a=parse(body['from']);b=parse(body['to'])
    if b<=a or (b-a).days>366:raise ValueError('Zeitraum muss positiv und höchstens ein Jahr lang sein.')
    return a,b,whole

def submit(c,actor,body):
    uid=int(body.get('user_id') or actor);person(c,uid)
    if uid!=actor:require(c,actor,'absence.enter_other')
    a,b,whole=request_range(body);kind=str(body['kind']);p=policy(c)
    meta=c.execute('SELECT * FROM absence_kinds WHERE code=? AND active=1',(kind,)).fetchone()
    if not meta:raise ValueError('Unbekannte Tagesart.')
    meta=dict(meta)
    if meta['vacation'] and not whole and not p['hourly_paid']:raise ValueError('Bezahlter Urlaub ist nur für ganze Tage erlaubt.')
    if not whole and int((b-a).total_seconds())%(p['minimum_minutes']*60):raise ValueError('Zeitraum entspricht nicht der erlaubten Mindestschrittweite.')
    models=model_list(c,uid)
    if any(model_on(models,d) is None for d in days(a.astimezone(TZ).date(),(b-timedelta(seconds=1)).astimezone(TZ).date()+timedelta(days=1))):raise ValueError('Arbeitszeitmodell fehlt für diesen Zeitraum.')
    if conflicts(c,uid,a,b,kind):raise ValueError('Überschneidung mit einer vorhandenen Abwesenheit. Bitte zuerst ändern oder stornieren.')
    # Store policy and category rule snapshots: later edits cannot reinterpret it.
    state='awaiting_employee' if uid!=actor else 'pending' if p['approval_paid' if meta['rule']=='paid' else 'approval_unpaid'] else 'approved'
    cur=c.execute('INSERT INTO staff_requests(user_id,created_by,kind,start_at,end_at,whole_day,state,policy_json,note,decision_note,created_at,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(uid,actor,kind,iso(a),iso(b),int(whole),state,json.dumps(p),str(body.get('note') or '')[:2000],'',iso(now()),json.dumps({'kind':meta})))
    if meta['vacation']:
        for year in range(a.astimezone(TZ).year,(b-timedelta(seconds=1)).astimezone(TZ).year+1):
            bal=vacation_balance(c,uid,year)
            if not bal['configured'] or bal['after_pending']<0:raise ValueError('Urlaubskonto fehlt oder Resturlaub reicht nicht aus.')
    if state=='approved':reconcile_closed_months(c,actor,uid,a,b)
    if state=='pending':
        key='absence.review' if meta['rule']=='paid' else 'absence.review_unpaid'
        for person_row in c.execute('SELECT id FROM users WHERE active=1 AND id<>?',(uid,)):
            if acl.can(c,person_row['id'],key):notify(c,person_row['id'],'absence','Neuer Abwesenheitsantrag wartet auf Genehmigung.',request_id=cur.lastrowid)
    notify(c,uid,'absence','Abwesenheit '+state+' · '+str(a.astimezone(TZ).date()),request_id=cur.lastrowid)
    audit(c,actor,uid,'absence',cur.lastrowid,'submitted',{'kind':kind,'state':state});return {'ok':True,'id':cur.lastrowid,'state':state}

def cancellation(c,actor,body):
    r=c.execute("SELECT * FROM staff_requests WHERE id=? AND user_id=? AND state IN ('approved','pending','awaiting_employee')",(int(body['id']),actor)).fetchone()
    if not r or r['kind'] in ('cancel','correction'):raise ValueError('Nur eigene genehmigte Abwesenheit kann zur Stornierung angefragt werden.')
    a,b,whole=request_range(body)
    if r['whole_day'] and not whole:raise ValueError('Ganztägige Abwesenheiten bitte tageweise stornieren; Stundenurlaub lässt sich stundenweise stornieren.')
    if a<parse(r['start_at']) or b>parse(r['end_at']):raise ValueError('Stornierung muss innerhalb des ursprünglichen Zeitraums liegen.')
    if c.execute("SELECT 1 FROM staff_requests WHERE parent_id=? AND kind='cancel' AND state IN ('pending','approved') AND start_at<? AND end_at>?",(r['id'],iso(b),iso(a))).fetchone():raise ValueError('Für diesen Zeitraum existiert bereits eine Stornierung.')
    cur=c.execute('INSERT INTO staff_requests(user_id,created_by,kind,start_at,end_at,whole_day,state,policy_json,note,decision_note,created_at,parent_id,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(actor,actor,'cancel',iso(a),iso(b),int(whole),'pending',r['policy_json'],str(body.get('note') or '')[:2000],'',iso(now()),r['id'],r['payload_json']))
    audit(c,actor,actor,'absence',cur.lastrowid,'cancellation_requested',{'parent':r['id']});return {'ok':True,'id':cur.lastrowid}

def decide(c,actor,body):
    rid=int(body['id']);r=c.execute('SELECT * FROM staff_requests WHERE id=?',(rid,)).fetchone()
    if not r:raise ValueError('Antrag nicht gefunden.')
    if r['version']!=int(body['version']):raise ValueError('Antrag wurde inzwischen geändert. Bitte aktualisieren.')
    if r['state'] not in ('pending','awaiting_employee'):raise ValueError('Antrag ist bereits entschieden.')
    p=json.loads(r['policy_json']);payload=json.loads(r['payload_json']);approved=body.get('approve') is True
    if r['state']=='awaiting_employee':
        if actor!=r['user_id']:raise PermissionError('Nur der betroffene Mitarbeiter kann diesen Eintrag bestätigen.')
    else:
        permission='correction.review' if r['kind']=='correction' else 'absence.review' if payload['kind']['rule']=='paid' else 'absence.review_unpaid'
        require(c,actor,permission)
        if actor==r['user_id']:
            require(c,actor,'correction.review_self' if r['kind']=='correction' else 'absence.review_self')
            if not p['self_approval']:raise PermissionError('Eigengenehmigung ist laut geltender Richtlinie ausgeschaltet.')
    note=str(body.get('note') or '')[:2000]
    if not approved and not note.strip():raise ValueError('Bitte Ablehnung begründen.')
    if approved and r['kind'] not in ('cancel','correction','sick'):
        conflict=conflicts(c,r['user_id'],parse(r['start_at']),parse(r['end_at']),r['kind'],rid,approved_only=True)
        if conflict:raise ValueError('Seit Antragstellung besteht ein Abwesenheitskonflikt. Bitte klären.')
    if approved and r['kind']=='correction':apply_correction(c,actor,r,payload)
    c.execute('UPDATE staff_requests SET state=?,version=version+1,decision_note=?,decided_at=?,decided_by=? WHERE id=? AND version=?',('approved' if approved else 'rejected',note,iso(now()),actor,rid,r['version']))
    if approved and payload.get('kind',{}).get('vacation') and r['kind']!='cancel':
        for year in range(parse(r['start_at']).astimezone(TZ).year,(parse(r['end_at'])-timedelta(seconds=1)).astimezone(TZ).year+1):
            bal=vacation_balance(c,r['user_id'],year)
            if not bal['configured'] or bal['after_pending']<0:raise ValueError('Resturlaub reicht nicht mehr aus.')
    if approved:reconcile_closed_months(c,actor,r['user_id'],parse(r['start_at']),parse(r['end_at']))
    notify(c,r['user_id'],'absence','Antrag '+('genehmigt' if approved else 'abgelehnt')+' · '+str(parse(r['start_at']).astimezone(TZ).date()),request_id=rid)
    audit(c,actor,r['user_id'],'absence',rid,'approved' if approved else 'rejected',{'note':note});return {'ok':True}

def apply_correction(c,actor,r,payload):
    """Validate the complete proposal before changing a shift or its pauses."""
    import workday
    uid=r['user_id'];day=payload['day'];ident=payload.get('work_id')
    old=c.execute('SELECT * FROM work_sessions WHERE id=? AND owner_id=?',(ident,uid)).fetchone() if ident else None
    if ident and (not old or dict(old)!=payload['before']):raise ValueError('Stempelung wurde inzwischen geändert. Bitte neu öffnen.')
    a,b=payload.get('start'),payload.get('end')
    for d in {day[:7],*[str(parse(v).astimezone(TZ).date())[:7] for v in [a,b,*([old['started_at'],old['ended_at']] if old else [])] if v]}:
        if c.execute('SELECT 1 FROM staff_month_closures WHERE user_id=? AND month=?',(uid,d)).fetchone():raise ValueError('Monat abgeschlossen. Korrekturbuchung über die Buchhaltung erforderlich.')
    old_pauses=[dict(x) for x in c.execute('SELECT * FROM work_pauses WHERE work_session_id=? ORDER BY started_at,id',(ident,))] if ident else []
    if old and payload.get('original_pauses') is not None and payload['original_pauses']!=old_pauses:raise ValueError('Pausen wurden inzwischen geändert. Bitte neu öffnen.')
    if not a and not b:
        if ident:raise ValueError('Vorhandene Stempelung benötigt Beginn und Ende.')
        return None
    if not a or not b or parse(b)<=parse(a):raise ValueError('Ende muss nach Beginn liegen.')
    if parse(a).astimezone(TZ).date()!=date.fromisoformat(day) or parse(b)>now():raise ValueError('Korrektur muss am gewählten Tag beginnen und in der Vergangenheit liegen.')
    if (parse(b)-parse(a)).total_seconds()>48*3600:raise ValueError('Eine Stempelung darf höchstens 48 Stunden umfassen. Bitte mehrtägige Einträge aufteilen.')
    for w in c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND id<>?',(uid,ident or 0)):
        if parse(w['started_at'])<parse(b) and (not w['ended_at'] or parse(w['ended_at'])>parse(a)):raise ValueError('Arbeitszeiten überschneiden sich.')
    projects=[dict(x) for x in c.execute('SELECT * FROM entries WHERE work_session_id=? AND is_idle=0',(ident,))] if ident else []
    if any(parse(e['started_at'])<parse(a) or not e['ended_at'] or parse(e['ended_at'])>parse(b) for e in projects):raise ValueError('Projektzeiten liegen außerhalb der korrigierten Arbeitszeit. Bitte zuerst klären.')
    raw=payload.get('pauses',old_pauses)
    if not isinstance(raw,list) or len(raw)>100:raise ValueError('Ungültige Pausenliste.')
    pauses=[]
    for x in raw:
        start,end=iso(parse(x['started_at'])),iso(parse(x['ended_at']))
        if not parse(a)<=parse(start)<parse(end)<=parse(b):raise ValueError('Pausen müssen innerhalb der Arbeitszeit liegen.')
        if any(parse(e['started_at'])<parse(end) and parse(e['ended_at'])>parse(start) for e in projects):raise ValueError('Pause überschneidet sich mit Projektzeit. Bitte zuerst die Projektstempelung korrigieren.')
        pauses.append({'started_at':start,'ended_at':end})
    pauses.sort(key=lambda x:x['started_at'])
    if any(parse(x['ended_at'])>parse(y['started_at']) for x,y in zip(pauses,pauses[1:])):raise ValueError('Pausen überschneiden sich.')
    if ident:c.execute('UPDATE work_sessions SET started_at=?,ended_at=? WHERE id=? AND owner_id=?',(a,b,ident,uid))
    else:ident=c.execute('INSERT INTO work_sessions(owner_id,started_at,ended_at) VALUES(?,?,?)',(uid,a,b)).lastrowid
    if 'pauses' in payload:
        c.execute('DELETE FROM work_pauses WHERE work_session_id=?',(ident,))
        for x in pauses:c.execute('INSERT INTO work_pauses(owner_id,work_session_id,started_at,ended_at) VALUES(?,?,?,?)',(uid,ident,x['started_at'],x['ended_at']))
    workday.reconcile(c,uid)
    after=dict(c.execute('SELECT * FROM work_sessions WHERE id=?',(ident,)).fetchone())
    def total(w,ps):return None if not w or not w['ended_at'] else int((parse(w['ended_at'])-parse(w['started_at'])).total_seconds())-sum(int((parse(x['ended_at'])-parse(x['started_at'])).total_seconds()) for x in ps if x['ended_at'])
    audit(c,actor,uid,'worktime',ident,'Arbeitszeit korrigiert' if old else 'Arbeitszeit nachgestempelt',{'day':day,'before':dict(old) if old else None,'after':after,'pauses_before':old_pauses,'pauses_after':pauses,'seconds_before':total(old,old_pauses),'seconds_after':total(after,pauses),'note':payload.get('note','')})
    return ident

def correction(c,actor,body):
    p=policy(c);uid=int(body.get('user_id') or actor)
    if uid!=actor:require(c,actor,'correction.review')
    elif p['correction_mode']=='none':raise PermissionError('Eigene Stempelkorrekturen sind ausgeschaltet.')
    d=date.fromisoformat(body['day']);ident=int(body.get('work_id') or 0)
    before=c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND id=?',(uid,ident)).fetchone() if ident else None
    if ident and not before:raise PermissionError('Stempelung nicht zugänglich.')
    if before and ('original_start' not in body or body['original_start']!=before['started_at'] or body.get('original_end')!=before['ended_at']):raise ValueError('Stempelung wurde inzwischen geändert. Bitte neu öffnen.')
    payload={'day':str(d),'work_id':ident,'before':dict(before) if before else None,'start':iso(parse(body['start'])) if body.get('start') else None,'end':iso(parse(body['end'])) if body.get('end') else None,'note':str(body.get('note') or '').strip()[:2000]}
    for key in ('pauses','original_pauses'):
        if key in body:payload[key]=body[key]
    if d>=now().astimezone(TZ).date() and not payload['start']:raise ValueError('Nur vergangene Tage können ohne Arbeit bestätigt werden.')
    if not payload['note']:raise ValueError('Begründung erforderlich.')
    if bool(payload['start'])!=bool(payload['end']):raise ValueError('Beginn und Ende gemeinsam angeben.')
    work_id=apply_correction(c,actor,{'user_id':uid},payload)
    cur=c.execute('INSERT INTO staff_requests(user_id,created_by,kind,start_at,end_at,whole_day,state,policy_json,note,decision_note,created_at,decided_at,decided_by,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(uid,actor,'correction',iso(midnight(d)),iso(midnight(d+timedelta(days=1))),1,'approved',json.dumps(p),payload['note'],'Direkt gespeichert; keine Genehmigung erforderlich.',iso(now()),iso(now()),actor,json.dumps(payload)))
    if not work_id:audit(c,actor,uid,'correction',cur.lastrowid,'Tag ohne Arbeitszeit bestätigt',payload)
    if uid!=actor:notify(c,uid,'correction','Deine Arbeitszeit vom '+d.strftime('%d.%m.%Y')+' wurde korrigiert. Details stehen im Zeitverlauf.')
    return {'ok':True,'work_id':work_id,'state':'approved'}


def context(c,uid):
    perms=acl.permissions_for_user(c,uid)
    return {'policy_help':__import__('permission_help').POLICIES,'policy':policy(c),'permissions':sorted(perms),'kinds':[dict(r) for r in c.execute('SELECT * FROM absence_kinds WHERE active=1 ORDER BY name')],
      'people':[dict(r) for r in c.execute("SELECT u.id,u.username,p.first_name,p.last_name FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.active=1 ORDER BY u.username")],
      'subdivisions':list(holidays.DE.subdivisions),'today':str(now().astimezone(TZ).date())}

def inbox(c,uid):
    perms=acl.permissions_for_user(c,uid);can_review=bool(perms&{'absence.review','absence.review_unpaid','correction.review'})
    rows=c.execute("SELECT r.*,u.username FROM staff_requests r JOIN users u ON u.id=r.user_id WHERE r.state IN ('pending','awaiting_employee')"+('' if can_review else ' AND r.user_id=?')+' ORDER BY r.created_at',() if can_review else (uid,))
    out=[]
    for row in rows:
        r=dict(row);payload=json.loads(r['payload_json']);r['payload']=payload
        allowed=r['user_id']==uid
        if r['state']=='pending':
            key='correction.review' if r['kind']=='correction' else 'absence.review' if payload['kind']['rule']=='paid' else 'absence.review_unpaid'
            allowed|=key in perms
        if allowed:r['can_decide']=can_decide(c,uid,r,perms);out.append(r)
    return out

def account(c,actor,body):
    require(c,actor,'staff.manage');uid=int(body['user_id']);person(c,uid);year=int(body['year'])
    ent=Fraction(str(body['days']))*1_000_000;carry=Fraction(str(body.get('carry',0)))*1_000_000
    if not 2000<=year<=2200 or min(ent,carry)<0 or max(ent,carry)>366_000_000:raise ValueError('Ungültiger Urlaubsanspruch.')
    until=str(body.get('carry_until') or '')
    if until and date.fromisoformat(until).year!=year:raise ValueError('Übertragsfrist muss im Urlaubsjahr liegen.')
    c.execute('DELETE FROM vacation_accounts WHERE user_id=? AND year=?',(uid,year))
    c.execute('INSERT INTO vacation_accounts VALUES(?,?,?,?,?)',(uid,year,int(ent),int(carry),until))
    if vacation_balance(c,uid,year)['after_pending']<0:raise ValueError('Anspruch unterschreitet bereits genehmigten oder reservierten Urlaub.')
    audit(c,actor,uid,'vacation_account',year,'changed',body);return {'ok':True}

def movement(c,actor,body):
    require(c,actor,'payroll.manage');uid=int(body['user_id']);person(c,uid);d=date.fromisoformat(body['day']);kind=body['kind'];note=str(body.get('note') or '').strip()
    if d>now().astimezone(TZ).date():raise ValueError('Keine zukünftigen Kontobuchungen.')
    if c.execute('SELECT 1 FROM staff_month_closures WHERE user_id=? AND month=?',(uid,str(d)[:7])).fetchone():raise ValueError('Buchung in einen abgeschlossenen Monat nicht möglich. Aktuelles Buchungsdatum verwenden.')
    if not note or kind not in ('payout','adjustment'):raise ValueError('Art und Begründung erforderlich.')
    amount=seconds(abs(Fraction(str(body['hours']))))
    if not amount:raise ValueError('Bitte einen Stundenbetrag größer als null eintragen.')
    if kind=='payout':amount=-amount
    elif Fraction(str(body['hours']))<0:amount=-amount
    if kind=='payout' and account_balance(c,uid,d)['balance_seconds']+amount<0:raise ValueError('Nicht genügend gebuchte Überstunden für diese Auszahlung.')
    import uuid
    c.execute('INSERT INTO staff_movements(user_id,day,seconds,kind,note,created_by,created_at,source_key) VALUES(?,?,?,?,?,?,?,?)',(uid,str(d),amount,kind,note[:2000],actor,iso(now()),uuid.uuid4().hex))
    audit(c,actor,uid,'time_account',str(d),kind,{'seconds':amount,'note':note})
    notify(c,uid,'time_account',('Überstunden ausgezahlt' if kind=='payout' else 'Stundenkonto korrigiert')+' · '+d.strftime('%d.%m.%Y')+' · '+str(round(amount/3600,2))+' Stunden · '+note[:200])
    return {'ok':True}

def close_month(c,actor,body):
    require(c,actor,'payroll.manage');uid=int(body['user_id']);month=str(body['month']);report=month_report(c,uid,month)
    if any(d['state']!='closed' for d in report['days']):raise ValueError('Monat enthält offene, zukünftige oder ungeklärte Tage.')
    if report['closure']:raise ValueError('Monat bereits abgeschlossen. Änderungen werden als Korrekturbuchung erfasst.')
    snapshot={'posted_seconds':report['posted_seconds'],'days':report['days']}
    c.execute('INSERT INTO staff_month_closures VALUES(?,?,?,?,?)',(uid,month,json.dumps(snapshot),actor,iso(now())))
    audit(c,actor,uid,'payroll_month',month,'closed',snapshot);return {'ok':True}

def reopen_month(c,actor,body):
    require(c,actor,'payroll.manage');uid=int(body['user_id']);month=str(body['month']);note=str(body.get('note') or '').strip()
    if not note:raise ValueError('Zum Wiederöffnen ist eine Begründung erforderlich.')
    row=c.execute('SELECT * FROM staff_month_closures WHERE user_id=? AND month=?',(uid,month)).fetchone()
    if not row:raise ValueError('Dieser Monat ist nicht abgeschlossen.')
    snapshot=json.loads(row['snapshot_json'])
    c.execute('DELETE FROM staff_month_closures WHERE user_id=? AND month=?',(uid,month))
    audit(c,actor,uid,'payroll_month',month,'reopened',{'note':note[:2000],'previous_closure':snapshot,'closed_at':row['created_at'],'closed_by':row['created_by']})
    notify(c,uid,'time_account','Abrechnungsmonat '+month+' wurde wieder geöffnet · '+note[:200])
    return {'ok':True}

def payroll_overview(c,actor,body):
    require(c,actor,'staff.view')
    month=str(body.get('month') or str(now().astimezone(TZ).date())[:7])
    start=date.fromisoformat(month+'-01');end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    target=int(body.get('user_id') or 0);status_filter=str(body.get('status') or 'all')
    if status_filter not in ('all','open','attention','closed'):raise ValueError('Ungültiger Statusfilter.')
    users=[dict(r) for r in c.execute('''SELECT u.id,u.username,p.first_name,p.last_name
      FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id
      WHERE u.active=1'''+(' AND u.id=?' if target else '')+' ORDER BY p.last_name,p.first_name,u.username',((target,) if target else ()))]
    today=now().astimezone(TZ).date();through=min(today,end-timedelta(days=1));rows=[]
    for user in users:
        report=month_report(c,user['id'],month);closure=c.execute('SELECT created_at,created_by FROM staff_month_closures WHERE user_id=? AND month=?',(user['id'],month)).fetchone()
        problem_days=sum(d['state'] in ('unresolved','unconfigured') for d in report['days'])
        future_days=sum(d['state'] in ('planned','provisional') for d in report['days'])
        item_status='closed' if closure else 'attention' if problem_days else 'open'
        if status_filter!='all' and item_status!=status_filter:continue
        display=' '.join(x for x in (user.get('first_name'),user.get('last_name')) if x).strip() or user['username']
        balance=account_balance(c,user['id'],through) if through>=start else {'balance_seconds':0,'unresolved_days':0,'configured':bool(report['models'])}
        payouts=sum(-m['seconds'] for m in report['movements'] if m['kind']=='payout')
        rows.append({'user_id':user['id'],'username':user['username'],'name':display,'status':item_status,
          'configured':bool(report['models']),'posted_seconds':report['posted_seconds'],'movement_seconds':report['movement_seconds'],
          'balance_seconds':balance['balance_seconds'],'problem_days':problem_days,'future_days':future_days,
          'payout_seconds':payouts,'movement_count':len(report['movements']),'revision_seconds':report['revision_seconds'],
          'closed_at':closure['created_at'] if closure else '', 'closed_by':closure['created_by'] if closure else None,
          'can_close':not closure and not problem_days and not future_days and all(d['state']=='closed' for d in report['days'])})
    movements=[dict(r) for r in c.execute('''SELECT m.*,u.username,p.first_name,p.last_name
      FROM staff_movements m JOIN users u ON u.id=m.user_id LEFT JOIN user_profiles p ON p.user_id=u.id
      WHERE m.day>=? AND m.day<?'''+(' AND m.user_id=?' if target else '')+' ORDER BY m.day DESC,m.id DESC',(str(start),str(end),*((target,) if target else ())))]
    return {'month':month,'rows':rows,'movements':movements,'summary':{
      'employees':len(rows),'closed':sum(r['status']=='closed' for r in rows),'attention':sum(r['status']=='attention' for r in rows),
      'balance_seconds':sum(r['balance_seconds'] for r in rows),'payout_seconds':sum(r['payout_seconds'] for r in rows)}}

def payroll_export(c,actor,body):
    data=payroll_overview(c,actor,{**body,'status':body.get('status') or 'all'})
    stream=io.StringIO();writer=csv.writer(stream,delimiter=';',lineterminator='\n')
    writer.writerow(['Mitarbeiter','Benutzername','Monat','Status','Monatsdifferenz (Sek.)','Bewegungen (Sek.)','Stundenkonto (Sek.)','Ausgezahlt (Sek.)','Klärungstage','Abgeschlossen am'])
    labels={'open':'Offen','attention':'Klärung erforderlich','closed':'Abgeschlossen'}
    def cell(value):
        text=str(value or '')
        return "'"+text if text[:1] in ('=','+','-','@') else text
    for row in data['rows']:
        writer.writerow([cell(row['name']),cell(row['username']),data['month'],labels[row['status']],row['posted_seconds'],row['movement_seconds'],row['balance_seconds'],row['payout_seconds'],row['problem_days'],row['closed_at']])
    return {'filename':'mitarbeiterabrechnung-'+data['month']+'.csv','content':'\ufeff'+stream.getvalue(),'content_type':'text/csv;charset=utf-8'}

def kind_save(c,actor,body):
    require(c,actor,'staff.policy');code=str(body['code']);name=str(body['name']).strip();rule=body['rule'];color=str(body.get('color') or '#62a5fa')
    import re
    if not re.fullmatch('[a-z][a-z0-9_-]{1,40}',code) or not name or rule not in ('paid','debit','reduce') or not re.fullmatch('#[0-9a-fA-F]{6}',color):raise ValueError('Tagesart ungültig.')
    old=c.execute('SELECT * FROM absence_kinds WHERE code=?',(code,)).fetchone()
    c.execute('DELETE FROM absence_kinds WHERE code=?',(code,))
    c.execute('INSERT INTO absence_kinds VALUES(?,?,?,?,?,?)',(code,name[:120],rule,int(body.get('vacation') is True),color,int(body.get('active',True) is True)))
    audit(c,actor,actor,'absence_kind',code,'changed',{'before':dict(old) if old else None,'after':body});return {'ok':True}

def calendar_data(c,uid,start,end):
    result=[]
    rows=[dict(r) for r in c.execute("SELECT r.*,u.username FROM staff_requests r JOIN users u ON u.id=r.user_id WHERE r.start_at<? AND r.end_at>? AND (r.state='approved' OR (r.user_id=? AND r.state IN ('pending','awaiting_employee'))) ORDER BY r.start_at",(iso(midnight(end)),iso(midnight(start)),uid))]
    for r in rows:
        if r['kind'] in ('cancel','correction'):continue
        own=r['user_id']==uid;meta=json.loads(r['payload_json'])['kind']
        spans=request_spans(r,rows)
        if r['kind']=='vacation':
            cuts=[span for sick in rows if sick['user_id']==r['user_id'] and sick['kind']=='sick' and sick['state']=='approved' for span in request_spans(sick,rows)]
            spans=subtract(spans,cuts)
        for a,b in spans:
            result.append({'id':r['id'],'user_id':r['user_id'],'employee':r['username'],'type':'absence','start':iso(a),'end':iso(b),'whole_day':bool(r['whole_day']),'title':meta['name'] if own else 'Abwesend','state':r['state'],'color':meta['color'] if own else '#8a9bad','details':r['note'] if own else ''})
    data=dataset(c,uid,start,end)
    for d in days(start,end):
        title=holiday_name(model_on(data['models'],d),d,data['overrides'])
        if title:result.append({'id':str(d),'user_id':uid,'employee':'','type':'holiday','title':title,'start':iso(midnight(d)),'end':iso(midnight(d+timedelta(days=1))),'whole_day':True,'state':'planned'})
    team=acl.can(c,uid,'calendar.work_team');owner_sql='' if team else ' AND w.owner_id=?';args=(iso(midnight(end)),iso(midnight(start)))+(() if team else (uid,))
    for table,kind in [('work_sessions','work'),('work_pauses','pause')]:
        for r in c.execute('SELECT w.*,u.username FROM '+table+' w JOIN users u ON u.id=w.owner_id WHERE w.started_at<? AND (w.ended_at IS NULL OR w.ended_at>?)'+owner_sql,args):result.append({'id':r['id'],'user_id':r['owner_id'],'employee':r['username'],'type':kind,'title':'Arbeitszeit' if kind=='work' else 'Pause','start':r['started_at'],'end':r['ended_at'] or iso(now()),'state':'running' if not r['ended_at'] else 'recorded'})
    for r in c.execute('SELECT w.*,p.name,u.username FROM entries w JOIN projects p ON p.id=w.project_id JOIN users u ON u.id=w.owner_id WHERE w.is_idle=0 AND w.started_at<? AND (w.ended_at IS NULL OR w.ended_at>?)'+owner_sql,args):result.append({'id':r['id'],'user_id':r['owner_id'],'employee':r['username'],'type':'project','title':r['name'],'start':r['started_at'],'end':r['ended_at'] or iso(now()),'state':'running' if not r['ended_at'] else 'recorded'})
    import duty_plan
    for r in duty_plan.listing(c,uid,{'from':str(start),'to':str(end-timedelta(days=1))})['slots']:result.append({'id':r['id'],'user_id':r['user_id'],'employee':r['username'],'type':'duty','title':r['name'],'start':r['starts'],'end':r['ends'],'state':'planned'})
    return result

def handle(c,uid,action,body):
    if action=='account/read':
        require(c,uid,'staff.manage');target=int(body.get('user_id') or uid);year=int(body.get('year') or now().year)
        if not c.execute('SELECT id FROM users WHERE id=?',(target,)).fetchone():raise ValueError('Mitarbeiter nicht gefunden.')
        if not 2000<=year<=2099:raise ValueError('Ungültiges Jahr.')
        row=c.execute('SELECT * FROM vacation_accounts WHERE user_id=? AND year=?',(target,year)).fetchone()
        return {'year':year,'days':row['entitlement']/1000000 if row else 0,'carry':row['carry']/1000000 if row else 0,'carry_until':row['carry_until'] if row else ''}

    if action=='history/read':return time_history(c,uid,body)
    if action=='notifications/detail':return notification_detail(c,uid,body)
    if action=='notifications/list':return notifications(c,uid,body)
    if action=='notifications/seen':return notification_seen(c,uid,body)
    if action=='movement/preview':return movement_preview(c,uid,body)
    if action=='movement/reverse':return reverse_movement(c,uid,body)
    if action=='payroll/overview':return payroll_overview(c,uid,body)
    if action=='payroll/export':return payroll_export(c,uid,body)
    if action=='context':return context(c,uid)
    if action=='tracking/report':return tracking_report(c,uid,body)
    if action=='report':
        target=int(body.get('user_id') or uid)
        if target!=uid:require(c,uid,'staff.view')
        month=str(body.get('month') or str(now().astimezone(TZ).date())[:7]);report=month_report(c,target,month)
        report['vacation']=vacation_balance(c,target,int(month[:4]));report['account']=account_balance(c,target)
        if target!=uid and not acl.can(c,uid,'absence.review'):
            for r in report['requests']:r.update(note='',decision_note='',payload={},payload_json='{}',kind='absence')
        return report
    if action=='absence/preview':return absence_preview(c,uid,body)
    if action=='inbox':return {'requests':inbox(c,uid)}
    if action=='calendar':
        a=date.fromisoformat(body['from']);b=date.fromisoformat(body['to'])+timedelta(days=1)
        if not 0<(b-a).days<=366:raise ValueError('Kalenderzeitraum ungültig.')
        return {'events':calendar_data(c,uid,a,b),'day_bounds':[{'day':str(d),'start':iso(midnight(d)),'end':iso(midnight(d+timedelta(days=1)))} for d in days(a,b)]}
    handlers={'model/save':save_model,'policy/save':save_policy,'account/save':account,'absence/submit':submit,'absence/cancel':cancellation,'absence/approve':decide,'correction/submit':correction,'movement/pay':movement,'month/close':close_month,'month/reopen':reopen_month,'kind/save':kind_save}
    if action not in handlers:raise ValueError('Unbekannte Arbeitszeitaktion.')
    return handlers[action](c,uid,body)


def conflicts(c,uid,a,b,kind,exclude=0,approved_only=False):
    data=dataset(c,uid,a.astimezone(TZ).date(),b.astimezone(TZ).date()+timedelta(days=1))
    states={'approved'} if approved_only else {'approved','pending','awaiting_employee'}
    new_meta=c.execute('SELECT vacation FROM absence_kinds WHERE code=?',(kind,)).fetchone()
    for r in data['requests']:
        if r['id']==exclude or r['state'] not in states or r['kind'] in ('cancel','correction'):continue
        if (kind=='sick' and r['payload']['kind'].get('vacation')) or (r['kind']=='sick' and new_meta and new_meta['vacation']):continue
        if any(x<b and y>a for x,y in request_spans(r,data['requests'])):return True
    return False


def account_balance(c,uid,through=None):
    through=through or now().astimezone(TZ).date();models=model_list(c,uid)
    if not models:return {'balance_seconds':0,'unresolved_days':0,'configured':False}
    start=date.fromisoformat(models[0]['valid_from']);end=through+timedelta(days=1)
    if start>end:return {'balance_seconds':0,'unresolved_days':0,'configured':True}
    closures={r['month']:json.loads(r['snapshot_json']) for r in c.execute('SELECT * FROM staff_month_closures WHERE user_id=? AND month<=?',(uid,str(through)[:7]))}
    total=models[0]['opening_seconds'];unresolved=0;cursor=start.replace(day=1);all_data=dataset(c,uid,start,end)
    while cursor<end:
        next_month=(cursor.replace(day=28)+timedelta(days=4)).replace(day=1);key=str(cursor)[:7]
        if key in closures:
            snapshot=closures[key]
            total+=sum(r['posted_seconds'] for r in snapshot.get('days',[]) if start<=date.fromisoformat(r['day'])<=through) if snapshot.get('days') else snapshot['posted_seconds']
        else:
            first=max(cursor,start);last=min(next_month,end);a=iso(midnight(first));b=iso(midnight(last));data={**all_data,'work':[r for r in all_data['work'] if r['started_at']<b and (not r['ended_at'] or r['ended_at']>a)],'pauses':[r for r in all_data['pauses'] if r['started_at']<b and (not r['ended_at'] or r['ended_at']>a)],'requests':[r for r in all_data['requests'] if r['start_at']<b and r['end_at']>a]}
            for d in days(first,last):
                value=daily(data,d);total+=value['posted_seconds'];unresolved+=value['state']=='unresolved'
        cursor=next_month
    total+=int(c.execute('SELECT COALESCE(SUM(seconds),0) AS total FROM staff_movements WHERE user_id=? AND day<=?',(uid,str(through))).fetchone()['total'])
    return {'balance_seconds':total,'unresolved_days':unresolved,'configured':True}


def entry_correction(c,actor,body):
    p=policy(c)
    if p['correction_mode']=='none':raise PermissionError('Eigene Stempelkorrekturen sind ausgeschaltet.')
    r=c.execute('SELECT * FROM entries WHERE owner_id=? AND id=?',(actor,int(body['id']))).fetchone()
    if not r:raise PermissionError('Stempelung nicht zugänglich.')
    d=parse(r['started_at']).astimezone(TZ).date()
    if c.execute('SELECT 1 FROM staff_month_closures WHERE user_id=? AND month=?',(actor,str(d)[:7])).fetchone():raise ValueError('Monat abgeschlossen. Korrektur über die Buchhaltung.')
    for field in ('started_at','ended_at'):
        value=body.get(field)
        if value and c.execute('SELECT 1 FROM staff_month_closures WHERE user_id=? AND month=?',(actor,str(parse(value).astimezone(TZ).date())[:7])).fetchone():raise ValueError('Zielmonat ist abgeschlossen.')
    import workday
    workday.edit(c,actor,body,now())
    after=dict(c.execute('SELECT * FROM entries WHERE id=?',(r['id'],)).fetchone())
    audit(c,actor,actor,'worktime',r['work_session_id'] or 'entry:'+str(r['id']),'Projektstempelung korrigiert',{'day':str(d),'before':dict(r),'after':after})
    return {'ok':True,'state':'approved','message':'Direkt gespeichert. Änderung im Verlauf dokumentiert.'}


def absence_preview(c,uid,body):
    target=int(body.get('user_id') or uid)
    if target!=uid:require(c,uid,'absence.enter_other')
    a,b,whole=request_range(body);meta=c.execute('SELECT * FROM absence_kinds WHERE code=? AND active=1',(str(body['kind']),)).fetchone()
    if not meta:raise ValueError('Tagesart fehlt.')
    meta=dict(meta);p=policy(c)
    if meta['vacation'] and not whole and not p['hourly_paid']:raise ValueError('Stundenurlaub ist nicht freigegeben.')
    if conflicts(c,target,a,b,meta['code']):raise ValueError('Zeitraum überschneidet eine andere Abwesenheit.')
    proposal={'id':-1,'user_id':target,'kind':meta['code'],'start_at':iso(a),'end_at':iso(b),'whole_day':whole,'state':'pending','parent_id':None,'payload':{'kind':meta},'policy':p}
    years=[]
    for year in range(a.astimezone(TZ).year,(b-timedelta(seconds=1)).astimezone(TZ).year+1):
        before=vacation_balance(c,target,year);after=vacation_balance(c,target,year,[proposal]);years.append({'year':year,'days_requested':(after['approved']+after['pending']-before['approved']-before['pending'])/1_000_000,'remaining_days':after['after_pending']/1_000_000,'configured':before['configured']})
    return {'years':years,'approval_required':p['approval_paid' if meta['rule']=='paid' else 'approval_unpaid'],'can_submit':not meta['vacation'] or all(x['configured'] and x['remaining_days']>=0 for x in years)}


_base_work_overview=wm.overview

def work_overview(c,uid,body,clock=None):
    result=_base_work_overview(c,uid,body,clock)
    selected=date.fromisoformat(result['selected_day']);start=min(selected.replace(day=1),date.fromisoformat(result['week_start']));end=max((selected.replace(day=28)+timedelta(days=4)).replace(day=1),date.fromisoformat(result['week_end'])+timedelta(days=1))
    data=dataset(c,uid,start,end);rows=[]
    for d in days(start,end):
        r=daily(data,d,clock);closed=r['state']=='closed';credit=r['credit_seconds']+r['reduction_seconds'];target=r['target_seconds']
        rows.append({'day':str(d),'target_seconds':target,'actual_seconds':r['worked_seconds'],'pause_seconds':0,'holiday':r['holiday'] or ', '.join(r['labels']),'holiday_seconds':credit,'holiday_pending_seconds':r['planned_credit_seconds'] if r['state'] in ('planned','provisional') else 0,'difference_seconds':r['posted_seconds'] if closed else None,'remaining_seconds':max(0,target-r['worked_seconds']-r['planned_credit_seconds']) if target is not None else None,'closed':d<date.fromisoformat(result['today']),'future':d>date.fromisoformat(result['today']),'unclosed_work':r['state']=='unresolved','model_id':model_on(data['models'],d)['id'] if model_on(data['models'],d) else None})
    pauses={r['day']:r['pause_seconds'] for r in result['days']}
    for r in rows:r['pause_seconds']=pauses.get(r['day'],0)
    result['day']=next(r for r in rows if r['day']==str(selected));result['days']=[r for r in rows if r['day'][:7]==str(selected)[:7]]
    result['week']=wm.summarize([r for r in rows if result['week_start']<=r['day']<=result['week_end']]);result['month']=wm.summarize(result['days']);return result


def notify(c,uid,kind,message,request_id=None,project_id=None):
    ident=c.execute('INSERT INTO user_notifications(user_id,kind,message,created_at) VALUES(?,?,?,?)',(uid,kind,message,iso(now()))).lastrowid
    if request_id or project_id:c.execute('INSERT INTO notification_links VALUES(?,?,?)',(ident,request_id,project_id))

def reconcile_closed_months(c,actor,uid,a,b):
    import uuid
    months=[r['month'] for r in c.execute('SELECT month FROM staff_month_closures WHERE user_id=? AND month>=? AND month<=?',(uid,str(a.astimezone(TZ).date())[:7],str((b-timedelta(seconds=1)).astimezone(TZ).date())[:7]))]
    for month in months:
        report=month_report(c,uid,month)
        if any(r['target_seconds'] is None for r in report['days']):raise ValueError('Arbeitszeitmodell des abgeschlossenen Monats fehlt.')
        difference=sum(r['delta_seconds'] or 0 for r in report['days'])-report['closure']['posted_seconds']
        prior=c.execute('SELECT seconds FROM staff_month_revisions WHERE user_id=? AND month=?',(uid,month)).fetchone()
        change=difference-(prior['seconds'] if prior else 0)
        if not change:continue
        c.execute('INSERT INTO staff_movements(user_id,day,seconds,kind,note,created_by,created_at,source_key) VALUES(?,?,?,?,?,?,?,?)',(uid,str(now().astimezone(TZ).date()),change,'adjustment','Nachberechnung genehmigter Abwesenheit für '+month,actor,iso(now()),uuid.uuid4().hex))
        c.execute('DELETE FROM staff_month_revisions WHERE user_id=? AND month=?',(uid,month));c.execute('INSERT INTO staff_month_revisions VALUES(?,?,?)',(uid,month,difference))
        audit(c,actor,uid,'payroll_revision',month,'posted',{'seconds':change,'total_revision':difference})


def can_decide(c,uid,r,perms=None):
    if r['state']=='awaiting_employee':return uid==r['user_id']
    if r['state']!='pending':return False
    payload=r.get('payload') if isinstance(r,dict) else None
    payload=payload or json.loads(r['payload_json']);p=json.loads(r['policy_json'])
    key='correction.review' if r['kind']=='correction' else 'absence.review' if payload['kind']['rule']=='paid' else 'absence.review_unpaid'
    if perms is None:perms=acl.permissions_for_user(c,uid)
    if key not in perms:return False
    if uid==r['user_id']:return p['self_approval'] and ('correction.review_self' if r['kind']=='correction' else 'absence.review_self') in perms
    return True


def tracking_report(c,actor,body):
    uid=int(body.get('user_id') or actor)
    if uid!=actor:require(c,actor,'staff.view')
    selected=wm.day_value(body.get('day') or now().astimezone(TZ).date());mode=body.get('mode','week')
    if mode=='day':start=selected;end=start+timedelta(days=1)
    elif mode=='week':start=selected-timedelta(days=selected.weekday());end=start+timedelta(days=7)
    elif mode=='month':start=selected.replace(day=1);end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    else:raise ValueError('Tag, Woche oder Monat wählen.')
    data=dataset(c,uid,start,end);rows=[daily(data,d) for d in days(start,end)]
    prior=account_balance(c,uid,start-timedelta(days=1));balance=prior['balance_seconds'];configured=prior['configured']
    movements=[dict(r) for r in c.execute('SELECT * FROM staff_movements WHERE user_id=? AND day>=? AND day<? ORDER BY day,id',(uid,str(start),str(end)))]
    closures={r['month']:json.loads(r['snapshot_json']) for r in c.execute('SELECT * FROM staff_month_closures WHERE user_id=? AND month>=? AND month<=?',(uid,str(start)[:7],str(end-timedelta(days=1))[:7]))}
    frozen={d['day']:d for closure in closures.values() for d in closure.get('days',[])}
    for r in rows:
        a=midnight(date.fromisoformat(r['day']));b=midnight(date.fromisoformat(r['day'])+timedelta(days=1))
        clock=now();r['work']=[{'id':w['id'],'start':iso(max(parse(w['started_at']),a)),'end':iso(min(parse(w['ended_at']),b)) if w['ended_at'] else (iso(b) if b<=clock else None)} for w in sorted(data['work'],key=lambda w:w['started_at']) if parse(w['started_at'])<min(b,clock) and (min(parse(w['ended_at']),clock) if w['ended_at'] else clock)>a]
        r['correction_seconds']=sum(m['seconds'] for m in movements if m['day']==r['day'] and m['kind'] in ('adjustment','payout_reversal'))
        r['payout_seconds']=-sum(m['seconds'] for m in movements if m['day']==r['day'] and m['kind']=='payout')
        booked=frozen.get(r['day'],r)['posted_seconds'];balance+=booked+r['correction_seconds']-r['payout_seconds']
        r['balance_seconds']=balance if configured and r['state'] not in ('unconfigured','planned') else None
        r['frozen']=r['day'] in frozen
    requests=data['requests']
    perms=acl.permissions_for_user(c,actor) if requests else set()
    for r in requests:r['can_decide']=can_decide(c,actor,r,perms)
    if uid!=actor:
        requests=[]
        for r in rows:r['labels']=['Abwesend'] if r['labels'] else []
    full_pauses=[dict(p) for p in c.execute('SELECT * FROM work_pauses WHERE owner_id=? ORDER BY started_at,id',(uid,))]
    return {'user_id':uid,'own':uid==actor,'from':str(start),'to':str(end-timedelta(days=1)),'day':str(selected),'mode':mode,'week_number':selected.isocalendar().week,'days':rows,'movements':movements,'work':[dict(w,pauses=[p for p in full_pauses if p['work_session_id']==w['id']]) for w in data['work']],'projects':[dict(r) for r in c.execute('SELECT e.*,p.name project_name FROM entries e JOIN projects p ON p.id=e.project_id WHERE e.owner_id=? AND e.is_idle=0 AND e.started_at<? AND (e.ended_at IS NULL OR e.ended_at>?) ORDER BY e.started_at',(uid,iso(midnight(end)),iso(midnight(start))))],'requests':requests,'account':account_balance(c,uid),'vacation':vacation_balance(c,uid,selected.year),'can_view_team':acl.can(c,actor,'staff.view')}


def time_history(c,actor,body):
    uid=int(body.get('user_id') or actor)
    if uid!=actor:require(c,actor,'staff.view')
    day=date.fromisoformat(body['day']);a,b=iso(midnight(day)),iso(midnight(day+timedelta(days=1)))
    work=[dict(x) for x in c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND started_at<? AND (ended_at IS NULL OR ended_at>?)',(uid,b,a))]
    ids=[str(w['id']) for w in work]
    condition='a.entity_id IN ('+','.join('?' for _ in ids)+') OR ' if ids else ''
    rows=c.execute("SELECT a.*,u.username,p.first_name,p.last_name FROM audit_events a LEFT JOIN users u ON u.id=a.actor_id LEFT JOIN user_profiles p ON p.user_id=a.actor_id WHERE a.owner_id=? AND a.entity_type IN ('worktime','work_correction','correction') AND ("+condition+"a.changes_json LIKE ?) ORDER BY a.id LIMIT 1000",(uid,*ids,'%"day": "'+str(day)+'"%'))
    events=[]
    for r in rows:
        changes=json.loads(r['changes_json']);name=((r['last_name'] or '')+', '+(r['first_name'] or '')).strip(', ') or r['username'] or 'Nicht dokumentiert'
        events.append({'id':r['id'],'action':r['action'],'created_at':r['created_at'],'actor':name,'changes':changes,'source':r['source']})
    return {'history':events,'employee_id':uid,'day':str(day)}


def notifications(c,uid,body):
    requests=[r for r in inbox(c,uid) if r['can_decide']]
    manager=acl.can(c,uid,'duty.manage')
    swaps=[dict(r) for r in c.execute("SELECT * FROM duty_swaps WHERE (state='pending' AND to_user=?)"+(" OR state='review'" if manager else '')+' ORDER BY created_at',(uid,))]
    rows=[dict(r) for r in c.execute('SELECT n.*,r.read_at,l.request_id,l.project_id FROM user_notifications n LEFT JOIN notification_links l ON l.notification_id=n.id LEFT JOIN notification_reads r ON r.user_id=n.user_id AND r.notification_id=n.id WHERE n.user_id=? ORDER BY n.id DESC LIMIT 200',(uid,))]
    unread=c.execute('SELECT COUNT(*) n FROM user_notifications n LEFT JOIN notification_reads r ON r.user_id=n.user_id AND r.notification_id=n.id WHERE n.user_id=? AND r.notification_id IS NULL',(uid,)).fetchone()['n']
    return {'notifications':rows,'requests':requests,'swaps':swaps,'unread':unread,'action_count':len(requests)+len(swaps)}


def notification_seen(c,uid,body):
    ident=int(body['id'])
    if not c.execute('SELECT id FROM user_notifications WHERE id=? AND user_id=?',(ident,uid)).fetchone():raise PermissionError('Benachrichtigung nicht zugänglich.')
    c.execute('INSERT OR IGNORE INTO notification_reads VALUES(?,?,?)',(uid,ident,iso(now())))
    return {'ok':True}


def reverse_movement(c,actor,body):
    require(c,actor,'payroll.manage');ident=int(body['id']);d=date.fromisoformat(body['day']);note=str(body.get('note') or '').strip()
    r=c.execute("SELECT * FROM staff_movements WHERE id=? AND kind='payout'",(ident,)).fetchone()
    if not r:raise ValueError('Auszahlung nicht gefunden.')
    if not note or d>now().astimezone(TZ).date() or str(d)<r['day']:raise ValueError('Begründung und gültiges Stornodatum ab Auszahlungsdatum erforderlich.')
    if c.execute('SELECT 1 FROM staff_month_closures WHERE user_id=? AND month=?',(r['user_id'],str(d)[:7])).fetchone():raise ValueError('Storno in einen offenen Monat buchen.')
    key='payout-reversal:'+str(ident)
    if c.execute('SELECT id FROM staff_movements WHERE source_key=?',(key,)).fetchone():raise ValueError('Auszahlung ist bereits storniert.')
    new_id=c.execute('INSERT INTO staff_movements(user_id,day,seconds,kind,note,created_by,created_at,source_key) VALUES(?,?,?,?,?,?,?,?)',(r['user_id'],str(d),-r['seconds'],'payout_reversal','Storno Auszahlung #'+str(ident)+': '+note[:1900],actor,iso(now()),key)).lastrowid
    audit(c,actor,r['user_id'],'time_account',new_id,'Auszahlung storniert',{'original_id':ident,'seconds':-r['seconds'],'note':note})
    notify(c,r['user_id'],'time_account','Auszahlung storniert · '+d.strftime('%d.%m.%Y')+' · '+str(round(-r['seconds']/3600,2))+' Stunden gutgeschrieben · '+note[:200])
    return {'ok':True,'id':new_id}


def movement_preview(c,actor,body):
    require(c,actor,'payroll.manage');uid=int(body.get('user_id') or actor);d=date.fromisoformat(body.get('day') or str(now().astimezone(TZ).date()))
    if d>now().astimezone(TZ).date():raise ValueError('Keine zukünftigen Kontobuchungen.')
    payouts=[dict(r) for r in c.execute("SELECT m.* FROM staff_movements m WHERE m.user_id=? AND m.kind='payout' ORDER BY m.day DESC,m.id DESC LIMIT 100",(uid,))]
    reversed_ids={r['source_key'] for r in c.execute("SELECT source_key FROM staff_movements WHERE user_id=? AND kind='payout_reversal'",(uid,))}
    return {'account':account_balance(c,uid,d),'payouts':[p for p in payouts if 'payout-reversal:'+str(p['id']) not in reversed_ids]}


def notification_detail(c,uid,body):
    r=c.execute('SELECT n.*,l.request_id,l.project_id FROM user_notifications n LEFT JOIN notification_links l ON l.notification_id=n.id WHERE n.id=? AND n.user_id=?',(int(body['id']),uid)).fetchone()
    if not r:raise PermissionError('Benachrichtigung nicht zugänglich.')
    result={'notification':dict(r)}
    if r['request_id']:
        request=c.execute('SELECT * FROM staff_requests WHERE id=?',(r['request_id'],)).fetchone()
        if request:
            request=dict(request);payload=json.loads(request['payload_json']);request['payload']=payload
            permitted=request['user_id']==uid or acl.can(c,uid,'absence.review' if payload.get('kind',{}).get('rule')=='paid' else 'absence.review_unpaid')
            if permitted:request['can_decide']=can_decide(c,uid,request);result['request']=request
    return result
