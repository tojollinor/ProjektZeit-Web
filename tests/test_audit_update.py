"""Regression coverage for the 0.7.3 audit fixes and permission boundaries."""
import json
import unittest
from datetime import date
import test_company_services as fixtures
import staff_time as st
import company_projects as cp
import project_catalog as pc
import project_access
import time_workspace as tw
import workday
import zammad_cache_runtime as zc

class AuditUpdateTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.CompanyServiceTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.CompanyServiceTest.tearDownClass.__func__)
    setUp=fixtures.CompanyServiceTest.setUp
    tearDown=fixtures.CompanyServiceTest.tearDown
    model=fixtures.CompanyServiceTest.model

    def shift(self,**values):
        return st.correction(self.c,2,{'day':'2026-09-07','start':'2026-09-07T08:00:00+02:00','end':'2026-09-07T17:00:00+02:00','note':'Vergessene Stempelung',**values})

    def test_direct_shift_validates_and_records_pause_and_net_duration(self):
        r=self.shift(pauses=[{'started_at':'2026-09-07T12:00:00+02:00','ended_at':'2026-09-07T12:30:00+02:00'}])
        self.assertEqual(r['state'],'approved')
        self.assertFalse(any(x['kind']=='correction' for x in st.inbox(self.c,1)))
        h=st.time_history(self.c,2,{'day':'2026-09-07'})['history']
        self.assertEqual(len(h),1);self.assertEqual(h[0]['changes']['seconds_after'],30600)
        self.assertEqual(h[0]['actor'],'worker');self.assertEqual(h[0]['action'],'Arbeitszeit nachgestempelt')
        work=dict(self.c.execute('SELECT * FROM work_sessions WHERE id=?',(r['work_id'],)).fetchone())
        pauses=[dict(x) for x in self.c.execute('SELECT * FROM work_pauses WHERE work_session_id=?',(r['work_id'],))]
        self.shift(work_id=r['work_id'],original_start=work['started_at'],original_end=work['ended_at'],original_pauses=pauses,pauses=[],end='2026-09-07T16:00:00+02:00')
        h=st.time_history(self.c,2,{'day':'2026-09-07'})['history'];self.assertEqual(h[-1]['changes']['seconds_before'],30600);self.assertEqual(h[-1]['changes']['seconds_after'],28800)

    def test_invalid_manual_times_never_create_a_pending_request(self):
        for values in [{'end':'2026-09-07T07:00:00+02:00'},{'end':'2026-09-20T18:00:00+02:00'},{'day':'2026-09-08'},{'pauses':[{'started_at':'2026-09-07T07:00:00+02:00','ended_at':'2026-09-07T09:00:00+02:00'}]},{'pauses':[{'started_at':'2026-09-07T10:00:00+02:00','ended_at':'2026-09-07T12:00:00+02:00'},{'started_at':'2026-09-07T11:00:00+02:00','ended_at':'2026-09-07T13:00:00+02:00'}]}]:
            with self.subTest(values=values),self.assertRaises(ValueError):self.shift(**values)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM staff_requests').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM work_sessions').fetchone()[0],0)

    def test_overlap_stale_edit_and_closed_month_rejected(self):
        ident=self.shift()['work_id'];row=dict(self.c.execute('SELECT * FROM work_sessions WHERE id=?',(ident,)).fetchone())
        with self.assertRaisesRegex(ValueError,'überschneiden'):self.shift()
        with self.assertRaisesRegex(ValueError,'inzwischen'):self.shift(work_id=ident,original_start='old',original_end=row['ended_at'])
        self.c.execute("INSERT INTO staff_month_closures VALUES(2,'2026-09','{}',1,'')")
        with self.assertRaisesRegex(ValueError,'abgeschlossen'):self.shift(work_id=ident,original_start=row['started_at'],original_end=row['ended_at'])

    def test_time_history_and_foreign_correction_are_permission_scoped(self):
        self.shift()
        with self.assertRaises(PermissionError):st.time_history(self.c,2,{'user_id':1,'day':'2026-09-07'})
        with self.assertRaises(PermissionError):self.shift(user_id=1)
        self.assertTrue(st.time_history(self.c,1,{'user_id':2,'day':'2026-09-07'})['history'])

    def test_all_stamp_events_audited_atomically(self):
        self.c.commit()
        for action,stamp in [('begin','08:00'),('pause','10:00'),('resume','10:30'),('end','17:00')]:
            workday.transition(self.c,2,action,{},st.parse('2026-09-08T'+stamp+':00+02:00'));self.c.commit()
        labels=[e['action'] for e in st.time_history(self.c,2,{'day':'2026-09-08'})['history']]
        self.assertEqual(labels,['Eingestempelt um','Pause eingestempelt um','Pause ausgestempelt um','Ausgestempelt um'])

    def test_notification_read_never_decides_absence(self):
        self.model(2);st.account(self.c,1,{'user_id':2,'year':2026,'days':20})
        r=st.submit(self.c,1,{'user_id':2,'kind':'vacation','whole_day':True,'from':'2026-09-14','to':'2026-09-14'})
        center=st.notifications(self.c,2,{});self.assertEqual(center['action_count'],1)
        nid=center['notifications'][0]['id'];st.notification_seen(self.c,2,{'id':nid})
        self.assertEqual(st.notifications(self.c,2,{})['unread'],0);self.assertEqual(st.notifications(self.c,2,{})['action_count'],1)
        with self.assertRaises(PermissionError):st.notification_seen(self.c,1,{'id':nid})
        self.assertEqual(st.notification_detail(self.c,2,{'id':nid})['request']['id'],r['id'])
        st.decide(self.c,2,{'id':r['id'],'version':1,'approve':True})
        self.assertEqual(st.notifications(self.c,2,{})['action_count'],0)
        self.assertFalse(st.notification_detail(self.c,2,{'id':nid})['request']['can_decide'])

    def test_legacy_pending_corrections_preserved_without_applying(self):
        self.c.execute("INSERT INTO staff_requests(user_id,created_by,kind,start_at,end_at,whole_day,state,policy_json,note,decision_note,created_at,payload_json) VALUES(2,2,'correction','','',1,'pending','{}','old','','','{}')")
        st.migrate(self.c);st.migrate(self.c)
        self.assertEqual(self.c.execute('SELECT state FROM staff_requests').fetchone()[0],'superseded')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM user_notifications WHERE user_id=2').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM work_sessions').fetchone()[0],0)

    def test_project_assignment_does_not_change_recorded_employee(self):
        cp.assign_employee(self.c,1,{'project_id':1,'user_id':2,'original_user_id':None})
        self.assertEqual(project_access.get(self.c,2,1)['owner_id'],1)
        self.assertEqual(pc.catalog(self.c,2,{})['projects'][0]['id'],1)
        self.assertEqual(self.c.execute('SELECT owner_id FROM entries WHERE id=1').fetchone()[0],1)
        with self.assertRaises(PermissionError):cp.assign_employee(self.c,2,{'project_id':1,'user_id':1,'original_user_id':2})
        self.assertTrue(project_access.can_work(self.c,2,1))
        self.c.execute("UPDATE projects SET active=0,status='closed' WHERE id=1")
        self.assertFalse(project_access.can_work(self.c,2,1))

    def bill(self):
        tw.review(self.c,1,{'day':'2026-09-07','source':'manual','key':'1','billable':True})
        self.c.execute("UPDATE projects SET status='closed',active=0 WHERE id=1")
        return cp.billing_submit(self.c,1,{'project_id':1,'descriptions':{'2026-09-07:1':'Update durchgeführt'}})

    def test_reopen_and_restart_do_not_rebill_existing_evidence(self):
        self.bill();self.c.execute("UPDATE projects SET status='open',active=1,billing_state='billed' WHERE id=1")
        self.assertEqual(cp.billing_preview(self.c,1,{'project_id':1})['groups'],[])
        cp.migrate(self.c)
        self.assertEqual(cp.billing_preview(self.c,1,{'project_id':1})['groups'],[])
        self.assertEqual(len(cp.billing_list(self.c,1,{})['descriptions']),1)
        self.c.execute("INSERT INTO entries(owner_id,project_id,category_id,started_at,ended_at,note) VALUES(1,1,1,'2026-09-08T07:00:00+00:00','2026-09-08T08:00:00+00:00','')")
        rid=self.c.execute('SELECT MAX(id) FROM entries').fetchone()[0]
        tw.review(self.c,1,{'day':'2026-09-08','source':'manual','key':str(rid),'billable':True})
        cp.migrate(self.c) # a restart cannot swallow new, unsubmitted evidence
        self.assertEqual(cp.billing_preview(self.c,1,{'project_id':1})['groups'][0]['seconds'],3600)
        self.c.execute("UPDATE projects SET status='closed' WHERE id=1")
        cp.billing_submit(self.c,1,{'project_id':1,'descriptions':{'2026-09-08:1':'Nacharbeiten'}})
        self.assertEqual(len(cp.billing_list(self.c,1,{})['descriptions']),2)
        with self.assertRaises(ValueError):cp.billing_submit(self.c,1,{'project_id':1,'descriptions':{'2026-09-08:1':'Doppelt'}})

    def test_payout_reversal_is_linked_unique_and_restores_balance(self):
        self.model(2)
        st.movement(self.c,1,{'user_id':2,'day':'2026-01-01','kind':'adjustment','hours':2,'note':'Start'})
        st.movement(self.c,1,{'user_id':2,'day':'2026-01-01','kind':'payout','hours':1,'note':'Ausgezahlt'})
        r=st.movement_preview(self.c,1,{'user_id':2,'day':'2026-01-01'})['payouts'][0]
        before=st.account_balance(self.c,2,date(2026,1,1))['balance_seconds']
        st.reverse_movement(self.c,1,{'id':r['id'],'day':'2026-01-01','note':'Fehlbuchung'})
        self.assertEqual(st.account_balance(self.c,2,date(2026,1,1))['balance_seconds'],before+3600)
        self.assertEqual(st.movement_preview(self.c,1,{'user_id':2,'day':'2026-01-01'})['payouts'],[])
        with self.assertRaises(ValueError):st.reverse_movement(self.c,1,{'id':r['id'],'day':'2026-01-01','note':'Doppelt'})
        with self.assertRaises(PermissionError):st.reverse_movement(self.c,2,{'id':r['id'],'day':'2026-01-01','note':'Fremd'})

    def test_ticket_owner_not_cache_or_customer_identity(self):
        identities={'worker@example.test':{'employee_id':2,'employee_name':'worker'}}
        self.assertEqual(zc.ticket_employee({'owner':{'email':'Worker@Example.Test'}},identities)['employee_id'],2)
        self.assertEqual(zc.ticket_employee({'owner':'worker@example.test'},identities)['employee_id'],2)
        self.assertEqual(zc.ticket_employee({'owner_id':2,'customer':{'email':'worker@example.test'}},identities),{})

    def test_linked_ticket_owners_require_same_instance_and_unique_login(self):
        for uid,domain,login in [(1,'https://tickets.example.test','Boss@Example.Test'),(2,'https://tickets.example.test/','worker@example.test')]:
            self.c.execute("INSERT INTO integrations VALUES(?,'zammad',?,?,?,'')",(uid,domain,login,'fixture'))
        identities=zc.employee_identities(self.c,1)
        self.assertEqual(identities['boss@example.test']['employee_name'],'Muster, Max')
        self.assertEqual(identities['worker@example.test']['employee_id'],2)
        self.c.execute("UPDATE integrations SET domain='https://other.example.test' WHERE owner_id=2")
        self.assertNotIn('worker@example.test',zc.employee_identities(self.c,1))
        self.c.execute("UPDATE integrations SET domain='https://tickets.example.test',username='boss@example.test' WHERE owner_id=2")
        self.assertEqual(zc.employee_identities(self.c,1),{})

    def test_multi_employee_billing_preserves_each_service_author(self):
        cp.assign_employee(self.c,1,{'project_id':1,'user_id':2,'original_user_id':None})
        self.c.execute("INSERT INTO categories(id,owner_id,name) VALUES(2,2,'Support')")
        self.c.execute("INSERT INTO entries(id,owner_id,project_id,category_id,started_at,ended_at,note) VALUES(2,2,1,2,'2026-09-07T08:00:00+00:00','2026-09-07T09:00:00+00:00','')")
        for uid in (1,2):tw.review(self.c,uid,{'day':'2026-09-07','source':'manual','key':str(uid),'billable':True})
        self.assertEqual(pc.catalog(self.c,1,{})['projects'][0]['seconds'],10800)
        groups=cp.billing_preview(self.c,1,{'project_id':1})['groups']
        self.assertEqual({g['key'] for g in groups},{'2026-09-07:1','2026-09-07:2'})
        self.c.execute("UPDATE projects SET status='closed',active=0 WHERE id=1")
        cp.billing_submit(self.c,1,{'project_id':1,'descriptions':{g['key']:'Leistung '+g['employee_name'] for g in groups}})
        text=' '.join(g['text'] for g in cp.billing_list(self.c,1,{})['descriptions'])
        self.assertIn('Muster, Max',text);self.assertIn('worker',text)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM billed_evidence').fetchone()[0],2)

    def test_repeated_project_start_has_no_false_history_and_end_records_pause(self):
        cp.assign_employee(self.c,1,{'project_id':1,'user_id':2,'original_user_id':None})
        self.c.execute("INSERT INTO categories(id,owner_id,name) VALUES(2,2,'Support')");self.c.commit()
        for action,clock in [('begin','08:00'),('switch','09:00'),('switch','09:10'),('pause','12:00'),('end','12:30')]:
            workday.transition(self.c,2,action,{'project_id':1,'category_id':2},st.parse('2026-09-08T'+clock+':00+02:00'));self.c.commit()
        labels=[e['action'] for e in st.time_history(self.c,2,{'day':'2026-09-08'})['history']]
        self.assertEqual(labels.count('Projekt gestartet um'),1)
        self.assertEqual(labels[-2:],['Pause ausgestempelt um','Ausgestempelt um'])
