import sqlite3
import unittest

import final_batch_runtime as final
import performance_v2_runtime as perf


SCHEMA = '''
CREATE TABLE provider_assignments(
 owner_id INTEGER,provider TEXT,external_key TEXT,customer_id INTEGER,project_id INTEGER,
 match_type TEXT,match_value TEXT,assigned_by INTEGER,assigned_at TEXT,
 PRIMARY KEY(owner_id,provider,external_key));
CREATE TABLE customer_identity_links(
 owner_id INTEGER,customer_id INTEGER,provider TEXT,link_type TEXT,link_value TEXT,
 display_name TEXT,created_at TEXT);
CREATE TABLE customers(id INTEGER PRIMARY KEY,owner_id INTEGER,name TEXT);
CREATE TABLE projects(id INTEGER PRIMARY KEY,owner_id INTEGER,name TEXT);
CREATE TABLE provider_events(owner_id INTEGER,provider TEXT,external_key TEXT,occurred_at TEXT,captured_at TEXT);
'''


class PerformanceV2Tests(unittest.TestCase):
    def db(self):
        c = sqlite3.connect(':memory:')
        c.row_factory = sqlite3.Row
        c.executescript(SCHEMA)
        return c

    def test_enrichment_uses_fixed_number_of_reads_for_large_ticket_list(self):
        c = self.db()
        c.execute("INSERT INTO customers(id,owner_id,name) VALUES(1,7,'Kunde')")
        result = {'rows': [
            {'external_key': f'zammad:id:{i}', 'raw': {'customer': {'email': f'user{i}@example.test'}}, 'customer_hint': {}}
            for i in range(300)
        ]}
        statements = []
        c.set_trace_callback(statements.append)
        perf._fast_enrich(final, c, 7, 'zammad', result)
        reads = [s for s in statements if s.lstrip().upper().startswith('SELECT')]
        self.assertLessEqual(len(reads), 5)
        self.assertEqual(len(result['rows']), 300)

    def test_enrichment_preserves_identity_link_assignment_and_customer_name(self):
        c = self.db()
        c.execute("INSERT INTO customers(id,owner_id,name) VALUES(12,7,'Muster GmbH')")
        c.execute("INSERT INTO customer_identity_links(owner_id,customer_id,provider,link_type,link_value,display_name,created_at) VALUES(7,12,'zammad','email','kunde@example.test','','2026-09-12T10:00:00+00:00')")
        c.execute("INSERT INTO provider_events(owner_id,provider,external_key,occurred_at,captured_at) VALUES(7,'zammad','zammad:id:42','2026-09-12T11:00:00+00:00','2026-09-12T11:01:00+00:00')")
        result = {'rows': [{'external_key': 'zammad:id:42', 'raw': {'customer': {'email': 'KUNDE@EXAMPLE.TEST'}}, 'customer_hint': {}}]}
        perf._fast_enrich(final, c, 7, 'zammad', result)
        assignment = result['rows'][0]['assignment']
        self.assertEqual(assignment['customer_id'], 12)
        self.assertEqual(assignment['customer_name'], 'Muster GmbH')
        self.assertIsNotNone(c.execute("SELECT 1 FROM provider_assignments WHERE owner_id=7 AND provider='zammad' AND external_key='zammad:id:42'").fetchone())

    def test_old_event_is_not_retroactively_assigned_to_new_link(self):
        c = self.db()
        c.execute("INSERT INTO customers(id,owner_id,name) VALUES(12,7,'Muster GmbH')")
        c.execute("INSERT INTO customer_identity_links(owner_id,customer_id,provider,link_type,link_value,display_name,created_at) VALUES(7,12,'zammad','email','kunde@example.test','','2026-09-12T12:00:00+00:00')")
        c.execute("INSERT INTO provider_events(owner_id,provider,external_key,occurred_at,captured_at) VALUES(7,'zammad','zammad:id:42','2026-09-12T11:00:00+00:00','2026-09-12T11:01:00+00:00')")
        result = {'rows': [{'external_key': 'zammad:id:42', 'raw': {'customer': {'email': 'kunde@example.test'}}, 'customer_hint': {}}]}
        perf._fast_enrich(final, c, 7, 'zammad', result)
        self.assertIsNone(result['rows'][0]['assignment']['customer_id'])
        self.assertIsNone(c.execute("SELECT 1 FROM provider_assignments WHERE owner_id=7 AND provider='zammad' AND external_key='zammad:id:42'").fetchone())


if __name__ == '__main__':
    unittest.main()
