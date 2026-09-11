"""Customer master data and links to external provider records."""
import re
import sqlite3

PROVIDERS = ('starface', 'zammad', 'teamviewer')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS customer_profiles (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      contact_person TEXT NOT NULL DEFAULT '',
      email TEXT NOT NULL DEFAULT '',
      note TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,customer_id)
    );
    CREATE TABLE IF NOT EXISTS customer_phones (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      number TEXT NOT NULL,
      label TEXT NOT NULL DEFAULT '',
      source TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,customer_id,number)
    );
    CREATE TABLE IF NOT EXISTS customer_devices (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      provider TEXT NOT NULL,
      external_id TEXT NOT NULL,
      name TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,customer_id,provider,external_id)
    );
    CREATE TABLE IF NOT EXISTS customer_provider_links (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      provider TEXT NOT NULL,
      external_key TEXT NOT NULL,
      label TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,provider,external_key)
    );
    ''')


def _clean(value, limit=500):
    value = str(value or '').strip()
    return value[:limit]


def _customer(c, uid, customer_id):
    return c.execute('SELECT id,name FROM customers WHERE id=? AND owner_id=?', (customer_id, uid)).fetchone()


def create(c, uid, body):
    name = _clean(body.get('name'), 120)
    if not name:
        raise ValueError('Bitte einen Kundennamen eingeben.')
    try:
        cursor = c.execute('INSERT INTO customers(owner_id,name) VALUES(?,?)', (uid, name))
        customer_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        row = c.execute('SELECT id FROM customers WHERE owner_id=? AND name=?', (uid, name)).fetchone()
        if not row:
            raise
        customer_id = row['id']
    update(c, uid, customer_id, body)
    return customer_id


def update(c, uid, customer_id, body):
    if not _customer(c, uid, customer_id):
        raise ValueError('Unbekannter Kunde.')
    name = _clean(body.get('name'), 120)
    if name:
        try:
            c.execute('UPDATE customers SET name=? WHERE id=? AND owner_id=?', (name, customer_id, uid))
        except sqlite3.IntegrityError:
            raise ValueError('Ein Kunde mit diesem Namen existiert bereits.') from None
    contact = _clean(body.get('contact_person'), 250)
    email = _clean(body.get('email'), 250)
    note = _clean(body.get('note'), 2000)
    c.execute('DELETE FROM customer_profiles WHERE owner_id=? AND customer_id=?', (uid, customer_id))
    c.execute('INSERT INTO customer_profiles(owner_id,customer_id,contact_person,email,note) VALUES(?,?,?,?,?)',
              (uid, customer_id, contact, email, note))
    for item in body.get('phones') or []:
        number = _clean(item.get('number') if isinstance(item, dict) else item, 120)
        if not number:
            continue
        label = _clean(item.get('label') if isinstance(item, dict) else '', 80)
        source = _clean(item.get('source') if isinstance(item, dict) else '', 40)
        c.execute('INSERT OR IGNORE INTO customer_phones(owner_id,customer_id,number,label,source) VALUES(?,?,?,?,?)',
                  (uid, customer_id, number, label, source))
    return customer_id


def assign(c, uid, body):
    provider = _clean(body.get('provider'), 40).lower()
    key = _clean(body.get('external_key'), 255)
    if provider not in PROVIDERS or not key:
        raise ValueError('Ungültige Provider-Zuordnung.')
    customer_id = body.get('customer_id')
    if body.get('new_customer'):
        customer_id = create(c, uid, body['new_customer'])
    try:
        customer_id = int(customer_id)
    except (TypeError, ValueError):
        raise ValueError('Bitte einen Kunden auswählen.') from None
    if not _customer(c, uid, customer_id):
        raise ValueError('Unbekannter Kunde.')
    c.execute('DELETE FROM customer_provider_links WHERE owner_id=? AND provider=? AND external_key=?', (uid, provider, key))
    c.execute('INSERT INTO customer_provider_links(owner_id,customer_id,provider,external_key,label) VALUES(?,?,?,?,?)',
              (uid, customer_id, provider, key, _clean(body.get('label'), 250)))
    hints = body.get('hints') if isinstance(body.get('hints'), dict) else {}
    for number in hints.get('phones') or []:
        number = _clean(number, 120)
        if number:
            c.execute('INSERT OR IGNORE INTO customer_phones(owner_id,customer_id,number,label,source) VALUES(?,?,?,?,?)',
                      (uid, customer_id, number, 'Rufnummer', provider))
    device_id = _clean(hints.get('device_id'), 250)
    device_name = _clean(hints.get('device_name'), 250)
    if device_id or device_name:
        external_id = device_id or device_name
        c.execute('INSERT OR IGNORE INTO customer_devices(owner_id,customer_id,provider,external_id,name) VALUES(?,?,?,?,?)',
                  (uid, customer_id, provider, external_id, device_name))
    return customer_id


def links(c, uid, provider):
    if provider not in PROVIDERS:
        return {}
    rows = c.execute('''SELECT l.external_key,l.customer_id,c.name customer_name
                        FROM customer_provider_links l JOIN customers c ON c.id=l.customer_id
                        WHERE l.owner_id=? AND l.provider=?''', (uid, provider))
    return {r['external_key']: {'id': r['customer_id'], 'name': r['customer_name']} for r in rows}


def list_all(c, uid):
    customers = [dict(r) for r in c.execute('SELECT id,name FROM customers WHERE owner_id=? ORDER BY name', (uid,))]
    profiles = {r['customer_id']: dict(r) for r in c.execute('SELECT * FROM customer_profiles WHERE owner_id=?', (uid,))}
    phones = {}
    for r in c.execute('SELECT customer_id,number,label,source FROM customer_phones WHERE owner_id=? ORDER BY id', (uid,)):
        phones.setdefault(r['customer_id'], []).append(dict(r))
    devices = {}
    for r in c.execute('SELECT customer_id,provider,external_id,name FROM customer_devices WHERE owner_id=? ORDER BY id', (uid,)):
        devices.setdefault(r['customer_id'], []).append(dict(r))
    providers = {}
    for r in c.execute('SELECT customer_id,provider,external_key,label FROM customer_provider_links WHERE owner_id=? ORDER BY id', (uid,)):
        providers.setdefault(r['customer_id'], []).append(dict(r))
    result = []
    for customer in customers:
        profile = profiles.get(customer['id'], {})
        customer.update(contact_person=profile.get('contact_person', ''), email=profile.get('email', ''), note=profile.get('note', ''),
                        phones=phones.get(customer['id'], []), devices=devices.get(customer['id'], []), provider_links=providers.get(customer['id'], []))
        result.append(customer)
    return result


def starface_hint(description, raw):
    description = _clean(description, 500)
    contact, company = description, ''
    match = re.match(r'^\s*(.*?)\s*\(([^()]*)\)\s*$', description)
    if match:
        contact, company = match.group(1).strip(), match.group(2).strip()
    phones = []
    for key in ('callerNumber', 'calledNumber', 'number'):
        value = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(value, str) and value.strip() and value.strip() not in phones:
            phones.append(value.strip())
    return {'name': company or contact, 'contact_person': contact if company else '', 'phones': phones}
