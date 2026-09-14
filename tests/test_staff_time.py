import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import test_workday as fixtures
import admin_controls
import system_features
import workday
import duty_plan
import staff_time as st

class StaffTimeTest(unittest.TestCase):
    def setUp(self):
        fixtures.WorkdayTest.setUp(self)
        with app.db() as c:
            admin_controls.migrate(c);system_features.migrate(c);workday.migrate(c);c.executescript("CREATE TABLE IF NOT EXISTS user_notifications(id INTEGER PRIMARY KEY,user_id INTEGER,kind TEXT,message TEXT,created_at TEXT)");st.migrate(c);duty_plan.migrate(c);st.register()
            self.uid=c.execute('SELECT id FROM users').fetchone()['id']
            c.execute('INSERT OR IGNORE INTO system_superadmins(user_id) VALUES(?)',(self.uid,))
            st.save_model(c,self.uid,dict(user_id=self.uid,valid_from='2026-01-01',mode='weekly',hours=40,weights=[1,1,1,1,1,0,0],subdivision='SH'))
            st.account(c,self.uid,dict(user_id=self.uid,year=2026,days=30))
        self.clock=patch.object(st,'now',return_value=datetime(2026,9,13,12,tzinfo=timezone.utc));self.clock.start()
    def tearDown(self):self.clock.stop();fixtures.WorkdayTest.tearDown(self)
    def request(self,kind,a,b=None,whole=True,approve=True):
        with app.db() as c:
            r=st.submit(c,self.uid,dict(kind=kind,whole_day=whole,**{'from':a,'to':b or a}))
            if approve:c.execute("UPDATE staff_requests SET state='approved' WHERE id=?",(r['id'],))
            return r['id']
    def day(self,d):
        with app.db(read_only=True) as c:
            d=date.fromisoformat(d);return st.daily(st.dataset(c,self.uid,d,d+timedelta(days=1)),d)
    def test_monthly_distribution_preserves_target_and_includes_holiday(self):
        model=dict(mode='monthly',target_seconds=173*3600,weights=[1,1,1,1,1,0,0])
        values=[st.daily_target(model,d) for d in st.days(date(2026,1,1),date(2026,2,1))]
        self.assertEqual(sum(values),173*3600);self.assertGreater(values[0],0)
    def test_holiday_credits_only_after_day_and_actual_work_adds(self):
        with patch.object(st,'now',return_value=st.parse('2026-01-01T12:00:00+01:00')):
            r=self.day('2026-01-01');self.assertEqual(r['posted_seconds'],0);self.assertEqual(r['state'],'provisional')
        with app.db() as c:c.execute('INSERT INTO work_sessions(owner_id,started_at,ended_at) VALUES(?,?,?)',(self.uid,'2026-01-01T08:00:00+00:00','2026-01-01T10:00:00+00:00'))
        r=self.day('2026-01-01');self.assertEqual(r['credit_seconds'],28800);self.assertEqual(r['posted_seconds'],7200)
    def test_sick_replaces_vacation_without_double_credit(self):
        self.request('vacation','2026-09-07');self.request('sick','2026-09-07')
        r=self.day('2026-09-07');self.assertEqual(r['credit_seconds'],28800);self.assertEqual(r['vacation_units'],0);self.assertEqual(r['delta_seconds'],0)
    def test_approved_cancellation_allows_new_request_and_hides_calendar(self):
        rid=self.request('vacation','2026-09-07')
        with app.db() as c:
            r=st.cancellation(c,self.uid,dict(id=rid,whole_day=True,**{'from':'2026-09-07','to':'2026-09-07'}));c.execute("UPDATE staff_requests SET state='approved' WHERE id=?",(r['id'],))
            events=st.calendar_data(c,self.uid,date(2026,9,7),date(2026,9,8));self.assertFalse(any(e['type']=='absence' for e in events))
        self.request('vacation','2026-09-07')
        self.assertEqual(self.day('2026-09-07')['vacation_units'],1000000)
    def test_hourly_leave_exact_fraction(self):
        with app.db() as c:c.execute('INSERT INTO staff_policy_versions(valid_from,settings_json,created_by,created_at) VALUES(?,?,?,?)',('2026-01-01',json.dumps({**st.DEFAULT_POLICY,'hourly_paid':True}),self.uid,st.iso(st.now())))
        self.request('vacation','2026-09-07T09:00:00+02:00','2026-09-07T10:00:00+02:00',False)
        r=self.day('2026-09-07');self.assertEqual(r['vacation_units'],125000);self.assertEqual(r['credit_seconds'],3600)
    def test_missing_model_cannot_create_free_vacation(self):
        with self.assertRaisesRegex(ValueError,'Arbeitszeitmodell'):self.request('vacation','2025-12-31')
    def test_missing_stamp_needs_clarification(self):
        self.assertEqual(self.day('2026-09-07')['posted_seconds'],-28800)
        self.request('timeoff','2026-09-07');self.assertEqual(self.day('2026-09-07')['posted_seconds'],-28800)
    def test_closed_month_stays_frozen_after_cancellation(self):
        rid=self.request('vacation','2026-09-07')
        with app.db() as c:
            c.execute('INSERT INTO staff_month_closures VALUES(?,?,?,?,?)',(self.uid,'2026-09',json.dumps({'posted_seconds':123,'days':[]}),self.uid,st.iso(st.now())))
            r=st.cancellation(c,self.uid,dict(id=rid,whole_day=True,**{'from':'2026-09-07','to':'2026-09-07'}));c.execute("UPDATE staff_requests SET state='approved' WHERE id=?",(r['id'],))
            self.assertEqual(st.month_report(c,self.uid,'2026-09')['posted_seconds'],123)
    def test_self_approval_is_disabled_even_for_superadmin(self):
        rid=self.request('vacation','2026-09-07',approve=False)
        with app.db() as c:
            with self.assertRaisesRegex(PermissionError,'Eigengenehmigung'):st.decide(c,self.uid,dict(id=rid,version=1,approve=True))
    def test_payout_cannot_exceed_booked_balance(self):
        with app.db() as c:
            with self.assertRaisesRegex(ValueError,'Nicht genügend'):st.movement(c,self.uid,dict(user_id=self.uid,day='2026-09-13',hours=100,kind='payout',note='Test'))

if __name__=='__main__':unittest.main()
