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
import runtime,provider_budget as budget,staff_time as st
from concurrent.futures import ThreadPoolExecutor
app=runtime.initialize(False)
with app.db() as c:
 c.execute("INSERT INTO users(id,username,password_salt,password_hash,role,created_at) VALUES(1,'ci','','','admin','')")
 c.execute("INSERT INTO user_role_links(user_id,role_id) SELECT 1,id FROM role_definitions WHERE role_key='admin'")
 st.save_model(c,1,dict(user_id=1,valid_from='2026-01-01',mode='weekly',hours=40,weekdays=[0,1,2,3,4],subdivision='SH'))
 st.account(c,1,dict(user_id=1,year=2026,days=20))
 assert len(st.tracking_report(c,1,{'day':'2026-09-14'})['days'])==7
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
