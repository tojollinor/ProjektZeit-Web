"""STARFACE internal extension directory with automatic REST discovery and manual fallback."""
import re
from datetime import datetime, timezone
import integrations


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS starface_extension_map (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      extension TEXT NOT NULL,
      name TEXT NOT NULL,
      external_id TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT 'manual',
      updated_at TEXT NOT NULL,
      UNIQUE(owner_id,extension)
    );
    ''')


def _clean(value, limit=250):
    return str(value or '').strip()[:limit]


def _extension(value):
    value=_clean(value,40)
    digits=''.join(re.findall(r'\d',value))
    return digits if digits and len(digits) <= 5 else ''


def _items(payload, preferred=()):
    if isinstance(payload,list): return [x for x in payload if isinstance(x,dict)]
    if not isinstance(payload,dict): return []
    for key in preferred:
        value=payload.get(key)
        if isinstance(value,list): return [x for x in value if isinstance(x,dict)]
    for value in payload.values():
        if isinstance(value,list) and all(isinstance(x,dict) for x in value): return value
    return []


def _user_name(user):
    for key in ('displayName','display_name','fullName','fullname','name'):
        value=_clean(user.get(key))
        if value: return value
    first=_clean(user.get('firstName') or user.get('firstname') or user.get('first_name'))
    last=_clean(user.get('lastName') or user.get('lastname') or user.get('last_name'))
    return (' '.join(x for x in (first,last) if x)).strip()


def _user_id(user):
    for key in ('id','userId','userid','user_id','accountId','account_id','loginId','login_id'):
        value=_clean(user.get(key),120)
        if value:return value
    return ''


def _numbers_from_value(value):
    out=[]
    if isinstance(value,(str,int)):
        ext=_extension(value)
        if ext:out.append(ext)
    elif isinstance(value,list):
        for item in value:
            if isinstance(item,dict):
                for key in ('number','phoneNumber','phonenumber','internal','extension'):
                    ext=_extension(item.get(key))
                    if ext:out.append(ext)
            else:
                ext=_extension(item)
                if ext:out.append(ext)
    elif isinstance(value,dict):
        for key in ('number','phoneNumber','phonenumber','internal','extension'):
            ext=_extension(value.get(key))
            if ext:out.append(ext)
    return out


def _user_extensions(user):
    result=[]
    for key,value in user.items():
        low=str(key).lower()
        if any(token in low for token in ('internal','extension','phonenumber','phone_number','phone numbers','phonenumbers')):
            result.extend(_numbers_from_value(value))
    return list(dict.fromkeys(result))


def _save_auto(c,uid,extension,name,external_id=''):
    extension=_extension(extension);name=_clean(name)
    if not extension or not name:return
    existing=c.execute('SELECT source FROM starface_extension_map WHERE owner_id=? AND extension=?',(uid,extension)).fetchone()
    if existing and existing['source']=='manual':return
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    if existing:
        c.execute('UPDATE starface_extension_map SET name=?,external_id=?,source=?,updated_at=? WHERE owner_id=? AND extension=?',
                  (name,_clean(external_id,120),'starface',now,uid,extension))
    else:
        c.execute('INSERT INTO starface_extension_map(owner_id,extension,name,external_id,source,updated_at) VALUES(?,?,?,?,?,?)',
                  (uid,extension,name,_clean(external_id,120),'starface',now))


def save_manual(c,uid,extension,name):
    extension=_extension(extension);name=_clean(name)
    if not extension:raise ValueError('Interne STARFACE-Nummern dürfen höchstens fünf Ziffern haben.')
    if not name:raise ValueError('Bitte einen Mitarbeiternamen eingeben.')
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    row=c.execute('SELECT id FROM starface_extension_map WHERE owner_id=? AND extension=?',(uid,extension)).fetchone()
    if row:
        c.execute('UPDATE starface_extension_map SET name=?,source=?,updated_at=? WHERE id=?',(name,'manual',now,row['id']))
    else:
        c.execute('INSERT INTO starface_extension_map(owner_id,extension,name,source,updated_at) VALUES(?,?,?,?,?)',(uid,extension,name,'manual',now))


def list_all(c,uid):
    return [dict(r) for r in c.execute('SELECT extension,name,external_id,source,updated_at FROM starface_extension_map WHERE owner_id=? ORDER BY LENGTH(extension),extension',(uid,))]


def refresh(c,uid,config,client_factory=integrations.Client):
    """Best-effort import. Manual mappings always win over automatic data."""
    client=client_factory(config['domain'])
    headers={'Authorization':'Bearer '+config['secret'],'X-Version':'2'}
    users_payload=None; phone_payload=None; errors=[]
    for path,kind in (('/rest/users','users'),('/rest/phonenumbers','phones')):
        try:
            status,payload,message=client.request(path,headers)
        except (OSError,ValueError) as error:
            errors.append('%s: %s'%(kind,str(error)));continue
        if 200 <= status < 300:
            if kind=='users':users_payload=payload
            else:phone_payload=payload
        else:
            errors.append('%s: HTTP %s%s'%(kind,status,(' · '+str(message)) if message else ''))
    users=_items(users_payload,('users','items','data','results'))
    by_id={}; imported=0
    for user in users:
        name=_user_name(user);uid_value=_user_id(user)
        if uid_value and name:by_id[uid_value]=name
        for ext in _user_extensions(user):
            if name:_save_auto(c,uid,ext,name,uid_value);imported+=1
    phones=_items(phone_payload,('phoneNumbers','phonenumbers','numbers','items','data','results'))
    for phone in phones:
        ext=''
        for key in ('number','phoneNumber','phonenumber','internal','extension'):
            ext=_extension(phone.get(key))
            if ext:break
        if not ext:continue
        user_id=''
        for key in ('userId','userid','user_id','assignedUserId','assigned_user_id','accountId','account_id'):
            user_id=_clean(phone.get(key),120)
            if user_id:break
        name=by_id.get(user_id,'')
        if not name:
            nested=phone.get('user')
            if isinstance(nested,dict):name=_user_name(nested);user_id=user_id or _user_id(nested)
        if name:_save_auto(c,uid,ext,name,user_id);imported+=1
    return {'imported':imported,'errors':errors}
