import calendar
from datetime import date, datetime, timedelta, timezone
import unittest
from unittest.mock import patch
import app
import admin_controls as acl
import system_features
import test_workday
import work_models as wm

CLOCK=datetime(2026,9,14,12,tzinfo=timezone.utc)


class WorkModelTests(unittest.TestCase):
    tearDown=test_workday.WorkdayTest.tearDown
    def setUp(self):
        test_workday.WorkdayTest.setUp(self)
        self.clock=patch('work_models.now',return_value=CLOCK);self.clock.start();self.addCleanup(self.clock.stop)
        self.superpatch=patch('admin_controls.is_superadmin',return_value=False);self.superpatch.start();self.addCleanup(self.superpatch.stop)
        with app.db() as c:
            acl.migrate(c);system_features.migrate(c);wm.migrate(c)
            role=c.execute("INSERT INTO role_definitions(role_key,name,created_at) VALUES('work-test','Work test','')").lastrowid
            c.execute('INSERT INTO role_permissions VALUES(?,?)',(role,wm.PERMISSION))
            c.execute('INSERT INTO user_role_links VALUES(?,?)',(self.uid,role))
            self.other=c.execute("INSERT INTO users(username,password_salt,password_hash,role,created_at) VALUES('employee','','','user','')").lastrowid
    def save(self,c,**values):
        return wm.save(c,self.uid,{'user_id':self.uid,'valid_from':'2026-01-01','mode':'weekly','hours':40,'weekdays':[0,1,2,3,4],'subdivision':'SH',**values})
    def session(self,c,start,end,pauses=()):
        ident=c.execute('INSERT INTO work_sessions(owner_id,started_at,ended_at) VALUES(?,?,?)',(self.uid,start,end)).lastrowid
        for a,b in pauses:c.execute('INSERT INTO work_pauses(owner_id,work_session_id,started_at,ended_at) VALUES(?,?,?,?)',(self.uid,ident,a,b))
        return ident

    def test_monthly_exact_distribution_including_holidays(self):
        with app.db() as c:
            self.save(c,mode='monthly',hours=173)
            m=wm.models(c,self.uid)[0]
            for month in range(1,13):
                ds=[date(2026,month,i) for i in range(1,calendar.monthrange(2026,month)[1]+1)]
                self.assertEqual(sum(wm.target(m,d) for d in ds),173*3600)
                self.assertTrue(all(wm.target(m,d)==0 for d in ds if d.weekday()>4))
            self.assertGreater(wm.target(m,date(2026,1,1)),0)
            self.assertNotEqual(wm.target(m,date(2026,1,2)),wm.target(m,date(2026,2,2)))

    def test_weekly_and_daily_with_custom_days(self):
        m={'mode':'weekly','target_seconds':40*3600,'weekdays':[0,2,4]}
        ds=[date(2026,9,14)+timedelta(days=i) for i in range(7)]
        self.assertEqual(sum(wm.target(m,d) for d in ds),40*3600)
        self.assertEqual(wm.target(m,ds[1]),0)
        m['mode']='daily';m['target_seconds']=8*3600
        self.assertEqual(sum(wm.target(m,d) for d in ds),24*3600)

    def test_holiday_credit_only_after_day_and_work_added(self):
        with app.db() as c:
            self.save(c)
            self.session(c,'2026-01-01T08:00:00+00:00','2026-01-01T10:00:00+00:00')
            before=wm.overview(c,self.uid,{'day':'2026-01-01'},datetime(2025,12,31,12,tzinfo=timezone.utc))
            during=wm.overview(c,self.uid,{'day':'2026-01-01'},datetime(2026,1,1,12,tzinfo=timezone.utc))
            after=wm.overview(c,self.uid,{'day':'2026-01-01'},datetime(2026,1,1,23,tzinfo=timezone.utc))
            self.assertEqual(before['day']['holiday_seconds'],0)
            self.assertEqual(during['day']['holiday_seconds'],0)
            self.assertEqual(after['day']['holiday_seconds'],8*3600)
            self.assertEqual(after['day']['difference_seconds'],2*3600)
            self.assertEqual(after['month']['closed_difference_seconds'],2*3600)
            self.assertEqual(after['month']['closed_days'],1)

    def test_pauses_union_and_no_project_double_count(self):
        with app.db() as c:
            self.save(c)
            self.session(c,'2026-09-10T06:00:00+00:00','2026-09-10T14:00:00+00:00',[
                ('2026-09-10T08:00:00+00:00','2026-09-10T08:45:00+00:00'),
                ('2026-09-10T08:30:00+00:00','2026-09-10T09:00:00+00:00')])
            r=wm.overview(c,self.uid,{'day':'2026-09-10'})['day']
            self.assertEqual(r['actual_seconds'],7*3600)
            self.assertEqual(r['pause_seconds'],3600)
            self.assertEqual(r['difference_seconds'],-3600)
            own=wm.overview(c,self.other,{'day':'2026-09-10','user_id':self.uid})
            self.assertEqual(own['day']['actual_seconds'],0)
            self.assertIsNone(own['day']['target_seconds'])

    def test_dst_midnight_and_open_session_uncertainty(self):
        with app.db() as c:
            self.save(c,mode='daily',hours=8,weekdays=[6])
            self.session(c,'2026-03-28T23:00:00+00:00','2026-03-29T22:00:00+00:00')
            r=wm.overview(c,self.uid,{'day':'2026-03-29'})['day']
            self.assertEqual(r['actual_seconds'],23*3600)
            self.session(c,'2026-09-13T06:00:00+00:00',None)
            r=wm.overview(c,self.uid,{'day':'2026-09-13'})
            self.assertTrue(r['day']['unclosed_work'])
            self.assertIsNone(r['day']['difference_seconds'])
            self.assertIsNone(r['week']['closed_difference_seconds'])

    def test_history_validation_and_concurrent_update(self):
        with app.db() as c:
            self.save(c)
            with self.assertRaises(ValueError):self.save(c,valid_from='2026-09-01',hours=30)
            ident=self.save(c,valid_from='2026-10-01',hours=30)['id']
            self.save(c,id=ident,version=1,valid_from='2026-10-01',hours=35)
            with self.assertRaises(ValueError):self.save(c,id=ident,version=1,valid_from='2026-10-01',hours=32)
            items=wm.models(c,self.uid)
            self.assertEqual(wm.model_on(items,date(2026,9,30))['target_seconds'],40*3600)
            self.assertEqual(wm.model_on(items,date(2026,10,1))['target_seconds'],35*3600)
            for fields in [{'weekdays':[]},{'hours':'NaN'},{'hours':0},{'mode':'bad'},{'subdivision':'XX'},{'weekdays':[True]}]:
                with self.assertRaises(ValueError):self.save(c,valid_from='2026-11-01',**fields)
            with self.assertRaises(PermissionError):wm.save(c,self.other,{'user_id':self.other})
            with self.assertRaises(PermissionError):wm.admin_list(c,self.other,{})

    def test_week_crosses_month_and_missing_model_stays_unknown(self):
        with app.db() as c:
            self.save(c,valid_from='2026-01-01')
            r=wm.overview(c,self.uid,{'day':'2026-02-01'},datetime(2026,2,2,12,tzinfo=timezone.utc))
            self.assertEqual(r['week_start'],'2026-01-26')
            self.assertEqual(r['week']['target_seconds'],40*3600)
            self.assertEqual(r['week']['closed_difference_seconds'],-40*3600)
            self.assertEqual(r['month']['closed_difference_seconds'],0)
            r=wm.overview(c,self.other,{'day':'2026-02-01'})
            self.assertIsNone(r['month']['target_seconds'])
            self.assertIsNone(r['month']['closed_difference_seconds'])

    def test_local_holiday_variants(self):
        self.assertNotIn(date(2026,8,15),wm.holiday_calendar(2026,'BY'))
        self.assertIn(date(2026,8,15),wm.holiday_calendar(2026,'BY-C'))
        self.assertIn(date(2026,8,8),wm.holiday_calendar(2026,'Augsburg'))
        self.assertIn(date(2026,10,31),wm.holiday_calendar(2026,'SH'))

    def test_closed_nonworkday_has_no_holiday_credit(self):
        with app.db() as c:
            self.save(c)
            r=wm.overview(c,self.uid,{'day':'2026-10-31'},datetime(2026,11,1,12,tzinfo=timezone.utc))['day']
            self.assertTrue(r['holiday'])
            self.assertEqual(r['holiday_seconds'],0)
            self.assertEqual(r['difference_seconds'],0)
