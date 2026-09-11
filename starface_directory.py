"""STARFACE internal extension directory with multi-source discovery and manual fallback."""
import json
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
    if not isinstance(user,dict):return ''
    for key in ('displayName','display_name','fullName','fullname','name','label'):
        value=_clean(user.get(key))
        if value: return value
    first=_clean(user.get('firstName') or user.get('firstname') or user.get('first_name'))
    last=_clean(user.get('lastName') or user.get('lastname') or user.get('last_name'))
    return (' '.join(x for x in (first,last) if x)).strip()


def _user_id(user):
    if not isinstance(user,dict):return ''
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
                for key in ('number','phoneNumber','phonenumber','internal','extension','phone'):
                    ext=_extension(item.get(key))
                    if ext:out.append(ext)
            else:
                ext=_extension(item)
                if ext:out.append(ext)
    elif isinstance(value,dict):
        for key in ('number','phoneNumber','phonenumber','internal','extension','phone'):
            ext=_extension(value.get(key))
            if ext:out.append(ext)
    return out


def _user_extensions(user):
    result=[]
    if not isinstance(user,dict):return result
    for key,value in user.items():
        low=str(key).lower().replace('_','')
        if any(token in low for token in ('internal','extension','phonenumber','phone','number')):
            result.extend(_numbers_from_value(value))
    return list(dict.fromkeys(result))


def _save_auto(c,uid,extension,name,external_id='',source='starface'):
    extension=_extension(extension);name=_clean(name)
    if not extension or not name:return False
    existing=c.execute('SELECT source FROM starface_extension_map WHERE owner_id=? AND extension=?',(uid,extension)).fetchone()
    if existing and existing['source']=='manual':return False
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    if existing:
        c.execute('UPDATE starface_extension_map SET name=?,external_id=?,source=?,updated_at=? WHERE owner_id=? AND extension=?',
                  (name,_clean(external_id,120),source,now,uid,extension))
    else:
        c.execute('INSERT INTO starface_extension_map(owner_id,extension,name,external_id,source,updated_at) VALUES(?,?,?,?,?,?)',
                  (uid,extension,name,_clean(external_id,120),source,now))
    return True


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


def _load_endpoint(client,path,headers,errors):
    try:status,payload,message=client.request(path,headers)
    except (OSError,ValueError) as error:
        errors.append('%s: %s'%(path,str(error)));return None
    if 200<=status<300:return payload
    if status not in (403,404):errors.append('%s: HTTP %s%s'%(path,status,(' · '+str(message)) if message else ''))
    return None


def _name_from_call_side(raw,side):
    prefixes=('caller','calling') if side=='caller' else ('called','callee','destination')
    for key,value in raw.items():
        low=str(key).lower()
        if any(low.startswith(p) for p in prefixes) and any(x in low for x in ('name','display','label')):
            text=_clean(value)
            if text:return text
    return ''


def _description_name(raw):
    text=_clean(raw.get('callDescription'),250)
    if not text:return ''
    match=re.match(r'^\s*(.*?)\s*\(([^()]*)\)\s*$',text)
    return (match.group(1) if match else text).strip()[:250]


def _learn_from_history(c,uid,my_name=''):
    imported=0
    for row in c.execute('SELECT raw_json FROM provider_events WHERE owner_id=? AND provider=? ORDER BY captured_at DESC',(uid,'starface')):
        try:raw=json.loads(row['raw_json'])
        except Exception:continue
        if not isinstance(raw,dict):continue
        direction=str(raw.get('direction') or '').upper()
        caller=_extension(raw.get('callerNumber'));called=_extension(raw.get('calledNumber'))
        caller_name=_name_from_call_side(raw,'caller');called_name=_name_from_call_side(raw,'called')
        if caller and caller_name and _save_auto(c,uid,caller,caller_name,source='history'):imported+=1
        if called and called_name and _save_auto(c,uid,called,called_name,source='history'):imported+=1
        # Die persönliche Anrufliste verrät zuverlässig, welche Seite die eigene
        # Durchwahl ist. /users/me liefert dazu den Namen des angemeldeten Kontos.
        own=called if direction=='INBOUND' else caller if direction=='OUTBOUND' else ''
        if own and my_name and _save_auto(c,uid,own,my_name,source='history-me'):imported+=1
        # Bei internen Gesprächen beschreibt STARFACE häufig den jeweils anderen
        # Teilnehmer im callDescription-Feld.
        if caller and called:
            other=caller if direction=='INBOUND' else called if direction=='OUTBOUND' else ''
            other_name=_description_name(raw)
            if other and other_name and other_name.casefold()!=my_name.casefold() and _save_auto(c,uid,other,other_name,source='history'):imported+=1
    return imported


def refresh(c,uid,config,client_factory=integrations.Client):
    """Best-effort import from REST variants plus already cached call history.

    Manual mappings always win. STARFACE installations differ significantly in
    exposed REST resources, so one missing endpoint no longer makes discovery fail.
    """
    client=client_factory(config['domain'])
    headers={'Authorization':'Bearer '+config['secret'],'X-Version':'2'}
    errors=[];sources=[];imported=0;by_id={};me_name=''

    me=_load_endpoint(client,'/rest/users/me',headers,errors)
    if isinstance(me,dict):
        me_name=_user_name(me);me_id=_user_id(me)
        for ext in _user_extensions(me):
            if me_name and _save_auto(c,uid,ext,me_name,me_id,'starface-me'):imported+=1
        if me_name:sources.append('users/me')

    users_payload=None
    for path in ('/rest/users','/rest/users?expand=true','/rest/user'):
        payload=_load_endpoint(client,path,headers,errors)
        if payload is not None:
            users_payload=payload;sources.append(path.split('?')[0]);break
    users=_items(users_payload,('users','items','data','results'))
    if isinstance(users_payload,dict) and not users and _user_name(users_payload):users=[users_payload]
    for user in users:
        name=_user_name(user);uid_value=_user_id(user)
        if uid_value and name:by_id[uid_value]=name
        for ext in _user_extensions(user):
            if name and _save_auto(c,uid,ext,name,uid_value):imported+=1

    phone_payload=None
    for path in ('/rest/phonenumbers','/rest/phoneNumbers','/rest/phonenumbers?expand=true'):
        payload=_load_endpoint(client,path,headers,errors)
        if payload is not None:
            phone_payload=payload;sources.append(path.split('?')[0]);break
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
        if not name:name=_user_name(phone)
        if name and _save_auto(c,uid,ext,name,user_id):imported+=1

    learned=_learn_from_history(c,uid,me_name)
    if learned:sources.append('Anrufhistorie');imported+=learned
    # 403/404 sind bei STARFACE je nach Version normal und werden nicht als
    # sichtbarer Fehler gewertet, wenn wenigstens eine Quelle funktioniert hat.
    if sources:errors=[x for x in errors if 'HTTP 403' not in x and 'HTTP 404' not in x]
    return {'imported':imported,'errors':errors[:8],'sources':list(dict.fromkeys(sources))}
