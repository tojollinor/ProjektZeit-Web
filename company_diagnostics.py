"""Opt-in isolated provider probes: no cached events or time bookings are written."""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
import staff_time as st
import provider_budget

def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS company_probes(id VARCHAR(64) PRIMARY KEY,owner_id INTEGER NOT NULL,provider VARCHAR(32) NOT NULL,state VARCHAR(24) NOT NULL,started_at VARCHAR(40) NOT NULL,finished_at VARCHAR(40) NOT NULL,report_json LONGTEXT NOT NULL);''')

def start(app,uid,body):
    provider=body['provider']
    if provider not in provider_budget.DEFAULTS:raise ValueError('Provider ungültig.')
    ident=uuid.uuid4().hex
    with app.db() as c:
        st.require(c,uid,'sync.diagnostics')
        if c.execute("SELECT 1 FROM company_probes WHERE owner_id=? AND state='running' AND started_at>?",(uid,st.iso(st.now()-st.timedelta(seconds=40)))).fetchone():raise ValueError('Ein Test läuft bereits. Bitte zuerst stoppen.')
        c.execute("INSERT INTO company_probes VALUES(?,?,?,'running',?,'','{}')",(ident,uid,provider,st.iso(st.now())))
    def monitor():
        process=None
        try:
            process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),str(uid),provider,ident],env={**os.environ,'DATA_DIR':str(app.DATA_DIR),'PZ_SYNC_WORKER':'1'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            deadline=time.monotonic()+30
            while process.poll() is None and time.monotonic()<deadline:
                with app.db(read_only=True) as c:row=c.execute('SELECT state FROM company_probes WHERE id=?',(ident,)).fetchone()
                if not row or row['state']!='running':break
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
            if process.poll() is None:process.kill();process.wait()
        finally:
            with app.db() as c:c.execute("UPDATE company_probes SET state='error',finished_at=?,report_json=? WHERE id=? AND state='running'",(st.iso(st.now()),json.dumps({'message':'Test abgebrochen oder Zeitlimit erreicht.','realtime':'unverified'}),ident))
    threading.Thread(target=monitor,name='pz-provider-probe',daemon=True).start();return {'ok':True,'id':ident,'state':'running'}

def stop(c,uid,body):
    st.require(c,uid,'sync.diagnostics');c.execute("UPDATE company_probes SET state='stopped',finished_at=? WHERE id=? AND owner_id=? AND state='running'",(st.iso(st.now()),str(body['id']),uid));return {'ok':True}

def status(c,uid,body):
    st.require(c,uid,'sync.diagnostics');rows=[dict(r) for r in c.execute('SELECT * FROM company_probes WHERE owner_id=? ORDER BY started_at DESC LIMIT 20',(uid,))]
    for r in rows:r['report']=json.loads(r.pop('report_json'))
    return {'probes':rows,'limits':{'requests':5,'seconds':30,'writes':'Nur Diagnoseergebnis; keine Leistungsbuchungen.'}}

def worker(uid,provider,ident):
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(10,10))
    import runtime,feature_runtime,integrations
    app=runtime.configure();provider_budget.initialize(app.DATA_DIR,create=False);provider_budget.install_transport();provider_budget.probe_remaining=5
    started=time.monotonic()
    try:
        with app.db(read_only=True) as c:st.person(c,uid);st.require(c,uid,'sync.diagnostics')
        config=feature_runtime.integration_config(app,uid,provider);result=integrations.diagnose(config)
        report={'duration_ms':round((time.monotonic()-started)*1000),'realtime':'unverified','message':'Dieser Test prüft die lesende Schnittstelle. Echtzeit-Ereignisse sind damit noch nicht bestätigt.','steps':[{k:v for k,v in step.items() if k in ('name','status','ok','duration_ms','count')} for step in result.get('steps',[])]}
        state='success' if report['steps'] and all(s.get('ok') and 200<=s.get('status',0)<300 for s in report['steps']) else 'error'
    except Exception:state='error';report={'message':'Schnittstellentest fehlgeschlagen. Zugang, Serverversion und Abfragebudget prüfen.','realtime':'unverified'}
    with app.db() as c:c.execute("UPDATE company_probes SET state=?,finished_at=?,report_json=? WHERE id=? AND owner_id=? AND state='running'",(state,st.iso(st.now()),json.dumps(report),ident,uid))

HANDLERS={'diagnostics/status':status,'diagnostics/stop':stop}
if __name__=='__main__':worker(int(sys.argv[1]),sys.argv[2],sys.argv[3])
