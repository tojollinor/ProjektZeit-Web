"""Durable action receipts and response delivery after database scopes commit.

An uncertain interrupted action is never automatically executed again.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

MUTATION=re.compile(r'/(save|assign(?:/(?:customer|project))?|profile|phone|contact-phone|contact|device|delete|action|review|reopen|edit|update|add|archive|begin|end|start|stop|pause|resume|active|approve|reject|submit|cancel|pay|close|swap|settings|status|clone|merge|roles|preferences|reset-user)$')
EXCLUDED=('/api/v1/auth/','/api/v1/integrations/','/api/v1/archive/','/api/v1/provider/refresh/','/api/v1/settings/','/api/v1/account/')

def eligible(path):
    if path in ('/api/v1/admin/user/create','/api/v1/customers', '/api/v1/categories', '/api/v1/projects', '/api/v1/users', '/api/v1/profile/avatar', '/api/v1/sessions/disconnect', '/api/v1/integrations/save', '/api/v1/integrations/remove', '/api/v1/account/save', '/api/v1/account/theme'):return True
    return bool(MUTATION.search(path)) and not path.startswith(EXCLUDED) and path not in ('/api/v1/provider/navigation-status',)

def stamp():return datetime.now(timezone.utc).isoformat(timespec='seconds')

def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS action_receipts(
        owner_id INTEGER NOT NULL, request_id VARCHAR(64) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL, path VARCHAR(255) NOT NULL,
        state VARCHAR(24) NOT NULL, status INTEGER, payload LONGTEXT,
        created_at VARCHAR(40) NOT NULL, completed_at VARCHAR(40),
        PRIMARY KEY(owner_id,request_id));''')

def reserve(c,uid,key,path,body):
    digest=hashlib.sha256((path+'\n'+json.dumps(body,sort_keys=True,separators=(',',':'))).encode()).hexdigest()
    c.execute('BEGIN IMMEDIATE')
    row=c.execute('SELECT * FROM action_receipts WHERE owner_id=? AND request_id=?',(uid,key)).fetchone()
    if row:
        if row['fingerprint']!=digest:raise ValueError('Anfragekennung bereits für andere Daten verwendet.')
        return dict(row)
    c.execute('INSERT INTO action_receipts(owner_id,request_id,fingerprint,path,state,created_at) VALUES(?,?,?,?,?,?)',(uid,key,digest,path,'pending',stamp()))
    return None

def install(app):
    original_init=app.init_db
    def init(create_admin=True):
        original_init(create_admin)
        with app.db() as c:migrate(c)
    app.init_db=init
    previous=app.App.do_POST
    def post(self):
        path=urlparse(self.path).path
        if path=='/api/v1/actions/receipt':
            session=self.require(csrf=True)
            if not session:return
            try:
                body=self.json_body()
                with app.db(read_only=True) as c:row=c.execute('SELECT state,status,payload FROM action_receipts WHERE owner_id=? AND request_id=?',(session['id'],str(body.get('request_id') or ''))).fetchone()
                return self.send_json(200,{'state':row['state'] if row else 'unknown','status':row['status'] if row else None,'payload':json.loads(row['payload']) if row and row['payload'] else None})
            except (ValueError,TypeError):return self.send_json(400,{'error':'Ungültige Anfrage.'})
        key=self.headers.get('Idempotency-Key','')
        use=bool(key and eligible(path))
        session=None
        if use:
            if not re.fullmatch(r'[A-Za-z0-9_-]{16,64}',key):return self.send_json(400,{'error':'Ungültige Anfragekennung.'})
            session=self.require(csrf=True)
            if not session:return
            try:
                body=self.json_body()
                with app.db() as c:existing=reserve(c,session['id'],key,path,body)
                if existing:
                    if existing['state']=='completed':return self.send_json(existing['status'],json.loads(existing['payload']))
                    return self.send_json(409,{'error':'Speicherstatus noch ungeklärt. Vorgang wird nicht erneut ausgeführt.','action_state':'pending','request_id':key})
            except (ValueError,TypeError) as e:return self.send_json(400,{'error':str(e)})
        # Legacy handlers sometimes send while still inside a transaction. Defer
        # their JSON response until the entire handler and all context managers exit.
        send=self.send_json;response=[]
        self.send_json=lambda status,payload,extra_headers=None:response.append((status,payload,extra_headers))
        failure=None
        try:previous(self)
        except Exception as e:failure=e
        finally:self.send_json=send
        if failure:
            if use:
                with app.db() as c:c.execute("UPDATE action_receipts SET state='uncertain' WHERE owner_id=? AND request_id=?",(session['id'],key))
            return send(500,{'error':'Vorgang konnte nicht bestätigt werden. Bitte Status prüfen.','action_state':'uncertain' if use else 'error','request_id':key})
        if not response:return
        status,payload,headers=response[-1]
        if use:
            with app.db() as c:c.execute("UPDATE action_receipts SET state='completed',status=?,payload=?,completed_at=? WHERE owner_id=? AND request_id=?",(status,json.dumps(payload,ensure_ascii=False),stamp(),session['id'],key))
        return send(status,payload,headers)
    app.App.do_POST=post
