import base64
import hashlib
import json
import threading
import urllib.request
import urllib.error
import http.cookiejar
import unittest
from unittest.mock import patch
import test_workday as fixtures
import app
import integrations


class IntegrationTests(unittest.TestCase):
    setUp=fixtures.WorkdayTest.setUp
    tearDown=fixtures.WorkdayTest.tearDown

    def data(self,provider='zammad'):
        return dict(provider=provider,domain='https://webapi.teamviewer.com' if provider=='teamviewer' else 'https://support.example.com',username='0001',secret='TopSecret-password')

    def test_encrypted_storage_and_host_binding(self):
        body=self.data()
        with app.db() as c:
            integrations.save(c,self.uid,body,app.DATA_DIR)
        with app.db() as c:
            row=c.execute('SELECT * FROM integrations').fetchone()
            self.assertNotIn(body['secret'],row['secret'])
            self.assertNotIn(row['secret'],json.dumps(integrations.list_configs(c,self.uid)))
            self.assertNotIn(body['secret'],json.dumps(integrations.list_configs(c,self.uid)))
            blank={**body,'secret':''}
            self.assertEqual(integrations.config(c,self.uid,blank,app.DATA_DIR)['secret'],body['secret'])
            with self.assertRaises(ValueError):
                integrations.config(c,self.uid,{**blank,'domain':'https://other.example.com'},app.DATA_DIR)
            with self.assertRaises(ValueError):
                integrations.config(c,self.uid+1,blank,app.DATA_DIR)
            with self.assertRaises(ValueError):
                integrations.config(c,self.uid,{**blank,'username':'someone-else'},app.DATA_DIR)

    def test_domains_and_ssrf_restrictions(self):
        self.assertEqual(integrations.domain('support.example.com/api/v1','zammad'),'https://support.example.com')
        self.assertEqual(integrations.domain('https://pbx.example.com:8443/rest','starface'),'https://pbx.example.com:8443')
        for value in ('http://support.example.com','https://user:pass@example.com','https://example.com/?x=1','https://example.com/path','https://example.com\n'):
            if value.endswith('\n'): continue  # surrounding whitespace is normalized
            with self.assertRaises(ValueError): integrations.domain(value,'zammad')
        with self.assertRaises(ValueError): integrations.domain('https://evil.example.com','teamviewer')
        for ip in ('127.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1','224.0.0.1','0.0.0.0'):
            self.assertFalse(integrations.allowed_address(ip),ip)
        for ip in ('192.168.1.2','10.0.0.5','8.8.8.8'):
            self.assertTrue(integrations.allowed_address(ip),ip)
        with patch('integrations.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('integrations.socket.create_connection') as connect:
            with self.assertRaises(ValueError): integrations.Connection('example.com',443).connect()
            connect.assert_not_called()

    def run_probe(self,provider,responses):
        calls=[]
        class FakeClient:
            def __init__(self,origin): pass
            def request(self,path,headers=None,body=None):
                calls.append((path,headers,body))
                item=responses[len(calls)-1]
                if isinstance(item,Exception): raise item
                return item
        return integrations.diagnose(self.data(provider),FakeClient),calls

    def test_teamviewer_script_token_and_reports(self):
        result,calls=self.run_probe('teamviewer',[(200,{'token_valid':True},'OK'),(200,{'records':[{'id':'c1','start_date':'2026-09-10T08:00:00Z','end_date':'2026-09-10T09:00:00Z','deviceid':'pc1','password':'TopSecret-password'}]},'OK')])
        self.assertTrue(result['ok'])
        self.assertTrue(all(c['found'] for c in result['checks']))
        self.assertEqual(calls[0][1]['Authorization'],'Bearer TopSecret-password')
        self.assertNotIn('TopSecret-password',json.dumps(result))
        result,calls=self.run_probe('teamviewer',[(200,{'token_valid':False},'OK')])
        self.assertFalse(result['ok']);self.assertEqual(len(calls),1)

    def test_zammad_basic_auth_and_permission_failure(self):
        result,calls=self.run_probe('zammad',[(200,{'id':1,'email':'person@example.com'},'OK'),(403,None,'Zugriff verweigert.')])
        self.assertFalse(result['ok'])
        self.assertEqual(calls[0][1]['Authorization'],'Basic '+base64.b64encode(b'0001:TopSecret-password').decode())
        self.assertEqual(result['steps'][1]['status'],403)

    def test_starface_challenge_and_redaction(self):
        result,calls=self.run_probe('starface',[(200,{'loginType':'Internal','nonce':'abc'},'OK'),(200,{'authToken':'SuperPrivateToken'},'OK'),(200,[{'id':7,'login':'0001','firstName':'Tobi','password':'TopSecret-password','name':'SuperPrivateToken'}],'OK')])
        self.assertTrue(result['ok'])
        expected='0001:'+hashlib.sha512(('0001abc'+hashlib.sha512(b'TopSecret-password').hexdigest()).encode()).hexdigest()
        self.assertEqual(calls[1][2]['secret'],expected)
        self.assertEqual(calls[2][1]['authToken'],'SuperPrivateToken')
        self.assertNotIn('SuperPrivateToken',json.dumps(result))
        self.assertNotIn('TopSecret-password',json.dumps(result))
        self.assertNotIn(expected,json.dumps(result))

    def test_timeout_and_non_json_are_not_success(self):
        result,_=self.run_probe('zammad',[TimeoutError()])
        self.assertFalse(result['ok'])
        result,_=self.run_probe('zammad',[(200,None,'Keine gültige JSON-Antwort.')])
        self.assertFalse(result['ok'])

    def test_static_files_cannot_expose_key(self):
        handler=object.__new__(app.App)
        for path in ('/../data/integration.key','/%2e%2e/data/integration.key','/..%5cdata%5cintegration.key'):
            self.assertEqual(handler.translate_path(path),str(app.STATIC/'__not_found__'))

    def test_admin_api_save_test_remove_and_user_denial(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.App)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:%d'%server.server_port
        client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        csrf=''
        def req(route,body=None):
            request=urllib.request.Request(base+route,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
            with client.open(request) as response: return json.load(response)
        try:
            req('/api/v1/login',{'username':'admin','password':'admin'})
            csrf=req('/api/v1/me')['csrf']
            req('/api/v1/integrations/save',self.data())
            listed=req('/api/v1/integrations')
            self.assertNotIn('TopSecret-password',json.dumps(listed))
            self.assertTrue(next(r for r in listed['integrations'] if r['provider']=='zammad')['has_secret'])
            with patch('integrations.diagnose',return_value={'ok':True,'steps':[]}) as probe:
                req('/api/v1/integrations/test',{**self.data(),'secret':''})
                self.assertEqual(probe.call_args.args[0]['secret'],'TopSecret-password')
            req('/api/v1/integrations/remove',{'provider':'zammad'})
            self.assertFalse(next(r for r in req('/api/v1/integrations')['integrations'] if r['provider']=='zammad')['has_secret'])
            with app.db() as c:
                c.execute("INSERT INTO users(username,password_salt,password_hash,role,created_at) SELECT 'normal',password_salt,password_hash,'user',created_at FROM users WHERE id=?",(self.uid,))
            req('/api/v1/logout',{})
            req('/api/v1/login',{'username':'normal','password':'admin'})
            csrf=req('/api/v1/me')['csrf']
            for route,body in [('/api/v1/integrations',None),('/api/v1/integrations/save',self.data()),('/api/v1/integrations/test',self.data())]:
                with self.assertRaises(urllib.error.HTTPError) as error: req(route,body)
                self.assertEqual(error.exception.code,403)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    unittest.main()
