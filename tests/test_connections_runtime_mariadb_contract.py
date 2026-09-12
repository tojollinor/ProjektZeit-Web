import unittest

import connections_runtime


class _Rows:
    def __init__(self, rows):
        self.rows = rows
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def __iter__(self):
        return iter(self.rows)


class _MariaLikeCursor:
    dialect = 'mariadb'
    def __init__(self):
        self.queries = []
    def execute(self, sql, args=()):
        self.queries.append((sql, args))
        if 'FROM integrations' in sql:
            return _Rows([])
        if 'FROM oauth_tokens' in sql:
            return _Rows([])
        return _Rows([])


class ConnectionsMariaContractTests(unittest.TestCase):
    def test_payload_uses_portable_parameterized_queries_only(self):
        cursor = _MariaLikeCursor()
        rows = connections_runtime.connection_payload(cursor, 9)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all('?' in sql for sql, _ in cursor.queries))
        self.assertFalse(any('PRAGMA' in sql.upper() for sql, _ in cursor.queries))


if __name__ == '__main__':
    unittest.main()
