"""MariaDB runtime with SQLite retained for local tests and legacy import."""
import os
import re
import sqlite3
from contextlib import contextmanager


def is_maria():
    return os.environ.get('DB_BACKEND', 'sqlite') == 'mariadb'


class Result:
    def __init__(self, cursor):
        self.rows = cursor.fetchall() if cursor.description else []
        self.lastrowid, self.rowcount = cursor.lastrowid, cursor.rowcount
        self.pos = 0
        cursor.close()

    def fetchone(self):
        if self.pos >= len(self.rows):
            return None
        row = self.rows[self.pos]
        self.pos += 1
        return row

    def fetchall(self):
        rows = self.rows[self.pos:]
        self.pos = len(self.rows)
        return rows

    def __iter__(self):
        return iter(self.fetchall())


class MariaConnection:
    dialect = 'mariadb'

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        import pymysql
        # Existing transaction boundaries are serialized by a database lock.
        if sql == 'BEGIN IMMEDIATE':
            sql = 'SELECT 1'
        sql = sql.replace('INSERT OR IGNORE', 'INSERT IGNORE')
        sql = sql.replace('RELEASE csv_row', 'RELEASE SAVEPOINT csv_row')
        sql = sql.replace('ROLLBACK TO csv_row', 'ROLLBACK TO SAVEPOINT csv_row')
        sql = sql.replace("datetime('now')", 'UTC_TIMESTAMP()')
        sql = sql.replace('?', '%s')
        try:
            cursor = self.conn.cursor()
            # PyMySQL applies Python %-formatting whenever an args object is passed.
            # With no bind parameters, call execute(sql) directly so literal SQL wildcards
            # such as LIKE 'superadmin.%' remain untouched.
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            return Result(cursor)
        except pymysql.IntegrityError as error:
            raise sqlite3.IntegrityError(str(error)) from error
        except pymysql.Error as error:
            raise sqlite3.DatabaseError(str(error)) from error

    def executemany(self, sql, rows):
        for row in rows:
            self.execute(sql, row)

    def executescript(self, script):
        for statement in script.split(';'):
            if not statement.strip():
                continue
            statement = statement.replace('INTEGER PRIMARY KEY', 'INTEGER PRIMARY KEY AUTO_INCREMENT')
            statement = statement.replace('TEXT PRIMARY KEY', 'VARCHAR(255) PRIMARY KEY')
            statement = statement.replace('COLLATE NOCASE', 'COLLATE utf8mb4_unicode_ci')
            statement = re.sub(r'\bTEXT\b', 'VARCHAR(255)', statement)
            statement = statement.replace('note VARCHAR(255)', 'note TEXT').replace('secret VARCHAR(255)', 'secret TEXT')
            self.execute(statement)


@contextmanager
def connect(sqlite_path):
    if not is_maria():
        conn = sqlite3.connect(sqlite_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()
        return
    import pymysql
    conn = pymysql.connect(host=os.environ.get('DB_HOST', 'db'),
                           port=int(os.environ.get('DB_PORT', '3306')),
                           user=os.environ.get('DB_USER', 'projektzeit'),
                           password=os.environ['DB_PASSWORD'],
                           database=os.environ.get('DB_NAME', 'projektzeit'),
                           charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
                           autocommit=False, connect_timeout=10)
    wrapper = MariaConnection(conn)
    lock = 'projektzeit:' + os.environ.get('DB_NAME', 'projektzeit')
    try:
        # Serialize units of work across threads/containers; prevents overlapping
        # timers and refresh-token races, including on an initially empty table.
        row = wrapper.execute('SELECT GET_LOCK(?, 15) AS acquired', (lock,)).fetchone()
        if row['acquired'] != 1:
            raise sqlite3.OperationalError('Datenbank ist beschäftigt. Bitte erneut versuchen.')
        yield wrapper
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        try:
            wrapper.execute('SELECT RELEASE_LOCK(?)', (lock,))
        finally:
            conn.close()
