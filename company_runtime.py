"""Company management routes; explicit service dispatch and transaction boundaries."""
from urllib.parse import urlparse
import sqlite3
import staff_time
import company_projects
import duty_plan
import company_sync
import company_diagnostics
import provider_budget
import work_models

READ_ACTIONS={'read','context','report','inbox','calendar','list','statistics','preview','status'}

def install(app):
    staff_time.register()
    work_models.overview=staff_time.work_overview
    import workday
    workday.entry_context_hook=company_projects.snapshot_entry
    import time_workspace
    original_workspace=time_workspace.workspace
    def workspace(c,uid,body,allow_team=False):
        result=original_workspace(c,uid,body,allow_team)
        owners={e['owner_id'] for e in result['events']}
        contexts={}
        if owners:
            marks=','.join('?' for _ in owners)
            contexts={(r['owner_id'],r['source'],r['source_key']):dict(r) for r in c.execute('SELECT * FROM event_work_context WHERE owner_id IN ('+marks+')',tuple(owners))}
        for e in result['events']:
            context=contexts.get((e['owner_id'],e['source'],str(e['key'])),{})
            e['location']=context.get('location','office' if e['source']=='teamviewer' else 'unknown');e['emergency']=bool(context.get('emergency',False))
        return result
    time_workspace.workspace=workspace
    original_init=app.init_db
    def init(create_admin=True):
        original_init(create_admin)
        with app.db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS company_write_lock(id INTEGER PRIMARY KEY)');c.execute('INSERT OR IGNORE INTO company_write_lock VALUES(1)');staff_time.migrate(c);company_projects.migrate(c);duty_plan.migrate(c);company_sync.migrate(c);company_diagnostics.migrate(c)
        provider_budget.initialize(app.DATA_DIR);provider_budget.install_transport()
    app.init_db=init
    original_category=app.App.add_category
    def add_category(self,session,body):
        with app.db(read_only=True) as c:
            if not __import__('admin_controls').can(c,session['id'],'categories.create'):return self.send_json(403,{'error':'Keine Berechtigung zum Anlegen von Zeitkategorien.'})
        return original_category(self,session,body)
    app.App.add_category=add_category
    previous=app.App.do_POST
    def post(self):
        path=urlparse(self.path).path
        if not path.startswith('/api/v1/company/') and path not in ('/api/v1/entries/edit','/api/v1/archive/start','/api/v1/archive/job'):return previous(self)
        session=self.require(csrf=True)
        if not session:return
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Benannte Felder erforderlich.')
            if path=='/api/v1/archive/start':return self.send_json(202,{'job':company_sync.start_refresh(app,session['id'],str(body.get('provider') or ''),full=True)})
            if path=='/api/v1/archive/job':return self.send_json(200,{'job':company_sync.job(app,session['id'],str(body.get('provider') or ''))})
            action='entry/correction' if path=='/api/v1/entries/edit' else path.removeprefix('/api/v1/company/')
            if action=='diagnostics/start':return self.send_json(202,company_diagnostics.start(app,session['id'],body))
            with app.db(read_only=action.rsplit('/',1)[-1] in READ_ACTIONS) as c:
                if action.rsplit('/',1)[-1] not in READ_ACTIONS:
                    c.execute('BEGIN IMMEDIATE')
                    if getattr(c,'dialect','')=='mariadb':c.execute('SELECT id FROM company_write_lock WHERE id=1 FOR UPDATE')
                handlers={'entry/correction':staff_time.entry_correction,**company_projects.HANDLERS,**duty_plan.HANDLERS,**company_sync.HANDLERS,**company_diagnostics.HANDLERS}
                result=handlers[action](c,session['id'],body) if action in handlers else staff_time.handle(c,session['id'],action,body)
            return self.send_json(200,result)
        except PermissionError as e:return self.send_json(403,{'error':str(e)})
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as e:return self.send_json(400,{'error':str(e)})
    app.App.do_POST=post
    import provider_cache_runtime,zammad_cache_runtime
    provider_cache_runtime.start_refresh=lambda a,u,p,days=0:company_sync.start_refresh(a,u,p,days)
    provider_cache_runtime.refresh_job=lambda u,p:company_sync.job(app,u,p)
    zammad_cache_runtime.start_refresh=lambda a,u:company_sync.start_refresh(a,u,'zammad')
    zammad_cache_runtime.job=lambda u:company_sync.job(app,u,'zammad')
