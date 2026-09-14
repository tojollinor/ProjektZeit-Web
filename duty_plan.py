"""Bounded on-call rotations and explicitly confirmed swaps."""
import json
from datetime import date,timedelta
import staff_time as st

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS duty_rotations(id INTEGER PRIMARY KEY,name VARCHAR(120) NOT NULL,starts VARCHAR(40) NOT NULL,ends VARCHAR(40) NOT NULL,period_days INTEGER NOT NULL,members_json LONGTEXT NOT NULL,review_swaps INTEGER NOT NULL,created_by INTEGER NOT NULL,created_at VARCHAR(40) NOT NULL);
    CREATE TABLE IF NOT EXISTS duty_slots(id INTEGER PRIMARY KEY,rotation_id INTEGER NOT NULL,user_id INTEGER NOT NULL,starts VARCHAR(40) NOT NULL,ends VARCHAR(40) NOT NULL,version INTEGER NOT NULL DEFAULT 1);
    CREATE INDEX IF NOT EXISTS idx_duty_dates ON duty_slots(starts,ends);
    CREATE TABLE IF NOT EXISTS duty_swaps(id INTEGER PRIMARY KEY,slot_id INTEGER NOT NULL,requested_by INTEGER NOT NULL,to_user INTEGER NOT NULL,starts VARCHAR(40) NOT NULL,ends VARCHAR(40) NOT NULL,slot_version INTEGER NOT NULL,state VARCHAR(24) NOT NULL,created_at VARCHAR(40) NOT NULL,decided_at VARCHAR(40),decided_by INTEGER);
    ''')

def save(c,uid,body):
    st.require(c,uid,'duty.manage');a=st.parse(body['from']);b=st.parse(body['to']);period=int(body.get('period_days',7));members=[int(x) for x in body['members']];name=str(body.get('name') or 'Notdienst').strip()[:120]
    if b<=a or (b-a).days>366 or not 1<=period<=31 or not 1<=len(members)<=100 or len(set(members))!=len(members):raise ValueError('Zeitraum maximal ein Jahr, Wechsel 1–31 Tage und eindeutige Mitarbeiter angeben.')
    if c.execute('SELECT 1 FROM duty_slots WHERE starts<? AND ends>?',(st.iso(b),st.iso(a))).fetchone():raise ValueError('Für diesen Zeitraum besteht bereits ein Notdienstplan.')
    for person in members:st.person(c,person)
    ident=c.execute('INSERT INTO duty_rotations(name,starts,ends,period_days,members_json,review_swaps,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(name,st.iso(a),st.iso(b),period,json.dumps(members),int(body.get('review_swaps',True) is True),uid,st.iso(st.now()))).lastrowid
    cursor=a.astimezone(st.TZ);index=0
    while cursor<b:
        end=min(b,cursor+timedelta(days=period));c.execute('INSERT INTO duty_slots(rotation_id,user_id,starts,ends) VALUES(?,?,?,?)',(ident,members[index%len(members)],st.iso(cursor),st.iso(end)));cursor=end;index+=1
    st.audit(c,uid,uid,'duty_plan',ident,'created',body);return {'ok':True,'id':ident}

def swap(c,uid,body):
    r=c.execute('SELECT * FROM duty_slots WHERE id=?',(int(body['id']),)).fetchone()
    if not r or r['user_id']!=uid:raise PermissionError('Nur eigenen Notdienst zum Tausch anbieten.')
    a=st.parse(body['from']);b=st.parse(body['to']);target=int(body['user_id']);st.person(c,target)
    if target==uid or a<st.now() or a<st.parse(r['starts']) or b>st.parse(r['ends']) or b<=a:raise ValueError('Zukünftigen Zeitraum innerhalb des eigenen Dienstes und anderen Mitarbeiter wählen.')
    if c.execute("SELECT 1 FROM duty_swaps WHERE slot_id=? AND state IN ('pending','review') AND starts<? AND ends>?",(r['id'],st.iso(b),st.iso(a))).fetchone():raise ValueError('Für diesen Zeitraum ist bereits ein Tausch offen.')
    ident=c.execute("INSERT INTO duty_swaps(slot_id,requested_by,to_user,starts,ends,slot_version,state,created_at) VALUES(?,?,?,?,?,?,'pending',?)",(r['id'],uid,target,st.iso(a),st.iso(b),r['version'],st.iso(st.now()))).lastrowid
    st.audit(c,uid,uid,'duty_swap',ident,'requested',body);return {'ok':True}

def decide(c,uid,body):
    r=c.execute('SELECT s.*,p.rotation_id,p.user_id,p.starts original_start,p.ends original_end,p.version,rot.review_swaps FROM duty_swaps s JOIN duty_slots p ON p.id=s.slot_id JOIN duty_rotations rot ON rot.id=p.rotation_id WHERE s.id=?',(int(body['id']),)).fetchone()
    if not r or r['state'] not in ('pending','review'):raise ValueError('Tausch bereits entschieden oder nicht vorhanden.')
    if r['state']=='pending' and r['to_user']!=uid:raise PermissionError('Nur der angefragte Mitarbeiter kann bestätigen.')
    if r['state']=='review':st.require(c,uid,'duty.manage')
    accept=body.get('approve') is True;state='rejected'
    if accept:
        if r['version']!=r['slot_version'] or r['user_id']!=r['requested_by']:raise ValueError('Dienstplan wurde verändert. Bitte Tausch neu anfragen.')
        if st.parse(r['starts'])<st.now():raise ValueError('Tauschzeitraum hat bereits begonnen.')
        if r['state']=='pending' and r['review_swaps']:state='review'
        else:
            st.person(c,r['to_user']);state='approved'
            c.execute('UPDATE duty_slots SET user_id=?,starts=?,ends=?,version=version+1 WHERE id=?',(r['to_user'],r['starts'],r['ends'],r['slot_id']))
            for a,b in [(r['original_start'],r['starts']),(r['ends'],r['original_end'])]:
                if st.parse(a)<st.parse(b):c.execute('INSERT INTO duty_slots(rotation_id,user_id,starts,ends) VALUES(?,?,?,?)',(r['rotation_id'],r['requested_by'],a,b))
    c.execute('UPDATE duty_swaps SET state=?,decided_at=?,decided_by=? WHERE id=?',(state,st.iso(st.now()),uid,r['id']))
    st.audit(c,uid,r['requested_by'],'duty_swap',r['id'],state,{});return {'ok':True,'state':state}

def listing(c,uid,body):
    a=date.fromisoformat(body['from']);b=date.fromisoformat(body['to'])+timedelta(days=1)
    if not 0<(b-a).days<=366:raise ValueError('Zeitraum maximal ein Jahr.')
    slots=[dict(r) for r in c.execute('SELECT s.*,u.username,r.name FROM duty_slots s JOIN users u ON u.id=s.user_id JOIN duty_rotations r ON r.id=s.rotation_id WHERE s.starts<? AND s.ends>? ORDER BY s.starts',(st.iso(st.midnight(b)),st.iso(st.midnight(a))))]
    admin=st.acl.can(c,uid,'duty.manage');requests=[dict(r) for r in c.execute("SELECT * FROM duty_swaps WHERE state IN ('pending','review')"+('' if admin else ' AND (requested_by=? OR to_user=?)'),() if admin else (uid,uid))]
    return {'slots':slots,'requests':requests}

HANDLERS={'duty/save':save,'duty/swap':swap,'duty/approve':decide,'duty/list':listing}
