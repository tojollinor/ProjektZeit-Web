"""Security enforcement and configurable transactional e-mail presentation."""
import hashlib
import re
import sqlite3
import time
from datetime import datetime, timezone
from http import cookies
from urllib.parse import urlsplit

import admin_controls
import email_runtime

_INSTALLED = False


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _columns(c, table):
    if getattr(c, 'dialect', '') == 'mariadb':
        return {r['COLUMN_NAME'] for r in c.execute(
            'SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=?', (table,)
        )}
    return {r['name'] for r in c.execute('PRAGMA table_info(%s)' % table)}


def migrate(c, default_session_ttl=43200):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS password_history(
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      password_salt VARCHAR(255) NOT NULL, password_hash VARCHAR(255) NOT NULL,
      changed_at VARCHAR(40) NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_password_history_user ON password_history(user_id,id);
    ''')
    session_columns = _columns(c, 'sessions')
    if 'created_at' not in session_columns:
        c.execute('ALTER TABLE sessions ADD COLUMN created_at BIGINT NOT NULL DEFAULT 0')
    security_columns = _columns(c, 'user_security_state')
    if 'password_changed_at' not in security_columns:
        c.execute("ALTER TABLE user_security_state ADD COLUMN password_changed_at VARCHAR(40) NOT NULL DEFAULT ''")
    stamp = now_iso()
    for user in c.execute('SELECT id,created_at FROM users'):
        row = c.execute('SELECT user_id,password_changed_at FROM user_security_state WHERE user_id=?', (user['id'],)).fetchone()
        if not row:
            c.execute('INSERT INTO user_security_state(user_id,must_change_password,password_changed_at) VALUES(?,0,?)',
                      (user['id'], user['created_at'] or stamp))
        elif not row['password_changed_at']:
            c.execute('UPDATE user_security_state SET password_changed_at=? WHERE user_id=?',
                      (user['created_at'] or stamp, user['id']))
    c.execute('UPDATE sessions SET created_at=expires_at-? WHERE created_at=0', (int(default_session_ttl),))
    if not c.execute('SELECT 1 FROM system_settings WHERE setting_key=?', ('email.template',)).fetchone():
        admin_controls.set_setting(c, 'email.template', dict(email_runtime.EMAIL_TEMPLATE_DEFAULTS))


def ensure_password_unused(c, uid, password, verify_password):
    count = max(0, min(50, int(admin_controls.setting(c, 'policy.password_history', 0))))
    if count <= 0:
        return
    current = c.execute('SELECT password_salt,password_hash FROM users WHERE id=?', (int(uid),)).fetchone()
    candidates = [current] if current else []
    if _columns(c, 'password_history'):
        candidates.extend(c.execute('SELECT password_salt,password_hash FROM password_history WHERE user_id=? ORDER BY id DESC LIMIT ?',
                                    (int(uid), count)))
    if any(verify_password(str(password), row['password_salt'], row['password_hash']) for row in candidates):
        raise ValueError('Dieses Passwort wurde bereits verwendet. Bitte ein anderes Passwort wählen.')


def archive_password(c, uid, salt, digest):
    if not salt or not digest or not _columns(c, 'password_history'):
        return
    c.execute('INSERT INTO password_history(user_id,password_salt,password_hash,changed_at) VALUES(?,?,?,?)',
              (int(uid), str(salt), str(digest), now_iso()))
    old = list(c.execute('SELECT id FROM password_history WHERE user_id=? ORDER BY id DESC', (int(uid),)))[50:]
    for row in old:
        c.execute('DELETE FROM password_history WHERE id=?', (row['id'],))


def mark_password_changed(c, uid):
    if 'password_changed_at' not in _columns(c, 'user_security_state'):
        return
    if c.execute('SELECT 1 FROM user_security_state WHERE user_id=?', (int(uid),)).fetchone():
        c.execute('UPDATE user_security_state SET must_change_password=0,password_changed_at=? WHERE user_id=?',
                  (now_iso(), int(uid)))
    else:
        c.execute('INSERT INTO user_security_state(user_id,must_change_password,password_changed_at) VALUES(?,0,?)',
                  (int(uid), now_iso()))


def validate_template(value):
    if not isinstance(value, dict):
        raise ValueError('E-Mail-Vorlage muss benannte Felder enthalten.')
    result = {}
    result['company_name'] = str(value.get('company_name') or 'ProjektZeit').strip()[:120]
    if not result['company_name']:
        raise ValueError('Bitte einen Unternehmensnamen angeben.')
    for key in ('primary_color', 'accent_color'):
        color = str(value.get(key) or email_runtime.EMAIL_TEMPLATE_DEFAULTS[key]).strip()
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('Farben bitte als sechsstelligen Hex-Wert angeben.')
        result[key] = color.lower()
    logo = str(value.get('logo_url') or '').strip()[:1000]
    if logo:
        parsed = urlsplit(logo)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError('Logo-URL muss eine öffentliche HTTP- oder HTTPS-Adresse sein.')
    result['logo_url'] = logo
    result['footer_text'] = str(value.get('footer_text') or email_runtime.EMAIL_TEMPLATE_DEFAULTS['footer_text']).strip()[:1000]
    if not result['footer_text']:
        raise ValueError('Bitte einen Fußzeilentext angeben.')
    return result


def preview(c, supplied=None):
    template = validate_template(supplied) if isinstance(supplied, dict) else email_runtime.email_template(c)
    content = email_runtime._mail_content('Sicherheitsinformation', 'Max Mustermann',
        'Dies ist eine Vorschau der zentralen E-Mail-Vorlage. Sicherheitscodes, Passwortänderungen und Bestätigungslinks verwenden dieses Erscheinungsbild.',
        'ProjektZeit öffnen', 'https://example.invalid/', '123456', template)
    # cid: images are correct for delivered mail but cannot render inside the
    # sandboxed browser preview.  Use the bundled public logo only there.
    if not template.get('logo_url'):
        content['html'] = content['html'].replace('cid:projektzeit-logo', '/projektzeit-logo.png')
    return {'template': template, 'html': content['html'], 'text': content['text']}


def _token_hash(handler):
    authorization = handler.headers.get('Authorization', '')
    if authorization.startswith('Bearer '):
        token = authorization[7:]
    else:
        jar = cookies.SimpleCookie(handler.headers.get('Cookie', ''))
        item = jar.get('pz_session')
        token = item.value if item else ''
    return hashlib.sha256(token.encode()).hexdigest() if token else ''


def _end_session(c, token_hash, reason):
    try:
        c.execute("UPDATE session_activity SET ended_at=?,end_reason=? WHERE token_hash=? AND ended_at=''",
                  (now_iso(), reason[:80], token_hash))
    except Exception:
        pass
    for table in ('session_mfa', 'native_sessions'):
        try: c.execute('DELETE FROM '+table+' WHERE token_hash=?', (token_hash,))
        except Exception: pass
    c.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash,))


def install(app):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    previous_init = app.init_db

    def init_db(create_admin=True):
        previous_init(create_admin)
        with app.db() as c:
            migrate(c, app.SESSION_TTL)
    app.init_db = init_db

    previous_session = app.App.current_session
    def current_session(self):
        token_hash = _token_hash(self)
        if token_hash:
            with app.db() as c:
                row = c.execute('''SELECT s.user_id,s.created_at,a.last_active_at,ss.password_changed_at
                  FROM sessions s LEFT JOIN session_activity a ON a.token_hash=s.token_hash
                  LEFT JOIN user_security_state ss ON ss.user_id=s.user_id WHERE s.token_hash=?''', (token_hash,)).fetchone()
                if row:
                    clock = int(time.time())
                    max_hours = max(1, int(admin_controls.setting(c, 'policy.session_max_hours', 12)))
                    idle_minutes = max(0, int(admin_controls.setting(c, 'policy.session_idle_minutes', 0)))
                    created = int(row['created_at'] or 0)
                    expired = bool(created and clock - created >= max_hours * 3600)
                    if idle_minutes and row['last_active_at']:
                        try:
                            last = datetime.fromisoformat(str(row['last_active_at']).replace('Z', '+00:00'))
                            expired = expired or (datetime.now(timezone.utc) - last.astimezone(timezone.utc)).total_seconds() >= idle_minutes * 60
                        except (TypeError, ValueError):
                            pass
                    if expired:
                        _end_session(c, token_hash, 'Sitzungsrichtlinie')
                        return None
                    expiry_days = max(0, int(admin_controls.setting(c, 'policy.password_expiry_days', 0)))
                    if expiry_days and row['password_changed_at']:
                        try:
                            changed = datetime.fromisoformat(str(row['password_changed_at']).replace('Z', '+00:00'))
                            if (datetime.now(timezone.utc) - changed.astimezone(timezone.utc)).total_seconds() >= expiry_days * 86400:
                                c.execute('UPDATE user_security_state SET must_change_password=1 WHERE user_id=?', (row['user_id'],))
                        except (TypeError, ValueError):
                            pass
        return previous_session(self)
    app.App.current_session = current_session

    previous_post = app.App.do_POST
    paths = {'/api/v1/admin/email-template/context', '/api/v1/admin/email-template/preview',
             '/api/v1/admin/email-template/save', '/api/v1/admin/email-template/test'}
    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in paths:
            return previous_post(self)
        session = self.require(csrf=True)
        if not session:
            return
        try:
            body = self.json_body()
            if not isinstance(body, dict):
                raise ValueError('Benannte Felder erforderlich.')
            if path.endswith('/context'):
                with app.db(read_only=True) as c:
                    admin_controls.require_permission(c, session['id'], 'smtp.view')
                    return self.send_json(200, preview(c))
            if path.endswith('/preview'):
                with app.db(read_only=True) as c:
                    admin_controls.require_permission(c, session['id'], 'smtp.view')
                    return self.send_json(200, preview(c, body.get('template')))
            if path.endswith('/save'):
                template = validate_template(body.get('template'))
                with app.db() as c:
                    admin_controls.require_permission(c, session['id'], 'smtp.edit')
                    admin_controls.set_setting(c, 'email.template', template)
                    __import__('system_features').audit(c, session['id'], session['id'], 'system_setting', 'email.template', 'updated', {'fields': sorted(template)})
                    return self.send_json(200, preview(c))
            recipient = email_runtime.normalize_email(body.get('recipient'), required=True)
            with app.db() as c:
                admin_controls.require_permission(c, session['id'], 'smtp.test')
                if not email_runtime.configured(c):
                    raise ValueError('E-Mail-Versand ist noch nicht eingerichtet.')
                email_runtime._queue(c, app.DATA_DIR, recipient, 'Test der E-Mail-Vorlage',
                    'Die zentrale E-Mail-Vorlage ist eingerichtet und der Versand funktioniert.', name='Testempfänger')
            email_runtime.start_worker(app)
            return self.send_json(200, {'ok': True})
        except PermissionError as error:
            return self.send_json(403, {'error': str(error)})
        except (ValueError, TypeError, KeyError, sqlite3.IntegrityError) as error:
            return self.send_json(400, {'error': str(error)})
    app.App.do_POST = do_POST
