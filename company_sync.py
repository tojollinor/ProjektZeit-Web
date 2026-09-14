"""Durable provider scheduler. Network work runs in bounded child processes."""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
import staff_time as st
import provider_budget

_stop=threading.Event();_started=False

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS company_sync_settings(provider VARCHAR(32) PRIMARY KEY,enabled INTEGER NOT NULL,day_seconds INTEGER NOT NULL,night_seconds INTEGER NOT NULL,day_start INTEGER NOT NULL,day_end INTEGER NOT NULL,next_at INTEGER NOT NULL DEFAULT 0,cursor_user INTEGER NOT NULL DEFAULT 0,lease_until INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS company_sync_cursors(owner_id INTEGER NOT NULL,provider VARCHAR(32) NOT NULL,last_success VARCHAR(40) NOT NULL,last_full VARCHAR(40) NOT NULL,PRIMARY KEY(owner_id,provider));
    CREATE TABLE IF NOT EXISTS company_sync_jobs(owner_id INTEGER NOT NULL,provider VARCHAR(32) NOT NULL,id VARCHAR(64) NOT NULL,state VARCHAR(24) NOT NULL,started_at VARCHAR(40) NOT NULL,finished_at VARCHAR(40) NOT NULL,error VARCHAR(255) NOT NULL,result_json LONGTEXT NOT NULL,PRIMARY KEY(owner_id,provider));
    ''')
    for provider in provider_budget.DEFAULTS:c.execute('INSERT OR IGNORE INTO company_sync_settings(provider,enabled,day_seconds,night_seconds,day_start,day_end) VALUES(?,1,120,900,7,19)',(provider,))

def job(app,uid,provider):
    with app.db(read_only=True) as c:r=c.execute('SELECT * FROM company_sync_jobs WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
    if not r:return {'provider':provider,'state':'idle','error':'','result':None}
    r=dict(r)
    if r['state']=='running' and (st.now()-st.parse(r['started_at'])).total_seconds()>210:r.update(state='error',error='Abgleich unterbrochen; bitte erneut starten.')
    r['result']=json.loads(r.pop('result_json'));return r

def start_refresh(app,uid,provider,days=7,scheduled=False,full=False):
    if provider not in provider_budget.DEFAULTS:raise ValueError('Unbekannter Provider.')
    clock=int(time.time());key=uuid.uuid4().hex
    with app.db() as c:
        c.execute('BEGIN IMMEDIATE');st.person(c,uid);st.require(c,uid,'integrations.view')
        settings=c.execute('SELECT * FROM company_sync_settings WHERE provider=?'+(' FOR UPDATE' if getattr(c,'dialect','')=='mariadb' else ''),(provider,)).fetchone()
        old=c.execute('SELECT * FROM company_sync_jobs WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
        if settings['lease_until']>clock:
            if old and old['state']=='running':return dict(old)
            raise ValueError('Unternehmensweiter Abgleich läuft bereits. Bitte nach dessen Abschluss erneut versuchen.')
        if scheduled and (not settings['enabled'] or settings['next_at']>clock):return {'state':'idle','provider':provider}
        cursor=c.execute('SELECT * FROM company_sync_cursors WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
        full=full or not cursor or not cursor['last_full'] or (st.now()-st.parse(cursor['last_full'])).total_seconds()>=7*86400 or (st.now()-st.parse(cursor['last_success'])).total_seconds()>=6*86400
        hour=st.now().astimezone(st.TZ).hour;interval=settings['day_seconds'] if settings['day_start']<=hour<settings['day_end'] else settings['night_seconds']
        c.execute('UPDATE company_sync_settings SET lease_until=?,next_at=?,cursor_user=? WHERE provider=?',(clock+210,clock+interval,uid,provider))
        c.execute('DELETE FROM company_sync_jobs WHERE owner_id=? AND provider=?',(uid,provider))
        c.execute("INSERT INTO company_sync_jobs VALUES(?,?,?,'running',?,'','','{}')",(uid,provider,key,st.iso(st.now())))
    def monitor():
        ok=False
        try:
            env={**os.environ,'DATA_DIR':str(app.DATA_DIR),'PZ_SYNC_WORKER':'1'}
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),str(uid),provider,key,'1' if full else '0'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:ok=process.wait(timeout=180)==0
            except subprocess.TimeoutExpired:process.kill();process.wait()
        except Exception:pass
        finally:
            with app.db() as c:
                if not ok:c.execute("UPDATE company_sync_jobs SET state='error',finished_at=?,error='Abgleich abgebrochen oder Zeitlimit erreicht; lokale Daten bleiben erhalten.' WHERE owner_id=? AND provider=? AND id=? AND state='running'",(st.iso(st.now()),uid,provider,key))
                c.execute('UPDATE company_sync_settings SET lease_until=0,next_at=CASE WHEN next_at<? THEN ? ELSE next_at END WHERE provider=? AND lease_until=?',(int(time.time())+(300 if not ok else 0),int(time.time())+(300 if not ok else 0),provider,clock+210))
    threading.Thread(target=monitor,name='pz-sync-monitor',daemon=True).start()
    return {'id':key,'provider':provider,'state':'running','started_at':st.iso(st.now()),'error':'','result':None}

def worker(uid,provider,key,full=False):
    import runtime
    app=runtime.configure()
    provider_budget.initialize(app.DATA_DIR,create=False);provider_budget.install_transport()
    with app.db(read_only=True) as c:
        st.person(c,uid);st.require(c,uid,'integrations.view')
        row=c.execute('SELECT id,state FROM company_sync_jobs WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
        if not row or row['id']!=key or row['state']!='running':return
    import feature_runtime,provider_archive,provider_cache_runtime,zammad_cache_runtime
    try:
        if provider=='zammad':result=zammad_cache_runtime._full_refresh(app,uid,incremental=not full)
        else:
            config=feature_runtime.integration_config(app,uid,provider)
            if provider=='teamviewer':result=provider_archive.sync_teamviewer(app.db,uid,config,full=full)
            else:result=provider_archive.sync_starface(app.db,uid,config,full=full)
            with app.db() as c:provider_cache_runtime._set_state(c,uid,provider,'valid','Verbindung erfolgreich geprüft.')
        with app.db() as c:
            previous=c.execute('SELECT last_full FROM company_sync_cursors WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
            c.execute('DELETE FROM company_sync_cursors WHERE owner_id=? AND provider=?',(uid,provider))
            c.execute('INSERT INTO company_sync_cursors VALUES(?,?,?,?)',(uid,provider,st.iso(st.now()),st.iso(st.now()) if full else previous['last_full'] if previous else ''))
            c.execute("UPDATE company_sync_jobs SET state='success',finished_at=?,result_json=? WHERE owner_id=? AND provider=? AND id=?",(st.iso(st.now()),json.dumps(result),uid,provider,key))
    except Exception:
        with app.db() as c:c.execute("UPDATE company_sync_jobs SET state='error',finished_at=?,error='Providerabgleich fehlgeschlagen. Verbindung und Abfragebudget in der Werkstatt prüfen.' WHERE owner_id=? AND provider=? AND id=?",(st.iso(st.now()),uid,provider,key))
        raise

def start_scheduler(app):
    global _started
    if _started or os.environ.get('PZ_SYNC_WORKER')=='1':return
    _started=True
    def loop():
        while not _stop.wait(5):
            try:
                with app.db(read_only=True) as c:
                    settings=[dict(r) for r in c.execute('SELECT * FROM company_sync_settings WHERE enabled=1 AND next_at<=? AND lease_until<=?',(int(time.time()),int(time.time())))]
                    credentials=[dict(r) for r in c.execute("SELECT i.owner_id,i.provider FROM integrations i JOIN users u ON u.id=i.owner_id WHERE u.active=1 AND i.secret<>'' UNION SELECT o.owner_id,'starface' provider FROM oauth_tokens o JOIN users u ON u.id=o.owner_id WHERE u.active=1")]
                    allowed={r['owner_id'] for r in credentials if st.acl.can(c,r['owner_id'],'integrations.view')}
                for setting in settings:
                    users=sorted({r['owner_id'] for r in credentials if r['provider']==setting['provider'] and r['owner_id'] in allowed})
                    if users:
                        chosen=next((x for x in users if x>setting['cursor_user']),users[0]);start_refresh(app,chosen,setting['provider'],scheduled=True)
            except Exception:continue
    threading.Thread(target=loop,name='pz-provider-scheduler',daemon=True).start()

def settings_save(c,uid,body):
    st.require(c,uid,'sync.manage');provider=body['provider'];day=int(body['day_seconds']);night=int(body['night_seconds']);a=int(body['day_start']);b=int(body['day_end'])
    if provider not in provider_budget.DEFAULTS or not 60<=day<=86400 or not day<=night<=86400 or not 0<=a<b<=24:raise ValueError('Intervalle mindestens 60 Sekunden, nachts mindestens Tagesintervall; Tagesfenster 0–24 Uhr.')
    c.execute('UPDATE company_sync_settings SET enabled=?,day_seconds=?,night_seconds=?,day_start=?,day_end=? WHERE provider=?',(int(body.get('enabled') is True),day,night,a,b,provider))
    # Budget has its own transaction to prevent long provider handlers holding its lock.
    provider_budget.set_cap(provider,body['cap']);st.audit(c,uid,uid,'sync_settings',provider,'saved',body);return {'ok':True}

def status(c,uid,body):
    st.require(c,uid,'sync.manage')
    return {'settings':[dict(r) for r in c.execute('SELECT * FROM company_sync_settings')],'budget':provider_budget.snapshot(),'jobs':[dict(r) for r in c.execute('SELECT owner_id,provider,state,started_at,finished_at,error FROM company_sync_jobs')],'realtime':{'state':'unverified','message':'Echtzeit-Unterstützung dieser Serverversionen ist noch nicht nachgewiesen. Automatischer Hintergrundabgleich ist verfügbar.'}}

HANDLERS={'sync/save':settings_save,'sync/status':status}

if __name__=='__main__':worker(int(sys.argv[1]),sys.argv[2],sys.argv[3],len(sys.argv)>4 and sys.argv[4]=='1')
