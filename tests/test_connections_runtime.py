import sqlite3
import unittest

import connections_runtime
import integrations


class ConnectionsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)')
        self.c.execute('INSERT INTO users(id,username) VALUES(1,?)', ('admin',))
        integrations.migrate(self.c)
        self.c.execute('CREATE TABLE oauth_tokens(owner_id INTEGER PRIMARY KEY, access_token TEXT)')

    def tearDown(self):
        self.c.close()

    def test_payload_is_local_and_contains_all_providers(self):
        rows = connections_runtime.connection_payload(self.c, 1)
        self.assertEqual([row['provider'] for row in rows], ['teamviewer', 'starface', 'zammad'])
        self.assertEqual(rows[0]['domain'], 'https://webapi.teamviewer.com')
        self.assertFalse(next(row for row in rows if row['provider'] == 'starface')['has_secret'])

    def test_starface_connected_flag_comes_from_local_oauth_table(self):
        self.c.execute(
            'INSERT INTO integrations(owner_id,provider,domain,username,secret,updated_at) VALUES(?,?,?,?,?,?)',
            (1, 'starface', 'https://starface.example', 'rest-client', 'encrypted', '2026-09-12T00:00:00Z'),
        )
        self.c.execute('INSERT INTO oauth_tokens(owner_id,access_token) VALUES(?,?)', (1, 'token'))
        rows = connections_runtime.connection_payload(self.c, 1)
        starface = next(row for row in rows if row['provider'] == 'starface')
        self.assertTrue(starface['has_secret'])
        self.assertEqual(starface['auth_mode'], 'oauth')


if __name__ == '__main__':
    unittest.main()
