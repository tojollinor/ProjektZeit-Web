import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from xmlrpc.client import dumps, loads, Fault
from urllib.parse import parse_qs, urlsplit
import starface_calls as sf

CONFIG = dict(domain='https://pbx.example.com', secret='private-token', days=30)


class CallsTest(unittest.TestCase):
    def result(self, entries, **config):
        rpc = Mock()
        rpc.call.side_effect = [True, {'entries': entries, 'totalCount': len(entries)}, True]
        result = sf.load(dict(CONFIG, **config), lambda _: rpc)
        return result, rpc

    def test_personal_calls_numbers_times_and_missed_direction(self):
        rows = [dict(direction=d, result=r, callerNumber='00123', calledNumber='00456', startTime=datetime(2026,9,11,23,59,30), duration=90)
                for d,r in [('INBOUND','MISSED'),('OUTBOUND','MISSED'),('OUTBOUND','ANSWERED')]]
        result, rpc = self.result(rows + [dict(rows[0],groupId='group-1')])
        self.assertEqual(len(result['rows']), 3)
        self.assertEqual(result['rows'][0]['cells'][:4], ['Eingehend','Verpasst','00123','00456'])
        self.assertEqual(result['rows'][1]['cells'][1], 'Nicht erreicht')
        self.assertEqual(result['rows'][2]['cells'][5:8], ['2026-09-11T23:59:30+00:00','2026-09-12T00:01:00+00:00','00:01:30'])
        self.assertTrue(result['rows'][2]['end_calculated'])
        self.assertEqual(rpc.call.call_args_list[1].args[1][2:5], ('','','NON_GROUP'))
        self.assertEqual(rpc.call.call_args_list[-1].args, ('connection.logout',))

    def test_filter_is_sent_to_pbx_and_checked_on_response(self):
        records = [dict(direction='INBOUND',result='MISSED',duration=0),dict(direction='OUTBOUND',result='MISSED')]
        result,rpc=self.result(records,call_type='missed')
        self.assertEqual(len(result['rows']),1)
        self.assertEqual(result['rows'][0]['cells'][7],'00:00:00')
        self.assertIsNone(result['rows'][0]['cells'][6])
        self.assertEqual(rpc.call.call_args_list[1].args[1][2:4],('INBOUND','MISSED'))

    def test_invalid_duration_and_secret_redaction(self):
        result,_=self.result([dict(direction='OUTBOUND',duration=-3,calledNumber='private-token',startTime='2026-09-11T12:00:00Z')])
        row=result['rows'][0]
        self.assertIsNone(row['cells'][6]);self.assertIsNone(row['duration_seconds'])
        self.assertNotIn('private-token',str(result))
        with self.assertRaises(ValueError):self.result([],call_type='../all')
        with self.assertRaises(ValueError):self.result([],offset=-1)

    def test_pagination(self):
        result,_=self.result([dict(direction='INBOUND')]*100,offset=100)
        # A total of 100 means there is no later page, even for a full response.
        self.assertIsNone(result['next_offset'])
        rpc=Mock();rpc.call.side_effect=[True,{'entries':[dict(direction='INBOUND')]*100,'totalCount':220},True]
        self.assertEqual(sf.load(dict(CONFIG,offset=100),lambda _:rpc)['next_offset'],200)

    def test_logout_on_failure(self):
        rpc=Mock();rpc.call.side_effect=[True,ValueError('failed'),True]
        with self.assertRaises(ValueError):sf.load(CONFIG,lambda _:rpc)
        self.assertEqual(rpc.call.call_args.args,('connection.logout',))

    def test_version_unavailable_does_not_break_connection(self):
        client=Mock();client.request.return_value=(403,None,'forbidden')
        self.assertIsNone(sf.server_info(CONFIG,lambda _:client)['version'])
        client.request.return_value=(200,{'version':'10.0.1.6'},'OK')
        self.assertEqual(sf.server_info(CONFIG,lambda _:client)['version'],'10.0.1.6')
        self.assertEqual(client.request.call_args.args[0],'/rest/server/version')

    @patch('starface_calls.integrations.Connection')
    def test_oauth_xmlrpc_transport_and_cookie(self, factory):
        connection=factory.return_value
        response=connection.getresponse.return_value
        response.status=200;response.getheaders.return_value=[('Set-Cookie','JSESSIONID=session; Secure; HttpOnly')]
        response.getheader.return_value=None
        def reply(value):response.read1.side_effect=[dumps((value,),methodresponse=True).encode(),b'']
        reply(True);rpc=sf.UciClient(CONFIG);self.assertTrue(rpc.call('connection.login'))
        sent=connection.request.call_args
        self.assertEqual(parse_qs(urlsplit(sent.args[1]).query)['de.vertico.starface.jwt'],['private-token'])
        params,method=loads(sent.kwargs['body']);self.assertEqual(method,'ucp.v30.requests.connection.login')
        reply(True);rpc.call('connection.logout')
        self.assertEqual(connection.request.call_args.kwargs['headers']['Cookie'],'JSESSIONID=session')
        response.read1.side_effect=[dumps(Fault(403,'private-token')).encode(),b'']
        with self.assertRaises(ValueError) as error:rpc.call('connection.login')
        self.assertNotIn('private-token',str(error.exception))
        response.status=302
        response.read1.side_effect=[b'<html>Login private-token?access_token=private-token</html>',b'']
        response.getheader.side_effect=lambda name: 'text/html; charset=utf-8' if name=='Content-Type' else ('https://pbx.example.com/login?token=private-token' if name=='Location' else None)
        with self.assertRaises(ValueError) as error:rpc.call('connection.login')
        message=str(error.exception)
        self.assertIn('Antworttyp: HTML',message)
        self.assertIn('Content-Type: text/html',message)
        self.assertNotIn('private-token',message)
        self.assertIn('AUSGEBLENDET',message)

    def test_route_uses_logged_in_owner_and_refreshed_oauth_token(self):
        import app
        from contextlib import contextmanager
        handler = object.__new__(app.App)
        handler.path = '/api/v1/integrations/list'
        handler.send_json = Mock()
        @contextmanager
        def db(): yield object()
        linked = dict(CONFIG, provider='starface', oauth=True)
        with patch.object(app, 'db', db), patch.object(app.starface_oauth, 'access', return_value=linked) as access, patch.object(app.starface_calls, 'load', return_value={'rows': []}) as load:
            handler.integration_list({'id': 42}, {'provider': 'starface', 'owner_id': 99, 'secret': 'untrusted', 'days': 7, 'call_type': 'missed'})
            self.assertEqual(access.call_args.args[1], 42)
            self.assertEqual(load.call_args.args[0]['secret'], 'private-token')
            self.assertEqual(load.call_args.args[0]['call_type'], 'missed')
            self.assertEqual(handler.send_json.call_args.args[0], 200)
