"""Exercise shared budget locking and company queries against an isolated MariaDB."""
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

@unittest.skipUnless(os.environ.get('PZ_TEST_MARIADB')=='1','Requires isolated MariaDB test server')
class CompanyMariaTest(unittest.TestCase):
    def test_shared_budget_and_staff_report(self):
        import pymysql
        name='pz_company_'+uuid.uuid4().hex[:12]
        conn=pymysql.connect(host=os.environ['DB_HOST'],port=int(os.environ['DB_PORT']),user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],autocommit=True)
        script='''
import runtime,provider_budget as budget,staff_time as st,json
from concurrent.futures import ThreadPoolExecutor
app=runtime.initialize(False)
with app.db() as c:
 c.execute("INSERT INTO users(id,username,password_salt,password_hash,role,created_at) VALUES(1,'ci','','','admin','')")
 c.execute("INSERT INTO user_role_links(user_id,role_id) SELECT 1,id FROM role_definitions WHERE role_key='admin'")
 st.save_model(c,1,dict(user_id=1,valid_from='2026-01-01',mode='weekly',hours=40,weekdays=[0,1,2,3,4],subdivision='SH'))
 st.account(c,1,dict(user_id=1,year=2026,days=20))
 report=st.tracking_report(c,1,{'day':'2026-09-14'})
 assert len(report['days'])==7
 assert type(report['account']['balance_seconds']) is int
 json.dumps(report,allow_nan=False)
with app.db() as c:
 import company_projects as cp,time_workspace as tw
 st.correction(c,1,{'day':'2026-09-07','start':'2026-09-07T08:00:00+02:00','end':'2026-09-07T17:00:00+02:00','note':'MariaDB Nachtrag','pauses':[{'started_at':'2026-09-07T12:00:00+02:00','ended_at':'2026-09-07T12:30:00+02:00'}]})
 assert st.time_history(c,1,{'day':'2026-09-07'})['history'][0]['changes']['seconds_after']==30600
 st.movement(c,1,{'user_id':1,'day':'2026-01-01','kind':'adjustment','hours':2,'note':'Start'})
 st.movement(c,1,{'user_id':1,'day':'2026-01-01','kind':'payout','hours':1,'note':'Abrechnung'})
 payout=st.movement_preview(c,1,{'user_id':1,'day':'2026-01-01'})['payouts'][0]
 st.reverse_movement(c,1,{'id':payout['id'],'day':'2026-01-01','note':'Storno'})
 assert not st.movement_preview(c,1,{'user_id':1,'day':'2026-01-01'})['payouts']
 center=st.notifications(c,1,{})
 assert center['unread']==3
 st.notification_seen(c,1,{'id':center['notifications'][0]['id']})
 assert st.notifications(c,1,{})['unread']==2
 pid=c.execute("INSERT INTO projects(owner_id,name,status) VALUES(1,'CI Projekt','closed')").lastrowid
 cid=c.execute("INSERT INTO categories(owner_id,name) VALUES(1,'CI')").lastrowid
 entry=c.execute("INSERT INTO entries(owner_id,project_id,category_id,started_at,ended_at,note) VALUES(1,?,?,'2026-09-07T07:00:00+00:00','2026-09-07T09:00:00+00:00','')",(pid,cid)).lastrowid
 tw.review(c,1,{'day':'2026-09-07','source':'manual','key':str(entry),'billable':True})
 cp.billing_submit(c,1,{'project_id':pid,'descriptions':{'2026-09-07:1':'MariaDB Prüfung'}})
 cp.migrate(c)
 assert not cp.billing_preview(c,1,{'project_id':pid})['groups']
 assert len(cp.billing_list(c,1,{})['descriptions'])==1
budget.set_cap('teamviewer',3)
def reserve(_):
 try:budget.reserve('teamviewer',100000);return True
 except ValueError:return False
with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(reserve,range(12)))==3
budget.initialize(app.DATA_DIR)
try:
 budget.reserve('teamviewer',100001)
 raise AssertionError('Budget was reset on restart')
except ValueError:pass
budget.reserve('teamviewer',186400)
'''
        try:
            with conn.cursor() as c:c.execute('CREATE DATABASE '+name+' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            with tempfile.TemporaryDirectory() as folder:
                env={**os.environ,'DATA_DIR':folder,'DB_BACKEND':'mariadb','DB_NAME':name,'DEMO_MODE':'1','SEED_DEMO':'0'}
                result=subprocess.run([sys.executable,'-c',script],env=env,text=True,capture_output=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr)
        finally:
            with conn.cursor() as c:c.execute('DROP DATABASE '+name)
            conn.close()
