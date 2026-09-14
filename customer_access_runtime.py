"""Company-wide customer records with field permissions and attributable changes.

Customer owner_id remains creation metadata. Provider archives and credentials
remain scoped to the signed-in employee.
"""
from functools import wraps
from urllib.parse import urlparse

import admin_controls as acl
import customer_data
import provider_archive
import provider_nav_runtime
import system_features


def required_permissions(path, body):
    if path in ('/api/v1/history/object', '/api/v1/audit/history'):
        if body.get('entity_type') == 'customer' or body.get('type') == 'customer':
            return {'customers.view_history'}
        return set()
    if path == '/api/v1/provider/assign/customer':
        return {'customers.links', 'customers.edit'}
    if path == '/api/v1/customers':
        return {'customers.create'}
    if not path.startswith('/api/v1/customers/'):
        return set()
    action = path.removeprefix('/api/v1/customers/')
    if action in ('data', 'detail', 'activity', 'extended'):
        return {'customers.view_basic'}
    if action == 'profile':
        return {'customers.edit' if body.get('id') else 'customers.create'}
    if action == 'master':
        return {'customers.edit' if body.get('save') else 'customers.view_basic'}
    if action in ('timeline',):
        return {'customers.view_history'}
    if action in ('links', 'link/candidates', 'workshop'):
        return {'customers.view_links'}
    if action in ('assign', 'zammad-organization', 'link/add', 'link/delete', 'device'):
        return {'customers.links', 'customers.edit'}
    if action in ('archive', 'delete'):
        return {'customers.' + action}
    return {'customers.edit'}


def filter_customer(customer, permissions):
    result = dict(customer)
    if 'customers.view_contacts' not in permissions:
        for key in ('email', 'contact_person', 'phones', 'contacts'):
            result.pop(key, None)
        if isinstance(result.get('master'), dict):
            result['master'] = {k: v for k, v in result['master'].items() if k != 'billing_email'}
    if 'customers.view_links' not in permissions:
        for key in ('devices', 'provider_links'):
            result.pop(key, None)
    return result


def filter_response(payload, permissions, starface):
    if not isinstance(payload, dict):
        return payload
    result = dict(payload)
    if 'customers' in result:
        result['customers'] = [filter_customer(row, permissions) for row in result['customers']]
    if isinstance(result.get('customer'), dict):
        result['customer'] = filter_customer(result['customer'], permissions)
    if 'customers.view_contacts' not in permissions:
        if 'master' in result:
            result['master'] = {k: v for k, v in result['master'].items() if k != 'billing_email'}
        if 'locations' in result:
            result['locations'] = [{k: v for k, v in r.items() if k != 'phone'} for r in result['locations']]
    if 'customers.view_links' not in permissions:
        for key in ('links', 'teamviewer_devices', 'zammad_organizations', 'zammad_assigned', 'zammad_tickets'):
            result.pop(key, None)
    for key in ('activity', 'events'):
        if key in result:
            result[key] = [row for row in result[key]
                           if 'customers.view_history' in permissions
                           and (row.get('provider') != 'starface' or starface['connected'])]
    result['starface_status'] = starface
    return result


def filter_history(payload, permissions):
    hidden = set()
    if 'customers.view_contacts' not in permissions:
        hidden.update({'email', 'billing_email', 'contact_person', 'contacts', 'phones', 'number', 'contact_id'})
    if 'customers.view_links' not in permissions:
        hidden.update({'devices', 'provider_links', 'external_key', 'link_value'})
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key not in hidden}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    rows = []
    for row in payload.get('history', []):
        action = row.get('action', '')
        if 'contacts' in hidden and any(part in action for part in ('contact', 'phone')):
            continue
        if 'devices' in hidden and any(part in action for part in ('device', 'link')):
            continue
        rows.append({**row, 'changes': clean(row.get('changes', {}))})
    return {**payload, 'history': rows}


def audit_change(c, uid, cid, action, before, after):
    if before != after:
        system_features.audit(c, uid, uid, 'customer', cid, action, {'old': before, 'new': after})


def _phone_customer(c, body):
    pid = int(body.get('id') or 0)
    if body.get('scope') == 'contact':
        row = c.execute('SELECT x.customer_id FROM customer_contact_phones p JOIN customer_contacts x ON x.id=p.contact_id WHERE p.id=?', (pid,)).fetchone()
    else:
        row = c.execute('SELECT customer_id FROM customer_phones WHERE id=?', (pid,)).fetchone()
    return row['customer_id'] if row else None


def install(app):
    # The audit insert uses the mutation's connection, so it commits or rolls
    # back with the change. Existing profile/contact/address events are retained.
    def wrap_change(module, name, customer_id):
        original = getattr(module, name)
        @wraps(original)
        def changed(c, uid, *args, **kwargs):
            cid = customer_id(c, args)
            before = customer_data.get_one(c, uid, cid) if cid else {}
            result = original(c, uid, *args, **kwargs)
            if name == 'create':
                cid = result
            if cid:
                after = customer_data.get_one(c, uid, cid)
                # Never write provider cache contents or credentials to CRM history.
                before.pop('provider_links', None)
                after.pop('provider_links', None)
                audit_change(c, uid, cid, name, before, after)
            return result
        setattr(module, name, changed)

    for name in ('add_company_phone', 'add_contact', 'add_device'):
        wrap_change(customer_data, name, lambda c, args: int(args[0]))
    def contact_customer(c, args):
        row = c.execute('SELECT customer_id FROM customer_contacts WHERE id=?', (int(args[0]),)).fetchone()
        return row['customer_id'] if row else None
    wrap_change(customer_data, 'add_contact_phone', contact_customer)
    wrap_change(customer_data, 'create', lambda c, args: None)
    for name in ('phone_update', 'phone_delete'):
        wrap_change(provider_archive, name, lambda c, args: _phone_customer(c, args[0]))
    original_master = acl.save_customer_master
    def save_master(c, uid, cid, body):
        before = acl.customer_master(c, uid, cid)
        result = original_master(c, uid, cid, body)
        audit_change(c, uid, cid, 'master_updated', before, acl.customer_master(c, uid, cid))
        return result
    acl.save_customer_master = save_master

    previous = app.App.do_POST
    def do_POST(self):
        path = urlparse(self.path).path
        relevant = path.startswith('/api/v1/customers') or path in (
            '/api/v1/history/object', '/api/v1/audit/history', '/api/v1/provider/assign/customer')
        if not relevant:
            return previous(self)
        try:
            body = self.json_body()
            if not isinstance(body, dict):
                raise ValueError('Eine JSON-Struktur ist erforderlich.')
            session = self.require(csrf=True)
            if not session:
                return
            with app.db(read_only=True) as c:
                uid = session['id']
                permissions = acl.permissions_for_user(c, uid)
                for permission in required_permissions(path, body):
                    acl.require_permission(c, uid, permission)
                if body.get('new_customer'):
                    acl.require_permission(c, uid, 'customers.create')
                starface = provider_nav_runtime.provider_status(app, c, uid, 'starface')
        except PermissionError as error:
            return self.send_json(403, {'error': str(error)})
        except (ValueError, TypeError) as error:
            return self.send_json(400, {'error': str(error)})
        send = self.send_json
        def filtered(status, payload, *args, **kwargs):
            if status == 200 and path.startswith('/api/v1/customers'):
                payload = filter_response(payload, permissions, starface)
            elif status == 200 and body.get('entity_type') == 'customer' and 'history' in payload:
                payload = filter_history(payload, permissions)
            return send(status, payload, *args, **kwargs)
        self.send_json = filtered
        try:
            return previous(self)
        finally:
            self.send_json = send
    app.App.do_POST = do_POST
