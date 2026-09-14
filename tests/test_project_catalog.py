import unittest
import project_catalog as pc
import app
import next_batch_runtime
import final_batch_runtime
import system_features
import time_workspace
import test_workday
import admin_controls
import customer_data


class ProjectCatalogTests(unittest.TestCase):
    setUpBase = test_workday.WorkdayTest.setUp
    tearDown = test_workday.WorkdayTest.tearDown

    def setUp(self):
        self.setUpBase()
        with app.db() as c:
            admin_controls.migrate(c)
            system_features.migrate(c)
            next_batch_runtime.migrate(c)
            final_batch_runtime.migrate(c)
            customer_data.migrate(c)
            time_workspace.migrate(c)
            pc.migrate(c)
            self.customer = c.execute('INSERT INTO customers(owner_id,name) VALUES(?,?)', (self.uid,'Customer')).lastrowid
            c.execute('UPDATE projects SET customer_id=? WHERE id=?',(self.customer,self.pids[0]))
            self.other = c.execute("INSERT INTO users(username,password_salt,password_hash,role,created_at) VALUES('other','','','user','')").lastrowid
            self.other_project = c.execute("INSERT INTO projects(owner_id,name) VALUES(?,'Private')",(self.other,)).lastrowid

    def test_clone_copies_only_customer_and_active_tags(self):
        with app.db() as c:
            t=pc.save_tag(c,self.uid,{'name':'Update','customer_id':self.customer})['id']
            archived=pc.save_tag(c,self.uid,{'name':'Old'})['id']
            pc.assign_tags(c,self.uid,{'project_id':self.pids[0],'tags':[t,archived]})
            pc.save_tag(c,self.uid,{'id':archived,'name':'Old','active':False})
            c.execute("UPDATE projects SET status='closed',active=0,billing_state='billed' WHERE id=?",(self.pids[0],))
            c.execute("INSERT INTO entries(owner_id,project_id,category_id,started_at,ended_at,note) VALUES(?,?,?,'2026-09-01T08:00:00+00:00','2026-09-01T09:00:00+00:00','Original')",(self.uid,self.pids[0],self.cid))
            new=pc.clone(c,self.uid,{'project_id':self.pids[0],'name':'Update 2'})['project_id']
            p=pc.project(c,self.uid,new)
            self.assertEqual((p['customer_id'],p['status'],p['active'],p['billing_state']),(self.customer,'active',1,''))
            self.assertEqual([r['tag_id'] for r in c.execute('SELECT tag_id FROM project_tag_links WHERE project_id=?',(new,))],[t])
            self.assertEqual(c.execute('SELECT COUNT(*) n FROM entries WHERE project_id=?',(new,)).fetchone()['n'],0)
            self.assertEqual(c.execute('SELECT template_id FROM project_origins WHERE project_id=?',(new,)).fetchone()['template_id'],self.pids[0])
            self.assertEqual(pc.project(c,self.uid,self.pids[0])['billing_state'],'billed')

    def test_ownership_scope_and_archive(self):
        with app.db() as c:
            t=pc.save_tag(c,self.uid,{'name':'Update','customer_id':self.customer})['id']
            with self.assertRaises(ValueError):pc.assign_tags(c,self.uid,{'project_id':self.pids[1],'tags':[t]})
            with self.assertRaises(PermissionError):pc.clone(c,self.uid,{'project_id':self.other_project,'name':'Forbidden'})
            with self.assertRaises(PermissionError):pc.assign_tags(c,self.other,{'project_id':self.pids[0],'tags':[t]})
            with self.assertRaises(PermissionError):pc.save_tag(c,self.other,{'id':t,'name':'Stolen'})
            pc.assign_tags(c,self.uid,{'project_id':self.pids[0],'tags':[t]})
            pc.save_tag(c,self.uid,{'id':t,'customer_id':self.customer,'name':'Update','active':False})
            pc.assign_tags(c,self.uid,{'project_id':self.pids[0],'tags':[t]})
            c.execute('UPDATE projects SET customer_id=? WHERE id=?',(self.customer,self.pids[1]))
            with self.assertRaises(ValueError):pc.assign_tags(c,self.uid,{'project_id':self.pids[1],'tags':[t]})
            self.assertEqual(pc.catalog(c,self.other,{})['tags'],[])
            self.assertEqual(len(pc.catalog(c,self.other,{})['projects']),1)

    def test_comparison_unions_manual_and_provider_intervals(self):
        with app.db() as c:
            for a,b in [('08:00','09:00'),('08:30','09:30')]:
                c.execute('INSERT INTO entries(owner_id,project_id,category_id,started_at,ended_at) VALUES(?,?,?,?,?)',(self.uid,self.pids[0],self.cid,'2026-09-01T'+a+':00+00:00','2026-09-01T'+b+':00+00:00'))
            c.execute("INSERT INTO event_intervals VALUES(?,'starface','call','2026-09-01T09:00:00+00:00','2026-09-01T10:00:00+00:00','','')",(self.uid,))
            c.execute("INSERT INTO provider_assignments(owner_id,provider,external_key,customer_id,project_id,assigned_by,assigned_at) VALUES(?,'starface','call',?,?,?,'')",(self.uid,self.customer,self.pids[0],self.uid))
            c.execute("INSERT INTO entries(owner_id,project_id,category_id,started_at) VALUES(?,?,?,'2026-09-01T11:00:00+00:00')",(self.uid,self.pids[0],self.cid))
            result=pc.catalog(c,self.uid,{})
            self.assertEqual(next(p for p in result['projects'] if p['id']==self.pids[0])['seconds'],7200)
            self.assertEqual(len(result['projects']),2)

    def test_validation_and_transaction_rollback(self):
        with app.db() as c:
            with self.assertRaises(ValueError):pc.clone(c,self.uid,{'project_id':self.pids[0],'name':'B'})
            with self.assertRaises(ValueError):pc.save_tag(c,self.uid,{'name':' '})
            pc.save_tag(c,self.uid,{'name':'Update'})
            with self.assertRaises(ValueError):pc.save_tag(c,self.uid,{'name':'Update'})
        with self.assertRaises(RuntimeError):
            with app.db() as c:
                pc.clone(c,self.uid,{'project_id':self.pids[0],'name':'Rollback'})
                raise RuntimeError('Commit interrupted')
        with app.db() as c:
            self.assertIsNone(c.execute("SELECT id FROM projects WHERE name='Rollback'").fetchone())

    def test_customer_change_excludes_stale_customer_tags(self):
        with app.db() as c:
            tag=pc.save_tag(c,self.uid,{'name':'Scoped','customer_id':self.customer})['id']
            pc.assign_tags(c,self.uid,{'project_id':self.pids[0],'tags':[tag]})
            c.execute('UPDATE projects SET customer_id=NULL WHERE id=?',(self.pids[0],))
            self.assertEqual(pc.catalog(c,self.uid,{})['links'],[])
            new=pc.clone(c,self.uid,{'project_id':self.pids[0],'name':'No stale tags'})['project_id']
            self.assertEqual(c.execute('SELECT COUNT(*) n FROM project_tag_links WHERE project_id=?',(new,)).fetchone()['n'],0)
