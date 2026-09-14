"""Company management routes; explicit service dispatch and transaction boundaries."""
from urllib.parse import urlparse
import sqlite3
import staff_time
import company_projects
import duty_plan
import company_sync
import company_diagnostics
import provider_budget

READ_ACTIONS={'context','report','inbox','calendar','list','statistics','preview','status'}

def install(app):
    staff_time.register()
    import workday
    workday.entry_context_hook=company_projects.snapshot_entry
    original_init=app.init_db
    def init(create_admin=True):
        original_init(create_admin)
        with app.db() as c:
            staff_time.migrate(c);company_projects.migrate(c);duty_plan.migrate(c);company_sync.migrate(c);company_diagnostics.migrate(c)
        provider_budget.initialize(app.DATA_DIR);provider_budget.install_transport()
    app.init_db=init
    previous=app.App.do_POST
    def post(self):
        path=urlparse(self.path).path
        if not path.startswith('/api/v1/company/') and path!='/api/v1/entries/edit':return previous(self)
        session=self.require(csrf=True)
        if not session:return
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Benannte Felder erforderlich.')
            action='entry/correction' if path=='/api/v1/entries/edit' else path.removeprefix('/api/v1/company/')
            if action=='diagnostics/start':return self.send_json(202,company_diagnostics.start(app,session['id'],body))
            with app.db(read_only=action.rsplit('/',1)[-1] in READ_ACTIONS) as c:
                if action.rsplit('/',1)[-1] not in READ_ACTIONS:c.execute('BEGIN IMMEDIATE')
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
