import os
import unittest
from unittest.mock import patch
import test_workday as fixtures
import app
import integrations
import migrate_sqlite


@unittest.skipUnless(os.environ.get('PZ_TEST_MARIADB') == '1', 'Requires isolated MariaDB test server')
class MigrationTests(unittest.TestCase):
    setUp = fixtures.WorkdayTest.setUp
    tearDown = fixtures.WorkdayTest.tearDown

    def test_import_preserves_ids_and_secrets_and_refuses_second_import(self):
        source = app.DATA_DIR / 'legacy.db'
        with patch.dict(os.environ, {'DB_BACKEND':'sqlite'}), patch.object(app,'DB_PATH',source):
            app.init_db()
            with app.db() as c:
                uid=c.execute('SELECT id FROM users').fetchone()['id']
                c.execute('INSERT INTO customers(id,owner_id,name) VALUES(?,?,?)',(42,uid,'Größe & Söhne'))
                c.execute('INSERT INTO projects(id,owner_id,customer_id,name) VALUES(?,?,?,?)',(53,uid,42,'Migration'))
                cid=c.execute('SELECT id FROM categories').fetchone()['id']
                c.execute('INSERT INTO entries(owner_id,project_id,category_id,started_at,ended_at,note) VALUES(?,?,?,?,?,?)',
                    (uid,53,cid,'2026-09-01T08:00:00+00:00','2026-09-01T09:00:00+00:00','Mehrzeilige\nBemerkung'))
                integrations.save(c,uid,{'provider':'teamviewer','domain':'https://webapi.teamviewer.com','username':'','secret':'migration-token'},app.DATA_DIR)
        with app.db() as c:
            c.execute('DELETE FROM projects');c.execute('DELETE FROM categories');c.execute('DELETE FROM users')
        counts=migrate_sqlite.migrate(source)
        self.assertEqual(counts['entries'],1)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT name FROM customers WHERE id=42').fetchone()['name'],'Größe & Söhne')
            self.assertEqual(c.execute('SELECT note FROM entries').fetchone()['note'],'Mehrzeilige\nBemerkung')
            saved=integrations.config(c,uid,{'provider':'teamviewer','domain':'https://webapi.teamviewer.com','username':'','secret':''},app.DATA_DIR)
            self.assertEqual(saved['secret'],'migration-token')
        with self.assertRaisesRegex(RuntimeError,'nicht leer'):
            migrate_sqlite.migrate(source)
