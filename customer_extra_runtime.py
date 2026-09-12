"""Billing addresses and customer locations for compact customer details."""
from urllib.parse import urlparse

import admin_controls
import system_features


def _clean(v,n=250):return str(v or '').strip()[:n]

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS customer_billing_addresses (
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      name TEXT NOT NULL DEFAULT '', street TEXT NOT NULL DEFAULT '', house_number TEXT NOT NULL DEFAULT '',
      zip_code TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT 'Deutschland',
      PRIMARY KEY(owner_id,customer_id)
    );
    CREATE TABLE IF NOT EXISTS customer_locations (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
      name TEXT NOT NULL, street TEXT NOT NULL DEFAULT '', house_number TEXT NOT NULL DEFAULT '',
      zip_code TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT 'Deutschland',
      phone TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_customer_locations_customer ON customer_locations(owner_id,customer_id,name);
    ''')


def payload(c,uid,cid):
    if not c.execute('SELECT 1 FROM customers WHERE id=? AND owner_id=?',(cid,uid)).fetchone():raise ValueError('Unbekannter Kunde.')
    billing=c.execute('SELECT name,street,house_number,zip_code,city,country FROM customer_billing_addresses WHERE owner_id=? AND customer_id=?',(uid,cid)).fetchone()
    locations=[dict(r) for r in c.execute('SELECT id,name,street,house_number,zip_code,city,country,phone FROM customer_locations WHERE owner_id=? AND customer_id=? ORDER BY name,id',(uid,cid))]
    return {'billing':dict(billing) if billing else {'name':'','street':'','house_number':'','zip_code':'','city':'','country':'Deutschland'},'locations':locations}


def install(app):
    original_init=app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:migrate(c)
    app.init_db=init_db
    previous=app.App.do_POST
    paths={'/api/v1/customers/extended','/api/v1/customers/billing/save','/api/v1/customers/location/save','/api/v1/customers/location/delete'}
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in paths:return previous(self)
        try:
            body=self.json_body();session=self.require(csrf=True)
            if not session:return
            uid=session['id'];cid=int(body.get('customer_id') or body.get('id') or 0)
            with app.db() as c:
                admin_controls.require_permission(c,uid,'customers.view' if path=='/api/v1/customers/extended' else 'customers.edit')
                if path=='/api/v1/customers/extended':return self.send_json(200,payload(c,uid,cid))
                if path=='/api/v1/customers/billing/save':
                    before=payload(c,uid,cid)['billing'];vals=tuple(_clean(body.get(k),500 if k=='name' else 250) for k in ('name','street','house_number','zip_code','city','country'))
                    c.execute('DELETE FROM customer_billing_addresses WHERE owner_id=? AND customer_id=?',(uid,cid));c.execute('INSERT INTO customer_billing_addresses(owner_id,customer_id,name,street,house_number,zip_code,city,country) VALUES(?,?,?,?,?,?,?,?)',(uid,cid,*vals));after=payload(c,uid,cid)['billing']
                    system_features.audit(c,uid,uid,'customer',cid,'billing_address_updated',{'old':before,'new':after});return self.send_json(200,{'ok':True,'billing':after})
                if path=='/api/v1/customers/location/save':
                    rid=int(body.get('location_id') or 0);vals={k:_clean(body.get(k),250) for k in ('name','street','house_number','zip_code','city','country','phone')}
                    if not vals['name']:raise ValueError('Bitte einen Namen für die Betriebsstätte eingeben.')
                    if rid:
                        before=c.execute('SELECT * FROM customer_locations WHERE id=? AND owner_id=? AND customer_id=?',(rid,uid,cid)).fetchone()
                        if not before:raise ValueError('Betriebsstätte nicht gefunden.')
                        c.execute('UPDATE customer_locations SET name=?,street=?,house_number=?,zip_code=?,city=?,country=?,phone=? WHERE id=?',(vals['name'],vals['street'],vals['house_number'],vals['zip_code'],vals['city'],vals['country'] or 'Deutschland',vals['phone'],rid));action='location_updated'
                    else:
                        rid=c.execute('INSERT INTO customer_locations(owner_id,customer_id,name,street,house_number,zip_code,city,country,phone) VALUES(?,?,?,?,?,?,?,?,?)',(uid,cid,vals['name'],vals['street'],vals['house_number'],vals['zip_code'],vals['city'],vals['country'] or 'Deutschland',vals['phone'])).lastrowid;action='location_added'
                    system_features.audit(c,uid,uid,'customer',cid,action,{'location_id':rid,'name':vals['name']});return self.send_json(200,{'ok':True,'location_id':rid})
                rid=int(body.get('location_id') or 0);row=c.execute('SELECT * FROM customer_locations WHERE id=? AND owner_id=? AND customer_id=?',(rid,uid,cid)).fetchone()
                if not row:raise ValueError('Betriebsstätte nicht gefunden.')
                c.execute('DELETE FROM customer_locations WHERE id=?',(rid,));system_features.audit(c,uid,uid,'customer',cid,'location_deleted',dict(row));return self.send_json(200,{'ok':True})
        except PermissionError as error:return self.send_json(403,{'error':str(error)})
        except (ValueError,TypeError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST
