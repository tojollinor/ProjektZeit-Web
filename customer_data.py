"""Customer master data, provider links, activity history and suggestions."""
import json
import re
import sqlite3
from datetime import datetime, timezone

PROVIDERS = ('starface', 'zammad', 'teamviewer')
PHONE_KINDS = ('Festnetz', 'Mobil', 'Privat', 'Zentrale', 'Durchwahl', 'Fax', 'Sonstige')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS customer_profiles (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      contact_person TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,customer_id)
    );
    CREATE TABLE IF NOT EXISTS customer_phones (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      number TEXT NOT NULL, label TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,customer_id,number)
    );
    CREATE TABLE IF NOT EXISTS customer_contacts (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS customer_contact_phones (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      contact_id INTEGER NOT NULL REFERENCES customer_contacts(id) ON DELETE CASCADE,
      number TEXT NOT NULL, label TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,contact_id,number)
    );
    CREATE TABLE IF NOT EXISTS customer_devices (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      provider TEXT NOT NULL, external_id TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,customer_id,provider,external_id)
    );
    CREATE TABLE IF NOT EXISTS customer_provider_links (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      provider TEXT NOT NULL, external_key TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,provider,external_key)
    );
    CREATE TABLE IF NOT EXISTS provider_events (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      provider TEXT NOT NULL, external_key TEXT NOT NULL, occurred_at TEXT NOT NULL DEFAULT '',
      summary TEXT NOT NULL DEFAULT '', raw_json LONGTEXT NOT NULL, hint_json LONGTEXT NOT NULL,
      captured_at TEXT NOT NULL, UNIQUE(owner_id,provider,external_key)
    );
    ''')


def _clean(value, limit=500):
    return str(value or '').strip()[:limit]


def _customer(c, uid, customer_id):
    return c.execute('SELECT id,name FROM customers WHERE id=? AND owner_id=?', (customer_id, uid)).fetchone()


def valid_phone(value):
    value = _clean(value, 120)
    return value if len(re.sub(r'\D', '', value)) > 5 else ''


def _kind(value):
    value = _clean(value, 40)
    return value or 'Sonstige'


def add_company_phone(c, uid, customer_id, number, label='Sonstige', source=''):
    number = valid_phone(number)
    if not number or not _customer(c, uid, customer_id):
        return False
    c.execute('INSERT OR IGNORE INTO customer_phones(owner_id,customer_id,number,label,source) VALUES(?,?,?,?,?)',
              (uid, customer_id, number, _kind(label), _clean(source, 40)))
    return True


def add_contact(c, uid, customer_id, name, email='', note='', phones=None):
    if not _customer(c, uid, customer_id):
        raise ValueError('Unbekannter Kunde.')
    name = _clean(name, 250)
    if not name:
        raise ValueError('Bitte einen Namen für den Ansprechpartner eingeben.')
    row = c.execute('SELECT id FROM customer_contacts WHERE owner_id=? AND customer_id=? AND name=?', (uid, customer_id, name)).fetchone()
    if row:
        contact_id = row['id']
        c.execute('UPDATE customer_contacts SET email=?,note=? WHERE id=?', (_clean(email,250), _clean(note,2000), contact_id))
    else:
        contact_id = c.execute('INSERT INTO customer_contacts(owner_id,customer_id,name,email,note) VALUES(?,?,?,?,?)',
                               (uid, customer_id, name, _clean(email,250), _clean(note,2000))).lastrowid
    for item in phones or []:
        if isinstance(item, dict):
            add_contact_phone(c, uid, contact_id, item.get('number'), item.get('label'), item.get('source'))
        else:
            add_contact_phone(c, uid, contact_id, item)
    return contact_id


def add_contact_phone(c, uid, contact_id, number, label='Sonstige', source=''):
    number = valid_phone(number)
    owner = c.execute('SELECT 1 FROM customer_contacts WHERE id=? AND owner_id=?', (contact_id, uid)).fetchone()
    if not number or not owner:
        return False
    c.execute('INSERT OR IGNORE INTO customer_contact_phones(owner_id,contact_id,number,label,source) VALUES(?,?,?,?,?)',
              (uid, contact_id, number, _kind(label), _clean(source,40)))
    return True


def add_device(c, uid, customer_id, provider, external_id='', name=''):
    if not _customer(c, uid, customer_id):
        raise ValueError('Unbekannter Kunde.')
    provider = _clean(provider,40).lower() or 'teamviewer'
    external_id, name = _clean(external_id,250), _clean(name,250)
    key = external_id or name
    if not key:
        raise ValueError('Gerätename oder Verbindungs-ID fehlt.')
    c.execute('INSERT OR IGNORE INTO customer_devices(owner_id,customer_id,provider,external_id,name) VALUES(?,?,?,?,?)',
              (uid, customer_id, provider, key, name))


def create(c, uid, body):
    name = _clean(body.get('name'), 120)
    if not name:
        raise ValueError('Bitte einen Kundennamen eingeben.')
    try:
        customer_id = c.execute('INSERT INTO customers(owner_id,name) VALUES(?,?)', (uid, name)).lastrowid
    except sqlite3.IntegrityError:
        row = c.execute('SELECT id FROM customers WHERE owner_id=? AND name=?', (uid, name)).fetchone()
        if not row: raise
        customer_id = row['id']
    update(c, uid, customer_id, body)
    return customer_id


def update(c, uid, customer_id, body):
    if not _customer(c, uid, customer_id):
        raise ValueError('Unbekannter Kunde.')
    name = _clean(body.get('name'), 120)
    if name:
        try: c.execute('UPDATE customers SET name=? WHERE id=? AND owner_id=?', (name, customer_id, uid))
        except sqlite3.IntegrityError: raise ValueError('Ein Kunde mit diesem Namen existiert bereits.') from None
    profile = c.execute('SELECT * FROM customer_profiles WHERE owner_id=? AND customer_id=?', (uid,customer_id)).fetchone()
    email = _clean(body.get('email', profile['email'] if profile else ''),250)
    note = _clean(body.get('note', profile['note'] if profile else ''),2000)
    legacy_contact = _clean(body.get('contact_person', ''),250)
    c.execute('DELETE FROM customer_profiles WHERE owner_id=? AND customer_id=?', (uid,customer_id))
    c.execute('INSERT INTO customer_profiles(owner_id,customer_id,contact_person,email,note) VALUES(?,?,?,?,?)', (uid,customer_id,'',email,note))
    for item in body.get('phones') or []:
        if isinstance(item,dict): add_company_phone(c,uid,customer_id,item.get('number'),item.get('label'),item.get('source'))
        else: add_company_phone(c,uid,customer_id,item)
    contacts = body.get('contacts')
    if isinstance(contacts,list):
        for contact in contacts:
            if isinstance(contact,dict) and _clean(contact.get('name')):
                add_contact(c,uid,customer_id,contact.get('name'),contact.get('email'),contact.get('note'),contact.get('phones'))
    elif legacy_contact:
        add_contact(c,uid,customer_id,legacy_contact,email,'',body.get('phones') or [])
    return customer_id


def assign(c, uid, body):
    provider, key = _clean(body.get('provider'),40).lower(), _clean(body.get('external_key'),255)
    if provider not in PROVIDERS or not key: raise ValueError('Ungültige Provider-Zuordnung.')
    customer_id = body.get('customer_id')
    if body.get('new_customer'): customer_id = create(c,uid,body['new_customer'])
    try: customer_id = int(customer_id)
    except (TypeError,ValueError): raise ValueError('Bitte einen Kunden auswählen.') from None
    if not _customer(c,uid,customer_id): raise ValueError('Unbekannter Kunde.')
    c.execute('DELETE FROM customer_provider_links WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key))
    c.execute('INSERT INTO customer_provider_links(owner_id,customer_id,provider,external_key,label) VALUES(?,?,?,?,?)',
              (uid,customer_id,provider,key,_clean(body.get('label'),250)))
    hints = body.get('hints') if isinstance(body.get('hints'),dict) else {}
    phones = [p for p in (valid_phone(v) for v in hints.get('phones') or []) if p]
    contact = _clean(hints.get('contact_person'),250)
    if contact:
        add_contact(c,uid,customer_id,contact,_clean(hints.get('email'),250),'',[{'number':p,'label':'Sonstige','source':provider} for p in phones])
    else:
        for p in phones: add_company_phone(c,uid,customer_id,p,'Sonstige',provider)
    if hints.get('device_id') or hints.get('device_name'):
        add_device(c,uid,customer_id,provider,hints.get('device_id'),hints.get('device_name'))
    return customer_id


def links(c, uid, provider):
    if provider not in PROVIDERS: return {}
    rows=c.execute('''SELECT l.external_key,l.customer_id,c.name customer_name FROM customer_provider_links l
                      JOIN customers c ON c.id=l.customer_id WHERE l.owner_id=? AND l.provider=?''',(uid,provider))
    return {r['external_key']:{'id':r['customer_id'],'name':r['customer_name']} for r in rows}


def list_all(c, uid):
    customers=[dict(r) for r in c.execute('SELECT id,name FROM customers WHERE owner_id=? ORDER BY name',(uid,))]
    profiles={r['customer_id']:dict(r) for r in c.execute('SELECT * FROM customer_profiles WHERE owner_id=?',(uid,))}
    phones={}
    for r in c.execute('SELECT id,customer_id,number,label,source FROM customer_phones WHERE owner_id=? ORDER BY id',(uid,)): phones.setdefault(r['customer_id'],[]).append(dict(r))
    contacts={}
    contact_phones={}
    for r in c.execute('SELECT id,customer_id,name,email,note FROM customer_contacts WHERE owner_id=? ORDER BY id',(uid,)): contacts.setdefault(r['customer_id'],[]).append(dict(r))
    for r in c.execute('SELECT id,contact_id,number,label,source FROM customer_contact_phones WHERE owner_id=? ORDER BY id',(uid,)): contact_phones.setdefault(r['contact_id'],[]).append(dict(r))
    devices={}
    for r in c.execute('SELECT id,customer_id,provider,external_id,name FROM customer_devices WHERE owner_id=? ORDER BY id',(uid,)): devices.setdefault(r['customer_id'],[]).append(dict(r))
    providers={}
    for r in c.execute('SELECT customer_id,provider,external_key,label FROM customer_provider_links WHERE owner_id=? ORDER BY id',(uid,)): providers.setdefault(r['customer_id'],[]).append(dict(r))
    for customer in customers:
        profile=profiles.get(customer['id'],{})
        cs=contacts.get(customer['id'],[])
        for contact in cs: contact['phones']=contact_phones.get(contact['id'],[])
        customer.update(email=profile.get('email',''),note=profile.get('note',''),phones=phones.get(customer['id'],[]),contacts=cs,
                        devices=devices.get(customer['id'],[]),provider_links=providers.get(customer['id'],[]))
    return customers


def _event_time(provider, raw):
    keys = ('startTime','start_date','updated_at','created_at','end_date')
    for key in keys:
        value=raw.get(key) if isinstance(raw,dict) else None
        if value: return _clean(value,80)
    return ''


def cache_rows(c, uid, provider, result):
    if provider not in PROVIDERS or not isinstance(result,dict): return
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    for row in result.get('rows') or []:
        if not isinstance(row,dict) or not row.get('external_key'): continue
        raw=row.get('raw') if isinstance(row.get('raw'),dict) else {}
        hint=row.get('customer_hint') if isinstance(row.get('customer_hint'),dict) else {}
        key=_clean(row.get('external_key'),255)
        summary=_clean(hint.get('name') or raw.get('callDescription') or raw.get('devicename') or raw.get('title'),500)
        c.execute('DELETE FROM provider_events WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key))
        c.execute('INSERT INTO provider_events(owner_id,provider,external_key,occurred_at,summary,raw_json,hint_json,captured_at) VALUES(?,?,?,?,?,?,?,?)',
                  (uid,provider,key,_event_time(provider,raw),summary,json.dumps(raw,ensure_ascii=False,default=str),json.dumps(hint,ensure_ascii=False,default=str),now))


def activity(c, uid, customer_id, limit=200):
    customer=_customer(c,uid,customer_id)
    if not customer: raise ValueError('Unbekannter Kunde.')
    phone_values=[]
    for r in c.execute('SELECT number FROM customer_phones WHERE owner_id=? AND customer_id=?',(uid,customer_id)): phone_values.append(r['number'])
    for r in c.execute('''SELECT p.number FROM customer_contact_phones p JOIN customer_contacts x ON x.id=p.contact_id
                          WHERE p.owner_id=? AND x.customer_id=?''',(uid,customer_id)): phone_values.append(r['number'])
    devices=[dict(r) for r in c.execute('SELECT provider,external_id,name FROM customer_devices WHERE owner_id=? AND customer_id=?',(uid,customer_id))]
    linked={(r['provider'],r['external_key']) for r in c.execute('SELECT provider,external_key FROM customer_provider_links WHERE owner_id=? AND customer_id=?',(uid,customer_id))}
    name=str(customer['name']).casefold(); matches=[]
    for r in c.execute('SELECT provider,external_key,occurred_at,summary,raw_json,hint_json,captured_at FROM provider_events WHERE owner_id=? ORDER BY captured_at DESC',(uid,)):
        raw_text=r['raw_json']; hint_text=r['hint_json']; matched=(r['provider'],r['external_key']) in linked
        if not matched and any(p and p in raw_text for p in phone_values): matched=True
        if not matched:
            for d in devices:
                if d['provider']==r['provider'] and ((d['external_id'] and d['external_id'] in raw_text) or (d['name'] and d['name'] in raw_text)): matched=True; break
        if not matched and name:
            try: matched=str(json.loads(hint_text).get('name') or '').casefold()==name
            except Exception: pass
        if matched:
            matches.append(dict(provider=r['provider'],external_key=r['external_key'],occurred_at=r['occurred_at'],summary=r['summary'],raw=json.loads(raw_text),hint=json.loads(hint_text)))
            if len(matches)>=limit: break
    return matches


def suggestions(c, uid):
    linked={(r['provider'],r['external_key']) for r in c.execute('SELECT provider,external_key FROM customer_provider_links WHERE owner_id=?',(uid,))}
    groups={}
    for r in c.execute('SELECT provider,external_key,summary,raw_json,hint_json FROM provider_events WHERE owner_id=? ORDER BY captured_at DESC',(uid,)):
        if (r['provider'],r['external_key']) in linked: continue
        try: hint=json.loads(r['hint_json']); raw=json.loads(r['raw_json'])
        except Exception: continue
        name=_clean(hint.get('name'),120)
        contact=_clean(hint.get('contact_person'),250)
        device=_clean(hint.get('device_name'),250)
        if not (name or contact or device): continue
        key=(name or contact or device).casefold()
        g=groups.setdefault(key,{'name':name or contact or device,'sources':set(),'contacts':set(),'phones':set(),'devices':{},'records':[]})
        g['sources'].add(r['provider'])
        if contact: g['contacts'].add(contact)
        for p in hint.get('phones') or []:
            p=valid_phone(p)
            if p: g['phones'].add(p)
        did=_clean(hint.get('device_id'),250)
        if device or did: g['devices'][did or device]=device
        if len(g['records'])<6: g['records'].append({'provider':r['provider'],'external_key':r['external_key'],'summary':r['summary'],'hint':hint,'raw':raw})
    out=[]
    for g in groups.values():
        g['sources']=sorted(g['sources']);g['contacts']=sorted(g['contacts']);g['phones']=sorted(g['phones']);g['devices']=[{'id':k,'name':v} for k,v in g['devices'].items()]
        out.append(g)
    return sorted(out,key=lambda x:(-len(x['sources']),x['name'].casefold()))[:300]


def starface_hint(description, raw):
    description=_clean(description,500); contact,company=description,''
    match=re.match(r'^\s*(.*?)\s*\(([^()]*)\)\s*$',description)
    if match: contact,company=match.group(1).strip(),match.group(2).strip()
    phones=[]
    for key in ('callerNumber','calledNumber','number'):
        value=valid_phone(raw.get(key) if isinstance(raw,dict) else '')
        if value and value not in phones: phones.append(value)
    return {'name':company or contact,'contact_person':contact if company else '','phones':phones}
