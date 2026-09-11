"""One-time, explicit migration into an empty MariaDB database. No sessions copied."""
import argparse
import sqlite3
from pathlib import Path
import app
import database


def migrate(source):
    if not database.is_maria():
        raise RuntimeError('DB_BACKEND=mariadb ist erforderlich.')
    source = Path(source).resolve(strict=True)
    app.init_db(create_admin=False)
    old = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    old.row_factory = sqlite3.Row
    counts = {}
    try:
        tables = {r['name'] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with app.db() as c:
            for table in ('users','customers','projects','categories','work_sessions','entries','integrations','oauth_tokens'):
                if c.execute('SELECT 1 FROM ' + table + ' LIMIT 1').fetchone():
                    raise RuntimeError('Zieldatenbank ist nicht leer. Import abgebrochen; keine Daten überschrieben.')
            for table in ('users','customers','projects','categories','work_sessions','entries','integrations','oauth_tokens'):
                if table not in tables:
                    continue
                # Only copy columns known by both schemas; generated columns stay server-owned.
                destination = {r['Field'] for r in c.execute('SHOW COLUMNS FROM ' + table) if 'GENERATED' not in r['Extra']}
                columns = [r['name'] for r in old.execute('PRAGMA table_info(' + table + ')') if r['name'] in destination]
                rows = old.execute('SELECT ' + ','.join(columns) + ' FROM ' + table).fetchall()
                for row in rows:
                    c.execute('INSERT INTO ' + table + ' (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', tuple(row))
                counts[table] = len(rows)
        return counts
    finally:
        old.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Pfad zur gesicherten SQLite-Datei')
    args = parser.parse_args()
    print(migrate(args.source))
