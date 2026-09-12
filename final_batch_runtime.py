"""Final September batch: object history, customer/provider assignments, callback state,
permission dependencies, work-block totals and super-admin migration.
"""
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import admin_controls
import system_features


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


DEPENDENCIES = {
    'users.create': {'users.view','admin.options.view'}, 'users.edit': {'users.view','admin.options.view'},
    'users.disable': {'users.view','admin.options.view'}, 'users.roles.assign': {'users.view','roles.view','admin.options.view'},
    'roles.view': {'admin.options.view'}, 'roles.create': {'roles.view','admin.options.view'}, 'roles.edit': {'roles.view','admin.options.view'},
    'roles.clone': {'roles.view','admin.options.view'}, 'roles.delete': {'roles.view','admin.options.view'}, 'roles.reset_user': {'roles.view','admin.options.view'},
    'security.policies.view': {'admin.options.view'}, 'security.policies.edit': {'security.policies.view','admin.options.view'},
    'security.2fa.reset_user': {'users.view','admin.options.view'}, 'security.sessions.end': {'users.view','admin.options.view'},
    'smtp.view': {'admin.options.view'}, 'smtp.edit': {'smtp.view','admin.options.view'}, 'smtp.test': {'smtp.view','admin.options.view'},
    'notifications.edit': {'admin.options.view'}, 'integrations.edit': {'integrations.view','admin.options.view'},
    'integrations.sync': {'integrations.view'}, 'integrations.debug': {'integrations.view','admin.options.view'},
    'system.options.edit': {'admin.options.view'}, 'bookkeeping.manage': {'bookkeeping.view'},
    'logs.view_team': {'logs.view_own'}, 'logs.view_all': {'logs.view_own'},
    'customers.view_contacts': {'customers.view_basic'}, 'customers.view_links': {'customers.view_basic'},
    'customers.view_history': {'customers.view_basic'}, 'customers.create': {'customers.view_basic'},
    'customers.edit': {'customers.view_basic'}, 'customers.archive': {'customers.view_basic'}, 'customers.delete': {'customers.view_basic'},
    'api.tokens.manage_own': set(),
}


def closure(perms):
    out=set(perms)
    changed=True
    while changed:
        changed=False
        for key,deps in DEPENDENCIES.items():
            if key in out:
                before=len(out);out.update(deps);changed=changed or len(out)!=before
    return out


def _register_permissions():
    additions={
      'Kunden': [('customers.view_basic','Kunden-Grunddaten ansehen'),('customers.view_contacts','Kontaktdaten ansehen'),
                  ('customers.view_links','Provider-Verknüpfungen ansehen'),('customers.view_history','Kundenhistorie ansehen'),
                  ('customers.archive','Kunden archivieren')],
      'API': [('api.tokens.manage_own','Eigene API-Tokens verwalten')],
    }
    existing={k for values in admin_controls.PERMISSION_CATEGORIES.values() for k,_ in values}
    for cat,items in additions.items():
        target=admin_controls.PERMISSION_CATEGORIES.setdefault(cat,[])
        for key,label in items:
            if key not in existing:target.append((key,label));existing.add(key)
            admin_controls.ALL_PERMISSIONS.add(key)
    admin_controls.DEFAULT_USER_PERMISSIONS.update({'customers.view','customers.view_basic','customers.view_contacts','customers.view_links','customers.view_history','api.tokens.manage_own'})
    admin_controls.DEFAULT_ADMIN_PERMISSIONS.update(admin_controls.ALL_PERMISSIONS)


def _columns(c,table):
    if getattr(c,'dialect','')=='mariadb':
        return {r['COLUMN_NAME'] for r in c.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=?",(table,))}
    return {r['name'] for r in c.execute('PRAGMA table_info(%s)'%table)}


def _seconds(a,b):
    if not a or not b:return 0
    try:
        x=datetime.fromisoformat(str(a).replace('Z','+00:00'));y=datetime.fromisoformat(str(b).replace('Z','+00:00'))
        return max(0,int((y-x).total_seconds()))
    except Exception:return 0


def recompute_work_totals(c,uid=None):
    sql='SELECT id,owner_id,started_at,ended_at FROM work_sessions'+(' WHERE owner_id=?' if uid is not None else '')
    args=(uid,) if uid is not None else ()
    for w in list(c.execute(sql,args)):
        pause=0
        for p in c.execute('SELECT started_at,ended_at FROM work_pauses WHERE work_session_id=?',(w['id'],)):
            pause+=_seconds(p['started_at'],p['ended_at'])
        gross=_seconds(w['started_at'],w['ended_at'])
        c.execute('UPDATE work_sessions SET pause_seconds=?,net_seconds=? WHERE id=?',(pause,max(0,gross-pause),w['id']))


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS customer_identity_links (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      provider VARCHAR(32) NOT NULL, link_type VARCHAR(32) NOT NULL, link_value VARCHAR(500) NOT NULL,
      display_name VARCHAR(500) NOT NULL DEFAULT '', created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at VARCHAR(40) NOT NULL, UNIQUE(owner_id,provider,link_type,link_value)
    );
    CREATE INDEX IF NOT EXISTS idx_customer_identity_links_customer ON customer_identity_links(owner_id,customer_id,provider);
    CREATE TABLE IF NOT EXISTS provider_assignments (
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, provider VARCHAR(32) NOT NULL,
      external_key VARCHAR(255) NOT NULL, customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
      project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL, match_type VARCHAR(32) NOT NULL DEFAULT '',
      match_value VARCHAR(500) NOT NULL DEFAULT '', assigned_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
      assigned_at VARCHAR(40) NOT NULL, PRIMARY KEY(owner_id,provider,external_key)
    );
    CREATE INDEX IF NOT EXISTS idx_provider_assignments_customer ON provider_assignments(owner_id,customer_id,provider);
    CREATE TABLE IF NOT EXISTS starface_manual_callbacks (
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, external_key VARCHAR(255) NOT NULL,
      marked_by INTEGER REFERENCES users(id) ON DELETE SET NULL, marked_at VARCHAR(40) NOT NULL,
      PRIMARY KEY(owner_id,external_key)
    );
    CREATE TABLE IF NOT EXISTS user_notifications (
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      kind VARCHAR(80) NOT NULL, message TEXT NOT NULL, created_at VARCHAR(40) NOT NULL, read_at VARCHAR(40) NOT NULL DEFAULT ''
    );
    ''')
    if 'archived' not in _columns(c,'customers'):c.execute("ALTER TABLE customers ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    workcols=_columns(c,'work_sessions')
    if 'pause_seconds' not in workcols:c.execute('ALTER TABLE work_sessions ADD COLUMN pause_seconds INTEGER NOT NULL DEFAULT 0')
    if 'net_seconds' not in workcols:c.execute('ALTER TABLE work_sessions ADD COLUMN net_seconds INTEGER NOT NULL DEFAULT 0')
    recompute_work_totals(c)
    admin=c.execute("SELECT id FROM role_definitions WHERE role_key='admin'").fetchone()
    if admin:
        legacy=[]
        try:legacy=[r['user_id'] for r in c.execute('SELECT user_id FROM system_superadmins')]
        except Exception:pass
        super_role=c.execute("SELECT id FROM role_definitions WHERE role_key='superadmin'").fetchone()
        if super_role:legacy += [r['user_id'] for r in c.execute('SELECT user_id FROM user_role_links WHERE role_id=?',(super_role['id'],))]
        for uid in set(legacy):
            c.execute('INSERT OR IGNORE INTO user_role_links(user_id,role_id) VALUES(?,?)',(uid,admin['id']));c.execute("UPDATE users SET role='admin' WHERE id=?",(uid,))
        if super_role:
            c.execute('DELETE FROM user_role_links WHERE role_id=?',(super_role['id'],));c.execute('DELETE FROM role_permissions WHERE role_id=?',(super_role['id'],));c.execute('DELETE FROM role_definitions WHERE id=?',(super_role['id'],))
        try:c.execute('DROP TABLE IF EXISTS system_superadmins')
        except Exception:pass
    c.execute("DELETE FROM system_settings WHERE setting_key LIKE 'superadmin.%'")
    for role in list(c.execute('SELECT id,role_key FROM role_definitions')):
        perms={r['permission_key'] for r in c.execute('SELECT permission_key FROM role_permissions WHERE role_id=?',(role['id'],))}
        if role['role_key']=='admin':perms=set(admin_controls.ALL_PERMISSIONS)
        perms=closure(perms);c.execute('DELETE FROM role_permissions WHERE role_id=?',(role['id'],))
        for key in sorted(perms & admin_controls.ALL_PERMISSIONS):c.execute('INSERT INTO role_permissions(role_id,permission_key) VALUES(?,?)',(role['id'],key))


def _audit(c,uid,entity_type,entity_id,action,changes=None):
    system_features.audit(c,uid,uid,entity_type,entity_id,action,changes or {})


def _provider_identifier(provider,raw,hint=None):
    hint=hint or {}
    if provider=='teamviewer':
        value=raw.get('deviceid') or raw.get('device_id') or hint.get('device_id');return ('teamviewer_id',str(value).strip()) if value not in (None,'') else ('','')
    if provider=='starface':
        direction=str(raw.get('direction') or '').upper();value=raw.get('callerNumber') if direction=='INBOUND' else raw.get('calledNumber');return ('phone',str(value or '').strip())
    if provider=='zammad':
        customer=raw.get('customer') if isinstance(raw.get('customer'),dict) else {};value=customer.get('email') or raw.get('customer_email') or hint.get('email');return ('email',str(value or '').strip().lower())
    return ('','')


def _ensure_assignment(c,uid,provider,event):
    key=event.get('external_key') or ''
    current=c.execute('SELECT * FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key)).fetchone()
    if current:return dict(current)
    typ,val=_provider_identifier(provider,event.get('raw') or {},event.get('customer_hint') or {})
    customer_id=None
    if val:
        link=c.execute('SELECT customer_id FROM customer_identity_links WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',(uid,provider,typ,val)).fetchone();customer_id=link['customer_id'] if link else None
    if customer_id:
        c.execute('INSERT INTO provider_assignments(owner_id,provider,external_key,customer_id,project_id,match_type,match_value,assigned_by,assigned_at) VALUES(?,?,?,?,NULL,?,?,NULL,?)',(uid,provider,key,customer_id,typ,val,now_iso()))
        return dict(c.execute('SELECT * FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key)).fetchone())
    return {'owner_id':uid,'provider':provider,'external_key':key,'customer_id':None,'project_id':None,'match_type':typ,'match_value':val}


def enrich_rows(c,uid,provider,result):
    for row in result.get('rows') or []:
        assignment=_ensure_assignment(c,uid,provider,row);row['assignment']=assignment
        if provider=='teamviewer' and assignment.get('customer_id'):
            typ,val=_provider_identifier(provider,row.get('raw') or {},row.get('customer_hint') or {})
            name=str((row.get('raw') or {}).get('devicename') or (row.get('customer_hint') or {}).get('device_name') or '')[:500]
            if typ and val and name:c.execute('UPDATE customer_identity_links SET display_name=? WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',(name,uid,provider,typ,val))
        if assignment.get('customer_id'):
            cu=c.execute('SELECT name FROM customers WHERE id=?',(assignment['customer_id'],)).fetchone();row['assignment']['customer_name']=cu['name'] if cu else ''
        if assignment.get('project_id'):
            pr=c.execute('SELECT name FROM projects WHERE id=?',(assignment['project_id'],)).fetchone();row['assignment']['project_name']=pr['name'] if pr else ''
    return result


def customer_links(c,uid,cid):
    return [dict(r) for r in c.execute('SELECT id,provider,link_type,link_value,display_name,created_at FROM customer_identity_links WHERE owner_id=? AND customer_id=? ORDER BY provider,display_name,link_value',(uid,cid))]


def _valid_customer(c,uid,cid):
    row=c.execute('SELECT id,name,archived FROM customers WHERE owner_id=? AND id=?',(uid,int(cid))).fetchone()
    if not row:raise ValueError('Kunde nicht gefunden.')
    return row


def install(app):
    _register_permissions()
    admin_controls.is_superadmin=lambda c,uid:False
    def permissions_for_user(c,uid):return {r['permission_key'] for r in c.execute('SELECT rp.permission_key FROM role_permissions rp JOIN user_role_links ur ON ur.role_id=rp.role_id WHERE ur.user_id=?',(uid,))}
    admin_controls.permissions_for_user=permissions_for_user;admin_controls.can=lambda c,uid,p:p in permissions_for_user(c,uid)
    old_set=admin_controls._set_role_permissions;admin_controls._set_role_permissions=lambda c,rid,perms:old_set(c,rid,closure(perms))

    original_init=app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:migrate(c)
    app.init_db=init_db

    try:
        wd=__import__('workday');old_reconcile=wd.reconcile
        def reconcile(c,uid):
            result=old_reconcile(c,uid);recompute_work_totals(c,uid);return result
        wd.reconcile=reconcile
    except Exception:pass
    try:
        pc=__import__('provider_cache_runtime');old_cached=pc.cached_list;pc.cached_list=lambda c,uid,p,b:enrich_rows(c,uid,p,old_cached(c,uid,p,b))
    except Exception:pass
    try:
        zc=__import__('zammad_cache_runtime');old_z=zc.cached_list;zc.cached_list=lambda c,uid:enrich_rows(c,uid,'zammad',old_z(c,uid))
    except Exception:pass
    try:
        nb=__import__('next_batch_runtime');old_missed=nb._missed_calls
        def missed(c,uid):
            hidden={r['external_key'] for r in c.execute('SELECT external_key FROM starface_manual_callbacks WHERE owner_id=?',(uid,))};return [r for r in old_missed(c,uid) if r.get('external_key') not in hidden]
        nb._missed_calls=missed
    except Exception:pass
    try:
        ar=__import__('api_runtime');old_scopes=ar.available_scopes
        def scopes(c,uid,kind):
            if kind!='user' or not admin_controls.can(c,uid,'api.tokens.manage_own'):return {}
            return old_scopes(c,uid,'user')
        ar.available_scopes=scopes;old_auth=ar._api_auth
        def auth(app_,handler):
            value=old_auth(app_,handler)
            if not value:return None
            if value.get('kind')!='user':handler.send_json(403,{'error':'Administrative API-Tokens sind deaktiviert.'});return None
            with app_.db() as c:value['permissions']=set(value.get('permissions') or ()) & set(scopes(c,value['id'],'user'))
            return value
        ar._api_auth=auth
    except Exception:pass

    previous_post=app.App.do_POST
    handled={'/api/v1/history/object','/api/v1/customers/links','/api/v1/customers/link/candidates','/api/v1/customers/link/add','/api/v1/customers/link/delete','/api/v1/provider/assign/customer','/api/v1/provider/assign/project','/api/v1/starface/callback/manual','/api/v1/customers/archive','/api/v1/customers/delete','/api/v1/admin/api/tokens/list','/api/v1/admin/api/tokens/create','/api/v1/admin/api/tokens/revoke'}
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in handled:return previous_post(self)
        if path.startswith('/api/v1/admin/api/tokens/'):
            session=self.require(csrf=True)
            if not session:return
            return self.send_json(410,{'error':'Administrative API-Tokens wurden entfernt. Bitte einen persönlichen API-Token verwenden.'})
        try:body=self.json_body();session=self.require(csrf=True)
        except Exception as e:return self.send_json(400,{'error':str(e)})
        if not session:return
        uid=session['id']
        try:
            with app.db() as c:
                if path=='/api/v1/history/object':
                    entity=str(body.get('entity_type') or '')[:80];eid=str(body.get('entity_id') or '')[:160]
                    if entity=='customer':admin_controls.require_permission(c,uid,'customers.view_basic')
                    return self.send_json(200,{'history':system_features.history(c,uid,entity,eid,int(body.get('limit') or 200))})
                if path=='/api/v1/customers/links':
                    admin_controls.require_permission(c,uid,'customers.view_links');cid=int(body.get('customer_id'));_valid_customer(c,uid,cid);return self.send_json(200,{'links':customer_links(c,uid,cid)})
                if path=='/api/v1/customers/link/candidates':
                    cid=int(body.get('customer_id'));_valid_customer(c,uid,cid);provider=str(body.get('provider') or '').lower();typ=str(body.get('link_type') or '').lower();val=str(body.get('link_value') or '').strip().lower() if typ=='email' else str(body.get('link_value') or '').strip();count=0
                    for event in c.execute('SELECT raw_json,hint_json FROM provider_events WHERE owner_id=? AND provider=?',(uid,provider)):
                        try:et,ev=_provider_identifier(provider,json.loads(event['raw_json'] or '{}'),json.loads(event['hint_json'] or '{}'))
                        except Exception:continue
                        if et==typ and ev==val:count+=1
                    return self.send_json(200,{'count':count,'provider':provider,'link_type':typ,'link_value':val})
                if path=='/api/v1/customers/link/add':
                    admin_controls.require_permission(c,uid,'customers.edit');cid=int(body.get('customer_id'));_valid_customer(c,uid,cid);provider=str(body.get('provider') or '').lower();typ=str(body.get('link_type') or '').lower();val=str(body.get('link_value') or '').strip();display=str(body.get('display_name') or '')[:500]
                    if provider not in ('zammad','starface','teamviewer') or typ not in ('email','phone','teamviewer_id') or not val:raise ValueError('Ungültige Verknüpfung.')
                    if typ=='email':val=val.lower()
                    previous=c.execute('SELECT customer_id FROM customer_identity_links WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',(uid,provider,typ,val)).fetchone();c.execute('DELETE FROM customer_identity_links WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',(uid,provider,typ,val));cur=c.execute('INSERT INTO customer_identity_links(owner_id,customer_id,provider,link_type,link_value,display_name,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(uid,cid,provider,typ,val,display,uid,now_iso()))
                    matched=0
                    for event in list(c.execute('SELECT external_key,raw_json,hint_json FROM provider_events WHERE owner_id=? AND provider=?',(uid,provider))):
                        try:et,ev=_provider_identifier(provider,json.loads(event['raw_json'] or '{}'),json.loads(event['hint_json'] or '{}'))
                        except Exception:continue
                        if et==typ and ev==val:
                            old=c.execute('SELECT project_id FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,event['external_key'])).fetchone();pid=old['project_id'] if old else None;c.execute('DELETE FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,event['external_key']));c.execute('INSERT INTO provider_assignments(owner_id,provider,external_key,customer_id,project_id,match_type,match_value,assigned_by,assigned_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid,provider,event['external_key'],cid,pid,typ,val,uid,now_iso()));matched+=1
                    _audit(c,uid,'customer',cid,'provider_link_added',{'provider':provider,'type':typ,'value':val,'matched':matched,'moved_from_customer':previous['customer_id'] if previous else None});return self.send_json(200,{'ok':True,'id':cur.lastrowid,'matched':matched})
                if path=='/api/v1/customers/link/delete':
                    admin_controls.require_permission(c,uid,'customers.edit');lid=int(body.get('id'));row=c.execute('SELECT * FROM customer_identity_links WHERE id=? AND owner_id=?',(lid,uid)).fetchone()
                    if not row:raise ValueError('Verknüpfung nicht gefunden.')
                    c.execute('DELETE FROM customer_identity_links WHERE id=?',(lid,));c.execute('UPDATE provider_assignments SET customer_id=NULL,project_id=NULL,assigned_by=?,assigned_at=? WHERE owner_id=? AND provider=? AND match_type=? AND match_value=?',(uid,now_iso(),uid,row['provider'],row['link_type'],row['link_value']));_audit(c,uid,'customer',row['customer_id'],'provider_link_removed',{'provider':row['provider'],'type':row['link_type'],'value':row['link_value']});return self.send_json(200,{'ok':True})
                if path=='/api/v1/provider/assign/customer':
                    provider=str(body.get('provider') or '').lower();key=str(body.get('external_key') or '');cid=int(body.get('customer_id'));_valid_customer(c,uid,cid);ev=c.execute('SELECT raw_json,hint_json FROM provider_events WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key)).fetchone()
                    if not ev:raise ValueError('Eintrag nicht gefunden.')
                    raw=json.loads(ev['raw_json'] or '{}');hint=json.loads(ev['hint_json'] or '{}');typ,val=_provider_identifier(provider,raw,hint)
                    if not typ or not val:raise ValueError('Für diesen Eintrag wurde kein stabiles Zuordnungsmerkmal gefunden.')
                    display=str(raw.get('devicename') or hint.get('device_name') or '')[:500];c.execute('DELETE FROM customer_identity_links WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',(uid,provider,typ,val));c.execute('INSERT INTO customer_identity_links(owner_id,customer_id,provider,link_type,link_value,display_name,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(uid,cid,provider,typ,val,display,uid,now_iso()))
                    matched=0
                    for event in list(c.execute('SELECT external_key,raw_json,hint_json FROM provider_events WHERE owner_id=? AND provider=?',(uid,provider))):
                        try:et,evv=_provider_identifier(provider,json.loads(event['raw_json'] or '{}'),json.loads(event['hint_json'] or '{}'))
                        except Exception:continue
                        if et==typ and evv==val:
                            old=c.execute('SELECT project_id FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,event['external_key'])).fetchone();pid=old['project_id'] if old else None;c.execute('DELETE FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,event['external_key']));c.execute('INSERT INTO provider_assignments(owner_id,provider,external_key,customer_id,project_id,match_type,match_value,assigned_by,assigned_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid,provider,event['external_key'],cid,pid,typ,val,uid,now_iso()));matched+=1
                    _audit(c,uid,'customer',cid,'provider_assigned',{'provider':provider,'type':typ,'value':val,'matched':matched});return self.send_json(200,{'ok':True,'matched':matched,'match_type':typ,'match_value':val})
                if path=='/api/v1/provider/assign/project':
                    provider=str(body.get('provider') or '').lower();key=str(body.get('external_key') or '');pid=int(body.get('project_id'));project=c.execute('SELECT id,customer_id FROM projects WHERE id=? AND owner_id=? AND is_system=0',(pid,uid)).fetchone()
                    if not project:raise ValueError('Projekt nicht gefunden.')
                    row=c.execute('SELECT * FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key)).fetchone()
                    if not row or not row['customer_id']:raise ValueError('Bitte zuerst einen Kunden zuordnen.')
                    if project['customer_id'] and project['customer_id']!=row['customer_id']:raise ValueError('Das Projekt gehört zu einem anderen Kunden.')
                    c.execute('UPDATE provider_assignments SET project_id=?,assigned_by=?,assigned_at=? WHERE owner_id=? AND provider=? AND external_key=?',(pid,uid,now_iso(),uid,provider,key));_audit(c,uid,'project',pid,'provider_entry_assigned',{'provider':provider,'external_key':key});return self.send_json(200,{'ok':True})
                if path=='/api/v1/starface/callback/manual':
                    key=str(body.get('external_key') or '')
                    if not c.execute("SELECT 1 FROM provider_events WHERE owner_id=? AND provider='starface' AND external_key=?",(uid,key)).fetchone():raise ValueError('Anruf nicht gefunden.')
                    c.execute('DELETE FROM starface_manual_callbacks WHERE owner_id=? AND external_key=?',(uid,key));c.execute('INSERT INTO starface_manual_callbacks(owner_id,external_key,marked_by,marked_at) VALUES(?,?,?,?)',(uid,key,uid,now_iso()));_audit(c,uid,'starface_call',key,'manually_called_back',{});return self.send_json(200,{'ok':True})
                if path=='/api/v1/customers/archive':
                    admin_controls.require_permission(c,uid,'customers.archive');cid=int(body.get('customer_id'));_valid_customer(c,uid,cid);state=1 if body.get('archived',True) else 0;c.execute('UPDATE customers SET archived=? WHERE id=? AND owner_id=?',(state,cid,uid));_audit(c,uid,'customer',cid,'archived' if state else 'restored',{});return self.send_json(200,{'ok':True,'archived':bool(state)})
                if path=='/api/v1/customers/delete':
                    admin_controls.require_permission(c,uid,'customers.delete');cid=int(body.get('customer_id'));row=_valid_customer(c,uid,cid);c.execute('UPDATE provider_assignments SET customer_id=NULL,project_id=NULL,assigned_by=?,assigned_at=? WHERE owner_id=? AND customer_id=?',(uid,now_iso(),uid,cid));c.execute('DELETE FROM customer_identity_links WHERE owner_id=? AND customer_id=?',(uid,cid));_audit(c,uid,'customer',cid,'deleted',{'name':row['name']});c.execute('DELETE FROM customers WHERE id=? AND owner_id=?',(cid,uid));return self.send_json(200,{'ok':True})
        except PermissionError as e:return self.send_json(403,{'error':str(e)})
        except (ValueError,TypeError,json.JSONDecodeError) as e:return self.send_json(400,{'error':str(e)})
    app.App.do_POST=do_POST
