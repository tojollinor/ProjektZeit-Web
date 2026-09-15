import sqlite3
import unittest
from unittest.mock import Mock

import final_batch_runtime as final
import final_batch_fix_runtime as final_fix


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
        self.assertEqual(final._provider_identifiers('zammad',{
            'customer':{'id':42,'email':'TEST@EXAMPLE.DE'},
            'organization':{'id':9},
        }),[('email','test@example.de'),('zammad_customer_id','42'),('zammad_organization_id','9')])

    def test_grouped_callback_marks_every_call_once(self):
        c=sqlite3.connect(':memory:')
        c.row_factory=sqlite3.Row
        c.executescript('''
          CREATE TABLE provider_events(owner_id INTEGER,provider TEXT,external_key TEXT);
          CREATE TABLE starface_manual_callbacks(owner_id INTEGER,external_key TEXT,marked_by INTEGER,marked_at TEXT,
            PRIMARY KEY(owner_id,external_key));
          INSERT INTO provider_events VALUES(7,'starface','call-1');
          INSERT INTO provider_events VALUES(7,'starface','call-2');
          INSERT INTO provider_events VALUES(8,'starface','call-3');
        ''')
        keys=final.mark_manual_callbacks(c,7,['call-1','call-2','call-1'])
        self.assertEqual(keys,['call-1','call-2'])
        self.assertEqual(c.execute('SELECT COUNT(*) n FROM starface_manual_callbacks WHERE owner_id=7').fetchone()['n'],2)
        with self.assertRaisesRegex(ValueError,'nicht gefunden'):
            final.mark_manual_callbacks(c,7,['call-1','call-3'])
        self.assertEqual(c.execute('SELECT COUNT(*) n FROM starface_manual_callbacks WHERE owner_id=7').fetchone()['n'],2)


    def test_starface_callback_targets_use_native_call_list_id_and_owner(self):
        c=sqlite3.connect(':memory:')
        c.row_factory=sqlite3.Row
        c.executescript("""
          CREATE TABLE provider_events(owner_id INTEGER,provider TEXT,external_key TEXT,raw_json TEXT);
          INSERT INTO provider_events VALUES(7,'starface','starface:id:event-1','{"id":"event-1","direction":"INBOUND","result":"MISSED"}');
          INSERT INTO provider_events VALUES(7,'starface','starface:id:event-2','{"id":"event-2","direction":"INBOUND","result":"MISSED"}');
          INSERT INTO provider_events VALUES(8,'starface','starface:id:event-3','{"id":"event-3","direction":"INBOUND","result":"MISSED"}');
        """)
        targets=final.starface_callback_targets(c,7,['starface:id:event-1','starface:id:event-2'])
        self.assertEqual(targets,[
            {'external_key':'starface:id:event-1','call_list_entry_id':'event-1'},
            {'external_key':'starface:id:event-2','call_list_entry_id':'event-2'},
        ])
        with self.assertRaisesRegex(ValueError,'nicht gefunden'):
            final.starface_callback_targets(c,7,['starface:id:event-3'])

    def test_starface_callback_targets_reject_non_missed_and_missing_native_id(self):
        c=sqlite3.connect(':memory:')
        c.row_factory=sqlite3.Row
        c.executescript("""
          CREATE TABLE provider_events(owner_id INTEGER,provider TEXT,external_key TEXT,raw_json TEXT);
          INSERT INTO provider_events VALUES(7,'starface','answered','{"id":"answered-1","direction":"INBOUND","result":"ANSWERED"}');
          INSERT INTO provider_events VALUES(7,'starface','missing-id','{"direction":"INBOUND","result":"MISSED"}');
        """)
        with self.assertRaisesRegex(ValueError,'Nur verpasste'):
            final.starface_callback_targets(c,7,['answered'])
        with self.assertRaisesRegex(ValueError,'Anruflisten-ID'):
            final.starface_callback_targets(c,7,['missing-id'])

    def test_starface_callback_sync_writes_server_before_local_marker(self):
        c=sqlite3.connect(':memory:')
        c.row_factory=sqlite3.Row
        c.executescript("""
          CREATE TABLE provider_events(owner_id INTEGER,provider TEXT,external_key TEXT,raw_json TEXT);
          CREATE TABLE starface_manual_callbacks(owner_id INTEGER,external_key TEXT,marked_by INTEGER,marked_at TEXT,PRIMARY KEY(owner_id,external_key));
          INSERT INTO provider_events VALUES(7,'starface','starface:id:event-1','{"id":"event-1","direction":"INBOUND","result":"MISSED"}');
        """)
        app=Mock();app.DATA_DIR='/tmp/test';app.starface_oauth.access.return_value={'domain':'https://pbx.example','secret':'token'}
        app.starface_calls.set_called_back.side_effect=ValueError('server rejected')
        with self.assertRaisesRegex(ValueError,'server rejected'):
            final.sync_starface_callbacks(app,c,7,['starface:id:event-1'])
        self.assertEqual(c.execute('SELECT COUNT(*) n FROM starface_manual_callbacks').fetchone()['n'],0)
        app.starface_calls.set_called_back.side_effect=None
        keys=final.sync_starface_callbacks(app,c,7,['starface:id:event-1'])
        self.assertEqual(keys,['starface:id:event-1'])
        app.starface_calls.set_called_back.assert_called_with({'domain':'https://pbx.example','secret':'token'},['event-1'],True)
        self.assertEqual(c.execute('SELECT COUNT(*) n FROM starface_manual_callbacks').fetchone()['n'],1)

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

    def test_existing_worktime_schema_can_reconcile_before_new_total_columns_exist(self):
        class DummyHandler:
            def do_POST(self):
                return None
        class DummyApp:
            App=DummyHandler
        final_fix.install(DummyApp)
        c=sqlite3.connect(':memory:')
        c.row_factory=sqlite3.Row
        c.executescript('''
          CREATE TABLE work_sessions(id INTEGER PRIMARY KEY,owner_id INTEGER,started_at TEXT,ended_at TEXT);
          CREATE TABLE work_pauses(id INTEGER PRIMARY KEY,owner_id INTEGER,work_session_id INTEGER,started_at TEXT,ended_at TEXT);
          INSERT INTO work_sessions(id,owner_id,started_at,ended_at) VALUES(1,7,'2026-09-12T08:00:00+00:00','2026-09-12T12:00:00+00:00');
        ''')
        final.recompute_work_totals(c,7)
        row=c.execute('SELECT id FROM work_sessions WHERE id=1').fetchone()
        self.assertEqual(row['id'],1)


if __name__=='__main__':
    unittest.main()
