"""Runtime layer for the September 2026 UI/account/audit batch."""
import json
from urllib.parse import urlparse, parse_qs

import system_features


def install(app):
    original_init = app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c: system_features.migrate(c)
    app.init_db = init_db

    # STARFACE OAuth uses one admin-managed client configuration for all users,
    # while OAuth tokens remain strictly user-bound.
    def global_client(db, uid, directory):
        with db() as c: return system_features.starface_client(c, directory)
    app.starface_oauth._stored_client = global_client

    # The OAuth callback must be usable by normal users as well. Client
    # configuration remains protected through the admin endpoints below.
    previous_get = app.App.do_GET
    def do_GET(self):
        path = urlparse(self.path).path
        if path == app.starface_oauth.CALLBACK:
            session = self.require()
            if not session: return
            try:
                app.starface_oauth.finish(app.db, session, parse_qs(urlparse(self.path).query), app.DATA_DIR)
            except (ValueError, OSError) as error:
                return self.send_json(400, {'error': str(error) if isinstance(error,ValueError) else 'STARFACE ist nicht erreichbar. Bitte erneut anmelden.'})
            self.send_response(303);self.send_header('Location','/?starface=connected');self.send_header('Content-Length','0');self.end_headers();return
        return previous_get(self)
    app.App.do_GET = do_GET

    # Audit core time tracking and master-data operations.
    original_edit = app.App.edit_entry
    def edit_entry(self, session, body):
        uid=session['id'];entry_id=int(body.get('id') or 0)
        with app.db() as c:
            row=c.execute('SELECT project_id,category_id,started_at,ended_at,note FROM entries WHERE id=? AND owner_id=?',(entry_id,uid)).fetchone()
            before=dict(row) if row else {}
        result=original_edit(self,session,body)
        with app.db() as c:
            row=c.execute('SELECT project_id,category_id,started_at,ended_at,note FROM entries WHERE id=? AND owner_id=?',(entry_id,uid)).fetchone()
            after=dict(row) if row else {}
            changes={k:{'old':before.get(k),'new':after.get(k)} for k in after if before.get(k)!=after.get(k)}
            if changes: system_features.audit(c,uid,uid,'time_entry',entry_id,'updated',changes)
        return result
    app.App.edit_entry=edit_entry

    original_start_timer=app.App.start_timer
    def start_timer(self,session,body):
        uid=session['id']
        with app.db() as c: before=c.execute('SELECT COALESCE(MAX(id),0) n FROM entries WHERE owner_id=?',(uid,)).fetchone()['n']
        result=original_start_timer(self,session,body)
        with app.db() as c:
            rows=list(c.execute('SELECT id,project_id,category_id,started_at,note FROM entries WHERE owner_id=? AND id>? ORDER BY id',(uid,before)))
            for row in rows: system_features.audit(c,uid,uid,'time_entry',row['id'],'created',dict(row),source='manual')
        return result
    app.App.start_timer=start_timer

    original_stop_timer=app.App.stop_timer
    def stop_timer(self,session,body):
        uid=session['id']
        with app.db() as c:
            rows=[dict(r) for r in c.execute('SELECT id,ended_at,note FROM entries WHERE owner_id=? AND ended_at IS NULL',(uid,))]
        result=original_stop_timer(self,session,body)
        with app.db() as c:
            for old in rows:
                row=c.execute('SELECT ended_at,note FROM entries WHERE id=? AND owner_id=?',(old['id'],uid)).fetchone()
                if row and row['ended_at']!=old['ended_at']:
                    system_features.audit(c,uid,uid,'time_entry',old['id'],'stopped',{'ended_at':{'old':old['ended_at'],'new':row['ended_at']}})
        return result
    app.App.stop_timer=stop_timer

    def wrap_create(method_name, entity_type, table):
        original=getattr(app.App,method_name)
        def wrapped(self,session,body):
            uid=session['id']
            with app.db() as c: before=c.execute(f'SELECT COALESCE(MAX(id),0) n FROM {table} WHERE owner_id=?',(uid,)).fetchone()['n']
            result=original(self,session,body)
            with app.db() as c:
                for row in c.execute(f'SELECT * FROM {table} WHERE owner_id=? AND id>? ORDER BY id',(uid,before)):
                    system_features.audit(c,uid,uid,entity_type,row['id'],'created',dict(row))
            return result
        setattr(app.App,method_name,wrapped)
    wrap_create('add_customer','customer','customers')
    wrap_create('add_project','project','projects')
    wrap_create('add_category','category','categories')

    # CRM mutation hooks. These functions are called by customer_runtime and
    # therefore provide a single place for a durable audit trail.
    ac=app.admin_controls if hasattr(app,'admin_controls') else __import__('admin_controls')
    original_master=ac.save_customer_master
    def save_master(c,uid,cid,values):
        before=ac.customer_master(c,uid,cid);result=original_master(c,uid,cid,values);after=ac.customer_master(c,uid,cid)
        changes={k:{'old':before.get(k,''),'new':after.get(k,'')} for k in after if before.get(k,'')!=after.get(k,'')}
        if changes:system_features.audit(c,uid,uid,'customer',cid,'master_data_updated',changes)
        return result
    ac.save_customer_master=save_master

    cd=app.customer_data if hasattr(app,'customer_data') else __import__('customer_data')
    pa=app.provider_archive if hasattr(app,'provider_archive') else __import__('provider_archive')
    old_add_phone=cd.add_company_phone
    def add_phone(c,uid,cid,number,label='Sonstige',source='manual'):
        result=old_add_phone(c,uid,cid,number,label,source)
        if result:system_features.audit(c,uid,uid,'customer',cid,'phone_added',{'number':number,'label':label},source=source or 'manual')
        return result
    cd.add_company_phone=add_phone
    old_contact=cd.add_contact
    def add_contact(c,uid,cid,name,email='',note='',phones=None):
        result=old_contact(c,uid,cid,name,email,note,phones);system_features.audit(c,uid,uid,'customer',cid,'contact_added',{'contact_id':result,'name':name,'email':email});return result
    cd.add_contact=add_contact
    old_device=cd.add_device
    def add_device(c,uid,cid,provider,external_id,name):
        result=old_device(c,uid,cid,provider,external_id,name);system_features.audit(c,uid,uid,'customer',cid,'device_added',{'provider':provider,'external_id':external_id,'name':name});return result
    cd.add_device=add_device
    old_phone_update=pa.phone_update
    def phone_update(c,uid,body):
        result=old_phone_update(c,uid,body);system_features.audit(c,uid,uid,'customer_phone',body.get('id'),'updated',{'number':body.get('number'),'label':body.get('label')});return result
    pa.phone_update=phone_update
    old_phone_delete=pa.phone_delete
    def phone_delete(c,uid,body):
        system_features.audit(c,uid,uid,'customer_phone',body.get('id'),'deleted',{'scope':body.get('scope')});return old_phone_delete(c,uid,body)
    pa.phone_delete=phone_delete

    previous_post=app.App.do_POST
    feature_paths={
      '/api/v1/account/context','/api/v1/account/save','/api/v1/account/theme',
      '/api/v1/audit/history','/api/v1/provider/health',
      '/api/v1/admin/starface/config','/api/v1/admin/starface/save',
      '/api/v1/starface/connect/start','/api/v1/archive/start','/api/v1/archive/job'
    }
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in feature_paths:return previous_post(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:return self.send_json(400,{'error':str(error)})
        session=self.require(csrf=True)
        if not session:return
        uid=session['id']
        try:
            if path=='/api/v1/account/context':
                with app.db() as c:return self.send_json(200,{'profile':system_features.self_profile(c,uid),'preferences':system_features.preference(c,uid)})
            if path=='/api/v1/account/save':
                with app.db() as c:return self.send_json(200,{'profile':system_features.save_self_profile(c,uid,body)})
            if path=='/api/v1/account/theme':
                with app.db() as c:return self.send_json(200,system_features.save_preference(c,uid,body.get('theme')))
            if path=='/api/v1/audit/history':
                with app.db() as c:return self.send_json(200,{'history':system_features.history(c,uid,body.get('entity_type'),body.get('entity_id'),body.get('limit',200))})
            if path=='/api/v1/provider/health':
                with app.db() as c:return self.send_json(200,{'providers':[system_features.provider_health(c,uid,p) for p in ('starface','teamviewer','zammad')]})
            if path=='/api/v1/admin/starface/config':
                with app.db() as c:
                    app.admin_controls.require_permission(c,uid,'integrations.view')
                    return self.send_json(200,system_features.starface_public(c))
            if path=='/api/v1/admin/starface/save':
                with app.db() as c:
                    app.admin_controls.require_permission(c,uid,'integrations.edit')
                    data=system_features.save_starface_client(c,uid,app.DATA_DIR,body.get('domain'),body.get('client_id'),body.get('client_secret'),bool(body.get('delete_secret')))
                    return self.send_json(200,data)
            if path=='/api/v1/starface/connect/start':
                with app.db() as c:
                    cfg=system_features.starface_public(c)
                if not cfg['has_client_secret']:
                    return self.send_json(409,{'error':'Noch kein Client-Secret hinterlegt. Bitte an den Administrator wenden.'})
                result=app.starface_oauth.start(app.db,session,{'desktop_prepare':True},app.DATA_DIR)
                return self.send_json(200,result)
            if path=='/api/v1/archive/start':
                provider=str(body.get('provider') or '').lower();config=integration_config(app,uid,provider)
                return self.send_json(202,{'job':system_features.start_history_job(app.db,uid,provider,config)})
            if path=='/api/v1/archive/job':
                return self.send_json(200,{'job':system_features.history_job(uid,body.get('provider'))})
        except PermissionError as error:return self.send_json(403,{'error':str(error)})
        except (ValueError,TypeError,OSError) as error:return self.send_json(400,{'error':str(error) if not isinstance(error,OSError) else 'Schnittstelle nicht erreichbar.'})
    app.App.do_POST=do_POST


def integration_config(app,uid,provider):
    with app.db() as c:
        if provider=='starface':return app.starface_oauth.access(c,uid,app.DATA_DIR)
        row=c.execute('SELECT * FROM integrations WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
        if not row:raise ValueError('Bitte zuerst die Schnittstelle in den Einstellungen verknüpfen.')
        return app.integrations.config(c,uid,dict(provider=provider,domain=row['domain'],username=row['username'],secret=''),app.DATA_DIR)


def serve(app, customer_runtime):
    customer_runtime.install(app)
    install(app)
    app.init_db()
    print('ProjektZeit Web läuft auf http://%s:%d'%(app.HOST,app.PORT))
    app.ThreadingHTTPServer((app.HOST,app.PORT),app.App).serve_forever()
