"""Transactional e-mail policies, secure action links and security notices."""
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import string
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import admin_controls
import integrations
import smtp_service


EMAIL_POLICIES = {
    'email_password_reset_allowed', 'email_verify_required',
    'notify_password_change', 'notify_email_change', 'notify_two_factor_change',
}
TOKEN_TTL = {'password_reset': 30 * 60, 'email_verify': 24 * 60 * 60}
MFA_TTL = 10 * 60
MFA_RESEND_SECONDS = 60
MFA_MAX_ATTEMPTS = 5
_APP = None
_WAKE = threading.Event()
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False
_INSTALLED = False


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _columns(c, table):
    if getattr(c, 'dialect', '') == 'mariadb':
        return {r['COLUMN_NAME'] for r in c.execute(
            'SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=?', (table,)
        )}
    return {r['name'] for r in c.execute('PRAGMA table_info(%s)' % table)}


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS user_email_state(
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      email VARCHAR(250) NOT NULL DEFAULT '', verified_at VARCHAR(40) NOT NULL DEFAULT '',
      verification_requested_at VARCHAR(40) NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS email_action_tokens(
      token_hash VARCHAR(64) PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      purpose VARCHAR(32) NOT NULL, email VARCHAR(250) NOT NULL, expires_at BIGINT NOT NULL,
      created_epoch BIGINT NOT NULL, used_at VARCHAR(40) NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_action_tokens(user_id,purpose,created_epoch);
    CREATE TABLE IF NOT EXISTS email_outbox(
      id INTEGER PRIMARY KEY, recipient VARCHAR(250) NOT NULL, subject VARCHAR(250) NOT NULL,
      body_secret LONGTEXT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
      next_attempt_at BIGINT NOT NULL DEFAULT 0, last_error VARCHAR(500) NOT NULL DEFAULT '',
      created_at VARCHAR(40) NOT NULL, sent_at VARCHAR(40) NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_email_outbox_status ON email_outbox(status,next_attempt_at,id);
    CREATE TABLE IF NOT EXISTS user_email_mfa(
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      email VARCHAR(250) NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
      created_at VARCHAR(40) NOT NULL
    );
    CREATE TABLE IF NOT EXISTS email_mfa_challenges(
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      email VARCHAR(250) NOT NULL, code_hash VARCHAR(64) NOT NULL, salt VARCHAR(64) NOT NULL,
      expires_at BIGINT NOT NULL, created_epoch BIGINT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
      used_at VARCHAR(40) NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_email_mfa_user ON email_mfa_challenges(user_id,created_epoch);
    ''')
    # Existing profile addresses predate verification support and remain trusted.
    stamp = now_iso()
    for row in c.execute("SELECT p.user_id,p.email FROM user_profiles p WHERE p.email<>''"):
        if not c.execute('SELECT 1 FROM user_email_state WHERE user_id=?', (row['user_id'],)).fetchone():
            c.execute('INSERT INTO user_email_state(user_id,email,verified_at) VALUES(?,?,?)',
                      (row['user_id'], normalize_email(row['email']), stamp))
    c.execute("UPDATE email_outbox SET status='queued' WHERE status='sending'")
    c.execute('DELETE FROM email_action_tokens WHERE expires_at<?', (int(time.time()) - 7 * 86400,))
    c.execute('DELETE FROM email_mfa_challenges WHERE expires_at<?', (int(time.time()) - 86400,))


def normalize_email(value, required=False):
    value = str(value or '').strip()
    if not value:
        if required:
            raise ValueError('Für diese Richtlinie ist eine E-Mail-Adresse erforderlich.')
        return ''
    if (len(value) > 250 or '\n' in value or '\r' in value or
            not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value)):
        raise ValueError('Bitte eine gültige E-Mail-Adresse eingeben.')
    return value


def smtp_configured(c):
    row = c.execute('SELECT host,sender_email FROM smtp_settings WHERE id=1').fetchone()
    return bool(row and str(row['host'] or '').strip() and str(row['sender_email'] or '').strip())


def _public_url():
    value = os.environ.get('APP_PUBLIC_URL', '').strip().rstrip('/')
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            return ''
    except ValueError:
        return ''
    return value


def configured(c):
    return smtp_configured(c)


def policy_enabled(c, key):
    if key not in EMAIL_POLICIES:
        return False
    return configured(c) and bool(admin_controls.setting(c, 'policy.' + key, admin_controls.POLICY_DEFAULTS[key]))


def link_features_configured(c):
    return configured(c) and bool(_public_url())


def _profile(c, uid):
    return c.execute('''SELECT u.id,u.username,u.active,p.email,p.first_name,p.last_name
                        FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.id=?''', (int(uid),)).fetchone()


def _state(c, uid):
    profile = _profile(c, uid)
    email = normalize_email(profile['email'] if profile else '')
    row = c.execute('SELECT * FROM user_email_state WHERE user_id=?', (int(uid),)).fetchone()
    verified = bool(row and email and str(row['email'] or '').casefold() == email.casefold() and row['verified_at'])
    return profile, email, verified


def email_verified(c, uid):
    return _state(c, uid)[2]


def ensure_email_available(c, email, uid=0):
    email = normalize_email(email)
    if not email:
        return email
    row = c.execute('SELECT user_id FROM user_profiles WHERE LOWER(email)=LOWER(?) AND user_id<>?', (email, int(uid or 0))).fetchone()
    if row:
        raise ValueError('Diese E-Mail-Adresse wird bereits von einem anderen Benutzer verwendet.')
    return email


def _replace_state(c, uid, email, verified_at=''):
    c.execute('DELETE FROM user_email_state WHERE user_id=?', (int(uid),))
    c.execute('INSERT INTO user_email_state(user_id,email,verified_at,verification_requested_at) VALUES(?,?,?,?)',
              (int(uid), normalize_email(email), str(verified_at or ''), ''))
    c.execute("UPDATE email_action_tokens SET used_at=? WHERE user_id=? AND purpose='email_verify' AND used_at=''",
              (now_iso(), int(uid)))


def _mail_content(subject, name, body, action_label='', action_url='', code=''):
    greeting = 'Hallo' + (' ' + str(name).strip() if str(name or '').strip() else '') + ','
    body = str(body or '').strip()
    plain = greeting + '\n\n' + body
    if code:
        plain += '\n\nDein Code: ' + str(code)
    if action_url:
        plain += '\n\n' + str(action_label or 'Öffnen') + ': ' + str(action_url)
    plain += '\n\nViele Grüße\nProjektZeit'
    paragraphs = ''.join('<p style="margin:0 0 16px;line-height:1.65;color:#334155">' +
                         html.escape(part).replace('\n', '<br>') + '</p>'
                         for part in body.split('\n\n') if part.strip())
    action = ''
    if action_url:
        action = ('<p style="margin:26px 0;text-align:center"><a href="' + html.escape(str(action_url), quote=True) +
                  '" style="display:inline-block;padding:13px 22px;border-radius:10px;background:#2f7fe6;color:#fff;'
                  'text-decoration:none;font-weight:700">' + html.escape(str(action_label or 'Öffnen')) + '</a></p>')
    code_box = ''
    if code:
        code_box = ('<div style="margin:24px 0;padding:18px;border:1px solid #bfdbfe;border-radius:12px;'
                    'background:#eff6ff;text-align:center"><div style="font-size:12px;letter-spacing:.08em;'
                    'text-transform:uppercase;color:#64748b;margin-bottom:7px">Dein Anmeldecode</div>'
                    '<div style="font:700 30px/1.2 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.18em;'
                    'color:#0f172a">' + html.escape(str(code)) + '</div></div>')
    document = '''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
    <body style="margin:0;background:#eef2f7;font-family:Inter,Segoe UI,Arial,sans-serif;color:#0f172a">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef2f7;padding:28px 12px"><tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#fff;border-radius:18px;overflow:hidden;box-shadow:0 12px 35px rgba(15,23,42,.12)">
          <tr><td style="padding:26px 30px;background:linear-gradient(135deg,#101827,#1d4f91);color:#fff">
            <table role="presentation" cellspacing="0" cellpadding="0"><tr>
              <td style="padding-right:14px"><img src="cid:projektzeit-logo" width="54" height="54" alt="ProjektZeit" style="display:block;border-radius:12px"></td>
              <td><div style="font-size:22px;font-weight:800">ProjektZeit</div><div style="font-size:13px;color:#bfdbfe">Sicher informiert</div></td>
            </tr></table>
          </td></tr>
          <tr><td style="padding:34px 34px 26px">
            <div style="width:46px;height:46px;border-radius:50%;background:#dbeafe;color:#2563eb;text-align:center;line-height:46px;font-size:23px;font-weight:800;margin-bottom:18px">&#10003;</div>
            <h1 style="margin:0 0 20px;font-size:25px;line-height:1.3;color:#0f172a">''' + html.escape(str(subject)) + '''</h1>
            <p style="margin:0 0 16px;line-height:1.65;color:#334155">''' + html.escape(greeting) + '''</p>''' + paragraphs + code_box + action + '''
            <p style="margin:26px 0 0;line-height:1.6;color:#64748b">Viele Grüße<br><strong style="color:#334155">ProjektZeit</strong></p>
          </td></tr>
          <tr><td style="padding:18px 34px;background:#f8fafc;border-top:1px solid #e2e8f0;font-size:12px;line-height:1.55;color:#64748b">
            Diese Nachricht wurde automatisch von ProjektZeit versendet. Bitte antworte nicht auf diese E-Mail.
          </td></tr>
        </table>
      </td></tr></table>
    </body></html>'''
    return {'text': plain, 'html': document}


def _queue(c, root, recipient, subject, body, name='', action_label='', action_url='', code=''):
    recipient = normalize_email(recipient, required=True)
    content = _mail_content(subject, name, body, action_label, action_url, code)
    encrypted = integrations.cipher(root).encrypt(json.dumps(content, ensure_ascii=False).encode()).decode()
    ident = c.execute('''INSERT INTO email_outbox(recipient,subject,body_secret,status,attempts,next_attempt_at,last_error,created_at,sent_at)
                         VALUES(?,?,?,'queued',0,0,'',?,'')''',
                      (recipient, str(subject)[:250], encrypted, now_iso())).lastrowid
    _WAKE.set()
    return ident


def _link(token, parameter):
    base = _public_url()
    if not base:
        raise ValueError('E-Mail ist noch nicht vollständig eingerichtet.')
    return base + '/?' + parameter + '=' + token


def _token(c, uid, purpose, email):
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    clock = int(time.time())
    c.execute("UPDATE email_action_tokens SET used_at=? WHERE user_id=? AND purpose=? AND used_at=''",
              (now_iso(), int(uid), purpose))
    c.execute('INSERT INTO email_action_tokens(token_hash,user_id,purpose,email,expires_at,created_epoch,used_at) VALUES(?,?,?,?,?,? ,?)',
              (digest, int(uid), purpose, normalize_email(email), clock + TOKEN_TTL[purpose], clock, ''))
    return raw


def request_verification(c, root, uid, force=False):
    profile, email, verified = _state(c, uid)
    if verified:
        return False
    if not profile or not profile['active'] or not email:
        raise ValueError('Für dieses Benutzerkonto ist keine E-Mail-Adresse hinterlegt.')
    if not policy_enabled(c, 'email_verify_required'):
        return False
    if not link_features_configured(c):
        raise ValueError('Für Bestätigungslinks fehlt die öffentliche ProjektZeit-Adresse (APP_PUBLIC_URL).')
    recent = c.execute("SELECT created_epoch FROM email_action_tokens WHERE user_id=? AND purpose='email_verify' AND used_at='' ORDER BY created_epoch DESC LIMIT 1", (uid,)).fetchone()
    if recent and not force and int(recent['created_epoch']) > int(time.time()) - 60:
        return False
    raw = _token(c, uid, 'email_verify', email)
    c.execute('UPDATE user_email_state SET verification_requested_at=? WHERE user_id=?', (now_iso(), uid))
    name = str(profile['first_name'] or profile['username'])
    url = _link(raw, 'verify-email')
    _queue(c, root, email, 'E-Mail-Adresse für ProjektZeit bestätigen',
           'Bitte bestätige deine E-Mail-Adresse. Der Link kann nur einmal verwendet werden und ist 24 Stunden gültig.\n\n'
           'Falls du diese Änderung nicht veranlasst hast, wende dich bitte an einen Administrator.',
           name=name, action_label='E-Mail-Adresse bestätigen', action_url=url)
    return True


def request_password_reset(c, root, email, request_ip=''):
    email = normalize_email(email, required=True)
    if not policy_enabled(c, 'email_password_reset_allowed') or not link_features_configured(c):
        return False
    rows = list(c.execute('''SELECT u.id,u.username,p.first_name,p.email FROM users u JOIN user_profiles p ON p.user_id=u.id
                             WHERE u.active=1 AND LOWER(p.email)=LOWER(?)''', (email,)))
    if len(rows) != 1:
        return False
    user = rows[0]
    recent = c.execute("SELECT COUNT(*) n FROM email_action_tokens WHERE user_id=? AND purpose='password_reset' AND created_epoch>?",
                       (user['id'], int(time.time()) - 3600)).fetchone()['n']
    if int(recent) >= 3:
        return False
    raw = _token(c, user['id'], 'password_reset', user['email'])
    name = str(user['first_name'] or user['username'])
    url = _link(raw, 'password-reset')
    _queue(c, root, user['email'], 'ProjektZeit-Passwort zurücksetzen',
           'Über den folgenden einmalig verwendbaren Link kannst du dein ProjektZeit-Passwort zurücksetzen. '
           'Der Link ist 30 Minuten gültig.\n\nFalls du den Reset nicht angefordert hast, ignoriere diese Nachricht.',
           name=name, action_label='Passwort zurücksetzen', action_url=url)
    return True


def consume_verification(c, token):
    digest = hashlib.sha256(str(token or '').encode()).hexdigest()
    row = c.execute("SELECT * FROM email_action_tokens WHERE token_hash=? AND purpose='email_verify'", (digest,)).fetchone()
    if not row or row['used_at'] or int(row['expires_at']) < int(time.time()):
        raise ValueError('Der Bestätigungslink ist ungültig oder abgelaufen.')
    profile, email, _ = _state(c, row['user_id'])
    if not profile or not email or email.casefold() != str(row['email']).casefold():
        raise ValueError('Die E-Mail-Adresse wurde inzwischen geändert. Bitte einen neuen Bestätigungslink anfordern.')
    stamp = now_iso()
    changed = c.execute("UPDATE email_action_tokens SET used_at=? WHERE token_hash=? AND used_at=''", (stamp, digest))
    if changed.rowcount != 1:
        raise ValueError('Der Bestätigungslink wurde bereits verwendet.')
    _replace_state(c, row['user_id'], email, stamp)
    return row['user_id']


def _security_notice(c, root, uid, policy, subject, text, recipient=None):
    if not policy_enabled(c, policy):
        return False
    profile, email, _ = _state(c, uid)
    recipient = normalize_email(recipient if recipient is not None else email)
    if not profile or not recipient:
        return False
    name = str(profile['first_name'] or profile['username'])
    _queue(c, root, recipient, subject, text, name=name)
    return True


def email_changed(c, root, uid, old_email, new_email):
    old_email, new_email = normalize_email(old_email), normalize_email(new_email)
    if old_email.casefold() == new_email.casefold():
        return
    reset_email_mfa(c, uid)
    _replace_state(c, uid, new_email)
    destination = old_email or new_email
    _security_notice(c, root, uid, 'notify_email_change', 'ProjektZeit-E-Mail-Adresse geändert',
                     f'Die E-Mail-Adresse deines ProjektZeit-Kontos wurde von „{old_email or "nicht hinterlegt"}“ auf „{new_email or "nicht hinterlegt"}“ geändert. Falls du diese Änderung nicht veranlasst hast, wende dich bitte sofort an einen Administrator.',
                     destination)
    if new_email and policy_enabled(c, 'email_verify_required'):
        request_verification(c, root, uid, force=True)


def two_factor_changed(c, root, uid, enabled, method=''):
    action = 'eingerichtet' if enabled else 'zurückgesetzt'
    detail = (' Als Methode wird ' + ('E-Mail-Code.' if method == 'email' else 'eine Authenticator-App.')
              if enabled and method else '')
    return _security_notice(c, root, uid, 'notify_two_factor_change', f'ProjektZeit-2FA {action}',
                            f'Die Zwei-Faktor-Authentifizierung deines ProjektZeit-Kontos wurde {action}.{detail} '
                            'Falls du das nicht veranlasst hast, ändere dein Passwort und wende dich bitte an einen Administrator.')


def password_changed(c, root, uid):
    return _security_notice(c, root, uid, 'notify_password_change', 'ProjektZeit-Passwort geändert',
                            'Das Passwort deines ProjektZeit-Kontos wurde geändert. Falls du das nicht veranlasst hast, wende dich bitte sofort an einen Administrator.')


def _mask_email(value):
    value = normalize_email(value)
    if not value:
        return ''
    local, domain = value.rsplit('@', 1)
    visible = local[:1]
    return visible + ('*' * max(3, len(local) - 1)) + '@' + domain


def email_mfa_enabled(c, uid):
    row = c.execute('SELECT email,enabled FROM user_email_mfa WHERE user_id=?', (int(uid),)).fetchone()
    profile, email, _ = _state(c, uid)
    return bool(row and row['enabled'] and profile and profile['active'] and email and
                str(row['email']).casefold() == email.casefold())


def email_mfa_available(c, uid):
    profile, email, _ = _state(c, uid)
    return bool(configured(c) and profile and profile['active'] and email)


def _email_code_settings(c):
    values = admin_controls.policy_values(c)
    try:
        length = int(values.get('email_mfa_code_length', 6))
    except (TypeError, ValueError):
        length = 6
    length = max(6, min(12, length))
    kind = values.get('email_mfa_code_kind', 'numeric')
    if kind not in ('numeric', 'alphanumeric'):
        kind = 'numeric'
    return length, kind


def _generate_email_code(c):
    length, kind = _email_code_settings(c)
    alphabet = string.digits if kind == 'numeric' else 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _code_hash(code, salt):
    return hashlib.pbkdf2_hmac('sha256', str(code).encode(), bytes.fromhex(str(salt)), 120000).hex()


def begin_email_mfa(c, root, user, force=False):
    profile, email, _ = _state(c, user['id'])
    if not configured(c):
        raise ValueError('E-Mail ist nicht eingerichtet. Bitte eine Authenticator-App verwenden oder einen Administrator informieren.')
    if not profile or not profile['active'] or not email:
        raise ValueError('Für dieses Benutzerkonto ist keine E-Mail-Adresse hinterlegt. Bitte eine Authenticator-App verwenden.')
    clock = int(time.time())
    recent = c.execute("SELECT * FROM email_mfa_challenges WHERE user_id=? AND used_at='' ORDER BY created_epoch DESC,id DESC LIMIT 1",
                       (user['id'],)).fetchone()
    if recent and int(recent['expires_at']) >= clock and int(recent['created_epoch']) > clock - MFA_RESEND_SECONDS:
        retry_after = MFA_RESEND_SECONDS - (clock - int(recent['created_epoch']))
        return {'mfa_required': True, 'mfa_method': 'email', 'code_sent': True,
                'masked_email': _mask_email(email), 'retry_after': max(1, retry_after)}
    c.execute("UPDATE email_mfa_challenges SET used_at=? WHERE user_id=? AND used_at=''", (now_iso(), user['id']))
    code = _generate_email_code(c)
    salt = secrets.token_bytes(16).hex()
    c.execute('''INSERT INTO email_mfa_challenges(user_id,email,code_hash,salt,expires_at,created_epoch,attempts,used_at)
                 VALUES(?,?,?,?,?,?,0,'')''',
              (user['id'], email, _code_hash(code, salt), salt, clock + MFA_TTL, clock))
    name = str(profile['first_name'] or profile['username'])
    _queue(c, root, email, 'Dein ProjektZeit-Anmeldecode',
           'Mit diesem einmalig verwendbaren Code kannst du deine Anmeldung bestätigen. Der Code ist 10 Minuten gültig.\n\n'
           'Falls du dich nicht angemeldet hast, ändere bitte dein Passwort und informiere einen Administrator.',
           name=name, code=code)
    return {'mfa_required': True, 'mfa_method': 'email', 'code_sent': True,
            'masked_email': _mask_email(email), 'retry_after': MFA_RESEND_SECONDS}


def verify_email_mfa(c, uid, code):
    code = str(code or '').strip().replace(' ', '').upper()
    row = c.execute("SELECT * FROM email_mfa_challenges WHERE user_id=? AND used_at='' ORDER BY created_epoch DESC,id DESC LIMIT 1",
                    (int(uid),)).fetchone()
    clock = int(time.time())
    if not row or int(row['expires_at']) < clock:
        if row:
            c.execute('UPDATE email_mfa_challenges SET used_at=? WHERE id=?', (now_iso(), row['id']))
        raise ValueError('Der E-Mail-Code ist abgelaufen. Bitte einen neuen Code anfordern.')
    if int(row['attempts']) >= MFA_MAX_ATTEMPTS:
        raise ValueError('Zu viele falsche Eingaben. Bitte einen neuen E-Mail-Code anfordern.')
    expected = _code_hash(code, row['salt'])
    if not hmac.compare_digest(expected, str(row['code_hash'])):
        attempts = int(row['attempts']) + 1
        c.execute('UPDATE email_mfa_challenges SET attempts=?,used_at=? WHERE id=?',
                  (attempts, now_iso() if attempts >= MFA_MAX_ATTEMPTS else '', row['id']))
        if attempts >= MFA_MAX_ATTEMPTS:
            raise ValueError('Zu viele falsche Eingaben. Bitte einen neuen E-Mail-Code anfordern.')
        raise ValueError('Der E-Mail-Code ist falsch.')
    stamp = now_iso()
    changed = c.execute("UPDATE email_mfa_challenges SET used_at=? WHERE id=? AND used_at=''", (stamp, row['id']))
    if changed.rowcount != 1:
        raise ValueError('Der E-Mail-Code wurde bereits verwendet.')
    profile, email, _ = _state(c, uid)
    if not profile or not email or email.casefold() != str(row['email']).casefold():
        raise ValueError('Die E-Mail-Adresse wurde inzwischen geändert. Bitte neu anmelden.')
    was_enabled = email_mfa_enabled(c, uid)
    c.execute('DELETE FROM user_email_mfa WHERE user_id=?', (int(uid),))
    c.execute('INSERT INTO user_email_mfa(user_id,email,enabled,created_at) VALUES(?,?,1,?)',
              (int(uid), email, stamp))
    c.execute('DELETE FROM user_mfa WHERE user_id=?', (int(uid),))
    _replace_state(c, uid, email, stamp)
    return not was_enabled


def reset_email_mfa(c, uid):
    c.execute('DELETE FROM user_email_mfa WHERE user_id=?', (int(uid),))
    c.execute('DELETE FROM email_mfa_challenges WHERE user_id=?', (int(uid),))


def mfa_context(c, uid):
    user = c.execute('SELECT * FROM users WHERE id=?', (int(uid),)).fetchone()
    totp = c.execute('SELECT enabled FROM user_mfa WHERE user_id=?', (int(uid),)).fetchone()
    method = 'email' if email_mfa_enabled(c, uid) else ('totp' if totp and totp['enabled'] else '')
    profile, email, verified = _state(c, uid)
    import auth_mfa
    return {'method': method, 'required': bool(user and auth_mfa.required(c, dict(user))),
            'email_available': email_mfa_available(c, uid), 'email_configured': configured(c),
            'email': _mask_email(email), 'email_verified': verified}


def _require_current_password(c, uid, password, verify_password):
    user = c.execute('SELECT * FROM users WHERE id=? AND active=1', (int(uid),)).fetchone()
    if not user or not verify_password(str(password or ''), user['password_salt'], user['password_hash']):
        raise ValueError('Das aktuelle Passwort ist falsch.')
    return dict(user)


def _end_sessions(c, uid, keep_hash=''):
    suffix = ' AND token_hash<>?' if keep_hash else ''
    args = (int(uid), keep_hash) if keep_hash else (int(uid),)
    stamp = now_iso()
    for sql, params in (
        ("UPDATE session_activity SET ended_at=?,end_reason='Passwort geändert' WHERE user_id=? AND ended_at=''" + (" AND token_hash<>?" if keep_hash else ''), (stamp, *args)),
        ('DELETE FROM session_mfa WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=?' + suffix + ')', args),
        ('DELETE FROM native_sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=?' + suffix + ')', args),
        ('DELETE FROM sessions WHERE user_id=?' + suffix, args),
        ("UPDATE api_tokens SET revoked_at=? WHERE owner_id=? AND revoked_at=''", (stamp, int(uid))),
    ):
        try: c.execute(sql, params)
        except Exception: pass


def change_password(c, root, uid, current_password, new_password, confirmation, hash_password, verify_password, keep_hash=''):
    row = c.execute('SELECT * FROM users WHERE id=? AND active=1', (int(uid),)).fetchone()
    if not row or not verify_password(str(current_password or ''), row['password_salt'], row['password_hash']):
        raise ValueError('Das aktuelle Passwort ist falsch.')
    if str(new_password or '') != str(confirmation or ''):
        raise ValueError('Die neuen Passwörter stimmen nicht überein.')
    admin_controls.validate_password(c, new_password)
    if verify_password(str(new_password), row['password_salt'], row['password_hash']):
        raise ValueError('Das neue Passwort muss sich vom bisherigen Passwort unterscheiden.')
    salt, digest = hash_password(str(new_password))
    c.execute('UPDATE users SET password_salt=?,password_hash=? WHERE id=?', (salt, digest, uid))
    c.execute('DELETE FROM user_security_state WHERE user_id=?', (int(uid),))
    c.execute('INSERT INTO user_security_state(user_id,must_change_password) VALUES(?,0)', (int(uid),))
    _end_sessions(c, uid, keep_hash)
    password_changed(c, root, uid)


def reset_password(c, root, token, new_password, confirmation, hash_password):
    digest = hashlib.sha256(str(token or '').encode()).hexdigest()
    row = c.execute("SELECT * FROM email_action_tokens WHERE token_hash=? AND purpose='password_reset'", (digest,)).fetchone()
    if not row or row['used_at'] or int(row['expires_at']) < int(time.time()):
        raise ValueError('Der Link zum Zurücksetzen ist ungültig oder abgelaufen.')
    profile, email, _ = _state(c, row['user_id'])
    if not profile or not profile['active'] or not email or email.casefold() != str(row['email']).casefold():
        raise ValueError('Der Link zum Zurücksetzen ist nicht mehr gültig.')
    if str(new_password or '') != str(confirmation or ''):
        raise ValueError('Die neuen Passwörter stimmen nicht überein.')
    admin_controls.validate_password(c, new_password)
    salt, password_hash = hash_password(str(new_password))
    stamp = now_iso()
    changed = c.execute("UPDATE email_action_tokens SET used_at=? WHERE token_hash=? AND used_at=''", (stamp, digest))
    if changed.rowcount != 1:
        raise ValueError('Der Link wurde bereits verwendet.')
    c.execute('UPDATE users SET password_salt=?,password_hash=? WHERE id=?', (salt, password_hash, row['user_id']))
    c.execute("UPDATE email_action_tokens SET used_at=? WHERE user_id=? AND used_at=''", (stamp, row['user_id']))
    _replace_state(c, row['user_id'], email, stamp)
    _end_sessions(c, row['user_id'])
    password_changed(c, root, row['user_id'])
    return row['user_id']


def deliver_outbox(app, limit=20):
    delivered = 0
    for _ in range(max(1, min(int(limit), 100))):
        with app.db() as c:
            row = c.execute("SELECT * FROM email_outbox WHERE status='queued' AND next_attempt_at<=? ORDER BY id LIMIT 1", (int(time.time()),)).fetchone()
            if not row:
                break
            c.execute("UPDATE email_outbox SET status='sending' WHERE id=? AND status='queued'", (row['id'],))
            try:
                settings, password = admin_controls._smtp_credentials(c, app.DATA_DIR)
                settings = dict(settings)
                decrypted = integrations.cipher(app.DATA_DIR).decrypt(row['body_secret'].encode()).decode()
                try:
                    content = json.loads(decrypted)
                    if not isinstance(content, dict): raise ValueError()
                except (ValueError, TypeError, json.JSONDecodeError):
                    content = {'text': decrypted, 'html': ''}
            except Exception as error:
                c.execute("UPDATE email_outbox SET status='queued',attempts=attempts+1,next_attempt_at=?,last_error=? WHERE id=?",
                          (int(time.time()) + 300, str(error)[:500], row['id']))
                break
        try:
            logo_path = Path(__file__).with_name('static') / 'projektzeit-logo.png'
            logo = logo_path.read_bytes() if logo_path.is_file() else b''
            smtp_service.send(settings, password, row['recipient'], row['subject'], content.get('text', ''),
                              html_body=content.get('html', ''), inline_logo=logo)
        except Exception as error:
            with app.db() as c:
                attempts = int(row['attempts']) + 1
                status = 'failed' if attempts >= 5 else 'queued'
                c.execute('UPDATE email_outbox SET status=?,attempts=?,next_attempt_at=?,last_error=? WHERE id=?',
                          (status, attempts, int(time.time()) + min(3600, 60 * (2 ** attempts)), str(error)[:500], row['id']))
        else:
            with app.db() as c:
                c.execute("UPDATE email_outbox SET status='sent',sent_at=?,last_error='' WHERE id=?", (now_iso(), row['id']))
            delivered += 1
    return delivered


def _worker(app):
    while True:
        _WAKE.wait(60)
        _WAKE.clear()
        time.sleep(0.1)
        try: deliver_outbox(app)
        except Exception: pass


def start_worker(app):
    global _WORKER_STARTED
    if os.environ.get('PZ_DISABLE_EMAIL_WORKER') == '1':
        return
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        thread = threading.Thread(target=_worker, args=(app,), name='pz-email-outbox', daemon=True)
        thread.start()
        _WORKER_STARTED = True
        _WAKE.set()


def install(app):
    global _APP, _INSTALLED
    if _INSTALLED:
        return
    _APP = app
    _INSTALLED = True
    previous_init = app.init_db
    def init_db(create_admin=True):
        previous_init(create_admin)
        with app.db() as c: migrate(c)
        start_worker(app)
    app.init_db = init_db

    original_context = admin_controls.admin_context
    def admin_context(c, uid):
        result = original_context(c, uid)
        result['email_configured'] = configured(c)
        result['email_link_features_configured'] = link_features_configured(c)
        return result
    admin_controls.admin_context = admin_context

    original_create = admin_controls.create_user
    def create_user(c, actor, body, hash_password):
        values = dict(body)
        required = policy_enabled(c, 'email_verify_required')
        values['email'] = ensure_email_available(c, normalize_email(values.get('email'), required=required))
        uid = original_create(c, actor, values, hash_password)
        _replace_state(c, uid, values['email'])
        if required: request_verification(c, app.DATA_DIR, uid, force=True)
        return uid
    admin_controls.create_user = create_user

    import system_features
    original_self_profile = system_features.save_self_profile
    def save_self_profile(c, uid, values):
        before = system_features.self_profile(c, uid)
        prepared = dict(values)
        required = policy_enabled(c, 'email_verify_required')
        prepared['email'] = ensure_email_available(c, normalize_email(prepared.get('email'), required=required), uid)
        result = original_self_profile(c, uid, prepared)
        email_changed(c, app.DATA_DIR, uid, before.get('email', ''), result.get('email', ''))
        return result
    system_features.save_self_profile = save_self_profile

    original_admin_profile = admin_controls.update_user_profile
    def update_user_profile(c, actor_uid, body):
        target = int(body.get('user_id') or 0)
        before = _profile(c, target)
        prepared = dict(body)
        required = policy_enabled(c, 'email_verify_required')
        prepared['email'] = ensure_email_available(c, normalize_email(prepared.get('email'), required=required), target)
        result = original_admin_profile(c, actor_uid, prepared)
        after = _profile(c, target)
        email_changed(c, app.DATA_DIR, target, before['email'] if before else '', after['email'] if after else '')
        return result
    admin_controls.update_user_profile = update_user_profile

    import auth_mfa
    original_verify = auth_mfa.verify
    def verify_mfa(c, uid, code, root, enroll=False, clock=None):
        before = c.execute('SELECT enabled FROM user_mfa WHERE user_id=?', (uid,)).fetchone()
        result = original_verify(c, uid, code, root, enroll=enroll, clock=clock)
        after = c.execute('SELECT enabled FROM user_mfa WHERE user_id=?', (uid,)).fetchone()
        if not (before and before['enabled']) and after and after['enabled']:
            reset_email_mfa(c, uid)
            two_factor_changed(c, root, uid, True, 'totp')
        return result
    auth_mfa.verify = verify_mfa

    original_mfa_login = auth_mfa.login
    def login_mfa(c, user, body, root):
        email_enabled = email_mfa_enabled(c, user['id'])
        totp = c.execute('SELECT enabled FROM user_mfa WHERE user_id=?', (user['id'],)).fetchone()
        totp_enabled = bool(totp and totp['enabled'])
        if email_enabled:
            if body.get('otp'):
                verify_email_mfa(c, user['id'], body.get('otp'))
                return {'_mfa_verified': True, 'mfa_method': 'email'}
            return begin_email_mfa(c, root, user, force=bool(body.get('resend_mfa')))
        if totp_enabled:
            result = original_mfa_login(c, user, body, root)
            if result.get('mfa_required'): result['mfa_method'] = 'totp'
            return result
        mandatory = auth_mfa.required(c, user)
        requested = str(body.get('mfa_method') or '').strip().lower()
        if not requested and body.get('enroll_2fa'):
            requested = 'totp'
        if not requested and body.get('enroll_email_2fa'):
            requested = 'email'
        if not mandatory and not requested:
            return {}
        available = email_mfa_available(c, user['id'])
        if not requested:
            return {'mfa_required': True, 'enrollment_required': True, 'method_selection': True,
                    'email_available': available,
                    'email_unavailable_reason': '' if available else ('E-Mail ist nicht eingerichtet.' if not configured(c)
                                                                      else 'Für dein Konto ist keine E-Mail-Adresse hinterlegt.')}
        if requested == 'email':
            if not available:
                raise ValueError('E-Mail-Code ist für dieses Konto nicht verfügbar. Bitte eine Authenticator-App verwenden.')
            if body.get('otp'):
                newly_enabled = verify_email_mfa(c, user['id'], body.get('otp'))
                if newly_enabled: two_factor_changed(c, root, user['id'], True, 'email')
                return {'_mfa_verified': True, 'mfa_method': 'email'}
            return {**begin_email_mfa(c, root, user, force=bool(body.get('resend_mfa'))),
                    'enrollment_required': True}
        if requested != 'totp':
            raise ValueError('Bitte eine gültige 2FA-Methode auswählen.')
        prepared = dict(body)
        prepared['enroll_2fa'] = True
        result = original_mfa_login(c, user, prepared, root)
        if result.get('mfa_required'): result['mfa_method'] = 'totp'
        return result
    auth_mfa.login = login_mfa

    original_session_allowed = auth_mfa.session_allowed
    def session_allowed(c, user, token_hash):
        if email_mfa_enabled(c, user['id']):
            return bool(c.execute('SELECT 1 FROM session_mfa WHERE token_hash=?', (token_hash,)).fetchone())
        return original_session_allowed(c, user, token_hash)
    auth_mfa.session_allowed = session_allowed

    previous_session = app.App.current_session
    def current_session(self):
        session = previous_session(self)
        if not session:
            return session
        with app.db(read_only=True) as c:
            if policy_enabled(c, 'email_verify_required') and not email_verified(c, session['id']):
                return None
            security = c.execute('SELECT must_change_password FROM user_security_state WHERE user_id=?', (session['id'],)).fetchone()
        return {**session, 'must_change_password': bool(security and security['must_change_password'])}
    app.App.current_session = current_session

    previous_require = app.App.require
    def require(self, csrf=False, admin=False):
        session = previous_require(self, csrf=csrf, admin=admin)
        if not session:
            return None
        path = urlsplit(self.path).path
        if session.get('must_change_password') and path not in ('/api/v1/me', '/api/v1/account/password', '/api/v1/logout'):
            self.send_json(403, {'error': 'Bitte zuerst das vorläufige Passwort ändern.', 'password_change_required': True})
            return None
        return session
    app.App.require = require

    previous_login = app.App.login
    def login(self, body, native=False):
        username = str(body.get('username') or '').strip()
        candidate = None
        with app.db(read_only=True) as c:
            row = c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            if row and row['active'] and policy_enabled(c, 'email_verify_required') and not email_verified(c, row['id']):
                candidate = dict(row)
        if candidate and app.verify_password(str(body.get('password') or ''), candidate['password_salt'], candidate['password_hash']):
            try:
                with app.db() as c: request_verification(c, app.DATA_DIR, candidate['id'])
            except ValueError as error:
                return self.send_json(403, {'error': str(error), 'email_verification_required': True})
            return self.send_json(403, {'error': 'E-Mail-Adresse noch nicht bestätigt. Ein Bestätigungslink wurde versendet.', 'email_verification_required': True})
        return previous_login(self, body, native=native)
    app.App.login = login

    previous_post = app.App.do_POST
    previous_get = app.App.do_GET
    public_paths = {
        '/api/v1/auth/email/options', '/api/v1/auth/password-reset/request',
        '/api/v1/auth/password-reset/complete', '/api/v1/auth/email-verification/complete',
    }
    def do_POST(self):
        path = urlsplit(self.path).path
        account_paths = {'/api/v1/account/password', '/api/v1/account/mfa/context',
                         '/api/v1/account/mfa/begin', '/api/v1/account/mfa/complete'}
        if path not in public_paths and path not in account_paths:
            return previous_post(self)
        try:
            body = self.json_body()
            if not isinstance(body, dict): raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:
            return self.send_json(400, {'error': str(error)})
        try:
            if path == '/api/v1/auth/email/options':
                with app.db(read_only=True) as c:
                    return self.send_json(200, {'email_configured': configured(c),
                                                'password_reset_available': link_features_configured(c) and policy_enabled(c, 'email_password_reset_allowed'),
                                                'remember_login_allowed': bool(admin_controls.setting(c, 'policy.remember_login_allowed', True))})
            if path == '/api/v1/auth/password-reset/request':
                with app.db() as c:
                    if not configured(c): raise ValueError('E-Mail nicht eingerichtet.')
                    if not link_features_configured(c): raise ValueError('Die öffentliche ProjektZeit-Adresse ist nicht eingerichtet.')
                    if not policy_enabled(c, 'email_password_reset_allowed'): raise ValueError('Passwort-Reset per E-Mail ist deaktiviert.')
                    request_password_reset(c, app.DATA_DIR, body.get('email'), str(self.client_address[0]))
                return self.send_json(200, {'ok': True, 'message': 'Falls die Adresse zu einem aktiven Konto gehört, wurde ein Link versendet.'})
            if path == '/api/v1/auth/password-reset/complete':
                with app.db() as c: reset_password(c, app.DATA_DIR, body.get('token'), body.get('password'), body.get('confirmation'), app.hash_password)
                return self.send_json(200, {'ok': True})
            if path == '/api/v1/auth/email-verification/complete':
                with app.db() as c: consume_verification(c, body.get('token'))
                return self.send_json(200, {'ok': True})
            session = self.require(csrf=True)
            if not session: return
            with app.db() as c:
                if path == '/api/v1/account/mfa/context':
                    return self.send_json(200, mfa_context(c, session['id']))
                if path == '/api/v1/account/mfa/begin':
                    user = _require_current_password(c, session['id'], body.get('current_password'), app.verify_password)
                    method = str(body.get('method') or '')
                    if method == 'email':
                        return self.send_json(200, begin_email_mfa(c, app.DATA_DIR, user, force=True))
                    if method != 'totp': raise ValueError('Bitte eine gültige 2FA-Methode auswählen.')
                    import auth_mfa
                    return self.send_json(200, {'mfa_method': 'totp', **auth_mfa.begin(c, user, app.DATA_DIR)})
                if path == '/api/v1/account/mfa/complete':
                    _require_current_password(c, session['id'], body.get('current_password'), app.verify_password)
                    method = str(body.get('method') or '')
                    result = {}
                    if method == 'email':
                        changed = verify_email_mfa(c, session['id'], body.get('otp'))
                        if changed: two_factor_changed(c, app.DATA_DIR, session['id'], True, 'email')
                    elif method == 'totp':
                        import auth_mfa
                        result = auth_mfa.verify(c, session['id'], body.get('otp'), app.DATA_DIR, enroll=True)
                    else: raise ValueError('Bitte eine gültige 2FA-Methode auswählen.')
                    return self.send_json(200, {'ok': True, **mfa_context(c, session['id']), **result})
                change_password(c, app.DATA_DIR, session['id'], body.get('current_password'), body.get('password'),
                                body.get('confirmation'), app.hash_password, app.verify_password, session['token_hash'])
            return self.send_json(200, {'ok': True})
        except ValueError as error:
            return self.send_json(400, {'error': str(error)})
    app.App.do_POST = do_POST

    def do_GET(self):
        if urlsplit(self.path).path == '/api/v1/me':
            session = self.require()
            if not session: return
            return self.send_json(200, {'user': {'id': session['id'], 'username': session['username'], 'role': session['role'],
                                                 'password_change_required': bool(session.get('must_change_password'))},
                                        'csrf': session['csrf']})
        return previous_get(self)
    app.App.do_GET = do_GET
