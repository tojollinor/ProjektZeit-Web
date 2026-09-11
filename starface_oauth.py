"""Server-side Authorization Code + PKCE. No provider tokens reach JavaScript."""
import base64
import hashlib
import json
import os
import secrets
import ssl
import time
from urllib.parse import urlsplit, urlencode, urljoin
from cryptography.fernet import InvalidToken
import integrations

CALLBACK = '/api/v1/integrations/starface/callback'
CLIENT_ID = 'rest-client'


def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS oauth_states (
        state_hash VARCHAR(64) PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
        session_hash VARCHAR(64) NOT NULL, secret TEXT NOT NULL, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS oauth_tokens (
        owner_id INTEGER PRIMARY KEY REFERENCES users(id), secret TEXT NOT NULL);'''.replace('owner_id INTEGER PRIMARY KEY REFERENCES', 'owner_id INT PRIMARY KEY REFERENCES'))


def public_url():
    value = os.environ.get('APP_PUBLIC_URL', '').strip().rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path
            or any(ord(ch) < 33 for ch in value)):
        raise ValueError('APP_PUBLIC_URL als vollständige Website-Adresse ohne Unterpfad setzen.')
    return value


def callback_url():
    return public_url() + CALLBACK


def endpoint(value, origin):
    parsed = urlsplit(value)
    allowed = {origin}
    allowed.update(x.strip().rstrip('/') for x in os.environ.get('STARFACE_OAUTH_ALLOWED_ORIGINS', '').split(',') if x.strip())
    target_origin = f'{parsed.scheme}://{parsed.netloc}'
    if (parsed.scheme != 'https' or target_origin not in allowed or parsed.username
            or parsed.password or parsed.fragment or any(ord(ch) < 33 for ch in value)):
        raise ValueError('OAuth-Endpunkt liegt außerhalb der freigegebenen HTTPS-Domain. STARFACE_OAUTH_ALLOWED_ORIGINS prüfen.')
    return target_origin, parsed.path + ('?' + parsed.query if parsed.query else '')


def _oauth_error(payload, body):
    if not isinstance(payload, dict):
        return ''
    values = []
    for key in ('error', 'error_description'):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        text = ' '.join(value.split())
        for secret in body.values():
            if isinstance(secret, str) and len(secret) >= 8:
                text = text.replace(secret, '[ausgeblendet]')
        values.append(text[:300])
    return ' – '.join(values)


def _safe_methods(value):
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, str) and 0 < len(x) <= 80 and all(32 < ord(c) < 127 for c in x)][:12]


def _validate_discovery(metadata):
    methods = _safe_methods(metadata.get('token_endpoint_auth_methods_supported'))
    if methods and 'none' not in methods:
        raise ValueError('STARFACE Discovery meldet keinen Public-Client-Modus für den Token-Endpunkt. '
                         'token_endpoint_auth_methods_supported=' + ', '.join(methods))
    challenges = _safe_methods(metadata.get('code_challenge_methods_supported'))
    if challenges and 'S256' not in challenges:
        raise ValueError('STARFACE Discovery meldet keine Unterstützung für PKCE S256. '
                         'code_challenge_methods_supported=' + ', '.join(challenges))
    return methods


def _invalid_client_hint(error, config):
    text = str(error)
    if 'invalid_client' not in text.lower():
        return error
    methods = config.get('token_auth_methods') or []
    discovery = ','.join(methods) if methods else 'nicht gemeldet'
    return ValueError(text + ' Verwendet wurden client_id=rest-client, Client-Authentifizierung=none, '
                      'redirect_uri=' + config['redirect_uri'] + '; Discovery auth methods=' + discovery + '.')


def _post_token(url, origin, body):
    target, path = endpoint(url, origin)
    parsed = urlsplit(target)
    conn = integrations.Connection(parsed.hostname, parsed.port or 443, timeout=8, context=ssl.create_default_context())
    encoded = urlencode(body).encode()
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'ProjektZeit/0.7.0',
    }
    try:
        conn.request('POST', path, body=encoded, headers=headers)
        response = conn.getresponse()
        raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError('STARFACE OAuth-Antwort ist größer als 256 KB.')
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            payload = None
        if not 200 <= response.status < 300:
            detail = _oauth_error(payload, body)
            suffix = ': ' + detail if detail else ''
            raise ValueError('STARFACE OAuth-Anfrage fehlgeschlagen (HTTP %s%s). Erneut anmelden oder Client-Konfiguration prüfen.' % (response.status, suffix))
        if not isinstance(payload, dict):
            raise ValueError('STARFACE OAuth-Antwort ist kein gültiges JSON-Objekt.')
        return payload
    finally:
        conn.close()


def request_url(url, origin, body=None):
    if body is not None:
        return _post_token(url, origin, body)
    for _ in range(4):
        target, path = endpoint(url, origin)
        client = integrations.Client(target)
        status, payload, _ = client.request(path, allow_discovery_redirect=True)
        if 300 <= status < 400:
            location = payload.get('redirect') if isinstance(payload, dict) else None
            if not location:
                raise ValueError('STARFACE-Discovery lieferte eine Weiterleitung ohne Ziel.')
            url = urljoin(url, location)
            endpoint(url, origin)
            continue
        if not 200 <= status < 300 or not isinstance(payload, dict):
            raise ValueError('STARFACE OAuth-Anfrage fehlgeschlagen (HTTP %s). Erneut anmelden oder Client-Konfiguration prüfen.' % status)
        return payload
    raise ValueError('Zu viele STARFACE-Discovery-Weiterleitungen.')


def pack(data, directory):
    return integrations.cipher(directory).encrypt(json.dumps(data).encode()).decode()


def unpack(value, directory):
    try:
        return json.loads(integrations.cipher(directory).decrypt(value.encode()))
    except (InvalidToken, ValueError):
        raise ValueError('OAuth-Daten konnten nicht gelesen werden. Bitte neu verknüpfen.') from None


def local_callback(value):
    parsed = urlsplit(str(value))
    try:
        valid = (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                 and parsed.port and 1024 <= parsed.port <= 65535
                 and parsed.path in ('', '/') and not parsed.query and not parsed.fragment
                 and not parsed.username and not parsed.password)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Lokale Rücksprungadresse muss http://127.0.0.1:PORT ohne Unterpfad sein.')
    return 'http://127.0.0.1:%s' % parsed.port


def start(db, session, body, directory):
    redirect = local_callback(body.get('redirect_uri')) if session.get('bearer') else callback_url()
    origin = integrations.domain(body.get('domain'), 'starface')
    metadata = request_url(origin + '/.well-known/openid-configuration', origin)
    authorization, token = metadata.get('authorization_endpoint', ''), metadata.get('token_endpoint', '')
    endpoint(authorization, origin)
    endpoint(token, origin)
    token_auth_methods = _validate_discovery(metadata)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    state = secrets.token_urlsafe(32)
    config = dict(origin=origin, token_endpoint=token, verifier=verifier, client_id=CLIENT_ID,
                  redirect_uri=redirect, token_auth_methods=token_auth_methods)
    with db() as c:
        c.execute('DELETE FROM oauth_states WHERE expires_at<? OR owner_id=?', (int(time.time()), session['id']))
        c.execute('INSERT INTO oauth_states VALUES(?,?,?,?,?)',
                  (hashlib.sha256(state.encode()).hexdigest(), session['id'], session['token_hash'], pack(config, directory), int(time.time()) + 600))
    query = urlencode(dict(response_type='code', client_id=CLIENT_ID, redirect_uri=redirect,
                           scope='pbx-login', state=state, code_challenge=challenge, code_challenge_method='S256'))
    return {'url': authorization + ('&' if '?' in authorization else '?') + query}


def token_data(payload, config, previous=None):
    access = payload.get('access_token')
    if not isinstance(access, str) or not access or any(ord(ch) < 33 for ch in access):
        raise ValueError('STARFACE lieferte keinen gültigen OAuth Access-Token.')
    if payload.get('token_type', '').lower() != 'bearer':
        raise ValueError('STARFACE lieferte keinen Bearer-Token.')
    try:
        lifetime = int(payload['expires_in'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('STARFACE lieferte keine gültige Token-Laufzeit.') from None
    if lifetime <= 0:
        raise ValueError('Der STARFACE-Token ist bereits abgelaufen.')
    saved = {k: config[k] for k in ('origin', 'token_endpoint', 'client_id', 'redirect_uri')}
    saved['token_auth_methods'] = config.get('token_auth_methods', [])
    return saved | dict(access_token=access,
        refresh_token=payload.get('refresh_token') or (previous or {}).get('refresh_token'),
        expires_at=time.time() + lifetime)


def finish(db, session, query, directory):
    state = query.get('state', [''])[0]
    if not state or len(state) > 200:
        raise ValueError('Ungültiger OAuth-Vorgang. Bitte erneut anmelden.')
    with db() as c:
        row = c.execute('SELECT * FROM oauth_states WHERE state_hash=?', (hashlib.sha256(state.encode()).hexdigest(),)).fetchone()
        if not row or row['owner_id'] != session['id'] or row['session_hash'] != session['token_hash'] or row['expires_at'] < time.time():
            raise ValueError('OAuth-Anmeldung abgelaufen oder gehört zu einer anderen Sitzung.')
        c.execute('DELETE FROM oauth_states WHERE state_hash=?', (row['state_hash'],))
        config = unpack(row['secret'], directory)
    if 'error' in query:
        raise ValueError('STARFACE-Anmeldung wurde abgebrochen oder abgelehnt.')
    code = query.get('code', [''])[0]
    if not code or len(code) > 8192:
        raise ValueError('STARFACE lieferte keinen gültigen Anmeldecode.')
    body = dict(grant_type='authorization_code', code=code, code_verifier=config['verifier'],
                client_id=CLIENT_ID, redirect_uri=config['redirect_uri'])
    try:
        payload = request_url(config['token_endpoint'], config['origin'], body)
    except ValueError as error:
        raise _invalid_client_hint(error, config) from None
    data = token_data(payload, config)
    with db() as c:
        if not c.execute('SELECT 1 FROM sessions WHERE token_hash=? AND expires_at>?', (session['token_hash'], int(time.time()))).fetchone():
            raise ValueError('ProjektZeit-Sitzung abgelaufen. Bitte erneut anmelden.')
        c.execute('DELETE FROM oauth_tokens WHERE owner_id=?', (session['id'],))
        c.execute('INSERT INTO oauth_tokens VALUES(?,?)', (session['id'], pack(data, directory)))
        integrations.store(c, session['id'], 'starface', config['origin'], '', '')


def access(c, uid, directory):
    row = c.execute('SELECT * FROM oauth_tokens WHERE owner_id=?', (uid,)).fetchone()
    if not row:
        raise ValueError('Bitte zuerst „Mit STARFACE anmelden“ verwenden.')
    data = unpack(row['secret'], directory)
    if data['expires_at'] <= time.time() + 30:
        if not data.get('refresh_token'):
            raise ValueError('STARFACE-Anmeldung abgelaufen. Bitte neu anmelden.')
        body = dict(grant_type='refresh_token', refresh_token=data['refresh_token'], client_id=CLIENT_ID)
        try:
            payload = request_url(data['token_endpoint'], data['origin'], body)
        except ValueError as error:
            raise _invalid_client_hint(error, data) from None
        data = token_data(payload, data, data)
        c.execute('UPDATE oauth_tokens SET secret=? WHERE owner_id=?', (pack(data, directory), uid))
    return dict(provider='starface', domain=data['origin'], username='', secret=data['access_token'], oauth=True)
