import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date,datetime,timezone
from pathlib import Path
from unittest.mock import patch
import staff_time as st
import admin_controls as acl
import company_projects as cp
import duty_plan
import customer_data
import time_workspace as tw

class CompanyServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();env={**os.environ,'DATA_DIR':cls.tmp.name,'DB_BACKEND':'sqlite','DEMO_MODE':'1','SEED_DEMO':'0'}
        subprocess.run([sys.executable,'-c','import runtime;runtime.initialize(False)'],env=env,check=True,capture_output=True);cls.seed=Path(cls.tmp.name)/'projektzeit.db'
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        with sqlite3.connect(self.seed) as seed:seed.backup(self.c)
        self.c.executescript("""INSERT INTO users(id,username,password_salt,password_hash,role,created_at) VALUES(1,'boss','','','admin',''),(2,'worker','','','user','');
        INSERT INTO user_role_links(user_id,role_id) SELECT 1,id FROM role_definitions WHERE role_key='admin';INSERT INTO user_role_links(user_id,role_id) SELECT 2,id FROM role_definitions WHERE role_key='user';INSERT INTO user_profiles(user_id,first_name,last_name) VALUES(1,'Max','Muster');
        INSERT INTO customers(id,owner_id,name) VALUES(1,1,'Kunde');INSERT INTO projects(id,owner_id,customer_id,name) VALUES(1,1,1,'Update');INSERT INTO categories(id,owner_id,name) VALUES(1,1,'Fernwartung');
        INSERT INTO entries(id,owner_id,project_id,category_id,started_at,ended_at,note) VALUES(1,1,1,1,'2026-09-07T07:00:00+00:00','2026-09-07T09:00:00+00:00','');""")
        self.superpatch=patch.object(acl,'is_superadmin',return_value=False);self.superpatch.start()
        st.register();self.clock=patch.object(st,'now',return_value=datetime(2026,9,13,12,tzinfo=timezone.utc));self.clock.start()
    def tearDown(self):self.clock.stop();self.superpatch.stop();self.c.close()
    def model(self,uid):st.save_model(self.c,1,dict(user_id=uid,valid_from='2026-01-01',mode='weekly',hours=40,weights=[1,1,1,1,1,0,0],subdivision='SH'))
    def test_tracking_employee_access_and_future_balance(self):
        self.model(1);self.model(2)
        with self.assertRaises(PermissionError):st.tracking_report(self.c,2,{'user_id':1,'day':'2026-09-14'})
        report=st.tracking_report(self.c,1,{'user_id':2,'day':'2026-09-14'})
        self.assertFalse(report['own']);self.assertEqual(report['user_id'],2)
        self.assertEqual(report['requests'],[])
        self.assertTrue(all(d['balance_seconds'] is None and d['delta_seconds'] is None for d in report['days']))
        own=st.tracking_report(self.c,2,{'day':'2026-09-07','mode':'day'})
        self.assertTrue(own['own']);self.assertEqual(own['days'][0]['posted_seconds'],-28800)

    def test_retroactive_cancellation_posts_once_and_preserves_close(self):
        self.model(2);st.account(self.c,1,{'user_id':2,'year':2026,'days':20})
        r=st.submit(self.c,2,{'kind':'vacation','whole_day':True,'from':'2026-08-03','to':'2026-08-03'})
        st.decide(self.c,1,{'id':r['id'],'version':1,'approve':True})
        snapshot=st.month_report(self.c,2,'2026-08')
        self.c.execute('INSERT INTO staff_month_closures VALUES(?,?,?,?,?)',(2,'2026-08',json.dumps(snapshot),1,st.iso(st.now())))
        cancel=st.cancellation(self.c,2,{'id':r['id'],'whole_day':True,'from':'2026-08-03','to':'2026-08-03'})
        st.decide(self.c,1,{'id':cancel['id'],'version':1,'approve':True})
        self.assertEqual(st.month_report(self.c,2,'2026-08')['posted_seconds'],snapshot['posted_seconds'])
        movement=self.c.execute('SELECT * FROM staff_movements WHERE user_id=2').fetchall()
        self.assertEqual(len(movement),1);self.assertEqual(movement[0]['seconds'],-28800)
        st.reconcile_closed_months(self.c,1,2,st.parse('2026-08-03T00:00:00+02:00'),st.parse('2026-08-04T00:00:00+02:00'))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM staff_movements WHERE user_id=2').fetchone()[0],1)

    def test_clone_carries_tags_but_no_time(self):
        tag=cp.tags(self.c,1,{'name':'Update','customer_id':1})['id'];cp.attach(self.c,1,{'project_id':1,'tags':[tag]});ident=cp.clone(self.c,1,{'project_id':1,'name':'Update neu'})['project_id']
        self.assertIsNone(self.c.execute('SELECT 1 FROM entries WHERE project_id=?',(ident,)).fetchone());self.assertEqual(self.c.execute('SELECT tag_id FROM project_tag_links WHERE project_id=?',(ident,)).fetchone()[0],tag)
    def test_billing_requires_text_and_uses_service_date_and_name(self):
        tw.review(self.c,1,{'day':'2026-09-07','source':'manual','key':'1','billable':True})
        with self.assertRaises(ValueError):cp.billing_submit(self.c,1,{'project_id':1})
        self.c.execute("UPDATE projects SET status='closed',active=0 WHERE id=1")
        cp.billing_submit(self.c,1,{'project_id':1,'descriptions':{'2026-09-07':'Kasse aktualisiert\nFunktion geprüft'}})
        text=cp.billing_list(self.c,1,{})['descriptions'][0]['text'];self.assertIn('07.09.2026 · Muster, Max',text);self.assertNotIn('13.09.2026',text);self.assertIn('• Funktion geprüft',text)
    def test_changed_review_cannot_be_billed(self):
        tw.review(self.c,1,{'day':'2026-09-07','source':'manual','key':'1','billable':True});self.c.execute("UPDATE entries SET ended_at='2026-09-07T10:00:00+00:00' WHERE id=1")
        with self.assertRaisesRegex(ValueError,'verändert'):cp.billing_preview(self.c,1,{'project_id':1})
    def test_manager_absence_requires_employee_confirmation_and_is_private(self):
        self.model(2);st.account(self.c,1,{'user_id':2,'year':2026,'days':20});r=st.submit(self.c,1,{'user_id':2,'kind':'vacation','whole_day':True,'from':'2026-09-14','to':'2026-09-14','note':'private'})
        self.assertEqual(r['state'],'awaiting_employee')
        with self.assertRaises(PermissionError):st.decide(self.c,1,{'id':r['id'],'version':1,'approve':True})
        st.decide(self.c,2,{'id':r['id'],'version':1,'approve':True});events=st.calendar_data(self.c,1,date(2026,9,14),date(2026,9,15));absence=next(e for e in events if e['type']=='absence');self.assertEqual(absence['title'],'Abwesend');self.assertEqual(absence['details'],'')
    def test_project_correction_is_direct_and_audited(self):
        self.c.commit();r=st.entry_correction(self.c,1,{'id':1,'original_start':'2026-09-07T07:00:00+00:00','original_end':'2026-09-07T09:00:00+00:00','original_note':'','project_id':1,'category_id':1,'started_at':'2026-09-07T07:00:00+00:00','ended_at':'2026-09-07T10:00:00+00:00','note':'Korrektur'})
        self.assertEqual(r['state'],'approved');self.assertEqual(self.c.execute('SELECT note FROM entries WHERE id=1').fetchone()[0],'Korrektur');self.assertTrue(self.c.execute("SELECT id FROM audit_events WHERE entity_type='worktime'").fetchone())
    def test_rotations_and_confirmed_day_swap_preserve_other_days(self):
        duty_plan.save(self.c,1,{'from':'2026-09-14T08:00:00+02:00','to':'2026-09-28T08:00:00+02:00','members':[1,2],'period_days':7,'review_swaps':False})
        slot=self.c.execute('SELECT id FROM duty_slots WHERE user_id=1').fetchone()[0]
        duty_plan.swap(self.c,1,{'id':slot,'user_id':2,'from':'2026-09-15T08:00:00+02:00','to':'2026-09-16T08:00:00+02:00'});rid=self.c.execute('SELECT id FROM duty_swaps').fetchone()[0]
        with self.assertRaises(PermissionError):duty_plan.decide(self.c,1,{'id':rid,'approve':True})
        duty_plan.decide(self.c,2,{'id':rid,'approve':True});self.assertEqual(self.c.execute('SELECT COUNT(*) FROM duty_slots').fetchone()[0],4)
    def test_unique_identity_auto_assigns_customer_only(self):
        self.c.execute("INSERT INTO customer_identity_links(owner_id,customer_id,provider,link_type,link_value,created_at) VALUES(1,1,'starface','phone','49123','')")
        customer_data.cache_rows(self.c,1,'starface',{'rows':[{'external_key':'call','raw':{'startTime':'2026-09-07T09:00:00Z','duration':60,'direction':'OUTBOUND','calledNumber':'+49 123'},'customer_hint':{}}]})
        r=self.c.execute("SELECT * FROM provider_assignments WHERE external_key='call'").fetchone();self.assertEqual(r['customer_id'],1);self.assertIsNone(r['project_id'])
    def test_outside_overlap_is_counted_once(self):
        cp.context_save(self.c,1,{'source':'manual','key':'1','location':'outside','emergency':False})
        self.c.execute("INSERT INTO event_intervals VALUES(1,'teamviewer','tv','2026-09-07T08:00:00+00:00','2026-09-07T10:00:00+00:00','teamviewer_id','123')")
        self.c.execute("INSERT INTO event_work_context VALUES(1,'teamviewer','tv','outside',0,'')")
        self.assertEqual(cp.outside(self.c,1,{'day':'2026-09-07'})['days'][0]['outside_seconds'],10800)

if __name__=='__main__':unittest.main()
