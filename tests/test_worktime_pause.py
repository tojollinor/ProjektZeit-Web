import os
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import workday


class WorktimePauseTest(unittest.TestCase):
    def setUp(self):
        self.maria_name=None
        if os.environ.get('PZ_TEST_MARIADB')=='1':
            import pymysql
            self.maria_name='pz_pause_'+uuid.uuid4().hex
            self.maria_admin=pymysql.connect(host=os.environ.get('DB_HOST','127.0.0.1'),port=int(os.environ.get('DB_PORT','3306')),user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],autocommit=True)
            with self.maria_admin.cursor() as cursor:cursor.execute('CREATE DATABASE `'+self.maria_name+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
            os.environ.update(DB_BACKEND='mariadb',DB_NAME=self.maria_name)
        self.tmp=tempfile.TemporaryDirectory();app.DATA_DIR=Path(self.tmp.name);app.DB_PATH=app.DATA_DIR/'test.db'
        os.environ.update(DEMO_MODE='1',ADMIN_USER='admin',ADMIN_PASSWORD='admin',SEED_DEMO='0')
        app.init_db()
        with app.db() as c:
            workday.migrate(c);self.uid=c.execute('SELECT id FROM users').fetchone()['id'];self.cid=c.execute('SELECT id FROM categories').fetchone()['id'];self.pid=c.execute('INSERT INTO projects(owner_id,name) VALUES(?,?)',(self.uid,'Projekt')).lastrowid

    def tearDown(self):
        self.tmp.cleanup()
        if self.maria_name:
            with self.maria_admin.cursor() as cursor:cursor.execute('DROP DATABASE `'+self.maria_name+'`')
            self.maria_admin.close()

    def at(self,value):return datetime.fromisoformat('2026-09-12T'+value).replace(tzinfo=timezone.utc)
    def action(self,name,value):
        with app.db() as c:workday.transition(c,self.uid,name,{'project_id':self.pid,'category_id':self.cid},self.at(value))

    def test_pause_closes_project_and_is_not_idle_time(self):
        self.action('begin','08:00');self.action('switch','08:10');self.action('pause','09:00')
        with app.db() as c:
            pause=workday.active_pause(c,self.uid);self.assertIsNotNone(pause)
            self.assertIsNone(c.execute('SELECT id FROM entries WHERE owner_id=? AND is_idle=0 AND ended_at IS NULL',(self.uid,)).fetchone())
        with self.assertRaisesRegex(ValueError,'Pause beenden'):
            self.action('switch','09:05')
        self.action('resume','09:15');self.action('switch','09:20');self.action('end','10:00')
        with app.db() as c:
            pauses=[dict(x) for x in c.execute('SELECT * FROM work_pauses WHERE owner_id=?',(self.uid,))]
            idle=[dict(x) for x in c.execute('SELECT * FROM entries WHERE owner_id=? AND is_idle=1 ORDER BY started_at',(self.uid,))]
        self.assertEqual(len(pauses),1);self.assertIsNotNone(pauses[0]['ended_at'])
        for row in idle:
            a,b=workday.stamp(row['started_at']),workday.stamp(row['ended_at'])
            self.assertFalse(a < self.at('09:15') and b > self.at('09:00'))

    def test_end_during_pause_closes_pause(self):
        self.action('begin','08:00');self.action('pause','08:30');self.action('end','09:00')
        with app.db() as c:
            self.assertIsNone(workday.active_pause(c,self.uid));self.assertIsNone(c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND ended_at IS NULL',(self.uid,)).fetchone())


if __name__=='__main__':unittest.main()
