"""TOTP enrollment, single-use recovery codes, and verified session markers."""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote, urlencode
import admin_controls as acl
import integrations


def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS user_mfa(
        user_id INTEGER PRIMARY KEY, secret LONGTEXT NOT NULL, pending_secret LONGTEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 0, last_counter BIGINT NOT NULL DEFAULT -1,
        recovery_json LONGTEXT NOT NULL, pending_until BIGINT NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS session_mfa(token_hash VARCHAR(64) PRIMARY KEY);''')
    c.execute('DELETE FROM session_mfa WHERE token_hash NOT IN (SELECT token_hash FROM sessions)')


def totp(secret, counter):
    digest = hmac.new(base64.b32decode(secret), struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((struct.unpack('>I', digest[offset:offset+4])[0] & 0x7fffffff) % 1000000).zfill(6)


def required(c, user, clock=None):
    policy = acl.policy_values(c)
    mode = policy.get('two_factor_mode', 'optional')
    if mode == 'required':
        return True
    if mode != 'roles':
        return False
    required_roles = {str(value) for value in policy.get('two_factor_required_roles', [])}
    if not required_roles:
        return False
    assigned = {str(row['role_key']) for row in c.execute(
        '''SELECT d.role_key FROM role_definitions d
           JOIN user_role_links l ON l.role_id=d.id WHERE l.user_id=?''', (user['id'],)
    )}
    return bool(required_roles & assigned)


def begin(c, user, root):
    row = c.execute('SELECT * FROM user_mfa WHERE user_id=?', (user['id'],)).fetchone()
    if row and row['enabled']:
        raise ValueError('2FA ist bereits eingerichtet.')
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    encrypted = integrations.cipher(root).encrypt(secret.encode()).decode()
    expiry = int(time.time()) + 600
    if row:
        c.execute('UPDATE user_mfa SET pending_secret=?,pending_until=? WHERE user_id=?', (encrypted, expiry, user['id']))
    else:
        c.execute("INSERT INTO user_mfa(user_id,secret,pending_secret,recovery_json,pending_until) VALUES(?,'',?,'[]',?)", (user['id'], encrypted, expiry))
    return {'secret': secret, 'uri': 'otpauth://totp/' + quote('ProjektZeit:' + user['username'], safe='') + '?' + urlencode({'secret': secret, 'issuer': 'ProjektZeit', 'algorithm': 'SHA1', 'digits': 6, 'period': 30})}


def verify(c, uid, code, root, enroll=False, clock=None):
    row = c.execute('SELECT * FROM user_mfa WHERE user_id=?', (uid,)).fetchone()
    if not row:
        raise ValueError('2FA bitte zuerst einrichten.')
    clock = int(time.time() if clock is None else clock)
    if enroll and row['pending_until'] < clock:
        raise ValueError('Einrichtung abgelaufen. Anmeldung erneut beginnen.')
    encrypted = row['pending_secret'] if enroll else row['secret']
    if not encrypted:
        raise ValueError('2FA-Einrichtung fehlt.')
    secret = integrations.cipher(root).decrypt(encrypted.encode()).decode()
    code = str(code or '').strip().replace(' ', '')
    counter = clock // 30
    match = next((n for n in (counter-1, counter, counter+1) if n >= 0 and n > row['last_counter'] and hmac.compare_digest(totp(secret, n), code)), None)
    recovery = json.loads(row['recovery_json'])
    hashed = hashlib.sha256(code.encode()).hexdigest()
    if match is None and not enroll and hashed in recovery:
        recovery.remove(hashed)
        changed=c.execute('UPDATE user_mfa SET recovery_json=? WHERE user_id=? AND recovery_json=?', (json.dumps(recovery), uid, row['recovery_json']))
        if changed.rowcount!=1:raise ValueError('Wiederherstellungscode bereits verwendet.')
        return {}
    if match is None:
        raise ValueError('2FA-Code ungültig oder bereits verwendet. Bitte den nächsten aktuellen Code eingeben.')
    if enroll:
        codes = [secrets.token_hex(6) for _ in range(8)]
        changed=c.execute("UPDATE user_mfa SET secret=pending_secret,pending_secret='',enabled=1,last_counter=?,recovery_json=?,pending_until=0 WHERE user_id=? AND enabled=0 AND pending_secret=?", (match, json.dumps([hashlib.sha256(x.encode()).hexdigest() for x in codes]), uid, encrypted))
        if changed.rowcount!=1:raise ValueError('2FA-Einrichtung wurde inzwischen geändert. Bitte erneut anmelden.')
        return {'recovery_codes': codes}
    changed=c.execute('UPDATE user_mfa SET last_counter=? WHERE user_id=? AND last_counter<?', (match, uid, match))
    if changed.rowcount!=1:raise ValueError('2FA-Code bereits verwendet.')
    return {}


def login(c, user, body, root):
    row = c.execute('SELECT enabled FROM user_mfa WHERE user_id=?', (user['id'],)).fetchone()
    enabled = bool(row and row['enabled'])
    if not enabled and not required(c, user) and not body.get('enroll_2fa'):
        return {}
    if body.get('otp'):
        return {**verify(c, user['id'], body['otp'], root, enroll=not enabled), '_mfa_verified': True}
    if enabled:
        return {'mfa_required': True}
    return {'mfa_required': True, 'enrollment_required': True, **begin(c, user, root)}


def session_allowed(c, user, token_hash):
    row = c.execute('SELECT enabled FROM user_mfa WHERE user_id=?', (user['id'],)).fetchone()
    if not (row and row['enabled']) and not required(c, user):
        return True
    return bool(c.execute('SELECT 1 FROM session_mfa WHERE token_hash=?', (token_hash,)).fetchone())
