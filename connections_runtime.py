"""Fast local-only settings payload for integration configuration."""
import time
from urllib.parse import urlparse

import integrations
import starface_oauth


def connection_payload(c, uid):
    data = integrations.list_configs(c, uid)
    for item in data:
        if item['provider'] == 'starface':
            try:
                item['has_secret'] = bool(c.execute(
                    'SELECT 1 FROM oauth_tokens WHERE owner_id=?', (uid,)
                ).fetchone())
            except Exception:
                item['has_secret'] = False
            item['auth_mode'] = 'oauth'
    return data


def install(app):
    previous_post = app.App.do_POST

    def do_POST(self):
        if urlparse(self.path).path != '/api/v1/settings/connections':
            return previous_post(self)
        started = time.monotonic()
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
                data = connection_payload(c, session['id'])
                try:
                    callback = starface_oauth.callback_url()
                except ValueError:
                    callback = ''
            return self.send_json(200, {
                'integrations': data,
                'starface_callback': callback,
                'source': 'local',
                'duration_ms': round((time.monotonic() - started) * 1000),
            })
        except Exception as error:
            return self.send_json(500, {'error': 'Verbindungseinstellungen konnten nicht geladen werden.', 'detail': str(error)[:300]})

    app.App.do_POST = do_POST
