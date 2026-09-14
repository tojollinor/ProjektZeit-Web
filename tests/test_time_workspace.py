import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import timezone
from unittest.mock import patch

import customer_data
import diagnostics
import time_workspace as tw


class TimeWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        env={**os.environ,'DATA_DIR':cls.temp.name,'DB_BACKEND':'sqlite','DEMO_MODE':'1','SEED_DEMO':'0'}
        subprocess.run([sys.executable,'-c','import runtime; runtime.initialize(False)'],env=env,check=True,capture_output=True)
        cls.seed=Path(cls.temp.name)/'projektzeit.db'

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        with sqlite3.connect(self.seed) as seed:seed.backup(self.c)
        self.c.executescript("""
        INSERT INTO users(id,username,password_salt,password_hash,role,created_at) VALUES(1,'one','','','admin',''),(2,'two','','','user','');
        INSERT INTO customers(id,owner_id,name) VALUES(1,1,'Customer'),(2,2,'Private');
        INSERT INTO projects(id,owner_id,customer_id,name) VALUES(1,1,1,'Project'),(2,2,2,'Private project');
        INSERT INTO categories(id,owner_id,name) VALUES(1,1,'Work'),(2,2,'Work');
        INSERT INTO entries(id,owner_id,project_id,category_id,started_at,ended_at,note) VALUES(1,1,1,1,'2026-03-28T22:30:00+00:00','2026-03-29T02:30:00+00:00',''),(2,2,2,2,'2026-03-29T00:00:00+00:00','2026-03-29T01:00:00+00:00','');
        """)
        customer_data.cache_rows(self.c,1,'starface',{'rows':[{'external_key':'call1','raw':{'startTime':'2026-03-29T01:00:00Z','duration':600,'direction':'OUTBOUND','calledNumber':'+49 123'},'customer_hint':{}}]})
        self.body={'day':'2026-03-29'}

    def tearDown(self):self.c.close()

    def test_full_runtime_schema_and_owned_events(self):
        result=tw.workspace(self.c,1,self.body)
        self.assertEqual({e['owner_id'] for e in result['events']},{1})
        self.assertEqual(len(result['events']),2)
        self.assertEqual(result['summary']['overlaps'],2)
        self.assertEqual(result['summary']['billable_seconds'],0)
        with self.assertRaises(PermissionError):tw.workspace(self.c,1,{**self.body,'customer_id':2})
        with self.assertRaises(PermissionError):tw.workspace(self.c,1,{**self.body,'customer_id':1,'team':True})

    def test_statistics_split_at_midnight_and_dst(self):
        result=tw.statistics(self.c,1,{'day':'2026-03-28','days':2})
        self.assertEqual(dict(result['per_day']),{'2026-03-28':1800,'2026-03-29':12600})
        self.assertEqual(result['total'],14400)
        a,b=tw.bounds(self.body)
        self.assertEqual((b.astimezone(timezone.utc)-a.astimezone(timezone.utc)).total_seconds(),23*3600)

    def test_assignment_does_not_bill_and_overlapping_review_rejected(self):
        with patch('admin_controls.require_permission'):
            tw.assign(self.c,1,{'project_id':1,'items':[{'source':'starface','key':'call1'}]})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM time_reviews').fetchone()[0],0)
        tw.review(self.c,1,{**self.body,'source':'manual','key':'1','billable':True})
        with self.assertRaisesRegex(ValueError,'Überschneidung'):
            tw.review(self.c,1,{**self.body,'source':'starface','key':'call1','billable':True})
        tw.review(self.c,1,{**self.body,'source':'starface','key':'call1','billable':False})
        self.assertEqual(self.c.execute('SELECT SUM(billable) FROM time_reviews').fetchone()[0],1)
        self.c.execute("UPDATE entries SET ended_at='2026-03-29T02:00:00+00:00' WHERE id=1")
        manual=next(e for e in tw.workspace(self.c,1,self.body)['events'] if e['source']=='manual')
        self.assertFalse(manual['reviewed'])

    def test_client_cannot_assign_other_users_event(self):
        with patch('admin_controls.require_permission'):
            with self.assertRaises(ValueError):tw.assign(self.c,1,{'project_id':1,'items':[{'source':'manual','key':'2'}]})
            with self.assertRaises(ValueError):tw.assign(self.c,1,{'project_id':2,'items':[{'source':'manual','key':'1'}]})

    def test_exact_phone_suggestion_and_customer_history(self):
        self.c.execute("INSERT INTO customer_phones(owner_id,customer_id,number) VALUES(1,1,'+49-123')")
        result=tw.workspace(self.c,1,self.body)
        call=next(e for e in result['events'] if e['source']=='starface')
        self.assertEqual([p['id'] for p in call['suggestions']],[1])
        self.assertEqual([e['external_key'] for e in customer_data.activity(self.c,1,1)],['call1'])
        self.assertIn('call1',[e['key'] for e in tw.workspace(self.c,1,{**self.body,'customer_id':1})['events']])

    def test_ticket_point_event_never_invents_work(self):
        a,b=tw.normalize('zammad',{'created_at':'2026-03-29T01:00:00Z','duration':999})
        self.assertIsNotNone(a);self.assertIsNone(b)

    def test_read_path_does_not_write(self):
        self.c.execute('PRAGMA query_only=ON')
        tw.workspace(self.c,1,self.body)
        tw.statistics(self.c,1,self.body)
        customer_data.get_one(self.c,1,1)
        customer_data.activity(self.c,1,1)

    def test_diagnostics_redacts_nested_credentials(self):
        text=json.dumps(diagnostics.sanitize({'nested':{'client_secret':'supersecret'},'message':'Authorization: Bearer abcdef access_token=abcdef'}))
        self.assertNotIn('supersecret',text);self.assertNotIn('abcdef',text)


if __name__=='__main__':unittest.main()

class FullRuntimeHTTPTests(unittest.TestCase):
    def test_production_dispatch_reads_and_reviews_over_http(self):
        script=r'''
import runtime,threading,json,urllib.request,http.cookiejar
app=runtime.initialize()
with app.db() as c:
 uid=c.execute('SELECT id FROM users WHERE username=?',('ciuser',)).fetchone()['id']
 c.execute('INSERT INTO customers(owner_id,name) VALUES(?,?)',(uid,'Example'))
 cid=c.execute('SELECT id FROM customers WHERE owner_id=?',(uid,)).fetchone()['id']
 c.execute('INSERT INTO projects(owner_id,customer_id,name) VALUES(?,?,?)',(uid,cid,'Example'))
server=app.ThreadingHTTPServer(('127.0.0.1',0),app.App)
threading.Thread(target=server.serve_forever,daemon=True).start()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
base='http://127.0.0.1:'+str(server.server_address[1]);csrf=''
def post(path,body):
 request=urllib.request.Request(base+path,json.dumps(body).encode(),{'Content-Type':'application/json','X-CSRF-Token':csrf})
 with opener.open(request,timeout=5) as response:
  assert response.headers.get('Server-Timing'),response.headers
  return json.load(response)
login=post('/api/v1/login',{'username':'ciuser','password':'ci-only-password-2026'})
with opener.open(base+'/api/v1/me') as response:csrf=json.load(response)['csrf']
assert post('/api/v1/time-workspace/read',{'day':'2026-03-29'})['events']==[]
assert post('/api/v1/time-workspace/statistics',{'day':'2026-03-29'})['total']==0
assert post('/api/v1/customers/detail',{'id':cid})['customer']['name']=='Example'
catalog=post('/api/v1/project-catalog/list',{})
pid=catalog['projects'][0]['id']
tag=post('/api/v1/project-catalog/tags/save',{'name':'HTTP tag','customer_id':cid})['id']
post('/api/v1/project-catalog/tags/assign',{'project_id':pid,'tags':[tag]})
body={'project_id':pid,'name':'HTTP copy'}
def copy_once():
 request=urllib.request.Request(base+'/api/v1/project-catalog/clone',json.dumps(body).encode(),{'Content-Type':'application/json','X-CSRF-Token':csrf,'Idempotency-Key':'project-copy-http'})
 with opener.open(request,timeout=5) as response:return json.load(response)
first=copy_once();assert copy_once()==first
catalog=post('/api/v1/project-catalog/list',{})
assert len(catalog['projects'])==2
assert {'project_id':first['project_id'],'tag_id':tag} in catalog['links']
request=urllib.request.Request(base+'/api/v1/project-catalog/clone',json.dumps({'project_id':pid,'name':'No CSRF'}).encode(),{'Content-Type':'application/json'})
try:
 opener.open(request,timeout=5)
 raise AssertionError('Missing CSRF accepted')
except __import__('urllib.error',fromlist=['HTTPError']).HTTPError as error:assert error.code==403

server.shutdown()
'''
        with tempfile.TemporaryDirectory() as folder:
            env={**os.environ,'DATA_DIR':folder,'DB_BACKEND':'sqlite','DEMO_MODE':'1','SEED_DEMO':'0','ADMIN_USER':'ciuser','ADMIN_PASSWORD':'ci-only-password-2026'}
            result=subprocess.run([sys.executable,'-c',script],env=env,text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(os.environ.get('PZ_TEST_MARIADB')=='1','Requires isolated MariaDB test server')
    def test_complete_runtime_schema_on_mariadb(self):
        import pymysql,uuid
        name='pz_full_'+uuid.uuid4().hex[:12]
        conn=pymysql.connect(host=os.environ['DB_HOST'],port=int(os.environ['DB_PORT']),user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],autocommit=True)
        try:
            with conn.cursor() as c:c.execute('CREATE DATABASE '+name+' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            with tempfile.TemporaryDirectory() as folder:
                env={**os.environ,'DATA_DIR':folder,'DB_BACKEND':'mariadb','DB_NAME':name,'DEMO_MODE':'1','SEED_DEMO':'0'}
                result=subprocess.run([sys.executable,'-c','import runtime; app=runtime.initialize(False); import time_workspace; c=app.db(); conn=c.__enter__(); conn.execute("INSERT INTO users(id,username,password_salt,password_hash,role,created_at) VALUES(1,\'ci\',\'\',\'\',\'admin\',\'\')"); conn.execute("INSERT INTO customers(id,owner_id,name) VALUES(1,1,\'Example\')"); c.__exit__(None,None,None); c=app.db(read_only=True); conn=c.__enter__(); assert time_workspace.workspace(conn,1,{\'day\':\'2026-03-29\',\'customer_id\':1})[\'events\']==[]; c.__exit__(None,None,None)'],env=env,text=True,capture_output=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr)
        finally:
            with conn.cursor() as c:c.execute('DROP DATABASE '+name)
            conn.close()
