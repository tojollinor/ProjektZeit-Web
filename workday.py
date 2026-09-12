"""Transactional workday tracking, pauses and non-overlapping entry corrections."""
from datetime import datetime, timezone


def stamp(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def migrate(c):
    if getattr(c, 'dialect', '') == 'mariadb':
        c.executescript('''CREATE TABLE IF NOT EXISTS work_sessions (
            id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
            started_at TEXT NOT NULL, ended_at TEXT);
            CREATE TABLE IF NOT EXISTS work_pauses (
              id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              work_session_id INTEGER NOT NULL REFERENCES work_sessions(id) ON DELETE CASCADE,
              started_at TEXT NOT NULL, ended_at TEXT);
            CREATE INDEX IF NOT EXISTS idx_work_pauses_owner ON work_pauses(owner_id,work_session_id,started_at);
            ALTER TABLE entries ADD COLUMN IF NOT EXISTS is_idle INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE entries ADD COLUMN IF NOT EXISTS work_session_id INTEGER REFERENCES work_sessions(id);
            ALTER TABLE projects ADD COLUMN IF NOT EXISTS active INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE projects ADD COLUMN IF NOT EXISTS is_system INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS open_owner INTEGER
              GENERATED ALWAYS AS (CASE WHEN ended_at IS NULL THEN owner_id ELSE NULL END) PERSISTENT;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_work_open ON work_sessions(open_owner);''')
        return
    c.execute("""CREATE TABLE IF NOT EXISTS work_sessions (
        id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
        started_at TEXT NOT NULL, ended_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS work_pauses (
        id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        work_session_id INTEGER NOT NULL REFERENCES work_sessions(id) ON DELETE CASCADE,
        started_at TEXT NOT NULL, ended_at TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_work_pauses_owner ON work_pauses(owner_id,work_session_id,started_at)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_work_open ON work_sessions(owner_id) WHERE ended_at IS NULL")
    for table, column, definition in (
        ('entries', 'is_idle', 'INTEGER NOT NULL DEFAULT 0'),
        ('entries', 'work_session_id', 'INTEGER REFERENCES work_sessions(id)'),
        ('projects', 'active', 'INTEGER NOT NULL DEFAULT 1'),
        ('projects', 'is_system', 'INTEGER NOT NULL DEFAULT 0'),
    ):
        if column not in [r['name'] for r in c.execute('PRAGMA table_info(%s)' % table)]:
            c.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, column, definition))


def idle_ids(c, uid):
    project = c.execute('SELECT id FROM projects WHERE owner_id=? AND is_system=1', (uid,)).fetchone()
    if not project:
        name = 'unproduktiv'
        if c.execute('SELECT 1 FROM projects WHERE owner_id=? AND name=?', (uid, name)).fetchone():
            name = 'unproduktiv (Arbeitszeit)'
        pid = c.execute('INSERT INTO projects(owner_id,name,is_system,active) VALUES(?,?,1,0)', (uid, name)).lastrowid
    else:
        pid = project['id']
    c.execute("INSERT OR IGNORE INTO categories(owner_id,name) VALUES(?,'Allgemein')", (uid,))
    cid = c.execute("SELECT id FROM categories WHERE owner_id=? AND name='Allgemein'", (uid,)).fetchone()['id']
    return pid, cid


def overlap(c, uid, start, end, exclude=None):
    for row in c.execute('SELECT id,started_at,ended_at FROM entries WHERE owner_id=? AND is_idle=0', (uid,)):
        if row['id'] == exclude:
            continue
        if (end is None or stamp(row['started_at']) < end) and (row['ended_at'] is None or stamp(row['ended_at']) > start):
            raise ValueError('Der Zeitraum überschneidet sich mit einer anderen Projektstempelung.')


def active_pause(c, uid, work_session_id=None):
    sql='SELECT * FROM work_pauses WHERE owner_id=? AND ended_at IS NULL'
    args=[uid]
    if work_session_id is not None:
        sql+=' AND work_session_id=?';args.append(work_session_id)
    return c.execute(sql+' ORDER BY id DESC LIMIT 1',tuple(args)).fetchone()


def reconcile(c, uid):
    """Persist unproductive time as complement of projects and pauses inside working periods."""
    sessions = c.execute('SELECT * FROM work_sessions WHERE owner_id=? ORDER BY started_at', (uid,)).fetchall()
    if not sessions:
        return
    pid, cid = idle_ids(c, uid)
    productive = c.execute('SELECT * FROM entries WHERE owner_id=? AND is_idle=0', (uid,)).fetchall()
    productive = sorted(productive, key=lambda r: stamp(r['started_at']))
    pauses = c.execute('SELECT * FROM work_pauses WHERE owner_id=? ORDER BY started_at', (uid,)).fetchall()
    for session in sessions:
        start = stamp(session['started_at']); end = stamp(session['ended_at']) if session['ended_at'] else None
        occupied=[]
        for row in productive:
            a=stamp(row['started_at']);b=stamp(row['ended_at']) if row['ended_at'] else None
            if row['work_session_id'] and row['work_session_id']!=session['id']: continue
            if b is not None and b<=start: continue
            if end is not None and a>=end: continue
            occupied.append((max(a,start), min(b,end) if b is not None and end else b))
        for row in pauses:
            if row['work_session_id']!=session['id']: continue
            a=stamp(row['started_at']);b=stamp(row['ended_at']) if row['ended_at'] else None
            occupied.append((max(a,start), min(b,end) if b is not None and end else b))
        occupied.sort(key=lambda x:x[0])
        gaps=[];cursor=start
        for a,b in occupied:
            if cursor is None: break
            if a>cursor:gaps.append((iso(cursor),iso(a)))
            if b is None:cursor=None;break
            if b>cursor:cursor=b
        if cursor is not None and (end is None or cursor<end):gaps.append((iso(cursor),iso(end) if end else None))
        old=list(c.execute('SELECT * FROM entries WHERE owner_id=? AND work_session_id=? AND is_idle=1',(uid,session['id'])))
        keep=set()
        for a,b in gaps:
            match=next((r for r in old if r['started_at']==a and r['id'] not in keep),None)
            if match:
                c.execute('UPDATE entries SET ended_at=? WHERE id=?',(b,match['id']));keep.add(match['id'])
            else:
                rowid=c.execute('INSERT INTO entries(owner_id,project_id,category_id,started_at,ended_at,is_idle,work_session_id) VALUES(?,?,?,?,?,1,?)',(uid,pid,cid,a,b,session['id'])).lastrowid;keep.add(rowid)
        for row in old:
            if row['id'] not in keep:c.execute('DELETE FROM entries WHERE id=?',(row['id'],))


def transition(c, uid, action, body, now):
    c.execute('BEGIN IMMEDIATE')
    current=c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND ended_at IS NULL',(uid,)).fetchone();t=iso(now)
    if action=='begin':
        if current:raise ValueError('Der Arbeitstag läuft bereits.')
        overlap(c,uid,now,None);c.execute('INSERT INTO work_sessions(owner_id,started_at) VALUES(?,?)',(uid,t));return
    if not current:raise ValueError('Bitte zuerst Arbeitsbeginn drücken.')
    pause=active_pause(c,uid,current['id'])
    if action=='pause':
        if pause:raise ValueError('Die Pause läuft bereits.')
        c.execute('UPDATE entries SET ended_at=? WHERE owner_id=? AND is_idle=0 AND ended_at IS NULL',(t,uid))
        c.execute('INSERT INTO work_pauses(owner_id,work_session_id,started_at) VALUES(?,?,?)',(uid,current['id'],t));reconcile(c,uid);return
    if action=='resume':
        if not pause:raise ValueError('Es läuft keine Pause.')
        c.execute('UPDATE work_pauses SET ended_at=? WHERE id=?',(t,pause['id']));reconcile(c,uid);return
    if pause:
        if action=='end':c.execute('UPDATE work_pauses SET ended_at=? WHERE id=?',(t,pause['id']))
        else:raise ValueError('Bitte zuerst die Pause beenden.')
    if action=='switch':
        pid,cid=body.get('project_id'),body.get('category_id')
        if not c.execute('SELECT 1 FROM projects WHERE id=? AND owner_id=? AND active=1 AND is_system=0',(pid,uid)).fetchone():raise ValueError('Bitte ein aktives Projekt auswählen.')
        if not c.execute('SELECT 1 FROM categories WHERE id=? AND owner_id=?',(cid,uid)).fetchone():raise ValueError('Bitte eine Zeitkategorie auswählen.')
        running=c.execute('SELECT * FROM entries WHERE owner_id=? AND is_idle=0 AND ended_at IS NULL',(uid,)).fetchone()
        if running and running['project_id']==pid and running['category_id']==cid:return
    c.execute('UPDATE entries SET ended_at=? WHERE owner_id=? AND is_idle=0 AND ended_at IS NULL',(t,uid))
    if action=='end':c.execute('UPDATE work_sessions SET ended_at=? WHERE id=?',(t,current['id']))
    elif action=='switch':
        overlap(c,uid,now,None);c.execute('INSERT INTO entries(owner_id,project_id,category_id,started_at,note,work_session_id) VALUES(?,?,?,?,?,?)',(uid,pid,cid,t,str(body.get('note',''))[:2000],current['id']))
    reconcile(c,uid)


def edit(c, uid, body, now):
    c.execute('BEGIN IMMEDIATE')
    row=c.execute('SELECT * FROM entries WHERE id=? AND owner_id=?',(body.get('id'),uid)).fetchone()
    if not row:raise ValueError('Stempelung nicht gefunden.')
    if body.get('original_start')!=row['started_at'] or body.get('original_end')!=row['ended_at'] or body.get('original_note')!=row['note']:raise ValueError('Die Stempelung wurde inzwischen geändert. Bitte neu öffnen.')
    note=str(body.get('note',''))[:2000]
    if not row['ended_at'] or (row['is_idle'] and not body.get('project_id')):
        c.execute('UPDATE entries SET note=? WHERE id=?',(note,row['id']));return
    a,b=stamp(body['started_at']),stamp(body['ended_at'])
    if b<=a or b>now:raise ValueError('Das Ende muss nach dem Start und darf nicht in der Zukunft liegen.')
    pid,cid=body.get('project_id'),body.get('category_id')
    if not c.execute('SELECT 1 FROM projects WHERE id=? AND owner_id=? AND is_system=0',(pid,uid)).fetchone() or not c.execute('SELECT 1 FROM categories WHERE id=? AND owner_id=?',(cid,uid)).fetchone():raise ValueError('Projekt oder Kategorie ist ungültig.')
    if row['work_session_id']:
        work=c.execute('SELECT * FROM work_sessions WHERE id=?',(row['work_session_id'],)).fetchone()
        if a<stamp(work['started_at']) or (work['ended_at'] and b>stamp(work['ended_at'])):raise ValueError('Die Stempelung muss innerhalb ihrer Arbeitszeit bleiben.')
    overlap(c,uid,a,b,row['id']);c.execute('UPDATE entries SET project_id=?,category_id=?,started_at=?,ended_at=?,note=?,is_idle=0 WHERE id=?',(pid,cid,iso(a),iso(b),note,row['id']));reconcile(c,uid)
