"""Runtime extension for customer master data without duplicating the main HTTP app."""
from urllib.parse import urlparse
import customer_data


def install(app):
    original_init = app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:
            customer_data.migrate(c)
    app.init_db = init_db

    original_dashboard = app.App.dashboard
    def dashboard(self, session):
        # Keep the existing dashboard response untouched. Rich customer data is
        # deliberately loaded through /api/v1/customers/data to avoid changing
        # the compact dashboard contract.
        return original_dashboard(self, session)
    app.App.dashboard = dashboard

    original_post = app.App.do_POST
    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ('/api/v1/customers/data','/api/v1/customers/assign','/api/v1/customers/profile'):
            return original_post(self)
        try:
            body = self.json_body()
            if not isinstance(body, dict):
                raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:
            return self.send_json(400, {'error': str(error)})
        session = self.require(csrf=True)
        if not session:
            return
        try:
            with app.db() as c:
                if path == '/api/v1/customers/data':
                    providers = {p: customer_data.links(c, session['id'], p) for p in customer_data.PROVIDERS}
                    return self.send_json(200, {'customers': customer_data.list_all(c, session['id']), 'links': providers})
                if path == '/api/v1/customers/assign':
                    customer_id = customer_data.assign(c, session['id'], body)
                    return self.send_json(200, {'ok': True, 'customer_id': customer_id})
                customer_id = body.get('id')
                if customer_id:
                    customer_id = int(customer_id)
                    customer_data.update(c, session['id'], customer_id, body)
                else:
                    customer_id = customer_data.create(c, session['id'], body)
                return self.send_json(200, {'ok': True, 'customer_id': customer_id})
        except (ValueError, TypeError) as error:
            return self.send_json(400, {'error': str(error)})
    app.App.do_POST = do_POST


def serve(app):
    install(app)
    app.init_db()
    print('ProjektZeit Web läuft auf http://%s:%d' % (app.HOST, app.PORT))
    app.ThreadingHTTPServer((app.HOST, app.PORT), app.App).serve_forever()
