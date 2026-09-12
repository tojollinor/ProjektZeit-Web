"""Second performance pass: batch provider enrichment and user diagnostics."""
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import provider_archive

_STARTED = time.monotonic()


def _parse(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _fast_enrich(final, c, uid, provider, result):
    rows = result.get('rows') or []
    if not rows:
        return result

    assignments = {
        r['external_key']: dict(r)
        for r in c.execute(
            'SELECT owner_id,provider,external_key,customer_id,project_id,match_type,match_value,assigned_by,assigned_at '
            'FROM provider_assignments WHERE owner_id=? AND provider=?', (uid, provider)
        )
    }
    links = {}
    for r in c.execute(
        'SELECT customer_id,link_type,link_value,display_name,created_at '
        'FROM customer_identity_links WHERE owner_id=? AND provider=?', (uid, provider)
    ):
        links[(r['link_type'], r['link_value'])] = dict(r)
    customers = {r['id']: r['name'] for r in c.execute('SELECT id,name FROM customers WHERE owner_id=?', (uid,))}
    projects = {r['id']: r['name'] for r in c.execute('SELECT id,name FROM projects WHERE owner_id=?', (uid,))}
    events = {}
    if links:
        for r in c.execute(
            'SELECT external_key,occurred_at,captured_at FROM provider_events WHERE owner_id=? AND provider=?', (uid, provider)
        ):
            events[r['external_key']] = dict(r)

    stamp = final.now_iso()
    display_updates = {}
    for row in rows:
        key = str(row.get('external_key') or '')
        assignment = assignments.get(key)
        if assignment is None:
            typ, value = final._provider_identifier(provider, row.get('raw') or {}, row.get('customer_hint') or {})
            customer_id = None
            link = links.get((typ, value)) if typ and value else None
            if link:
                allowed = True
                created = _parse(link.get('created_at'))
                event = events.get(key) or {}
                event_time = _parse(event.get('occurred_at')) or _parse(event.get('captured_at'))
                if created and event_time and event_time < created:
                    allowed = False
                if allowed:
                    customer_id = link.get('customer_id')
            assignment = {
                'owner_id': uid, 'provider': provider, 'external_key': key,
                'customer_id': customer_id, 'project_id': None,
                'match_type': typ, 'match_value': value,
                'assigned_by': None, 'assigned_at': stamp if customer_id else ''
            }
            if customer_id:
                c.execute(
                    'INSERT INTO provider_assignments(owner_id,provider,external_key,customer_id,project_id,match_type,match_value,assigned_by,assigned_at) '
                    'VALUES(?,?,?,?,NULL,?,?,NULL,?)',
                    (uid, provider, key, customer_id, typ, value, stamp)
                )
                assignments[key] = assignment
        row['assignment'] = dict(assignment)
        customer_id = assignment.get('customer_id')
        project_id = assignment.get('project_id')
        if customer_id:
            row['assignment']['customer_name'] = customers.get(customer_id, '')
        if project_id:
            row['assignment']['project_name'] = projects.get(project_id, '')
        if provider == 'teamviewer' and customer_id:
            typ = assignment.get('match_type') or ''
            value = assignment.get('match_value') or ''
            link = links.get((typ, value))
            name = str((row.get('raw') or {}).get('devicename') or (row.get('customer_hint') or {}).get('device_name') or '')[:500]
            if link and name and name != str(link.get('display_name') or ''):
                display_updates[(typ, value)] = name

    for (typ, value), name in display_updates.items():
        c.execute(
            'UPDATE customer_identity_links SET display_name=? WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',
            (name, uid, provider, typ, value)
        )
    return result


def _count(c, sql, args=()):
    try:
        row = c.execute(sql, args).fetchone()
        if not row:
            return 0
        try:
            return int(row['n'])
        except Exception:
            return int(row[0])
    except Exception:
        return None


def install(app):
    try:
        final = __import__('final_batch_runtime')
        final.enrich_rows = lambda c, uid, provider, result: _fast_enrich(final, c, uid, provider, result)
    except Exception:
        final = None

    original_init = app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        try:
            with app.db() as c:
                c.execute('CREATE INDEX IF NOT EXISTS idx_operation_logs_owner_id ON operation_logs(owner_id,id)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_provider_events_owner_provider_captured ON provider_events(owner_id,provider,captured_at)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_customer_contacts_owner_customer ON customer_contacts(owner_id,customer_id)')
        except Exception:
            pass
    app.init_db = init_db

    previous_post = app.App.do_POST
    def do_POST(self):
        if urlparse(self.path).path != '/api/v1/diagnostics/snapshot':
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
        with app.db() as c:
            counts = {
                'customers': _count(c, 'SELECT COUNT(*) n FROM customers WHERE owner_id=?', (uid,)),
                'projects': _count(c, 'SELECT COUNT(*) n FROM projects WHERE owner_id=?', (uid,)),
                'entries': _count(c, 'SELECT COUNT(*) n FROM entries WHERE owner_id=?', (uid,)),
                'zammad_tickets': _count(c, 'SELECT COUNT(*) n FROM zammad_ticket_cache WHERE owner_id=?', (uid,)),
                'provider_events_zammad': _count(c, "SELECT COUNT(*) n FROM provider_events WHERE owner_id=? AND provider='zammad'", (uid,)),
                'provider_events_starface': _count(c, "SELECT COUNT(*) n FROM provider_events WHERE owner_id=? AND provider='starface'", (uid,)),
                'provider_events_teamviewer': _count(c, "SELECT COUNT(*) n FROM provider_events WHERE owner_id=? AND provider='teamviewer'", (uid,)),
                'operation_logs': _count(c, 'SELECT COUNT(*) n FROM operation_logs WHERE owner_id=?', (uid,)),
            }
            logs = provider_archive.list_logs(c, uid, '', '', 1000)
            providers = []
            try:
                nav = __import__('provider_nav_runtime')
                providers = [nav.provider_status(app, c, uid, p) for p in ('zammad', 'starface', 'teamviewer')]
            except Exception:
                providers = []
            dialect = str(getattr(c, 'dialect', '') or 'sqlite')
        return self.send_json(200, {
            'server_time': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'frontend_version': str(getattr(app, 'FRONTEND_VERSION', '') or ''),
            'database': dialect,
            'process_uptime_seconds': int(time.monotonic() - _STARTED),
            'thread_count': threading.active_count(),
            'counts': counts,
            'providers': providers,
            'logs': logs,
        })
    app.App.do_POST = do_POST
