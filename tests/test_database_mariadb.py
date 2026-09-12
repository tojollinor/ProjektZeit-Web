import sys
import types
import unittest

import database


class _Cursor:
    def __init__(self):
        self.description = None
        self.lastrowid = 0
        self.rowcount = 0
        self.calls = []

    def execute(self, *args):
        self.calls.append(args)

    def fetchall(self):
        return []

    def close(self):
        pass


class _Conn:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def cursor(self):
        return self.cursor_obj


class MariaConnectionExecuteTests(unittest.TestCase):
    def setUp(self):
        fake = types.SimpleNamespace(IntegrityError=Exception, Error=Exception)
        self.previous = sys.modules.get('pymysql')
        sys.modules['pymysql'] = fake

    def tearDown(self):
        if self.previous is None:
            sys.modules.pop('pymysql', None)
        else:
            sys.modules['pymysql'] = self.previous

    def test_literal_percent_without_params_is_not_sent_through_mogrify(self):
        raw = _Conn()
        c = database.MariaConnection(raw)
        c.execute("DELETE FROM system_settings WHERE setting_key LIKE 'superadmin.%'")
        self.assertEqual(raw.cursor_obj.calls, [("DELETE FROM system_settings WHERE setting_key LIKE 'superadmin.%'",)])

    def test_bound_params_still_use_parameterized_execute(self):
        raw = _Conn()
        c = database.MariaConnection(raw)
        c.execute('SELECT * FROM users WHERE id=?', (7,))
        self.assertEqual(raw.cursor_obj.calls, [('SELECT * FROM users WHERE id=%s', (7,))])


if __name__ == '__main__':
    unittest.main()
