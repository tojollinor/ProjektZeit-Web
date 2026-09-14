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
            pass
        try:
            row=c.execute('SELECT domain FROM integrations WHERE provider=? ORDER BY updated_at DESC LIMIT 1',(provider,)).fetchone()
            return str(row['domain'] or '') if row else ''
        except Exception:
            return ''
    try:
        row=c.execute('SELECT domain FROM provider_system_config WHERE provider=?',(provider,)).fetchone()
        return str(row['domain'] or '') if row else ''
    except Exception:
        try:
            row=c.execute('SELECT domain FROM integrations WHERE provider=? ORDER BY updated_at DESC LIMIT 1',(provider,)).fetchone()
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
        row=c.execute('SELECT level,message,created_at FROM operation_logs WHERE owner_id=? AND category=? ORDER BY id DESC LIMIT 1',(uid,provider)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _starface_client_secret(app,c,uid):
    # OAuth uses the company-wide client in feature_runtime. Legacy personal
    # credentials must never override a missing or removed central secret.
    try:
        central=c.execute('SELECT client_secret FROM starface_system_config WHERE id=1').fetchone()
        return bool(central and str(central['client_secret'] or '').strip())
    except Exception:
        return False


def provider_status(app, c, uid, provider):
    provider=str(provider or '').lower()
    domain=_central_domain(c,provider)
    configured_server=bool(domain)
    ever=False;credentials=False;client_secret_configured=None
    if provider=='starface':
        client_secret_configured=_starface_client_secret(app,c,uid)
        try:
            token=c.execute('SELECT 1 FROM oauth_tokens WHERE owner_id=?',(uid,)).fetchone()
            credentials=bool(token)
            ever=credentials or bool(c.execute('SELECT 1 FROM provider_events WHERE owner_id=? AND provider=? LIMIT 1',(uid,provider)).fetchone())
        except Exception:
            pass
        try:
            ever=ever or bool(c.execute('SELECT 1 FROM integrations WHERE owner_id=? AND provider=?',(uid,provider)).fetchone())
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
    confirmed=access['state']=='valid' and bool(access['checked_at'])
    connected=bool(configured_server and credentials and confirmed and not bad_state)
    if configured_server and credentials and not confirmed and not bad_state and (provider!='starface' or client_secret_configured):
        return {'provider':provider,'connected':False,'reason':'unknown','label':'Status noch nicht geprüft','detail':'Zugangsdaten sind hinterlegt; noch keine erfolgreiche Verbindungsprüfung.','configured':True,'ever_configured':ever,'checked_at':access['checked_at']}
    if provider=='starface' and not client_secret_configured:
        connected=False;reason='missing_client_secret';detail='Es wurde kein STARFACE Client Secret hinterlegt. Bitte an einen Administrator wenden.'
    elif connected:
        reason='connected';detail='Verbindung ist eingerichtet.'
    elif not configured_server or not credentials:
        reason=('expired' if ever else 'missing') if provider=='starface' else ('interrupted' if ever else 'missing')
        detail='Verbindung wurde unterbrochen.' if ever else 'Verbindung wurde noch nicht eingerichtet.'
    else:
        reason=('expired' if access['state']=='invalid' else 'unavailable') if provider=='starface' else 'interrupted';detail=access['message'] or (last.get('message') if last else '') or 'Verbindung wurde unterbrochen.'
    result={'provider':provider,'connected':connected,'reason':reason,'label':'Verbunden' if connected else 'Nicht verbunden',
            'detail':detail,'configured':bool(configured_server and credentials),'ever_configured':ever,
            'checked_at':access['checked_at'] or (last.get('created_at') if last else '')}
    if client_secret_configured is not None:result['client_secret_configured']=client_secret_configured
    return result


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
            providers=[provider_status(app,c,session['id'],p) for p in ('zammad','starface','teamviewer')]
        return self.send_json(200,{'providers':providers})
    app.App.do_POST=do_POST
