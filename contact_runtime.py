"""Small runtime extension for editing customer contacts with audit history."""
from urllib.parse import urlparse

import customer_data
import system_features


def install(app):
    # customer_runtime calls customer_data.update dynamically, so wrapping it here
    # captures company-name/profile edits without changing the legacy route.
    original_customer_update = customer_data.update
    def customer_update(c, uid, customer_id, body):
        row = c.execute('''SELECT c.name,p.email,p.note FROM customers c
                           LEFT JOIN customer_profiles p ON p.customer_id=c.id AND p.owner_id=c.owner_id
                           WHERE c.id=? AND c.owner_id=?''', (customer_id, uid)).fetchone()
        before = dict(row) if row else {}
        result = original_customer_update(c, uid, customer_id, body)
        row = c.execute('''SELECT c.name,p.email,p.note FROM customers c
                           LEFT JOIN customer_profiles p ON p.customer_id=c.id AND p.owner_id=c.owner_id
                           WHERE c.id=? AND c.owner_id=?''', (customer_id, uid)).fetchone()
        after = dict(row) if row else {}
        changes = {key: {'old': before.get(key) or '', 'new': after.get(key) or ''}
                   for key in after if (before.get(key) or '') != (after.get(key) or '')}
        if changes:
            system_features.audit(c, uid, uid, 'customer', customer_id, 'profile_updated', changes)
        return result
    customer_data.update = customer_update

    previous_post = app.App.do_POST

    def do_POST(self):
        path = urlparse(self.path).path
        if path != '/api/v1/customers/contact/update':
            return previous_post(self)
        try:
            body = self.json_body()
            if not isinstance(body, dict):
                raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:
            return self.send_json(400, {'error': str(error)})
        session = self.require(csrf=True)
        if not session:
            return
        uid = session['id']
        try:
            contact_id = int(body.get('id') or 0)
            name = str(body.get('name') or '').strip()[:250]
            email = str(body.get('email') or '').strip()[:250]
            note = str(body.get('note') or '').strip()[:2000]
            if not name:
                raise ValueError('Bitte einen Namen für den Ansprechpartner eingeben.')
            with app.db() as c:
                row = c.execute('SELECT customer_id,name,email,note FROM customer_contacts WHERE id=? AND owner_id=?', (contact_id, uid)).fetchone()
                if not row:
                    raise ValueError('Ansprechpartner nicht gefunden.')
                before = dict(row)
                c.execute('UPDATE customer_contacts SET name=?,email=?,note=? WHERE id=? AND owner_id=?', (name, email, note, contact_id, uid))
                after = {'customer_id': before['customer_id'], 'name': name, 'email': email, 'note': note}
                changes = {key: {'old': before.get(key) or '', 'new': after.get(key) or ''}
                           for key in ('name','email','note') if (before.get(key) or '') != (after.get(key) or '')}
                if changes:
                    system_features.audit(c, uid, uid, 'customer', before['customer_id'], 'contact_updated',
                                          {'contact_id': contact_id, **changes})
            return self.send_json(200, {'ok': True})
        except (ValueError, TypeError) as error:
            return self.send_json(400, {'error': str(error)})

    app.App.do_POST = do_POST
