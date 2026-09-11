import time
import unittest
from urllib.parse import urlsplit, parse_qs
from unittest.mock import patch
import test_workday as fixtures
import app
import starface_oauth as oauth


class StarfaceClientSecretTests(unittest.TestCase):
    setUp = fixtures.WorkdayTest.setUp
    tearDown = fixtures.WorkdayTest.tearDown

    def session(self, bearer=False):
        session = dict(id=self.uid, token_hash='sf-secret-session', bearer=bearer)
        with app.db() as c:
            if not c.execute('SELECT 1 FROM sessions WHERE token_hash=?', (session['token_hash'],)).fetchone():
                c.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                          (session['token_hash'], self.uid, 'csrf', int(time.time()) + 600))
        return session

    def configure(self, session):
        return oauth.start(app.db, session, {
            'configure_only': True,
            'domain': 'https://pbx.example.com',
            'client_id': 'rest-client',
            'client_secret': 'very-private-client-secret',
        }, app.DATA_DIR)

    def test_saved_client_secret_uses_basic_and_stays_server_side(self):
        web = self.session(False)
        self.configure(web)
        with patch.dict('os.environ', {'APP_PUBLIC_URL': 'https://time.example.com'}):
            prepared = oauth.start(app.db, web, {'desktop_prepare': True}, app.DATA_DIR)
        values = parse_qs(urlsplit(prepared['uri']).query)
        self.assertEqual(values['server'], ['https://time.example.com'])
        request = values['request'][0]
        native = dict(web, bearer=True)
        discovery = {
            'authorization_endpoint': 'https://pbx.example.com/auth',
            'token_endpoint': 'https://pbx.example.com/token',
            'token_endpoint_auth_methods_supported': ['client_secret_basic', 'client_secret_post'],
            'code_challenge_methods_supported': ['S256'],
        }
        with patch.object(oauth, 'request_url', return_value=discovery):
            started = oauth.start(app.db, native, {
                'launch_request': request,
                'redirect_uri': 'http://127.0.0.1:49152',
            }, app.DATA_DIR)
        query = parse_qs(urlsplit(started['url']).query)
        self.assertEqual(query['client_id'], ['rest-client'])
        token = {'access_token': 'access', 'refresh_token': 'refresh', 'expires_in': 3600, 'token_type': 'Bearer'}
        with patch.object(oauth, 'request_url', return_value=token) as call:
            oauth.finish(app.db, native, {'state': query['state'], 'code': ['code']}, app.DATA_DIR)
            body = call.call_args.args[2]
            auth = call.call_args.kwargs['auth']
            self.assertNotIn('client_secret', body)
            self.assertNotIn('client_id', body)
            self.assertEqual(auth['method'], 'client_secret_basic')
            self.assertEqual(auth['client_id'], 'rest-client')
            self.assertEqual(auth['client_secret'], 'very-private-client-secret')
        with app.db() as c:
            token_row = c.execute('SELECT secret FROM oauth_tokens WHERE owner_id=?', (self.uid,)).fetchone()
            integration_row = c.execute('SELECT secret FROM integrations WHERE owner_id=? AND provider=?', (self.uid, 'starface')).fetchone()
            self.assertNotIn('very-private-client-secret', token_row['secret'])
            self.assertNotIn('very-private-client-secret', integration_row['secret'])

    def test_client_secret_post_is_supported(self):
        session = self.session(True)
        self.configure(session)
        discovery = {
            'authorization_endpoint': 'https://pbx.example.com/auth',
            'token_endpoint': 'https://pbx.example.com/token',
            'token_endpoint_auth_methods_supported': ['client_secret_post'],
            'code_challenge_methods_supported': ['S256'],
        }
        with patch.object(oauth, 'request_url', return_value=discovery):
            started = oauth.start(app.db, session, {
                'domain': 'https://pbx.example.com',
                'redirect_uri': 'http://127.0.0.1:49153',
            }, app.DATA_DIR)
        query = parse_qs(urlsplit(started['url']).query)
        token = {'access_token': 'access', 'refresh_token': 'refresh', 'expires_in': 3600, 'token_type': 'Bearer'}
        with patch.object(oauth, 'request_url', return_value=token) as call:
            oauth.finish(app.db, session, {'state': query['state'], 'code': ['code']}, app.DATA_DIR)
            self.assertEqual(call.call_args.kwargs['auth']['method'], 'client_secret_post')

    def test_desktop_launch_request_is_one_time(self):
        web = self.session(False)
        self.configure(web)
        with patch.dict('os.environ', {'APP_PUBLIC_URL': 'https://time.example.com'}):
            prepared = oauth.start(app.db, web, {'desktop_prepare': True}, app.DATA_DIR)
        request = parse_qs(urlsplit(prepared['uri']).query)['request'][0]
        native = dict(web, bearer=True)
        discovery = {
            'authorization_endpoint': 'https://pbx.example.com/auth',
            'token_endpoint': 'https://pbx.example.com/token',
            'token_endpoint_auth_methods_supported': ['client_secret_basic'],
            'code_challenge_methods_supported': ['S256'],
        }
        with patch.object(oauth, 'request_url', return_value=discovery):
            oauth.start(app.db, native, {'launch_request': request, 'redirect_uri': 'http://127.0.0.1:49154'}, app.DATA_DIR)
            with self.assertRaisesRegex(ValueError, 'Desktop-Anfrage'):
                oauth.start(app.db, native, {'launch_request': request, 'redirect_uri': 'http://127.0.0.1:49155'}, app.DATA_DIR)


if __name__ == '__main__':
    unittest.main()
