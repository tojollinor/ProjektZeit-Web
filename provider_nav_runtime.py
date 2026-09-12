"""Connection state for provider navigation badges and reconnect prompts."""
from urllib.parse import urlparse


def _table_exists(c, name):
    try:
        c.execute(f'SELECT 1 FROM {name} LIMIT 1').fetchone()
        return True
    except Exception:
        return False


def _central_domain(c, provider):
    if provider == 'starface':
        try:
            row=c.execute('SELECT domain FROM starface_system_config WHERE id=1').fetchone()
            return str(row['domain'] or '') if row else ''
        except Exception:
            return ''
    try:
        row=c.execute('SELECT domain FROM provider_system_config WHERE provider=?',(provider,)).fetchone()
        return str(row['domain'] or '') if row else ''
    except Exception:
        return ''


def _access(c, uid, provider):
    try:
        row=c.execute('SELECT state,message,checked_at FROM provider_access_state WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
        if row:return {'state':str(row['state'] or 'unknown'),'message':str(row['message'] or ''),'checked_at':str(row['checked_at'] or '')}
    except Exception:
        pass
    return {'state':'unknown','message':'','checked_at':''}


def _last_log(c, uid, provider):
    try:
        row=c.execute('SELECT level,message,created_at FROM operation_logs WHERE owner_id=? AND category=? ORDER BY id DESC',(uid,provider)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def provider_status(c, uid, provider):
    provider=str(provider or '').lower()
    domain=_central_domain(c,provider)
    configured_server=bool(domain)
    ever=False;credentials=False
    if provider=='starface':
        try:
            token=c.execute('SELECT 1 FROM oauth_tokens WHERE owner_id=?',(uid,)).fetchone()
            credentials=bool(token)
            ever=credentials or bool(c.execute('SELECT 1 FROM provider_events WHERE owner_id=? AND provider=? LIMIT 1',(uid,provider)).fetchone())
        except Exception:
            pass
    else:
        try:
            row=c.execute('SELECT secret FROM integrations WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
            credentials=bool(row and row['secret'])
            ever=bool(row)
        except Exception:
            pass
        try:
            ever=ever or bool(c.execute('SELECT 1 FROM provider_events WHERE owner_id=? AND provider=? LIMIT 1',(uid,provider)).fetchone())
        except Exception:
            pass
        if provider=='zammad':
            try:ever=ever or bool(c.execute('SELECT 1 FROM zammad_ticket_cache WHERE owner_id=? LIMIT 1',(uid,)).fetchone())
            except Exception:pass
    access=_access(c,uid,provider)
    last=_last_log(c,uid,provider)
    bad_state=access['state'] in ('invalid','unavailable')
    latest_error=bool(last and str(last.get('level') or '').lower()=='error')
    connected=bool(configured_server and credentials and not bad_state and not latest_error)
    if connected:
        reason='connected';detail='Verbindung ist eingerichtet.'
    elif not configured_server or not credentials:
        reason='interrupted' if ever else 'missing'
        detail='Verbindung wurde unterbrochen.' if ever else 'Verbindung wurde noch nicht eingerichtet.'
    else:
        reason='interrupted';detail=access['message'] or (last.get('message') if last else '') or 'Verbindung wurde unterbrochen.'
    return {'provider':provider,'connected':connected,'reason':reason,'label':'Verbunden' if connected else 'Nicht verbunden',
            'detail':detail,'configured':bool(configured_server and credentials),'ever_configured':ever,
            'checked_at':access['checked_at'] or (last.get('created_at') if last else '')}


def install(app):
    previous_post=app.App.do_POST
    def do_POST(self):
        if urlparse(self.path).path!='/api/v1/provider/navigation-status':return previous_post(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:return self.send_json(400,{'error':str(error)})
        session=self.require(csrf=True)
        if not session:return
        with app.db() as c:
            providers=[provider_status(c,session['id'],p) for p in ('zammad','starface','teamviewer')]
        return self.send_json(200,{'providers':providers})
    app.App.do_POST=do_POST
