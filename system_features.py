"""Cross-cutting ProjektZeit features: user preferences, audit history, STARFACE client config and async history jobs."""
import json
import secrets
import threading
from datetime import datetime, timezone

import integrations
import provider_archive

_JOBS = {}
_JOBS_LOCK = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS user_preferences (
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      theme TEXT NOT NULL DEFAULT 'system',
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit_events (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      action TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'manual',
      changes_json LONGTEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(owner_id,entity_type,entity_id,id DESC);
    CREATE TABLE IF NOT EXISTS starface_system_config (
      id INTEGER PRIMARY KEY,
      domain TEXT NOT NULL DEFAULT '',
      client_id TEXT NOT NULL DEFAULT 'rest-client',
      client_secret TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL,
      updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL
    );
    ''')


def _safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return str(value)


def audit(c, owner_id, actor_id, entity_type, entity_id, action, changes=None, source='manual'):
    c.execute('INSERT INTO audit_events(owner_id,actor_id,entity_type,entity_id,action,source,changes_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
              (owner_id, actor_id, str(entity_type)[:80], str(entity_id)[:160], str(action)[:80], str(source)[:40],
               json.dumps(_safe(changes or {}), ensure_ascii=False), now_iso()))


def history(c, owner_id, entity_type, entity_id, limit=200):
    limit = max(1, min(int(limit or 200), 500))
    rows = c.execute('''SELECT a.id,a.actor_id,a.action,a.source,a.changes_json,a.created_at,u.username actor_name
                        FROM audit_events a LEFT JOIN users u ON u.id=a.actor_id
                        WHERE a.owner_id=? AND a.entity_type=? AND a.entity_id=? ORDER BY a.id DESC''',
                     (owner_id, str(entity_type), str(entity_id)))
    out = []
    for row in rows:
        try: changes = json.loads(row['changes_json'])
        except Exception: changes = {}
        out.append({'id': row['id'], 'actor_id': row['actor_id'], 'actor': row['actor_name'] or 'System',
                    'action': row['action'], 'source': row['source'], 'changes': changes, 'created_at': row['created_at']})
        if len(out) >= limit: break
    return out


def preference(c, uid):
    row = c.execute('SELECT theme FROM user_preferences WHERE user_id=?', (uid,)).fetchone()
    return {'theme': row['theme'] if row and row['theme'] in ('system','light','dark') else 'system'}


def save_preference(c, uid, theme):
    theme = str(theme or 'system').lower()
    if theme not in ('system','light','dark'):
        raise ValueError('Unbekannte Darstellung.')
    before = preference(c, uid)['theme']
    c.execute('DELETE FROM user_preferences WHERE user_id=?', (uid,))
    c.execute('INSERT INTO user_preferences(user_id,theme,updated_at) VALUES(?,?,?)', (uid,theme,now_iso()))
    if before != theme:
        audit(c, uid, uid, 'account', uid, 'theme_changed', {'theme': {'old': before, 'new': theme}})
    return {'theme': theme}


def self_profile(c, uid):
    row = c.execute('''SELECT u.id,u.username,u.role,p.first_name,p.last_name,p.email,p.phone,p.note
                       FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.id=?''', (uid,)).fetchone()
    if not row: raise ValueError('Benutzer nicht gefunden.')
    return dict(row)


def save_self_profile(c, uid, values):
    before = self_profile(c, uid)
    first = str(values.get('first_name') or '')[:120]
    last = str(values.get('last_name') or '')[:120]
    email = str(values.get('email') or '')[:250]
    phone = str(values.get('phone') or '')[:80]
    note = str(before.get('note') or '')
    last_login = c.execute('SELECT last_login_at FROM user_profiles WHERE user_id=?',(uid,)).fetchone()
    last_login_at = last_login['last_login_at'] if last_login else ''
    c.execute('DELETE FROM user_profiles WHERE user_id=?',(uid,))
    c.execute('INSERT INTO user_profiles(user_id,first_name,last_name,email,phone,note,last_login_at) VALUES(?,?,?,?,?,?,?)',
              (uid,first,last,email,phone,note,last_login_at))
    changes = {}
    for key,new in [('first_name',first),('last_name',last),('email',email),('phone',phone)]:
        old = before.get(key) or ''
        if old != new: changes[key] = {'old': old, 'new': new}
    if changes: audit(c, uid, uid, 'account', uid, 'profile_changed', changes)
    return self_profile(c, uid)


def starface_public(c):
    row = c.execute('SELECT domain,client_id,client_secret,updated_at FROM starface_system_config WHERE id=1').fetchone()
    return {'domain': row['domain'] if row else '', 'client_id': row['client_id'] if row else 'rest-client',
            'has_client_secret': bool(row and row['client_secret']), 'updated_at': row['updated_at'] if row else ''}


def starface_client(c, directory):
    row = c.execute('SELECT domain,client_id,client_secret FROM starface_system_config WHERE id=1').fetchone()
    if not row or not row['domain'] or not row['client_secret']:
        return None
    try: secret = integrations.cipher(directory).decrypt(row['client_secret'].encode()).decode()
    except Exception: raise ValueError('STARFACE Client-Secret konnte nicht gelesen werden.') from None
    return {'origin': row['domain'], 'client_id': row['client_id'] or 'rest-client', 'client_secret': secret}


def save_starface_client(c, actor_id, directory, domain, client_id, client_secret=None, delete_secret=False):
    domain = integrations.domain(domain, 'starface')
    client_id = str(client_id or 'rest-client').strip()
    if not client_id or len(client_id) > 250 or ':' in client_id:
        raise ValueError('STARFACE Client-ID ist ungültig.')
    old = c.execute('SELECT domain,client_id,client_secret FROM starface_system_config WHERE id=1').fetchone()
    stored = old['client_secret'] if old else ''
    if delete_secret:
        stored = ''
    elif isinstance(client_secret, str) and client_secret:
        if len(client_secret) > 4096: raise ValueError('STARFACE Client-Secret ist zu lang.')
        stored = integrations.cipher(directory).encrypt(client_secret.encode()).decode()
    c.execute('DELETE FROM starface_system_config WHERE id=1')
    c.execute('INSERT INTO starface_system_config(id,domain,client_id,client_secret,updated_at,updated_by) VALUES(1,?,?,?,?,?)',
              (domain,client_id,stored,now_iso(),actor_id))
    changes = {}
    if not old or old['domain'] != domain: changes['domain']={'old': old['domain'] if old else '', 'new': domain}
    if not old or old['client_id'] != client_id: changes['client_id']={'old': old['client_id'] if old else '', 'new': client_id}
    if delete_secret: changes['client_secret']={'old':'hinterlegt' if old and old['client_secret'] else 'leer','new':'leer'}
    elif client_secret: changes['client_secret']={'old':'hinterlegt' if old and old['client_secret'] else 'leer','new':'hinterlegt'}
    audit(c, actor_id, actor_id, 'system_setting', 'starface_client', 'updated', changes)
    return starface_public(c)


def provider_health(c, uid, provider):
    provider = str(provider).lower()
    configured = False
    connected = False
    detail = ''
    if provider == 'starface':
        system = starface_public(c)
        configured = bool(system['domain'] and system['has_client_secret'])
        connected = bool(c.execute('SELECT 1 FROM oauth_tokens WHERE owner_id=?',(uid,)).fetchone())
        detail = 'Verbunden' if connected else ('Bereit zur Anmeldung' if configured else 'Client-Secret fehlt')
    else:
        row = c.execute('SELECT * FROM integrations WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
        configured = bool(row and row['domain'])
        connected = configured and bool(row['secret'])
        detail = 'Konfiguriert' if configured else 'Nicht eingerichtet'
    last = c.execute('SELECT level,message,created_at FROM operation_logs WHERE owner_id=? AND category=? ORDER BY id DESC',(uid,provider)).fetchone()
    if last and last['level']=='error':
        return {'provider':provider,'state':'error','label':'Problem','detail':last['message'],'checked_at':last['created_at']}
    state = 'ok' if (connected if provider=='starface' else configured) else 'warning'
    return {'provider':provider,'state':state,'label':'Verbunden' if state=='ok' else 'Nicht verbunden','detail':detail,
            'checked_at': last['created_at'] if last else ''}


def start_history_job(db_factory, uid, provider, config):
    provider = str(provider).lower()
    if provider not in ('starface','teamviewer'): raise ValueError('History-Sync ist nur für STARFACE und TeamViewer verfügbar.')
    key = f'{uid}:{provider}'
    with _JOBS_LOCK:
        existing = _JOBS.get(key)
        if existing and existing.get('state') == 'running': return dict(existing)
        job = {'id': secrets.token_urlsafe(12), 'provider': provider, 'state': 'running', 'started_at': now_iso(),
               'finished_at': '', 'result': None, 'error': ''}
        _JOBS[key] = job
    def worker():
        try:
            result = provider_archive.sync_starface(db_factory,uid,config,True) if provider=='starface' else provider_archive.sync_teamviewer(db_factory,uid,config,True)
            with _JOBS_LOCK:
                job.update(state='success', result=result, finished_at=now_iso())
        except Exception as error:
            with _JOBS_LOCK:
                job.update(state='error', error=str(error), finished_at=now_iso())
    threading.Thread(target=worker, name=f'pz-history-{provider}-{uid}', daemon=True).start()
    return dict(job)


def history_job(uid, provider):
    with _JOBS_LOCK:
        job = _JOBS.get(f'{uid}:{str(provider).lower()}')
        return dict(job) if job else {'provider':provider,'state':'idle','result':None,'error':''}
