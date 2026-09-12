import sqlite3
import unittest

import final_batch_runtime as final


class FinalBatchTests(unittest.TestCase):
    def test_permission_dependencies_close_transitively(self):
        perms=final.closure({'users.roles.assign','bookkeeping.manage','smtp.edit'})
        self.assertTrue({'users.view','roles.view','admin.options.view','bookkeeping.view','smtp.view'}.issubset(perms))

    def test_customer_dependency_keeps_basic_view(self):
        perms=final.closure({'customers.view_links','customers.delete'})
        self.assertIn('customers.view_basic',perms)

    def test_provider_identity_is_stable(self):
        self.assertEqual(final._provider_identifier('teamviewer',{'deviceid':'123','devicename':'Kasse'}),('teamviewer_id','123'))
        self.assertEqual(final._provider_identifier('starface',{'direction':'INBOUND','callerNumber':'+49123','calledNumber':'22'}),('phone','+49123'))
        self.assertEqual(final._provider_identifier('starface',{'direction':'OUTBOUND','callerNumber':'22','calledNumber':'+49456'}),('phone','+49456'))
        self.assertEqual(final._provider_identifier('zammad',{'customer':{'email':'TEST@EXAMPLE.DE'}}),('email','test@example.de'))

    def test_worktime_totals_are_derived_and_persisted(self):
        c=sqlite3.connect(':memory:')
        c.row_factory=sqlite3.Row
        c.executescript('''
          CREATE TABLE work_sessions(id INTEGER PRIMARY KEY,owner_id INTEGER,started_at TEXT,ended_at TEXT,pause_seconds INTEGER DEFAULT 0,net_seconds INTEGER DEFAULT 0);
          CREATE TABLE work_pauses(id INTEGER PRIMARY KEY,owner_id INTEGER,work_session_id INTEGER,started_at TEXT,ended_at TEXT);
          INSERT INTO work_sessions(id,owner_id,started_at,ended_at) VALUES(1,7,'2026-09-12T08:00:00+00:00','2026-09-12T12:00:00+00:00');
          INSERT INTO work_pauses(owner_id,work_session_id,started_at,ended_at) VALUES(7,1,'2026-09-12T09:00:00+00:00','2026-09-12T09:15:00+00:00');
          INSERT INTO work_pauses(owner_id,work_session_id,started_at,ended_at) VALUES(7,1,'2026-09-12T11:00:00+00:00','2026-09-12T11:30:00+00:00');
        ''')
        final.recompute_work_totals(c,7)
        row=c.execute('SELECT pause_seconds,net_seconds FROM work_sessions WHERE id=1').fetchone()
        self.assertEqual(row['pause_seconds'],2700)
        self.assertEqual(row['net_seconds'],11700)


if __name__=='__main__':
    unittest.main()
