import base64
import hashlib
import json
import time
import threading
import unittest
import urllib.request
import urllib.error
from urllib.parse import urlsplit, parse_qs
from unittest.mock import patch
import test_workday as fixtures
import app
import starface_oauth as oauth
import integrations


class OAuthTests(unittest.TestCase):
    setUp = fixtures.WorkdayTest.setUp
    tearDown = fixtures.WorkdayTest.tearDown

    def session(self):
        session = dict(id=self.uid, token_hash='test-session', bearer=False)
        with app.db() as c:
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)', (session['token_hash'], self.uid, 'csrf', int(time.time()) + 600))
        return session

    def begin(self, session):
        with patch.dict('os.environ', {'APP_PUBLIC_URL':'https://time.example.com'}), patch.object(oauth, 'request_url', return_value={
            'authorization_endpoint':'https://pbx.example.com/auth/authorize', 'token_endpoint':'https://pbx.example.com/auth/token'}):
            return oauth.start(app.db, session, {'domain':'https://pbx.example.com'}, app.DATA_DIR)

    def test_pkce_callback_encryption_and_replay(self):
        session = self.session()
        result = self.begin(session)
        query = parse_qs(urlsplit(result['url']).query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['redirect_uri'], ['https://time.example.com' + oauth.CALLBACK])
        token = {'access_token':'private-access', 'refresh_token':'private-refresh', 'expires_in':3600, 'token_type':'Bearer'}
        with patch.object(oauth,'request_url',return_value=token) as request:
            oauth.finish(app.db, session, {'state':query['state'], 'code':['test-code']}, app.DATA_DIR)
            verifier = request.call_args.args[2]['code_verifier']
            self.assertEqual(query['code_challenge'][0],base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='))
            with self.assertRaises(ValueError):
                oauth.finish(app.db, session, {'state':query['state'], 'code':['test-code']}, app.DATA_DIR)
        with app.db() as c:
            row = c.execute('SELECT secret FROM oauth_tokens').fetchone()
            self.assertNotIn('private-access', row['secret'])
            self.assertNotIn('private-refresh', row['secret'])
            self.assertEqual(oauth.access(c,self.uid,app.DATA_DIR)['secret'],'private-access')

    def test_state_session_expiry_and_host_binding(self):
        session=self.session(); query=parse_qs(urlsplit(self.begin(session)['url']).query)
        with self.assertRaises(ValueError):
            oauth.finish(app.db, dict(session,token_hash='other-session'), {'state':query['state'],'code':['x']},app.DATA_DIR)
        with app.db() as c:
            c.execute('UPDATE oauth_states SET expires_at=0')
        with self.assertRaises(ValueError):
            oauth.finish(app.db,session,{'state':query['state'],'code':['x']},app.DATA_DIR)
        with self.assertRaises(ValueError):
            oauth.endpoint('https://evil.example.com/token','https://pbx.example.com')
        with self.assertRaises(ValueError):
            oauth.endpoint('http://pbx.example.com/token','https://pbx.example.com')

    def test_refresh_rotates_and_provider_token_is_redacted(self):
        data=dict(origin='https://pbx.example.com',token_endpoint='https://pbx.example.com/token',client_id='rest-client',
                  redirect_uri='https://time.example.com'+oauth.CALLBACK,access_token='old-access',refresh_token='old-refresh',expires_at=0)
        with app.db() as c:
            c.execute('INSERT INTO oauth_tokens VALUES(?,?)',(self.uid,oauth.pack(data,app.DATA_DIR)))
            with patch.object(oauth,'request_url',return_value={'access_token':'new-access','refresh_token':'new-refresh','expires_in':3600,'token_type':'Bearer'}) as req:
                actual=oauth.access(c,self.uid,app.DATA_DIR)
                self.assertEqual(req.call_args.args[2]['grant_type'],'refresh_token')
                self.assertEqual(actual['secret'],'new-access')
            saved=oauth.unpack(c.execute('SELECT secret FROM oauth_tokens').fetchone()['secret'],app.DATA_DIR)
            self.assertEqual(saved['refresh_token'],'new-refresh')
        class Fake:
            def __init__(self, origin): pass
            def request(self,path,headers=None,body=None):
                self.headers=headers
                return 200,[{'id':1,'name':'new-access'}],'OK'
        result=integrations.diagnose(actual,Fake)
        self.assertTrue(result['ok'])
        self.assertNotIn('new-access',json.dumps(result))

    def test_native_token_cannot_be_cookie_and_revoke(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.App)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:%s'%server.server_port
        def request(path,body=None,headers=None):
            req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type':'application/json',**(headers or {})})
            with urllib.request.urlopen(req) as response:return json.load(response)
        try:
            result=request('/api/v1/auth/token',{'username':'admin','password':'admin','client_name':'Windows Test'})
            bearer={'Authorization':'Bearer '+result['access_token']}
            self.assertEqual(request('/api/v1/me',headers=bearer)['user']['id'],self.uid)
            request('/api/v1/work/begin',{},bearer)
            with self.assertRaises(urllib.error.HTTPError) as error:
                request('/api/v1/me',headers={'Cookie':'pz_session='+result['access_token']})
            self.assertEqual(error.exception.code,401)
            request('/api/v1/auth/revoke',{},bearer)
            with self.assertRaises(urllib.error.HTTPError):request('/api/v1/me',headers=bearer)
        finally:
            server.shutdown();server.server_close();thread.join()
