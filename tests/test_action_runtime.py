import contextlib
import json
import sqlite3
import types
import unittest
import action_runtime as actions

class ActionReceiptTest(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row;actions.migrate(self.c)
        self.c.execute('CREATE TABLE changes(value INTEGER)');self.c.commit();self.calls=0;self.responses=[]
        @contextlib.contextmanager
        def db(**kwargs):
            with self.c:yield self.c
        outer=self
        class Handler:
            path='/api/v1/company/model/save';headers={'Idempotency-Key':'test-request-000001'}
            def require(self,csrf=False):return {'id':1}
            def json_body(self):return {'hours':40}
            def send_json(self,status,payload,extra_headers=None):
                outer.assertFalse(outer.c.in_transaction,'Response sent before commit')
                outer.responses.append((status,payload))
            def do_POST(self):
                outer.calls+=1
                with db() as c:
                    c.execute('INSERT INTO changes VALUES(1)')
                    self.send_json(200,{'ok':True})
        self.app=types.SimpleNamespace(App=Handler,db=db,init_db=lambda create_admin=True:None)
        actions.install(self.app);self.handler=Handler()
    def tearDown(self):self.c.close()
    def test_success_delivered_after_commit_and_replayed_without_second_write(self):
        self.handler.do_POST();self.handler.do_POST()
        self.assertEqual(self.calls,1);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM changes').fetchone()[0],1)
        self.assertEqual(self.responses,[(200,{'ok':True})]*2)
    def test_same_key_cannot_change_body(self):
        self.handler.do_POST();self.handler.json_body=lambda:{'hours':20};self.handler.do_POST()
        self.assertEqual(self.responses[-1][0],400);self.assertEqual(self.calls,1)
    def test_pending_never_reexecutes(self):
        with self.c:actions.reserve(self.c,1,'test-request-000001',self.handler.path,{'hours':40})
        self.handler.do_POST();self.assertEqual(self.responses[-1][0],409);self.assertEqual(self.calls,0)
    def test_user_receipt_isolation(self):
        self.handler.do_POST();self.handler.path='/api/v1/actions/receipt';self.handler.require=lambda **kw:{'id':2};self.handler.json_body=lambda:{'request_id':'test-request-000001'}
        self.handler.do_POST();self.assertEqual(self.responses[-1][1]['state'],'unknown')

if __name__=='__main__':unittest.main()
