"""Systemweite Admin-/Super-Admin-Einstellungen ohne Compose-Migration.

Der bereits über ADMIN_USER angelegte Benutzer wird als Bootstrap-Super-Admin
markiert. Die bestehende users.role-Spalte bleibt aus Kompatibilitätsgründen
unverändert; feinere Rollen und Rechte liegen in eigenen Tabellen.
"""
import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage

import integrations


PERMISSION_CATEGORIES = {
    'Benutzerverwaltung': [
        ('users.view', 'Benutzer ansehen'),
        ('users.create', 'Benutzer anlegen'),
        ('users.edit', 'Benutzer bearbeiten'),
        ('users.disable', 'Benutzer aktivieren / deaktivieren'),
        ('users.roles.assign', 'Rollen Benutzern zuweisen'),
    ],
    'Rollen & Berechtigungen': [
        ('roles.view', 'Rollen ansehen'),
        ('roles.create', 'Rollen erstellen'),
        ('roles.edit', 'Rollen bearbeiten'),
        ('roles.clone', 'Rollen klonen'),
        ('roles.delete', 'Eigene Rollen löschen'),
        ('roles.reset_user', 'Rolle Benutzer auf Standard zurücksetzen'),
    ],
    'Kunden': [
        ('customers.view', 'Kunden ansehen'),
        ('customers.create', 'Kunden anlegen'),
        ('customers.edit', 'Kunden bearbeiten'),
        ('customers.links', 'Rufnummern, Geräte und Provider zuordnen'),
        ('customers.delete', 'Kunden löschen'),
    ],
    'Integrationen': [
        ('integrations.view', 'Integrationen ansehen'),
        ('integrations.edit', 'Integrationen konfigurieren'),
        ('integrations.sync', 'History-Import / Synchronisation starten'),
        ('integrations.debug', 'Debug-Rohdaten ansehen'),
    ],
    'Sicherheit': [
        ('security.policies.view', 'Sicherheitsrichtlinien ansehen'),
        ('security.policies.edit', 'Sicherheitsrichtlinien bearbeiten'),
        ('security.2fa.reset_user', '2FA normaler Benutzer zurücksetzen'),
        ('security.sessions.end', 'Sitzungen eines Benutzers beenden'),
    ],
    'E-Mail & Benachrichtigungen': [
        ('smtp.view', 'SMTP-Einstellungen ansehen'),
        ('smtp.edit', 'SMTP konfigurieren'),
        ('smtp.test', 'SMTP-Testmail senden'),
        ('notifications.edit', 'Benachrichtigungsregeln verwalten'),
    ],
    'System': [
        ('admin.options.view', 'Admin-Optionen öffnen'),
        ('logs.view', 'Logs ansehen'),
        ('system.options.edit', 'Systemoptionen ändern'),
    ],
}
ALL_PERMISSIONS = {key for values in PERMISSION_CATEGORIES.values() for key, _ in values}
DEFAULT_USER_PERMISSIONS = {
    'customers.view', 'customers.create', 'customers.edit', 'customers.links',
    'integrations.view',
}
DEFAULT_ADMIN_PERMISSIONS = ALL_PERMISSIONS - {'system.options.edit'}

POLICY_DEFAULTS = {
    'password_min_length': 12,
    'password_require_upper': False,
    'password_require_lower': False,
    'password_require_number': False,
    'password_require_special': False,
    'password_history': 0,
    'password_expiry_days': 0,
    'password_change_first_login': False,
    'login_max_attempts': 8,
    'login_lock_minutes': 10,
    'session_idle_minutes': 0,
    'session_max_hours': 12,
    'remember_login_allowed': True,
    'two_factor_mode': 'optional',
    'two_factor_admin_required': False,
    'two_factor_grace_days': 0,
    'email_password_reset_allowed': True,
    'email_verify_required': False,
    'notify_password_change': True,
    'notify_email_change': True,
    'notify_two_factor_change': True,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS system_superadmins (
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS user_profiles (
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '',
      email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
      last_login_at TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS role_definitions (
      id INTEGER PRIMARY KEY, role_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
      is_system INTEGER NOT NULL DEFAULT 0, is_editable INTEGER NOT NULL DEFAULT 1,
      is_resettable INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS role_permissions (
      role_id INTEGER NOT NULL REFERENCES role_definitions(id) ON DELETE CASCADE,
      permission_key TEXT NOT NULL, PRIMARY KEY(role_id,permission_key)
    );
    CREATE TABLE IF NOT EXISTS user_role_links (
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      role_id INTEGER NOT NULL REFERENCES role_definitions(id) ON DELETE CASCADE,
      PRIMARY KEY(user_id,role_id)
    );
    CREATE TABLE IF NOT EXISTS system_settings (
      setting_key TEXT PRIMARY KEY, value_json LONGTEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS smtp_settings (
      id INTEGER PRIMARY KEY, sender_name TEXT NOT NULL DEFAULT '', sender_email TEXT NOT NULL DEFAULT '',
      host TEXT NOT NULL DEFAULT '', port INTEGER NOT NULL DEFAULT 587, security_mode TEXT NOT NULL DEFAULT 'starttls',
      username TEXT NOT NULL DEFAULT '', password_secret TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS customer_master_fields (
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      name_addition TEXT NOT NULL DEFAULT '', street TEXT NOT NULL DEFAULT '', house_number TEXT NOT NULL DEFAULT '',
      zip_code TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT 'Deutschland',
      website TEXT NOT NULL DEFAULT '', billing_email TEXT NOT NULL DEFAULT '', tax_number TEXT NOT NULL DEFAULT '',
      vat_id TEXT NOT NULL DEFAULT '', customer_number TEXT NOT NULL DEFAULT '', payment_terms TEXT NOT NULL DEFAULT '',
      invoice_note TEXT NOT NULL DEFAULT '', PRIMARY KEY(owner_id,customer_id)
    );
    ''')
    _seed_roles(c)
    _seed_bootstrap(c)
    for key, value in POLICY_DEFAULTS.items():
        if not c.execute('SELECT 1 FROM system_settings WHERE setting_key=?', ('policy.'+key,)).fetchone():
            c.execute('INSERT INTO system_settings(setting_key,value_json,updated_at) VALUES(?,?,?)',
                      ('policy.'+key, json.dumps(value), now_iso()))
    if not c.execute('SELECT 1 FROM system_settings WHERE setting_key=?', ('superadmin.admin_may_reset_2fa',)).fetchone():
        c.execute('INSERT INTO system_settings(setting_key,value_json,updated_at) VALUES(?,?,?)',
                  ('superadmin.admin_may_reset_2fa', json.dumps(True), now_iso()))


def _role(c, role_key):
    return c.execute('SELECT * FROM role_definitions WHERE role_key=?', (role_key,)).fetchone()


def _seed_roles(c):
    roles = [
        ('superadmin', 'Super-Admin', 1, 0, 0, 1),
        ('admin', 'Admin', 1, 0, 0, 0),
        ('user', 'Benutzer', 1, 1, 1, 0),
    ]
    for key, name, system, editable, resettable, hidden in roles:
        if not _role(c, key):
            c.execute('INSERT INTO role_definitions(role_key,name,is_system,is_editable,is_resettable,hidden,created_at) VALUES(?,?,?,?,?,?,?)',
                      (key, name, system, editable, resettable, hidden, now_iso()))
    _set_role_permissions(c, _role(c, 'superadmin')['id'], ALL_PERMISSIONS)
    _set_role_permissions(c, _role(c, 'admin')['id'], DEFAULT_ADMIN_PERMISSIONS)
    if not c.execute('SELECT 1 FROM role_permissions WHERE role_id=? LIMIT 1', (_role(c, 'user')['id'],)).fetchone():
        _set_role_permissions(c, _role(c, 'user')['id'], DEFAULT_USER_PERMISSIONS)


def _seed_bootstrap(c):
    bootstrap = os.environ.get('ADMIN_USER', 'admin').strip()
    row = c.execute('SELECT id FROM users WHERE username=?', (bootstrap,)).fetchone()
    if row:
        c.execute('INSERT OR IGNORE INTO system_superadmins(user_id,created_at) VALUES(?,?)', (row['id'], now_iso()))
    super_role = _role(c, 'superadmin')
    admin_role = _role(c, 'admin')
    user_role = _role(c, 'user')
    for user in c.execute('SELECT id,role FROM users'):
        target = super_role if is_superadmin(c, user['id']) else (admin_role if user['role']=='admin' else user_role)
        if not c.execute('SELECT 1 FROM user_role_links WHERE user_id=? LIMIT 1', (user['id'],)).fetchone():
            c.execute('INSERT OR IGNORE INTO user_role_links(user_id,role_id) VALUES(?,?)', (user['id'], target['id']))
        if not c.execute('SELECT 1 FROM user_profiles WHERE user_id=?', (user['id'],)).fetchone():
            c.execute('INSERT INTO user_profiles(user_id) VALUES(?)', (user['id'],))


def is_superadmin(c, uid):
    return bool(c.execute('SELECT 1 FROM system_superadmins WHERE user_id=?', (uid,)).fetchone())


def _set_role_permissions(c, role_id, permissions):
    c.execute('DELETE FROM role_permissions WHERE role_id=?', (role_id,))
    for key in sorted(set(permissions) & ALL_PERMISSIONS):
        c.execute('INSERT INTO role_permissions(role_id,permission_key) VALUES(?,?)', (role_id, key))


def permissions_for_user(c, uid):
    if is_superadmin(c, uid):
        return set(ALL_PERMISSIONS)
    return {r['permission_key'] for r in c.execute('''SELECT rp.permission_key FROM role_permissions rp
        JOIN user_role_links ur ON ur.role_id=rp.role_id WHERE ur.user_id=?''', (uid,))}


def can(c, uid, permission):
    return is_superadmin(c, uid) or permission in permissions_for_user(c, uid)


def require_permission(c, uid, permission):
    if not can(c, uid, permission):
        raise PermissionError('Dafür fehlt die Berechtigung.')


def setting(c, key, default=None):
    row = c.execute('SELECT value_json FROM system_settings WHERE setting_key=?', (key,)).fetchone()
    if not row: return default
    try: return json.loads(row['value_json'])
    except Exception: return default


def set_setting(c, key, value):
    c.execute('DELETE FROM system_settings WHERE setting_key=?', (key,))
    c.execute('INSERT INTO system_settings(setting_key,value_json,updated_at) VALUES(?,?,?)',
              (key, json.dumps(value, ensure_ascii=False), now_iso()))


def policy_values(c):
    return {key: setting(c, 'policy.'+key, default) for key, default in POLICY_DEFAULTS.items()}


def list_roles(c, viewer_uid):
    superuser = is_superadmin(c, viewer_uid)
    rows = c.execute('SELECT * FROM role_definitions ORDER BY is_system DESC,name')
    result=[]
    for row in rows:
        if row['hidden'] and not superuser: continue
        permissions=[r['permission_key'] for r in c.execute('SELECT permission_key FROM role_permissions WHERE role_id=? ORDER BY permission_key',(row['id'],))]
        result.append(dict(id=row['id'], key=row['role_key'], name=row['name'], is_system=bool(row['is_system']),
                           editable=bool(row['is_editable']), resettable=bool(row['is_resettable']), hidden=bool(row['hidden']),
                           permissions=permissions))
    return result


def list_users(c, viewer_uid):
    superuser=is_superadmin(c,viewer_uid)
    out=[]
    for row in c.execute('''SELECT u.id,u.username,u.role,u.active,u.created_at,p.first_name,p.last_name,p.email,p.phone,p.note,p.last_login_at
                            FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id ORDER BY u.username'''):
        target_super=is_superadmin(c,row['id'])
        if target_super and not superuser: continue
        roles=[dict(id=r['id'],key=r['role_key'],name=r['name']) for r in c.execute('''SELECT d.id,d.role_key,d.name FROM role_definitions d
                    JOIN user_role_links l ON l.role_id=d.id WHERE l.user_id=? ORDER BY d.name''',(row['id'],)) if superuser or r['role_key']!='superadmin']
        out.append(dict(row, is_superadmin=target_super, roles=roles))
    return out


def save_role(c, actor_uid, body):
    require_permission(c,actor_uid,'roles.edit' if body.get('id') else 'roles.create')
    role_id=body.get('id');name=str(body.get('name') or '').strip()[:120]
    permissions=set(body.get('permissions') or []) & ALL_PERMISSIONS
    if not name: raise ValueError('Bitte einen Rollennamen eingeben.')
    if role_id:
        role=c.execute('SELECT * FROM role_definitions WHERE id=?',(int(role_id),)).fetchone()
        if not role: raise ValueError('Rolle nicht gefunden.')
        if not role['is_editable']: raise ValueError('Diese Systemrolle kann nicht bearbeitet werden.')
        c.execute('UPDATE role_definitions SET name=? WHERE id=?',(name,role['id']))
        _set_role_permissions(c,role['id'],permissions)
        return role['id']
    key='custom-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
    rid=c.execute('INSERT INTO role_definitions(role_key,name,is_system,is_editable,is_resettable,hidden,created_at) VALUES(?,?,0,1,0,0,?)',(key,name,now_iso())).lastrowid
    _set_role_permissions(c,rid,permissions)
    return rid


def clone_role(c, actor_uid, role_id):
    require_permission(c,actor_uid,'roles.clone')
    role=c.execute('SELECT * FROM role_definitions WHERE id=?',(int(role_id),)).fetchone()
    if not role or (role['hidden'] and not is_superadmin(c,actor_uid)): raise ValueError('Rolle nicht gefunden.')
    name=(role['name']+' – Klon')[:120]
    key='custom-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
    rid=c.execute('INSERT INTO role_definitions(role_key,name,is_system,is_editable,is_resettable,hidden,created_at) VALUES(?,?,0,1,0,0,?)',(key,name,now_iso())).lastrowid
    perms=[r['permission_key'] for r in c.execute('SELECT permission_key FROM role_permissions WHERE role_id=?',(role['id'],))]
    _set_role_permissions(c,rid,perms)
    return rid


def delete_role(c, actor_uid, role_id):
    require_permission(c,actor_uid,'roles.delete')
    role=c.execute('SELECT * FROM role_definitions WHERE id=?',(int(role_id),)).fetchone()
    if not role: return
    if role['is_system']: raise ValueError('Vordefinierte Rollen können nicht gelöscht werden.')
    c.execute('DELETE FROM role_definitions WHERE id=?',(role['id'],))


def reset_user_role(c, actor_uid):
    require_permission(c,actor_uid,'roles.reset_user')
    role=_role(c,'user');_set_role_permissions(c,role['id'],DEFAULT_USER_PERMISSIONS)


def assign_roles(c, actor_uid, user_id, role_ids):
    require_permission(c,actor_uid,'users.roles.assign')
    user_id=int(user_id)
    if is_superadmin(c,user_id) and not is_superadmin(c,actor_uid): raise PermissionError('Dieser Benutzer kann nicht verwaltet werden.')
    valid=[]
    for value in role_ids or []:
        role=c.execute('SELECT * FROM role_definitions WHERE id=?',(int(value),)).fetchone()
        if not role: continue
        if role['role_key']=='superadmin' and not is_superadmin(c,actor_uid): continue
        valid.append(role)
    if not valid: raise ValueError('Mindestens eine Rolle auswählen.')
    if is_superadmin(c,user_id) and not any(r['role_key']=='superadmin' for r in valid):
        raise ValueError('Der Bootstrap-Super-Admin kann nicht degradiert werden.')
    c.execute('DELETE FROM user_role_links WHERE user_id=?',(user_id,))
    for role in valid:c.execute('INSERT INTO user_role_links(user_id,role_id) VALUES(?,?)',(user_id,role['id']))


def update_user_profile(c, actor_uid, body):
    require_permission(c,actor_uid,'users.edit')
    user_id=int(body.get('user_id'))
    if is_superadmin(c,user_id) and not is_superadmin(c,actor_uid): raise PermissionError('Dieser Benutzer kann nicht verwaltet werden.')
    if not c.execute('SELECT 1 FROM users WHERE id=?',(user_id,)).fetchone(): raise ValueError('Benutzer nicht gefunden.')
    values=[str(body.get(k) or '').strip() for k in ('first_name','last_name','email','phone','note')]
    c.execute('DELETE FROM user_profiles WHERE user_id=?',(user_id,))
    c.execute('INSERT INTO user_profiles(user_id,first_name,last_name,email,phone,note,last_login_at) VALUES(?,?,?,?,?,?,?)',
              (user_id,*values,str(body.get('last_login_at') or '')))


def mark_login(c, user_id):
    row=c.execute('SELECT * FROM user_profiles WHERE user_id=?',(user_id,)).fetchone()
    if row:c.execute('UPDATE user_profiles SET last_login_at=? WHERE user_id=?',(now_iso(),user_id))
    else:c.execute('INSERT INTO user_profiles(user_id,last_login_at) VALUES(?,?)',(user_id,now_iso()))


def smtp_public(c):
    row=c.execute('SELECT * FROM smtp_settings WHERE id=1').fetchone()
    if not row:return {'sender_name':'','sender_email':'','host':'','port':587,'security_mode':'starttls','username':'','has_password':False,'updated_at':''}
    return {'sender_name':row['sender_name'],'sender_email':row['sender_email'],'host':row['host'],'port':row['port'],
            'security_mode':row['security_mode'],'username':row['username'],'has_password':bool(row['password_secret']),'updated_at':row['updated_at']}


def save_smtp(c, actor_uid, body, data_dir):
    require_permission(c,actor_uid,'smtp.edit')
    host=str(body.get('host') or '').strip()[:250];sender_email=str(body.get('sender_email') or '').strip()[:250]
    if not host or not sender_email: raise ValueError('SMTP-Host und Absenderadresse sind erforderlich.')
    port=int(body.get('port') or 587)
    if not 1<=port<=65535: raise ValueError('Ungültiger SMTP-Port.')
    mode=str(body.get('security_mode') or 'starttls').lower()
    if mode not in ('starttls','ssl','none'): raise ValueError('Ungültige SMTP-Verschlüsselung.')
    old=c.execute('SELECT password_secret FROM smtp_settings WHERE id=1').fetchone();secret=old['password_secret'] if old else ''
    password=body.get('password')
    if isinstance(password,str) and password:
        secret=integrations.cipher(data_dir).encrypt(password.encode()).decode()
    c.execute('DELETE FROM smtp_settings WHERE id=1')
    c.execute('INSERT INTO smtp_settings(id,sender_name,sender_email,host,port,security_mode,username,password_secret,updated_at) VALUES(1,?,?,?,?,?,?,?,?)',
              (str(body.get('sender_name') or '').strip()[:250],sender_email,host,port,mode,str(body.get('username') or '').strip()[:250],secret,now_iso()))


def _smtp_credentials(c, data_dir):
    row=c.execute('SELECT * FROM smtp_settings WHERE id=1').fetchone()
    if not row: raise ValueError('SMTP ist noch nicht konfiguriert.')
    password=''
    if row['password_secret']:
        password=integrations.cipher(data_dir).decrypt(row['password_secret'].encode()).decode()
    return row,password


def test_smtp(c, actor_uid, recipient, data_dir):
    require_permission(c,actor_uid,'smtp.test')
    row,password=_smtp_credentials(c,data_dir)
    recipient=str(recipient or '').strip()[:250]
    if not recipient: raise ValueError('Bitte eine Empfängeradresse für die Testmail eingeben.')
    msg=EmailMessage();msg['Subject']='ProjektZeit SMTP-Test';msg['From']=('%s <%s>'%(row['sender_name'],row['sender_email'])) if row['sender_name'] else row['sender_email'];msg['To']=recipient
    msg.set_content('Diese Testmail wurde erfolgreich von ProjektZeit versendet.')
    context=ssl.create_default_context()
    if row['security_mode']=='ssl':client=smtplib.SMTP_SSL(row['host'],row['port'],timeout=10,context=context)
    else:
        client=smtplib.SMTP(row['host'],row['port'],timeout=10)
        if row['security_mode']=='starttls':client.starttls(context=context)
    try:
        if row['username']:client.login(row['username'],password)
        client.send_message(msg)
    finally:client.quit()


def customer_master(c, uid, customer_id):
    row=c.execute('SELECT * FROM customer_master_fields WHERE owner_id=? AND customer_id=?',(uid,int(customer_id))).fetchone()
    if not row:return {'name_addition':'','street':'','house_number':'','zip_code':'','city':'','country':'Deutschland','website':'','billing_email':'','tax_number':'','vat_id':'','customer_number':'','payment_terms':'','invoice_note':''}
    data=dict(row);data.pop('owner_id',None);data.pop('customer_id',None);return data


def save_customer_master(c, uid, customer_id, body):
    customer_id=int(customer_id)
    if not c.execute('SELECT 1 FROM customers WHERE id=? AND owner_id=?',(customer_id,uid)).fetchone():raise ValueError('Kunde nicht gefunden.')
    keys=('name_addition','street','house_number','zip_code','city','country','website','billing_email','tax_number','vat_id','customer_number','payment_terms','invoice_note')
    vals=[str(body.get(k) or '').strip()[:2000 if k=='invoice_note' else 250] for k in keys]
    c.execute('DELETE FROM customer_master_fields WHERE owner_id=? AND customer_id=?',(uid,customer_id))
    c.execute('''INSERT INTO customer_master_fields(owner_id,customer_id,name_addition,street,house_number,zip_code,city,country,website,billing_email,tax_number,vat_id,customer_number,payment_terms,invoice_note)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(uid,customer_id,*vals))


def admin_context(c, uid):
    superuser=is_superadmin(c,uid)
    perms=sorted(permissions_for_user(c,uid))
    return {
        'is_superadmin':superuser,
        'permissions':perms,
        'permission_categories':{cat:[{'key':k,'label':label} for k,label in items] for cat,items in PERMISSION_CATEGORIES.items()},
        'roles':list_roles(c,uid) if (superuser or 'roles.view' in perms) else [],
        'users':list_users(c,uid) if (superuser or 'users.view' in perms) else [],
        'policies':policy_values(c) if (superuser or 'security.policies.view' in perms) else {},
        'smtp':smtp_public(c) if (superuser or 'smtp.view' in perms) else {},
        'superadmin_settings':({'admin_may_reset_2fa':bool(setting(c,'superadmin.admin_may_reset_2fa',True))} if superuser else {}),
    }
