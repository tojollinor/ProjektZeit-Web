"""Personal and administrative REST API tokens plus a small OpenAPI surface."""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

import admin_controls
import provider_cache_runtime

USER_SCOPES = {
    'customers.read':'Kunden lesen',
    'projects.read':'Projekte lesen',
    'time.read':'Zeiterfassung lesen',
    'tickets.read':'Zammad-Tickets lesen',
    'starface.read':'STARFACE-Historie lesen',
    'teamviewer.read':'TeamViewer-Historie lesen',
}
ADMIN_SCOPES = {
    'admin.users.read':('Benutzer lesen','users.view'),
    'admin.integrations.read':('Integrationsstatus lesen','integrations.view'),
    'admin.logs.read':('System-/Provider-Logs lesen','logs.view'),
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS api_tokens (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      kind TEXT NOT NULL DEFAULT 'user',
      name TEXT NOT NULL,
      token_hash VARCHAR(64) NOT NULL UNIQUE,
      token_prefix TEXT NOT NULL,
      permissions_json LONGTEXT NOT NULL,
      created_at TEXT NOT NULL,
      last_used_at TEXT NOT NULL DEFAULT '',
      expires_at TEXT NOT NULL DEFAULT '',
      revoked_at TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_api_tokens_owner ON api_tokens(owner_id,kind,id DESC);
    ''')


def _permissions(row):
    try:return [str(x) for x in json.loads(row['permissions_json']) if isinstance(x,str)]
    except Exception:return []


def available_scopes(c, uid, kind):
    if kind=='admin':
        return {key:label for key,(label,permission) in ADMIN_SCOPES.items() if admin_controls.can(c,uid,permission)}
    scopes=dict(USER_SCOPES)
    if not admin_controls.can(c,uid,'customers.view'):scopes.pop('customers.read',None)
    if not admin_controls.can(c,uid,'integrations.view'):
        for key in ('tickets.read','starface.read','teamviewer.read'):scopes.pop(key,None)
    return scopes


def list_tokens(c, uid, kind):
    allowed=available_scopes(c,uid,kind)
    rows=[]
    for r in c.execute('''SELECT id,name,token_prefix,permissions_json,created_at,last_used_at,expires_at,revoked_at
                          FROM api_tokens WHERE owner_id=? AND kind=? ORDER BY id DESC''',(uid,kind)):
        rows.append({'id':r['id'],'name':r['name'],'prefix':r['token_prefix'],'permissions':_permissions(r),
                     'created_at':r['created_at'],'last_used_at':r['last_used_at'],'expires_at':r['expires_at'],
                     'revoked_at':r['revoked_at'],'active':not bool(r['revoked_at'])})
    return {'kind':kind,'scopes':allowed,'tokens':rows}


def create_token(c, uid, body, kind):
    allowed=available_scopes(c,uid,kind)
    name=str(body.get('name') or '').strip()[:120]
    if not name:raise ValueError('Bitte einen Namen für den API-Token eingeben.')
    requested=body.get('permissions') if isinstance(body.get('permissions'),list) else []
    permissions=sorted({str(x) for x in requested if str(x) in allowed})
    if not permissions:raise ValueError('Bitte mindestens eine API-Berechtigung auswählen.')
    try:days=int(body.get('expires_days') or 0)
    except (TypeError,ValueError):raise ValueError('Ungültige Gültigkeitsdauer.') from None
    if days not in (0,30,90,365):raise ValueError('Gültigkeitsdauer muss 30, 90, 365 Tage oder unbegrenzt sein.')
    raw='pz_%s_%s'%('a' if kind=='admin' else 'u',secrets.token_urlsafe(32))
    digest=hashlib.sha256(raw.encode()).hexdigest();prefix=raw[:12]+'…'
    expires=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat(timespec='seconds') if days else ''
    cur=c.execute('''INSERT INTO api_tokens(owner_id,kind,name,token_hash,token_prefix,permissions_json,created_at,last_used_at,expires_at,revoked_at)
                     VALUES(?,?,?,?,?,?,?,'',?,'')''',(uid,kind,name,digest,prefix,json.dumps(permissions),now_iso(),expires))
    return {'id':cur.lastrowid,'token':raw,'prefix':prefix,'name':name,'permissions':permissions,'expires_at':expires}


def revoke(c, uid, token_id, kind):
    try:token_id=int(token_id)
    except (TypeError,ValueError):raise ValueError('Ungültiger API-Token.') from None
    row=c.execute('SELECT id FROM api_tokens WHERE id=? AND owner_id=? AND kind=?',(token_id,uid,kind)).fetchone()
    if not row:raise ValueError('API-Token nicht gefunden.')
    c.execute('UPDATE api_tokens SET revoked_at=? WHERE id=?',(now_iso(),token_id))


def _api_auth(app, handler):
    header=handler.headers.get('Authorization','')
    if not header.startswith('Bearer '):
        handler.send_json(401,{'error':'Bearer-Token erforderlich.'},{'WWW-Authenticate':'Bearer'});return None
    raw=header[7:].strip()
    if len(raw)<24 or len(raw)>300:
        handler.send_json(401,{'error':'Ungültiger API-Token.'});return None
    digest=hashlib.sha256(raw.encode()).hexdigest()
    with app.db() as c:
        row=c.execute('''SELECT t.*,u.username,u.role,u.active FROM api_tokens t JOIN users u ON u.id=t.owner_id
                         WHERE t.token_hash=?''',(digest,)).fetchone()
        if not row or not row['active'] or row['revoked_at']:
            handler.send_json(401,{'error':'API-Token ist ungültig oder widerrufen.'});return None
        if row['expires_at']:
            try:expired=datetime.fromisoformat(row['expires_at'].replace('Z','+00:00'))<=datetime.now(timezone.utc)
            except ValueError:expired=True
            if expired:
                handler.send_json(401,{'error':'API-Token ist abgelaufen.'});return None
        c.execute('UPDATE api_tokens SET last_used_at=? WHERE id=?',(now_iso(),row['id']))
        return {'id':row['owner_id'],'username':row['username'],'role':row['role'],'kind':row['kind'],'permissions':set(_permissions(row)),'token_id':row['id']}


def _need(handler, auth, scope, kind=None):
    if kind and auth['kind']!=kind:
        handler.send_json(403,{'error':'Dieser API-Token ist für diesen Bereich nicht freigegeben.'});return False
    if scope not in auth['permissions']:
        handler.send_json(403,{'error':'Dem API-Token fehlt die Berechtigung '+scope+'.'});return False
    return True


def _limit(query, default=100, maximum=500):
    try:return max(1,min(int((query.get('limit') or [default])[0]),maximum))
    except (TypeError,ValueError):return default


def _provider_events(c, uid, provider, limit):
    visible,state=provider_cache_runtime.provider_visible(c,uid,provider)
    if not visible:return {'provider':provider,'available':False,'access_state':state,'items':[]}
    items=[]
    for r in c.execute('''SELECT external_key,occurred_at,summary,raw_json,captured_at FROM provider_events
                          WHERE owner_id=? AND provider=? ORDER BY occurred_at DESC,captured_at DESC''',(uid,provider)):
        try:raw=json.loads(r['raw_json'])
        except Exception:raw={}
        items.append({'external_key':r['external_key'],'occurred_at':r['occurred_at'],'summary':r['summary'],
                      'raw':raw,'captured_at':r['captured_at']})
        if len(items)>=limit:break
    return {'provider':provider,'available':True,'access_state':state,'items':items}


def openapi_spec():
    return {
      'openapi':'3.1.0','info':{'title':'ProjektZeit REST API','version':'1.0.0','description':'Benutzergebundene ProjektZeit API. API-Tokens werden in den ProjektZeit-Einstellungen erzeugt.'},
      'components':{'securitySchemes':{'bearerAuth':{'type':'http','scheme':'bearer','bearerFormat':'ProjektZeit API Token'}}},
      'security':[{'bearerAuth':[]}],
      'paths':{
        '/api/v1/external/me':{'get':{'operationId':'getMe','summary':'API-Benutzer und Tokenrechte anzeigen'}},
        '/api/v1/external/customers':{'get':{'operationId':'listCustomers','summary':'Eigene Kunden auflisten'}},
        '/api/v1/external/customers/{id}':{'get':{'operationId':'getCustomer','summary':'Kundendetails lesen','parameters':[{'name':'id','in':'path','required':True,'schema':{'type':'integer'}}]}},
        '/api/v1/external/projects':{'get':{'operationId':'listProjects','summary':'Eigene Projekte auflisten'}},
        '/api/v1/external/time-entries':{'get':{'operationId':'listTimeEntries','summary':'Eigene Zeiterfassungen lesen'}},
        '/api/v1/external/zammad/tickets':{'get':{'operationId':'listCachedZammadTickets','summary':'Lokal gespeicherte Zammad-Tickets lesen'}},
        '/api/v1/external/starface/history':{'get':{'operationId':'listStarfaceHistory','summary':'Eigene STARFACE-Historie lesen'}},
        '/api/v1/external/teamviewer/history':{'get':{'operationId':'listTeamviewerHistory','summary':'Eigene TeamViewer-Historie lesen'}},
        '/api/v1/external/admin/users':{'get':{'operationId':'adminListUsers','summary':'Benutzer administrativ lesen'}},
        '/api/v1/external/admin/provider-status':{'get':{'operationId':'adminProviderStatus','summary':'Providerstatus administrativ lesen'}},
      }
    }


def install(app):
    original_init=app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:migrate(c)
    app.init_db=init_db

    previous_get=app.App.do_GET
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/v1/external/openapi.json':return self.send_json(200,openapi_spec())
        if not path.startswith('/api/v1/external/'):
            return previous_get(self)
        auth=_api_auth(app,self)
        if not auth:return
        query=parse_qs(urlparse(self.path).query);uid=auth['id'];limit=_limit(query)
        if path=='/api/v1/external/me':
            return self.send_json(200,{'user':{'id':uid,'username':auth['username'],'role':auth['role']},'kind':auth['kind'],'permissions':sorted(auth['permissions'])})
        if path=='/api/v1/external/customers':
            if not _need(self,auth,'customers.read'):return
            with app.db() as c:
                rows=[dict(r) for r in c.execute('SELECT id,name FROM customers WHERE owner_id=? ORDER BY name',(uid,))]
            return self.send_json(200,{'customers':rows[:limit]})
        if path.startswith('/api/v1/external/customers/'):
            if not _need(self,auth,'customers.read'):return
            try:cid=int(path.rsplit('/',1)[1])
            except ValueError:return self.send_json(400,{'error':'Ungültige Kunden-ID.'})
            cd=__import__('customer_data');ac=__import__('admin_controls')
            with app.db() as c:
                customers=cd.list_all(c,uid);customer=next((x for x in customers if x['id']==cid),None)
                if not customer:return self.send_json(404,{'error':'Kunde nicht gefunden.'})
                customer['master']=ac.customer_master(c,uid,cid)
            return self.send_json(200,{'customer':customer})
        if path=='/api/v1/external/projects':
            if not _need(self,auth,'projects.read'):return
            with app.db() as c:
                rows=[dict(r) for r in c.execute('''SELECT p.id,p.name,p.customer_id,p.active,c.name customer FROM projects p
                    LEFT JOIN customers c ON c.id=p.customer_id WHERE p.owner_id=? AND p.is_system=0 ORDER BY p.name''',(uid,))]
            return self.send_json(200,{'projects':rows[:limit]})
        if path=='/api/v1/external/time-entries':
            if not _need(self,auth,'time.read'):return
            with app.db() as c:
                rows=[dict(r) for r in c.execute('''SELECT e.id,e.started_at,e.ended_at,e.note,p.name project,k.name category,c.name customer
                    FROM entries e JOIN projects p ON p.id=e.project_id JOIN categories k ON k.id=e.category_id
                    LEFT JOIN customers c ON c.id=p.customer_id WHERE e.owner_id=? ORDER BY e.started_at DESC''',(uid,))]
            return self.send_json(200,{'time_entries':rows[:limit]})
        if path=='/api/v1/external/zammad/tickets':
            if not _need(self,auth,'tickets.read'):return
            with app.db() as c:
                items=[]
                for r in c.execute('SELECT external_key,occurred_at,summary,raw_json,captured_at FROM provider_events WHERE owner_id=? AND provider=? ORDER BY occurred_at DESC,captured_at DESC',(uid,'zammad')):
                    try:raw=json.loads(r['raw_json'])
                    except Exception:raw={}
                    items.append({'external_key':r['external_key'],'occurred_at':r['occurred_at'],'summary':r['summary'],'raw':raw,'captured_at':r['captured_at']})
                    if len(items)>=limit:break
            return self.send_json(200,{'tickets':items})
        if path in ('/api/v1/external/starface/history','/api/v1/external/teamviewer/history'):
            provider='starface' if 'starface' in path else 'teamviewer';scope=provider+'.read'
            if not _need(self,auth,scope):return
            with app.db() as c:return self.send_json(200,_provider_events(c,uid,provider,limit))
        if path=='/api/v1/external/admin/users':
            if not _need(self,auth,'admin.users.read','admin'):return
            with app.db() as c:return self.send_json(200,{'users':admin_controls.list_users(c,uid)})
        if path=='/api/v1/external/admin/provider-status':
            if not _need(self,auth,'admin.integrations.read','admin'):return
            sf=__import__('system_features');
            with app.db() as c:return self.send_json(200,{'providers':[sf.provider_health(c,uid,p) for p in ('starface','teamviewer','zammad')]})
        if path=='/api/v1/external/admin/logs':
            if not _need(self,auth,'admin.logs.read','admin'):return
            pa=__import__('provider_archive')
            with app.db() as c:return self.send_json(200,{'logs':pa.list_logs(c,uid,limit=limit)})
        return self.send_json(404,{'error':'API-Endpunkt nicht gefunden.'})
    app.App.do_GET=do_GET

    previous_post=app.App.do_POST
    paths={'/api/v1/api/tokens/list','/api/v1/api/tokens/create','/api/v1/api/tokens/revoke',
           '/api/v1/admin/api/tokens/list','/api/v1/admin/api/tokens/create','/api/v1/admin/api/tokens/revoke'}
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in paths:return previous_post(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:return self.send_json(400,{'error':str(error)})
        session=self.require(csrf=True)
        if not session:return
        uid=session['id'];kind='admin' if '/admin/api/' in path else 'user'
        try:
            with app.db() as c:
                if kind=='admin':admin_controls.require_permission(c,uid,'admin.options.view')
                if path.endswith('/list'):return self.send_json(200,list_tokens(c,uid,kind))
                if path.endswith('/create'):
                    created=create_token(c,uid,body,kind)
                    __import__('system_features').audit(c,uid,uid,'api_token',created['id'],'created',{'kind':kind,'name':created['name'],'permissions':created['permissions']})
                    return self.send_json(201,created)
                revoke(c,uid,body.get('id'),kind)
                __import__('system_features').audit(c,uid,uid,'api_token',body.get('id'),'revoked',{'kind':kind})
                return self.send_json(200,{'ok':True})
        except PermissionError as error:return self.send_json(403,{'error':str(error)})
        except (ValueError,TypeError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST
