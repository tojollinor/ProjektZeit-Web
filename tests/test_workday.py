import os
import sys
import tempfile
import unittest
import json
import threading
import urllib.request
import urllib.error
import http.cookiejar
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import workday


class WorkdayTest(unittest.TestCase):
    def setUp(self):
        self.maria_name = None
        if os.environ.get('PZ_TEST_MARIADB') == '1':
            import pymysql
            self.maria_name = 'pz_test_' + uuid.uuid4().hex
            self.maria_admin = pymysql.connect(host=os.environ.get('DB_HOST','127.0.0.1'), port=int(os.environ.get('DB_PORT','3306')),
                user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], autocommit=True)
            with self.maria_admin.cursor() as cursor:
                cursor.execute('CREATE DATABASE `' + self.maria_name + '` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
            os.environ.update(DB_BACKEND='mariadb', DB_NAME=self.maria_name)
        self.tmp = tempfile.TemporaryDirectory()
        app.DATA_DIR = Path(self.tmp.name)
        app.DB_PATH = app.DATA_DIR / 'test.db'
        os.environ.update(DEMO_MODE='1', ADMIN_USER='admin', ADMIN_PASSWORD='admin', SEED_DEMO='0')
        app.init_db()
        with app.db() as c:
            self.uid = c.execute('SELECT id FROM users').fetchone()['id']
            self.cid = c.execute('SELECT id FROM categories').fetchone()['id']
            self.pids = [c.execute('INSERT INTO projects(owner_id,name) VALUES(?,?)', (self.uid, name)).lastrowid for name in ('A', 'B')]

    def tearDown(self):
        self.tmp.cleanup()
        if self.maria_name:
            with self.maria_admin.cursor() as cursor:
                cursor.execute('DROP DATABASE `' + self.maria_name + '`')
            self.maria_admin.close()

    def at(self, value):
        return datetime.fromisoformat('2026-09-08T' + value).replace(tzinfo=timezone.utc)

    def action(self, action, time, project=0):
        with app.db() as c:
            workday.transition(c, self.uid, action, {'project_id': self.pids[project], 'category_id': self.cid}, self.at(time))

    def rows(self):
        with app.db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM entries ORDER BY started_at')]

    def test_workflow_and_gap_recalculation(self):
        self.action('begin', '08:00')
        self.action('switch', '08:10')
        self.action('switch', '09:00', 1)
        self.action('idle', '09:30')
        self.action('switch', '09:45')
        self.action('end', '10:00')
        rows = self.rows()
        self.assertEqual([r['is_idle'] for r in rows], [1, 0, 0, 1, 0])
        self.assertTrue(all(r['ended_at'] for r in rows))
        self.assertTrue(all(rows[i]['ended_at'] == rows[i+1]['started_at'] for i in range(len(rows)-1)))
        self.assertEqual(sum((workday.stamp(r['ended_at'])-workday.stamp(r['started_at'])).total_seconds() for r in rows), 7200)
        row = rows[1]
        body = dict(id=row['id'], original_start=row['started_at'], original_end=row['ended_at'], original_note=row['note'],
                    started_at=row['started_at'], ended_at=workday.iso(self.at('08:50')), project_id=row['project_id'], category_id=row['category_id'], note='Korrektur\nmehrzeilig')
        with app.db() as c:
            workday.edit(c, self.uid, body, self.at('12:00'))
        rows = self.rows()
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[2]['is_idle'], 1)
        self.assertEqual(rows[2]['started_at'], workday.iso(self.at('08:50')))
        self.assertTrue(all(rows[i]['ended_at'] == rows[i+1]['started_at'] for i in range(len(rows)-1)))
        with self.assertRaises(ValueError):
            with app.db() as c:
                workday.edit(c, self.uid, body, self.at('12:00'))

    def test_invalid_switch_rolls_back_and_only_one_open(self):
        with self.assertRaises(ValueError):
            self.action('switch', '08:00')
        self.action('begin', '08:00')
        self.action('switch', '08:10')
        with self.assertRaises(ValueError):
            with app.db() as c:
                workday.transition(c, self.uid, 'switch', {'project_id': 999, 'category_id': self.cid}, self.at('08:20'))
        self.assertEqual(sum(r['ended_at'] is None for r in self.rows()), 1)
        self.action('switch', '08:30')
        self.assertEqual(len(self.rows()), 2)
        with self.assertRaises(ValueError):
            self.action('begin', '08:40')

    def test_edit_overlap_rejected(self):
        self.action('begin', '08:00')
        self.action('switch', '08:10')
        self.action('switch', '09:00', 1)
        self.action('end', '10:00')
        row = self.rows()[1]
        body = dict(id=row['id'], original_start=row['started_at'], original_end=row['ended_at'], original_note=row['note'],
                    started_at=row['started_at'], ended_at=workday.iso(self.at('09:15')), project_id=row['project_id'], category_id=row['category_id'], note='')
        with self.assertRaisesRegex(ValueError, 'überschneidet'):
            with app.db() as c:
                workday.edit(c, self.uid, body, self.at('12:00'))
        self.assertEqual(self.rows()[1]['ended_at'], row['ended_at'])

    def test_idle_only_day_and_restart(self):
        self.action('begin', '08:00')
        app.init_db()
        self.assertEqual(sum(r['ended_at'] is None for r in self.rows()), 1)
        self.action('end', '09:00')
        self.action('begin', '10:00')
        self.action('end', '11:00')
        self.assertEqual(len(self.rows()), 2)
        self.assertTrue(all(r['is_idle'] for r in self.rows()))

    def test_reassign_part_of_idle_time(self):
        self.action('begin', '08:00')
        self.action('end', '10:00')
        row = self.rows()[0]
        body = dict(id=row['id'], original_start=row['started_at'], original_end=row['ended_at'], original_note=row['note'],
                    started_at=workday.iso(self.at('08:30')), ended_at=workday.iso(self.at('09:30')), project_id=self.pids[0], category_id=self.cid, note='Nachgetragen')
        with app.db() as c:
            workday.edit(c, self.uid, body, self.at('12:00'))
        self.assertEqual([r['is_idle'] for r in self.rows()], [1, 0, 1])

    def test_user_isolation(self):
        self.action('begin', '08:00')
        self.action('switch', '08:10')
        self.action('end', '10:00')
        row = self.rows()[1]
        with self.assertRaisesRegex(ValueError, 'nicht gefunden'):
            with app.db() as c:
                workday.edit(c, self.uid+1, {'id':row['id']}, self.at('12:00'))

    def test_http_workflow_and_csv_conflict(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.App)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:%d' % server.server_port
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        csrf = ''
        def request(route, body=None):
            headers = {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}
            req = urllib.request.Request(base + route, data=json.dumps(body).encode() if body is not None else None, headers=headers)
            with client.open(req) as response:
                return response.read().decode('utf-8-sig')
        try:
            request('/api/v1/login', {'username':'admin','password':'admin'})
            csrf = json.loads(request('/api/v1/me'))['csrf']
            request('/api/v1/work/begin', {})
            request('/api/v1/timer/start', {'project_id':self.pids[0],'category_id':self.cid})
            request('/api/v1/timer/start', {'project_id':self.pids[1],'category_id':self.cid})
            request('/api/v1/timer/stop', {})
            request('/api/v1/work/end', {})
            dashboard = json.loads(request('/api/v1/dashboard'))
            self.assertIsNone(dashboard['work'])
            self.assertEqual(len(dashboard['entries']), 4)
            self.assertEqual(sum(r['is_idle'] for r in dashboard['entries']), 2)
            exported = request('/api/v1/export.csv')
            imported = json.loads(request('/api/v1/import.csv', {'csv':exported}))
            self.assertEqual(imported['imported'], 0)
            self.assertEqual(imported['skipped'], 4)
            self.assertEqual(imported['errors'], [])
            row = next(r for r in dashboard['entries'] if not r['is_idle'])
            bad_csv = 'Projekt;Start;Ende\nAnderes Projekt;%s;%s' % (row['started_at'], row['ended_at'])
            conflict = json.loads(request('/api/v1/import.csv', {'csv':bad_csv}))
            self.assertEqual(conflict['imported'], 0)
            self.assertEqual(len(conflict['errors']), 1)
            body = dict(id=row['id'], original_start=row['started_at'], original_end=row['ended_at'], original_note=row['note'],
                        started_at=row['started_at'], ended_at=row['ended_at'], project_id=row['project_id'], category_id=row['category_id'], note='HTTP Test')
            request('/api/v1/entries/edit', body)
            request('/api/v1/projects/active', {'id':self.pids[0],'active':False})
            csrf = 'wrong'
            with self.assertRaises(urllib.error.HTTPError) as error:
                request('/api/v1/work/begin', {})
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
