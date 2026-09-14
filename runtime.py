"""One authoritative application bootstrap for production and integration tests."""
import importlib
import app

RUNTIMES = ('customer_runtime', 'feature_runtime', 'contact_runtime', 'ux_runtime', 'provider_cache_runtime', 'api_runtime', 'zammad_cache_runtime', 'provider_nav_runtime', 'worktime_runtime', 'customer_extra_runtime', 'next_batch_runtime', 'frontend_update_runtime', 'final_batch_runtime', 'final_batch_fix_runtime', 'profile_avatar_runtime', 'performance_runtime', 'performance_v2_runtime', 'connections_runtime', 'project_catalog', 'work_models', 'company_runtime', 'action_runtime')
_initialized=False

def configure():
    global _initialized
    if not _initialized:
        for name in RUNTIMES:
            importlib.import_module(name).install(app)
        _initialized=True
    return app

def initialize(create_admin=True):
    configure()
    app.init_db(create_admin)
    return app

if __name__ == "__main__":
    initialize()
    import company_sync
    company_sync.start_scheduler(app)
    print("ProjektZeit läuft auf Port", app.PORT, flush=True)
    app.ThreadingHTTPServer((app.HOST, app.PORT), app.App).serve_forever()
