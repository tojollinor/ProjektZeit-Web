"""UX/provider runtime additions for central endpoints, STARFACE browser login and live history logs."""
import ipaddress
import json
import secrets
import socket
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import integrations
import provider_archive
import starface_calls
import system_features

_JOBS = {}
_JOBS_LOCK = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS provider_system_config (
      provider VARCHAR(32) PRIMARY KEY,
      domain TEXT NOT NULL,
      updated_at VARCHAR(40) NOT NULL,
      updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL
    );
    ''')
    for provider in ('zammad', 'teamviewer'):
        row = c.execute('SELECT provider FROM provider_system_config WHERE provider=?', (provider,)).fetchone()
        if row:
            continue
        old = c.execute('SELECT domain FROM integrations WHERE provider=? AND domain<>? ORDER BY updated_at DESC LIMIT 1', (provider, '')).fetchone()
        domain = old['domain'] if old else ('https://webapi.teamviewer.com' if provider == 'teamviewer' else '')
        if domain:
            c.execute('INSERT INTO provider_system_config(provider,domain,updated_at,updated_by) VALUES(?,?,?,NULL)',
                      (provider, domain, now_iso()))


def provider_domain(c, provider):
    row = c.execute('SELECT domain FROM provider_system_config WHERE provider=?', (provider,)).fetchone()
    if row and row['domain']:
        return row['domain']
    return 'https://webapi.teamviewer.com' if provider == 'teamviewer' else ''


def provider_public(c):
    return {p: provider_domain(c, p) for p in ('zammad', 'teamviewer')}


def save_provider(c, actor_id, provider, domain):
    provider = str(provider or '').lower()
    if provider not in ('zammad', 'teamviewer'):
        raise ValueError('Unbekannte zentrale Schnittstelle.')
    normalized = integrations.domain(domain, provider)
    old = provider_domain(c, provider)
    c.execute('DELETE FROM provider_system_config WHERE provider=?', (provider,))
    c.execute('INSERT INTO provider_system_config(provider,domain,updated_at,updated_by) VALUES(?,?,?,?)',
              (provider, normalized, now_iso(), actor_id))
    if old != normalized:
        system_features.audit(c, actor_id, actor_id, 'system_setting', provider + '_server', 'updated',
                              {'domain': {'old': old, 'new': normalized}})
    return normalized


def network_probe(origin):
    result = {'origin': origin or '', 'host': '', 'addresses': [], 'private': False, 'reachable': False}
    if not origin:
        return result
    try:
        parsed = urlparse(origin)
        host = parsed.hostname or ''
        port = parsed.port or 443
        result['host'] = host
        addresses = []
        for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
            addr = item[4][0]
            if addr not in addresses:
                addresses.append(addr)
        result['addresses'] = addresses[:8]
        private = False
        for addr in addresses:
            ip = ipaddress.ip_address(addr)
            private = private or ip.is_private
        result['private'] = private
        if addresses:
            sock = socket.create_connection((addresses[0], port), timeout=1.5)
            sock.close()
            result['reachable'] = True
    except Exception as error:
        result['error'] = str(error)[:220]
    return result


def _copy_job(job):
    return json.loads(json.dumps(job, default=str))


def _job_log(job, level, message, details=None):
    with _JOBS_LOCK:
        entries = job.setdefault('logs', [])
        entries.append({'seq': len(entries) + 1, 'at': now_iso(), 'level': level, 'message': str(message),
                        'details': details or {}})
        if len(entries) > 1000:
            del entries[:len(entries)-1000]


def _finish_sync(db_factory, uid, provider, job, received, new, existing, pages):
    with db_factory() as c:
        state = provider_archive.update_sync_state(c, uid, provider)
        level = 'warning' if pages >= 1000 else 'success'
        message = f'{provider.upper() if provider == "starface" else "TeamViewer"} History synchronisiert · {received} geprüft · {new} neu · {existing} bereits vorhanden'
        provider_archive.add_log(c, uid, provider, level, 'history_sync', message, {'pages': pages, **state})
    result = {'provider': provider, 'received': received, 'new': new, 'existing': existing, 'pages': pages, **state}
    _job_log(job, 'success', message, result)
    return result


def _sync_starface(db_factory, uid, config, job):
    _job_log(job, 'info', 'STARFACE-Verbindung wird aufgebaut.')
    rpc = starface_calls.UciClient(config)
    if rpc.call('connection.login') is not True:
        raise ValueError('STARFACE-UCI-Anmeldung abgewiesen.')
    _job_log(job, 'success', 'STARFACE-UCI-Anmeldung erfolgreich.')
    received = new = existing = pages = 0
    try:
        offset = 0
        while True:
            result, next_offset, total = provider_archive._starface_page(config, rpc, offset)
            with db_factory() as c:
                stats = provider_archive.cache_with_stats(c, uid, 'starface', result)
            received += stats['received']; new += stats['new']; existing += stats['existing']; pages += 1
            _job_log(job, 'info', f'Seite {pages} verarbeitet · {stats["received"]} Datensätze · {stats["new"]} neu',
                     {'offset': offset, 'total': total, **stats})
            if next_offset is None or pages >= 1000:
                break
            offset = next_offset
    finally:
        try:
            rpc.call('connection.logout')
            _job_log(job, 'info', 'STARFACE-Verbindung sauber beendet.')
        except Exception:
            pass
    return _finish_sync(db_factory, uid, 'starface', job, received, new, existing, pages)


def _sync_teamviewer(db_factory, uid, config, job):
    _job_log(job, 'info', 'TeamViewer-History wird vorbereitet.')
    client = integrations.Client(config['domain'])
    now = datetime.now(timezone.utc)
    params = {'limit': 100, 'from_date': '2000-01-01T00:00:00Z', 'to_date': now.strftime('%Y-%m-%dT%H:%M:%SZ')}
    received = new = existing = pages = 0
    seen = set()
    while True:
        try:
            result, next_offset, batch_count = provider_archive._teamviewer_page(config, client, params)
        except ValueError as error:
            if pages == 0 and 'from_date' in params:
                _job_log(job, 'warning', 'Vollständiger Zeitraum wurde von TeamViewer abgewiesen. Fallback auf API-Standardzeitraum.', {'error': str(error)})
                params = {'limit': 100}
                result, next_offset, batch_count = provider_archive._teamviewer_page(config, client, params)
            else:
                raise
        with db_factory() as c:
            stats = provider_archive.cache_with_stats(c, uid, 'teamviewer', result)
        received += stats['received']; new += stats['new']; existing += stats['existing']; pages += 1
        _job_log(job, 'info', f'Seite {pages} verarbeitet · {stats["received"]} Datensätze · {stats["new"]} neu',
                 {'offset': params.get('offset', ''), **stats})
        if not next_offset or batch_count < 100 or str(next_offset) in seen or pages >= 1000:
            break
        seen.add(str(next_offset)); params['offset'] = str(next_offset)
    return _finish_sync(db_factory, uid, 'teamviewer', job, received, new, existing, pages)


def start_history_job(db_factory, uid, provider, config):
    provider = str(provider or '').lower()
    if provider not in ('starface', 'teamviewer'):
        raise ValueError('History-Sync ist nur für STARFACE und TeamViewer verfügbar.')
    key = f'{uid}:{provider}'
    with _JOBS_LOCK:
        existing = _JOBS.get(key)
        if existing and existing.get('state') == 'running':
            return _copy_job(existing)
        job = {'id': secrets.token_urlsafe(12), 'provider': provider, 'state': 'running', 'started_at': now_iso(),
               'finished_at': '', 'result': None, 'error': '', 'logs': []}
        _JOBS[key] = job
    _job_log(job, 'info', f'{"STARFACE" if provider == "starface" else "TeamViewer"} History-Import gestartet.')

    def worker():
        try:
            result = _sync_starface(db_factory, uid, config, job) if provider == 'starface' else _sync_teamviewer(db_factory, uid, config, job)
            with _JOBS_LOCK:
                job.update(state='success', result=result, finished_at=now_iso())
        except Exception as error:
            _job_log(job, 'error', str(error))
            try:
                with db_factory() as c:
                    provider_archive.add_log(c, uid, provider, 'error', 'history_sync', 'History-Import fehlgeschlagen', {'error': str(error)})
            except Exception:
                pass
            with _JOBS_LOCK:
                job.update(state='error', error=str(error), finished_at=now_iso())

    threading.Thread(target=worker, name=f'pz-live-history-{provider}-{uid}', daemon=True).start()
    return _copy_job(job)


def history_job(uid, provider):
    with _JOBS_LOCK:
        job = _JOBS.get(f'{uid}:{str(provider or "").lower()}')
        return _copy_job(job) if job else {'provider': provider, 'state': 'idle', 'result': None, 'error': '', 'logs': []}


def install(app):
    ac = __import__('admin_controls')
    feature = __import__('feature_runtime')

    original_init = app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:
            migrate(c)
    app.init_db = init_db

    # System-wide Zammad and TeamViewer server addresses, while credentials remain per-user.
    old_list = integrations.list_configs
    old_config = integrations.config
    def list_configs(c, uid):
        data = old_list(c, uid)
        for item in data:
            if item['provider'] in ('zammad', 'teamviewer'):
                item['domain'] = provider_domain(c, item['provider'])
                item['server_configured'] = bool(item['domain'])
        return data
    def config(c, uid, body, data_dir):
        payload = dict(body or {})
        provider = payload.get('provider')
        if provider in ('zammad', 'teamviewer'):
            central = provider_domain(c, provider)
            if not central:
                raise ValueError(f'{provider.capitalize()}-Server ist noch nicht zentral durch einen Administrator konfiguriert.')
            payload['domain'] = central
        return old_config(c, uid, payload, data_dir)
    integrations.list_configs = list_configs
    integrations.config = config
    app.integrations.list_configs = list_configs
    app.integrations.config = config

    previous_get = app.App.do_GET
    def do_GET(self):
        path = urlparse(self.path).path
        if path == app.starface_oauth.CALLBACK:
            session = self.require()
            if not session:
                return
            try:
                app.starface_oauth.finish(app.db, session, __import__('urllib.parse').parse.parse_qs(urlparse(self.path).query), app.DATA_DIR)
                location = '/?starface=connected'
            except Exception as error:
                try:
                    with app.db() as c:
                        provider_archive.add_log(c, session['id'], 'starface', 'warning', 'oauth_browser', 'STARFACE-Anmeldung über Weboberfläche fehlgeschlagen', {'error': str(error)})
                except Exception:
                    pass
                location = '/?starface=failed'
            self.send_response(303); self.send_header('Location', location); self.send_header('Content-Length', '0'); self.end_headers(); return
        return previous_get(self)
    app.App.do_GET = do_GET

    previous_post = app.App.do_POST
    owned = {
        '/api/v1/admin/provider/config', '/api/v1/admin/provider/save',
        '/api/v1/starface/connect/start', '/api/v1/starface/connect/windows',
        '/api/v1/archive/start', '/api/v1/archive/job'
    }
    def do_POST(self):
        path = urlparse(self.path).path
        if path not in owned:
            return previous_post(self)
        try:
            body = self.json_body()
            if not isinstance(body, dict):
                raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:
            return self.send_json(400, {'error': str(error)})
        session = self.require(csrf=True)
        if not session:
            return
        uid = session['id']
        try:
            if path == '/api/v1/admin/provider/config':
                with app.db() as c:
                    ac.require_permission(c, uid, 'integrations.view')
                    data = provider_public(c)
                    sf = system_features.starface_public(c)
                return self.send_json(200, {'providers': data, 'starface_network': network_probe(sf.get('domain'))})
            if path == '/api/v1/admin/provider/save':
                with app.db() as c:
                    ac.require_permission(c, uid, 'integrations.edit')
                    normalized = save_provider(c, uid, body.get('provider'), body.get('domain'))
                return self.send_json(200, {'provider': body.get('provider'), 'domain': normalized})
            if path == '/api/v1/starface/connect/start':
                with app.db() as c:
                    sf = system_features.starface_public(c)
                if not sf['has_client_secret']:
                    return self.send_json(409, {'error': 'Noch kein Client-Secret hinterlegt. Bitte an den Administrator wenden.'})
                try:
                    result = app.starface_oauth.start(app.db, session, {}, app.DATA_DIR)
                    result.update({'mode': 'browser', 'network': network_probe(sf.get('domain'))})
                    return self.send_json(200, result)
                except (ValueError, OSError) as error:
                    try:
                        with app.db() as c:
                            provider_archive.add_log(c, uid, 'starface', 'warning', 'oauth_browser', 'Direkte Web-Anmeldung konnte nicht vorbereitet werden', {'error': str(error)})
                    except Exception:
                        pass
                    return self.send_json(409, {'error': 'Anmeldung aus der Weboberfläche nicht möglich. Bitte den lokalen Windows-Client verwenden.', 'detail': str(error), 'fallback': 'windows'})
            if path == '/api/v1/starface/connect/windows':
                return self.send_json(200, app.starface_oauth.start(app.db, session, {'desktop_prepare': True}, app.DATA_DIR))
            if path == '/api/v1/archive/start':
                provider = str(body.get('provider') or '').lower()
                config = feature.integration_config(app, uid, provider)
                return self.send_json(202, {'job': start_history_job(app.db, uid, provider, config)})
            if path == '/api/v1/archive/job':
                return self.send_json(200, {'job': history_job(uid, body.get('provider'))})
        except PermissionError as error:
            return self.send_json(403, {'error': str(error)})
        except (ValueError, TypeError, OSError) as error:
            return self.send_json(400, {'error': str(error) if not isinstance(error, OSError) else 'Schnittstelle nicht erreichbar.'})
    app.App.do_POST = do_POST
