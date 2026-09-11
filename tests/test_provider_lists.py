import unittest
from unittest.mock import Mock, patch
import provider_lists as lists
import starface_oauth as oauth


class ProviderListsTest(unittest.TestCase):
    def test_connections_sorted_and_duration(self):
        client = Mock()
        client.request.side_effect = [
            (200, {'records': [{'devicename': 'Alt', 'start_date': '2026-09-01T23:50:00Z', 'end_date': '2026-09-02T00:10:00Z'}], 'next_offset': 'next'}, ''),
            (200, {'records': [{'devicename': 'Neu', 'start_date': '2026-09-03T10:00:00Z'}]}, '')]
        result = lists.teamviewer({'secret': 'token'}, client)
        self.assertEqual(result['columns'][0], 'Gerätename')
        self.assertEqual([r['cells'][0] for r in result['rows']], ['Neu', 'Alt'])
        self.assertEqual(result['rows'][1]['cells'][4], '00:20:00')
        self.assertEqual(result['rows'][0]['cells'][4], '–')
        self.assertIn('offset=next', client.request.call_args.args[0])

    def test_ticket_names_links_and_cached_organization(self):
        client = Mock()
        client.request.side_effect = [(200, [
            {'id': 7, 'number': '10007', 'title': 'Test', 'organization_id': 2, 'state': 'open'},
            {'id': 8, 'organization_id': 2},
            {'id': 'invalid', 'organization': {'name': 'Firma'}}], ''),
            (200, {'name': 'Kunde'}, '')]
        result = lists.zammad({'username': 'u', 'secret': 's', 'domain': 'https://support.example.com'}, client)
        self.assertEqual(result['columns'][:3], ['ID', 'Ticketnummer', 'Titel'])
        self.assertEqual(result['rows'][0]['cells'][:5], ['7', '10007', 'Test', 'Kunde', 'Offen'])
        self.assertEqual(result['rows'][1]['cells'][3], 'Kunde')
        self.assertEqual(client.request.call_count, 2)
        self.assertEqual(result['rows'][0]['ticket_id'], '7')
        self.assertIsNone(result['rows'][2]['ticket_id'])

    def test_empty_reports_and_date_filter(self):
        client=Mock();client.request.return_value=(200,{'records':[]},'')
        result=lists.teamviewer({'secret':'x'},client)
        self.assertNotIn('from_date',client.request.call_args.args[0])
        self.assertIn('keine Verbindungen',result['note'])
        lists.teamviewer({'secret':'x','days':90},client)
        self.assertIn('from_date',client.request.call_args.args[0])

    def test_ticket_detail_validation_and_redaction(self):
        client=Mock();client.request.side_effect=[(200,{'id':7,'title':'Test'},''),(200,[{'body':'secret-value','token':'hidden'}],'')]
        config={'domain':'https://support.example.com','username':'u','secret':'secret-value'}
        result=lists.ticket_detail(config,7,lambda _:client)
        self.assertEqual(result['articles'][0]['body'],'[ausgeblendet]')
        self.assertNotIn('token',result['articles'][0])
        with self.assertRaises(ValueError):lists.ticket_detail(config,'../users',lambda _:client)

    @patch('starface_oauth.integrations.Client')
    def test_relative_discovery_redirect(self, factory):
        factory.return_value.request.side_effect = [(302, {'redirect': '/auth/discovery'}, ''), (200, {'issuer': 'ok'}, '')]
        self.assertEqual(oauth.request_url('https://pbx.example.com/.well-known/openid-configuration', 'https://pbx.example.com'), {'issuer': 'ok'})
        self.assertEqual(factory.return_value.request.call_args.args[0], '/auth/discovery')

    @patch.dict('os.environ', {'STARFACE_OAUTH_ALLOWED_ORIGINS': ''})
    @patch('starface_oauth.integrations.Client')
    def test_unsafe_discovery_redirects(self, factory):
        for target in ('https://evil.example.com/x', 'http://pbx.example.com/x'):
            factory.return_value.request.return_value = (302, {'redirect': target}, '')
            with self.assertRaises(ValueError):
                oauth.request_url('https://pbx.example.com/discovery', 'https://pbx.example.com')

    @patch('starface_oauth.integrations.Client')
    def test_redirect_loop_and_token_redirect(self, factory):
        factory.return_value.request.return_value = (302, {'redirect': '/discovery'}, '')
        with self.assertRaises(ValueError):
            oauth.request_url('https://pbx.example.com/discovery', 'https://pbx.example.com')
        self.assertEqual(factory.return_value.request.call_count, 4)
        with patch('starface_oauth.integrations.Connection') as connection:
            response = Mock(status=302)
            response.read.return_value = b''
            connection.return_value.getresponse.return_value = response
            with self.assertRaises(ValueError):
                oauth.request_url('https://pbx.example.com/token', 'https://pbx.example.com', {'code':'test'})
            self.assertEqual(connection.return_value.request.call_count, 1)
