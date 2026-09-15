"""Release 0.8.0 backend: account lifecycle and browser-based desktop login."""
import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import admin_controls
import system_features


CLIENT_ID = 'projektzeit-windows'
PKCE_PATTERN = re.compile(r'^[A-Za-z0-9._~-]{43,128}$')


def _bootstrap_name():
    return os.environ.get('ADMIN_USER', 'admin').strip().casefold()


def _table_exists(c, name):
    if getattr(c, 'dialect', '') == 'mariadb':
        return bool(c.execute('SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=?', (name,)).fetchone())
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS user_deletions (
      user_id INTEGER PRIMARY KEY REFERENCES users(id), deleted_by INTEGER REFERENCES users(id),
      deleted_at VARCHAR(40) NOT NULL, self_service INTEGER NOT NULL,
      previous_username_hash VARCHAR(64) NOT NULL
    );
    CREATE TABLE IF NOT EXISTS client_authorization_codes (
      code_hash VARCHAR(64) PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      client_id VARCHAR(80) NOT NULL, client_name VARCHAR(120) NOT NULL,
      redirect_uri VARCHAR(255) NOT NULL, code_challenge VARCHAR(128) NOT NULL,
      expires_at BIGINT NOT NULL, used_at VARCHAR(40) NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_client_auth_expiry ON client_authorization_codes(expires_at);
    ''')
    c.execute('DELETE FROM client_authorization_codes WHERE expires_at<? OR used_at<>?', (int(time.time())-300, ''))


def _loopback_redirect(value):
    value = str(value or '').strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError('Ungültige Rückleitungsadresse.') from None
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1') or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path != '/callback' or port is None or not 1024 <= port <= 65535):
        raise ValueError('Der Windows-Client muss eine lokale Rückleitungsadresse verwenden.')
    return value


def _pkce_challenge(value):
    value = str(value or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', value):
        raise ValueError('Ungültige PKCE-Anfrage.')
    return value


def authorize(c, uid, body):
    if str(body.get('client_id') or '') != CLIENT_ID:
        raise ValueError('Unbekannter Client.')
    if str(body.get('response_type') or '') != 'code' or str(body.get('code_challenge_method') or '') != 'S256':
        raise ValueError('Der Windows-Client muss Authorization Code mit PKCE S256 verwenden.')
    redirect = _loopback_redirect(body.get('redirect_uri'))
    challenge = _pkce_challenge(body.get('code_challenge'))
    state = str(body.get('state') or '')
    if not 16 <= len(state) <= 300 or any(ord(ch) < 33 for ch in state):
        raise ValueError('Ungültiger Anmeldestatus.')
    client_name = ' '.join(str(body.get('client_name') or 'ProjektZeit für Windows').split())[:120]
    raw = secrets.token_urlsafe(48)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    expires = int(time.time()) + 180
    c.execute('INSERT INTO client_authorization_codes(code_hash,user_id,client_id,client_name,redirect_uri,code_challenge,expires_at) VALUES(?,?,?,?,?,?,?)',
              (digest, uid, CLIENT_ID, client_name, redirect, challenge, expires))
    system_features.audit(c, uid, uid, 'client_authorization', digest[:12], 'Windows-Anmeldung freigegeben', {'client_name':client_name})
    return {'redirect_url':redirect+'?'+urlencode({'code':raw,'state':state}), 'expires_in':180}


def exchange(c, app, body):
    if str(body.get('grant_type') or '') != 'authorization_code':
        raise ValueError('Nicht unterstützter OAuth-Grant.')
    if str(body.get('client_id') or '') != CLIENT_ID:
        raise ValueError('Unbekannter Client.')
    redirect = _loopback_redirect(body.get('redirect_uri'))
    verifier = str(body.get('code_verifier') or '')
    if not PKCE_PATTERN.fullmatch(verifier):
        raise ValueError('Ungültiger PKCE-Nachweis.')
    code_hash = hashlib.sha256(str(body.get('code') or '').encode()).hexdigest()
    row = c.execute('SELECT * FROM client_authorization_codes WHERE code_hash=?', (code_hash,)).fetchone()
    if not row or row['used_at'] or int(row['expires_at']) < int(time.time()):
        raise ValueError('Der Anmeldelink ist ungültig, abgelaufen oder bereits verwendet.')
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    if (row['client_id'] != CLIENT_ID or row['redirect_uri'] != redirect or
            not hmac.compare_digest(str(row['code_challenge']), expected)):
        raise ValueError('Die Anmeldeanfrage gehört nicht zu diesem Client.')
    changed = c.execute("UPDATE client_authorization_codes SET used_at=? WHERE code_hash=? AND used_at=''", (app.now_iso(), code_hash))
    if changed.rowcount != 1:
        raise ValueError('Der Anmeldelink wurde bereits verwendet.')
    user = c.execute('SELECT id,active FROM users WHERE id=?', (row['user_id'],)).fetchone()
    if not user or not user['active']:
        raise ValueError('Das Konto ist nicht mehr aktiv.')
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    ttl = max(3600, int(admin_controls.setting(c, 'policy.session_max_hours', 12))*3600)
    created = int(time.time())
    try:
        c.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at,created_at) VALUES(?,?,?,?,?)',
                  (token_hash, row['user_id'], csrf, created+ttl, created))
    except sqlite3.DatabaseError as error:
        if 'created_at' not in str(error):
            raise
        c.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',
                  (token_hash, row['user_id'], csrf, created+ttl))
    c.execute('INSERT INTO native_sessions(token_hash,client_name) VALUES(?,?)', (token_hash, row['client_name']))
    c.execute('INSERT OR IGNORE INTO session_mfa(token_hash) VALUES(?)', (token_hash,))
    return {'access_token':token,'token_type':'Bearer','expires_in':ttl}


def _protected(user):
    return bool(user and str(user['username']).casefold() == _bootstrap_name())


def _phone_key(value):
    digits=''.join(ch for ch in str(value or '') if ch.isdigit())
    if digits.startswith('00'):digits=digits[2:]
    if digits.startswith('49') and len(digits)>9:digits='0'+digits[2:]
    # Country and trunk prefixes differ between incoming and outgoing records.
    # A stable subscriber suffix is sufficient only once a real phone number is
    # present; short extensions deliberately remain exact.
    return digits[-10:] if len(digits)>=10 else digits


def reconcile_starface_callbacks(c, uid):
    """Close older missed calls after a later, successfully answered callback."""
    import json
    import starface_calls
    calls=[]
    for row in c.execute("SELECT external_key,occurred_at,raw_json FROM provider_events WHERE owner_id=? AND provider='starface' ORDER BY occurred_at,captured_at",(uid,)):
        try:raw=json.loads(row['raw_json'] or '{}')
        except (ValueError,TypeError):continue
        when=starface_calls.start_time(raw.get('startTime') or row['occurred_at'])
        if not when:continue
        direction=str(raw.get('direction') or '').upper();result=str(raw.get('result') or '').upper()
        number=raw.get('callerNumber') if direction=='INBOUND' else raw.get('calledNumber')
        key=_phone_key(number)
        if not key:continue
        calls.append((when,direction,result,key,row['external_key'],raw))
    pending={};marked=0
    for when,direction,result,key,external,raw in calls:
        called_back=raw.get('calledBack',raw.get('calledback',raw.get('called_back',False)))
        if direction=='INBOUND' and result=='MISSED' and not called_back:
            pending.setdefault(key,[]).append((when,external))
            continue
        duration=raw.get('duration')
        successful=direction=='OUTBOUND' and (result=='ANSWERED' or type(duration) is int and duration>0 and result not in ('MISSED','FAILED','BUSY'))
        if not successful:continue
        for missed_at,missed_key in pending.get(key,[]):
            if missed_at>=when:continue
            exists=c.execute('SELECT 1 FROM starface_manual_callbacks WHERE owner_id=? AND external_key=?',(uid,missed_key)).fetchone()
            if not exists:
                c.execute('INSERT INTO starface_manual_callbacks(owner_id,external_key,marked_by,marked_at) VALUES(?,?,?,?)',(uid,missed_key,uid,when.isoformat()))
                marked+=1
    if marked:
        system_features.audit(c,uid,uid,'starface_callbacks','automatic','Erfolgreiche Rückrufe abgeglichen',{'marked':marked})
    return marked


def deletion_context(c, uid):
    user = c.execute('SELECT id,username FROM users WHERE id=? AND active=1', (uid,)).fetchone()
    protected = _protected(user)
    return {'can_delete':bool(user and not protected), 'protected':protected,
            'reason':'Das über ADMIN_USER konfigurierte Systemkonto bleibt als Notfallzugang erhalten.' if protected else ''}


def _end_user_sessions(c, uid, stamp, reason):
    if _table_exists(c, 'session_activity'):
        c.execute("UPDATE session_activity SET ended_at=?,end_reason=? WHERE user_id=? AND ended_at=''", (stamp, reason, uid))
    for table in ('session_mfa', 'native_sessions'):
        if _table_exists(c, table):
            c.execute('DELETE FROM '+table+' WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=?)', (uid,))
    c.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
    if _table_exists(c, 'api_tokens'):
        c.execute("UPDATE api_tokens SET revoked_at=? WHERE owner_id=? AND revoked_at=''", (stamp, uid))


def delete_user(c, app, actor, target, password='', self_service=False):
    target = int(target or 0)
    user = c.execute('SELECT * FROM users WHERE id=?', (target,)).fetchone()
    if not user or _table_exists(c, 'user_deletions') and c.execute('SELECT 1 FROM user_deletions WHERE user_id=?', (target,)).fetchone():
        raise ValueError('Benutzer nicht gefunden.')
    if _protected(user):
        raise ValueError('Das über ADMIN_USER konfigurierte Systemkonto kann nicht gelöscht werden.')
    if self_service:
        if actor != target:
            raise PermissionError('Das eigene Konto ist nicht zugänglich.')
        if not app.verify_password(str(password or ''), user['password_salt'], user['password_hash']):
            raise ValueError('Das aktuelle Passwort ist falsch.')
    else:
        admin_controls.require_permission(c, actor, 'users.delete')
        if actor == target:
            raise ValueError('Das eigene Konto bitte in den persönlichen Einstellungen löschen.')
    stamp = app.now_iso()
    system_features.audit(c, target, actor, 'user', target, 'Konto gelöscht', {'self_service':self_service})
    _end_user_sessions(c, target, stamp, 'Konto gelöscht')
    for table in ('integrations','oauth_tokens','oauth_states','oauth_launch_requests','api_tokens',
                  'user_mfa','user_email_mfa','email_mfa_challenges','email_action_tokens',
                  'user_email_state','user_security_state','password_history','user_preferences',
                  'dashboard_preferences','user_profile_images','user_notifications',
                  'notification_reads','user_role_links','system_superadmins','session_activity',
                  'client_authorization_codes'):
        if not _table_exists(c, table):
            continue
        column = 'user_id'
        if table in ('integrations','oauth_tokens','oauth_states','oauth_launch_requests','api_tokens'):
            column = 'owner_id'
        c.execute('DELETE FROM '+table+' WHERE '+column+'=?', (target,))
    if _table_exists(c, 'user_profiles'):
        c.execute("UPDATE user_profiles SET first_name='',last_name='',email='',phone='',note='' WHERE user_id=?", (target,))
    salt, digest = app.hash_password(secrets.token_urlsafe(48))
    previous_hash = hashlib.sha256(str(user['username']).encode()).hexdigest()
    replacement = 'gelöscht-'+str(target)+'-'+previous_hash[:8]
    if c.execute('SELECT 1 FROM users WHERE username=? AND id<>?', (replacement, target)).fetchone():
        replacement += '-'+secrets.token_hex(4)
    c.execute('UPDATE users SET username=?,password_salt=?,password_hash=?,active=0 WHERE id=?',
              (replacement, salt, digest, target))
    c.execute('INSERT INTO user_deletions(user_id,deleted_by,deleted_at,self_service,previous_username_hash) VALUES(?,?,?,?,?)',
              (target, actor, stamp, int(self_service), previous_hash))
    return {'ok':True,'logged_out':self_service}


def decorate_users(c, viewer_uid, rows):
    """Hide deleted accounts and expose explicit deletion capability to the UI."""
    deleted={r['user_id'] for r in c.execute('SELECT user_id FROM user_deletions')} if _table_exists(c,'user_deletions') else set()
    can_delete=admin_controls.can(c,viewer_uid,'users.delete')
    result=[]
    for source in rows:
        row=dict(source)
        if row['id'] in deleted:
            continue
        row['is_bootstrap']=str(row['username']).casefold()==_bootstrap_name()
        row['can_delete']=bool(not row['is_bootstrap'] and (row['id']==viewer_uid or can_delete))
        result.append(row)
    return result


def install(app):
    category = admin_controls.PERMISSION_CATEGORIES.setdefault('Benutzerverwaltung', [])
    if not any(key == 'users.delete' for key, _ in category):
        category.append(('users.delete', 'Benutzerkonten dauerhaft entfernen'))
    admin_controls.ALL_PERMISSIONS.add('users.delete')
    admin_controls.DEFAULT_ADMIN_PERMISSIONS.add('users.delete')
    try:
        import final_batch_runtime
        final_batch_runtime.DEPENDENCIES['users.delete']={'users.view','admin.options.view'}
    except Exception:
        pass

    original_list_users = admin_controls.list_users
    def list_users(c, viewer_uid):
        return decorate_users(c, viewer_uid, original_list_users(c,viewer_uid))
    admin_controls.list_users=list_users

    try:
        import provider_archive
        original_starface_sync=provider_archive.sync_starface
        def sync_starface(db_factory,uid,config,full=True):
            result=original_starface_sync(db_factory,uid,config,full=full)
            with db_factory() as c:result['callbacks_reconciled']=reconcile_starface_callbacks(c,uid)
            return result
        provider_archive.sync_starface=sync_starface
    except Exception:
        pass
    try:
        import next_batch_runtime
        current_missed=next_batch_runtime._missed_calls
        def missed_calls(c,uid):
            reconcile_starface_callbacks(c,uid)
            return current_missed(c,uid)
        next_batch_runtime._missed_calls=missed_calls
    except Exception:
        pass

    original_init=app.init_db
    def init(create_admin=True):
        original_init(create_admin)
        with app.db() as c:migrate(c)
    app.init_db=init

    original_translate=app.App.translate_path
    def translate_path(self,path):
        clean=urlsplit(path).path
        if not clean.startswith('/api/') and clean not in ('/health',) and '.' not in clean.rsplit('/',1)[-1]:
            return original_translate(self,'/')
        return original_translate(self,path)
    app.App.translate_path=translate_path

    # Serve the fingerprinted SPA entry point for stable, reloadable URL paths.
    # Changing self.path only affects internal dispatch; the browser keeps the
    # requested address (including OAuth parameters) in its address bar.
    previous_get=app.App.do_GET
    def get(self):
        path=urlsplit(self.path).path
        spa=(path in ('/login','/client/authorize','/kalender','/projekte','/zeiterfassung',
                      '/kunden','/zammad','/starface','/teamviewer','/statistiken') or
             path.startswith(('/projekte/','/buchhaltung/','/einstellungen/','/admin/','/werkstatt/')))
        if not spa:
            return previous_get(self)
        requested=self.path
        try:
            self.path='/'
            return previous_get(self)
        finally:
            self.path=requested
    app.App.do_GET=get

    previous_post=app.App.do_POST
    paths={'/api/v1/admin/user/delete','/api/v1/account/delete','/api/v1/account/deletion-context',
           '/api/v1/client-auth/authorize','/api/v1/client-auth/token',
           '/api/v1/integrations/starface/start','/api/v1/integrations/starface/finish'}
    def post(self):
        path=urlsplit(self.path).path
        if path not in paths:return previous_post(self)
        try:
            if (path=='/api/v1/client-auth/token' and
                    self.headers.get('Content-Type','').split(';',1)[0].strip().lower()=='application/x-www-form-urlencoded'):
                length=int(self.headers.get('Content-Length','0'))
                if not 0 <= length <= 65536:
                    raise ValueError('Anfrage zu groß.')
                values=parse_qs(self.rfile.read(length).decode('utf-8'),keep_blank_values=True,strict_parsing=True)
                body={key:items[-1] for key,items in values.items()}
            else:
                body=self.json_body()
            if not isinstance(body,dict):raise ValueError('JSON-Objekt erforderlich.')
            if path=='/api/v1/client-auth/token':
                with app.db() as c:result=exchange(c,app,body)
                return self.send_json(200,result,{'Pragma':'no-cache'})
            session=self.require(csrf=True)
            if not session:return
            # These two desktop OAuth helpers are deliberately user-scoped. The
            # base router predates personal STARFACE tokens and treated every
            # integrations path as an administrator action.
            if path=='/api/v1/integrations/starface/start':return app.App.start_starface(self,session,body)
            if path=='/api/v1/integrations/starface/finish':return app.App.finish_starface(self,session,body)
            with app.db() as c:
                if path=='/api/v1/client-auth/authorize':result=authorize(c,session['id'],body)
                elif path=='/api/v1/account/deletion-context':result=deletion_context(c,session['id'])
                elif path=='/api/v1/account/delete':result=delete_user(c,app,session['id'],session['id'],body.get('current_password'),True)
                else:result=delete_user(c,app,session['id'],body.get('user_id'),'',False)
            headers={'Set-Cookie':'pz_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'} if result.get('logged_out') else None
            return self.send_json(200,result,headers)
        except PermissionError as error:return self.send_json(403,{'error':str(error)})
        except (ValueError,KeyError,TypeError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=post
