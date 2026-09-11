import base64
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import threading
import time
import workday
import integrations
import database
import starface_oauth
import provider_lists
from datetime import datetime, timezone
from contextlib import contextmanager
from http import cookies
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "projektzeit.db"
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
COOKIE_SECURE = os.environ.get("APP_SECURE_COOKIE", "0") == "1"
SESSION_TTL = 60 * 60 * 12
LOGIN_ATTEMPTS = {}
LOGIN_LOCK = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db():
    with database.connect(DB_PATH) as connection:
        yield connection


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return base64.b64encode(salt).decode(), base64.b64encode(digest).decode()


def verify_password(password, salt, expected):
    _, actual = hash_password(password, base64.b64decode(salt))
    return hmac.compare_digest(actual, expected)


def init_db(create_admin=True):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
          password_salt TEXT NOT NULL, password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('admin','user')), active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          csrf TEXT NOT NULL, expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS customers (
          id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          name TEXT NOT NULL, UNIQUE(owner_id,name)
        );
        CREATE TABLE IF NOT EXISTS projects (
          id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL, name TEXT NOT NULL,
          UNIQUE(owner_id,name)
        );
        CREATE TABLE IF NOT EXISTS categories (
          id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          name TEXT NOT NULL, UNIQUE(owner_id,name)
        );
        CREATE TABLE IF NOT EXISTS entries (
          id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          project_id INTEGER NOT NULL REFERENCES projects(id), category_id INTEGER NOT NULL REFERENCES categories(id),
          started_at TEXT NOT NULL, ended_at TEXT, note TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_entries_owner_start ON entries(owner_id,started_at DESC);
        """)
        workday.migrate(c)
        integrations.migrate(c)
        starface_oauth.migrate(c)
        c.executescript('''CREATE TABLE IF NOT EXISTS native_sessions (
            token_hash VARCHAR(64) PRIMARY KEY, client_name VARCHAR(120) NOT NULL);''')
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        c.execute('DELETE FROM native_sessions WHERE token_hash NOT IN (SELECT token_hash FROM sessions)')
        if not create_admin:
            return
        if database.is_maria() and DB_PATH.exists() and not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            raise RuntimeError('Vorhandene SQLite-Daten erkannt. Bitte zuerst migrate_sqlite.py ausführen (siehe UPGRADE-0.7.md).')
        demo_mode = os.environ.get("DEMO_MODE", "1") == "1"
        admin_user = os.environ.get("ADMIN_USER", "admin").strip()
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin" if demo_mode else "")
        if not admin_password:
            raise RuntimeError("ADMIN_PASSWORD muss gesetzt sein (mindestens 12 Zeichen).")
        if not demo_mode and (len(admin_password) < 12 or admin_password.startswith("Bitte-hier-")):
            raise RuntimeError("ADMIN_PASSWORD muss mindestens 12 Zeichen lang sein.")
        row = c.execute("SELECT id FROM users WHERE username=?", (admin_user,)).fetchone()
        if row is None:
            salt, digest = hash_password(admin_password)
            cursor = c.execute("INSERT INTO users(username,password_salt,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                               (admin_user, salt, digest, "admin", now_iso()))
            seed_demo(c, cursor.lastrowid)


def seed_demo(c, user_id):
    if os.environ.get("SEED_DEMO", "1") != "1":
        c.execute("INSERT OR IGNORE INTO categories(owner_id,name) VALUES(?,?)", (user_id, "Allgemein"))
        return
    c.execute("INSERT OR IGNORE INTO customers(owner_id,name) VALUES(?,?)", (user_id, "Hans Koll"))
    customer = c.execute("SELECT id FROM customers WHERE owner_id=? AND name=?", (user_id, "Hans Koll")).fetchone()["id"]
    c.execute("INSERT OR IGNORE INTO projects(owner_id,customer_id,name) VALUES(?,?,?)", (user_id, customer, "Lieferschein Anpassungen"))
    c.execute("INSERT OR IGNORE INTO projects(owner_id,customer_id,name) VALUES(?,?,?)", (user_id, customer, "Portal Relaunch"))
    for category in ("Allgemein", "Entwicklung", "Besprechung"):
        c.execute("INSERT OR IGNORE INTO categories(owner_id,name) VALUES(?,?)", (user_id, category))
    if not c.execute("SELECT 1 FROM entries WHERE owner_id=?", (user_id,)).fetchone():
        project_a = c.execute("SELECT id FROM projects WHERE owner_id=? AND name=?", (user_id, "Lieferschein Anpassungen")).fetchone()["id"]
        project_b = c.execute("SELECT id FROM projects WHERE owner_id=? AND name=?", (user_id, "Portal Relaunch")).fetchone()["id"]
        category_general = c.execute("SELECT id FROM categories WHERE owner_id=? AND name=?", (user_id, "Allgemein")).fetchone()["id"]
        category_dev = c.execute("SELECT id FROM categories WHERE owner_id=? AND name=?", (user_id, "Entwicklung")).fetchone()["id"]
        category_meeting = c.execute("SELECT id FROM categories WHERE owner_id=? AND name=?", (user_id, "Besprechung")).fetchone()["id"]
        today = datetime.now(timezone.utc)
        demo_entries = [
            (project_a, category_dev, today.replace(hour=6, minute=15, second=0, microsecond=0), today.replace(hour=7, minute=40, second=0, microsecond=0), "Layout und Export angepasst"),
            (project_b, category_general, today.replace(hour=8, minute=5, second=0, microsecond=0), today.replace(hour=9, minute=30, second=0, microsecond=0), "API-Abstimmung"),
            (project_a, category_meeting, today.replace(hour=11, minute=0, second=0, microsecond=0), today.replace(hour=13, minute=20, second=0, microsecond=0), "Kundenbesprechung und Umsetzung"),
        ]
        c.executemany("INSERT INTO entries(owner_id,project_id,category_id,started_at,ended_at,note) VALUES(?,?,?,?,?,?)",
                      [(user_id, project, category, start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"), note) for project, category, start, end, note in demo_entries])


class App(SimpleHTTPRequestHandler):
    server_version = "ProjektZeit/0.7.0"

    def log_message(self, fmt, *args):
        if urlparse(self.path).path in ('/health', starface_oauth.CALLBACK):
            return
        print("%s - %s" % (self.address_string(), fmt % args))

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'")
        super().end_headers()

    def translate_path(self, path):
        # Treat Windows and URL path separators identically on every host.
        # This keeps traversal checks deterministic on both Windows and Linux.
        clean = unquote(urlparse(path).path).replace("\\", "/")
        target = "index.html" if clean == "/" else clean.lstrip("/")
        resolved = (STATIC / target).resolve()
        if not resolved.is_relative_to(STATIC.resolve()):
            return str(STATIC / '__not_found__')
        return str(resolved)

    def json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Anfrage zu groß")
        return json.loads(self.rfile.read(length) or b"{}")

    def send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_csv(self, text):
        body = ("\ufeff" + text).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="ProjektZeit-Export.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def current_session(self):
        authorization = self.headers.get('Authorization', '')
        bearer = authorization.startswith('Bearer ')
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get("pz_session")
        if not bearer and not morsel:
            return None
        token_hash = hashlib.sha256((authorization[7:] if bearer else morsel.value).encode()).hexdigest()
        with db() as c:
            native = c.execute('SELECT 1 FROM native_sessions WHERE token_hash=?', (token_hash,)).fetchone()
            if bearer != bool(native):
                return None
            row = c.execute("""SELECT s.token_hash,s.csrf,u.id,u.username,u.role,u.active
                               FROM sessions s JOIN users u ON u.id=s.user_id
                               WHERE s.token_hash=? AND s.expires_at>?""", (token_hash, int(time.time()))).fetchone()
        return dict(row, bearer=bearer) if row and row["active"] else None

    def require(self, csrf=False, admin=False):
        session = self.current_session()
        if not session:
            self.send_json(401, {"error": "Nicht angemeldet"})
            return None
        if admin and session["role"] != "admin":
            self.send_json(403, {"error": "Administratorrechte erforderlich"})
            return None
        if csrf and not session['bearer'] and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
            self.send_json(403, {"error": "Ungültiger Sicherheitstoken"})
            return None
        return session

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            try:
                with db() as c:
                    c.execute('SELECT 1')
                return self.send_json(200, {"status": "ok", "version": "0.7.0"})
            except Exception:
                return self.send_json(503, {'status': 'database_unavailable'})
        if path == '/api/v1/capabilities':
            return self.send_json(200, {'api_version': 'v1', 'server_version': '0.7.0',
                'authentication': ['session_cookie', 'bearer'], 'token_endpoint': '/api/v1/auth/token',
                'token_lifetime_seconds': SESSION_TTL, 'refresh_tokens': False,
                'features': ['workday', 'project_switch', 'entries_edit', 'csv', 'integration_previews']})
        if path == starface_oauth.CALLBACK:
            session = self.require(admin=True)
            if not session: return
            try:
                starface_oauth.finish(db, session, parse_qs(urlparse(self.path).query), DATA_DIR)
            except (ValueError, OSError) as error:
                return self.send_json(400, {'error': str(error) if isinstance(error, ValueError) else 'STARFACE ist nicht erreichbar. Bitte erneut anmelden.'})
            self.send_response(303)
            self.send_header('Location', '/?starface=connected')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if path == '/api/v1/integrations':
            session = self.require(admin=True)
            if not session: return
            with db() as c:
                data=integrations.list_configs(c,session['id'])
                for item in data:
                    if item['provider'] == 'starface':
                        item['has_secret'] = bool(c.execute('SELECT 1 FROM oauth_tokens WHERE owner_id=?', (session['id'],)).fetchone())
                        item['auth_mode'] = 'oauth'
                try:
                    callback = starface_oauth.callback_url()
                except ValueError:
                    callback = ''
            return self.send_json(200,{'integrations':data, 'starface_callback': callback})
        if path == "/api/v1/me":
            session = self.require()
            return self.send_json(200, {"user": {"id": session["id"], "username": session["username"], "role": session["role"]}, "csrf": session["csrf"]}) if session else None
        if path == "/api/v1/dashboard":
            session = self.require()
            return self.dashboard(session) if session else None
        if path == "/api/v1/export.csv":
            session = self.require()
            return self.export_csv(session) if session else None
        if path.startswith("/api/"):
            return self.send_json(404, {"error": "Nicht gefunden"})
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self.json_body()
            if not isinstance(body,dict):
                raise ValueError('Eine JSON-Struktur mit benannten Feldern ist erforderlich.')
        except (ValueError, json.JSONDecodeError) as error:
            return self.send_json(400, {"error": str(error)})
        if path in ("/api/v1/login", '/api/v1/auth/token'):
            return self.login(body, native=path.endswith('/auth/token'))
        session = self.require(csrf=True, admin=path == "/api/v1/users" or path.startswith('/api/v1/integrations'))
        if not session:
            return
        routes = {
            '/api/v1/integrations/starface/start': self.start_starface,
            '/api/v1/integrations/starface/finish': self.finish_starface,
            '/api/v1/integrations/list': self.integration_list,
            '/api/v1/integrations/ticket': self.integration_list,
            '/api/v1/auth/revoke': self.logout,
            '/api/v1/integrations/save': self.save_integration,
            '/api/v1/integrations/test': self.test_integration,
            '/api/v1/integrations/remove': self.remove_integration,
            "/api/v1/work/begin": lambda s, b: self.work_action(s, b, 'begin'),
            "/api/v1/work/end": lambda s, b: self.work_action(s, b, 'end'),
            "/api/v1/entries/edit": self.edit_entry,
            "/api/v1/projects/active": self.project_active,
            "/api/v1/logout": self.logout,
            "/api/v1/customers": self.add_customer,
            "/api/v1/projects": self.add_project,
            "/api/v1/categories": self.add_category,
            "/api/v1/timer/start": self.start_timer,
            "/api/v1/timer/stop": self.stop_timer,
            "/api/v1/import.csv": self.import_csv,
            "/api/v1/users": self.add_user,
        }
        handler = routes.get(path)
        return handler(session, body) if handler else self.send_json(404, {"error": "Nicht gefunden"})

    def save_integration(self, session, body):
        if body.get('provider') == 'starface':
            return self.send_json(400, {'error': 'Bitte „Mit STARFACE anmelden“ verwenden.'})
        try:
            with db() as c:
                integrations.save(c,session['id'],body,DATA_DIR)
            return self.send_json(200,{'ok':True})
        except ValueError as error:
            return self.send_json(400,{'error':str(error)})

    def integration_list(self, session, body):
        if not integrations.TEST_LOCK.acquire(blocking=False):
            return self.send_json(429, {'error': 'Es laufen bereits Abfragen. Bitte kurz warten.'})
        try:
            with db() as c:
                row=c.execute('SELECT * FROM integrations WHERE owner_id=? AND provider=?', (session['id'],body.get('provider'))).fetchone()
                if not row:
                    raise ValueError('Bitte zuerst die Schnittstelle in den Einstellungen verknüpfen.')
                config=integrations.config(c,session['id'],dict(provider=row['provider'],domain=row['domain'],username=row['username'],secret=''),DATA_DIR)
            if urlparse(self.path).path.endswith('/ticket'):
                if config['provider'] != 'zammad':
                    raise ValueError('Ticketdetails sind nur für Zammad verfügbar.')
                return self.send_json(200,provider_lists.ticket_detail(config,body.get('ticket_id')))
            config['days'] = body.get('days', 0)
            return self.send_json(200,provider_lists.load(config))
        except (ValueError,OSError) as error:
            return self.send_json(400,{'error':str(error) if isinstance(error,ValueError) else 'Schnittstelle nicht erreichbar. Bitte erneut versuchen.'})
        finally:
            integrations.TEST_LOCK.release()

    def test_integration(self, session, body):
        if not integrations.TEST_LOCK.acquire(blocking=False):
            return self.send_json(429,{'error':'Es laufen bereits Verbindungstests. Bitte kurz warten.'})
        try:
            with db() as c:
                if body.get('provider') == 'starface':
                    data=starface_oauth.access(c,session['id'],DATA_DIR)
                    if body.get('domain') and integrations.domain(body['domain'], 'starface') != data['domain']:
                        raise ValueError('Domain geändert. Bitte neu mit STARFACE anmelden.')
                else:
                    data=integrations.config(c,session['id'],body,DATA_DIR)
            return self.send_json(200,integrations.diagnose(data))
        except ValueError as error:
            return self.send_json(400,{'error':str(error)})
        finally:
            integrations.TEST_LOCK.release()

    def remove_integration(self, session, body):
        if body.get('provider') not in integrations.PROVIDERS:
            return self.send_json(400,{'error':'Unbekannte Schnittstelle.'})
        with db() as c:
            if body['provider'] == 'starface':
                c.execute('DELETE FROM oauth_tokens WHERE owner_id=?', (session['id'],))
                c.execute('DELETE FROM oauth_states WHERE owner_id=?', (session['id'],))
            c.execute('DELETE FROM integrations WHERE owner_id=? AND provider=?',(session['id'],body['provider']))
        return self.send_json(200,{'ok':True})

    def start_starface(self, session, body):
        try:
            return self.send_json(200, starface_oauth.start(db, session, body, DATA_DIR))
        except (ValueError, OSError) as error:
            return self.send_json(400, {'error': str(error) if isinstance(error, ValueError) else 'STARFACE OAuth-Endpunkt ist nicht erreichbar.'})

    def finish_starface(self, session, body):
        if not session['bearer']:
            return self.send_json(403, {'error': 'Nur für den angemeldeten Windows-Client.'})
        try:
            query = {key: [value] for key, value in body.items() if key in ('code', 'state', 'error') and isinstance(value, str)}
            starface_oauth.finish(db, session, query, DATA_DIR)
            return self.send_json(200, {'ok': True})
        except (ValueError, OSError) as error:
            return self.send_json(400, {'error': str(error) if isinstance(error, ValueError) else 'STARFACE nicht erreichbar.'})

    def login(self, body, native=False):
        client = self.client_address[0]
        with LOGIN_LOCK:
            recent = [stamp for stamp in LOGIN_ATTEMPTS.get(client, []) if time.time() - stamp < 600]
            LOGIN_ATTEMPTS[client] = recent
            if len(recent) >= 8:
                return self.send_json(429, {"error": "Zu viele Anmeldeversuche. Bitte später erneut versuchen."})
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", ""))
        with db() as c:
            row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not row or not row["active"] or not verify_password(password, row["password_salt"], row["password_hash"]):
                with LOGIN_LOCK:
                    LOGIN_ATTEMPTS.setdefault(client, []).append(time.time())
                time.sleep(0.25)
                return self.send_json(401, {"error": "Benutzername oder Passwort ist falsch"})
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)",
                      (hashlib.sha256(token.encode()).hexdigest(), row["id"], csrf, int(time.time()) + SESSION_TTL))
            if native:
                c.execute('INSERT INTO native_sessions VALUES(?,?)', (hashlib.sha256(token.encode()).hexdigest(), str(body.get('client_name', 'Client'))[:120]))
        with LOGIN_LOCK:
            LOGIN_ATTEMPTS.pop(client, None)
        if native:
            return self.send_json(200, {'access_token': token, 'token_type': 'Bearer', 'expires_in': SESSION_TTL})
        cookie = "pz_session=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d%s" % (token, SESSION_TTL, "; Secure" if COOKIE_SECURE else "")
        return self.send_json(200, {"ok": True}, {"Set-Cookie": cookie})

    def logout(self, session, body):
        with db() as c:
            c.execute('DELETE FROM native_sessions WHERE token_hash=?', (session['token_hash'],))
            c.execute('DELETE FROM oauth_states WHERE session_hash=?', (session['token_hash'],))
            c.execute("DELETE FROM sessions WHERE token_hash=?", (session["token_hash"],))
        return self.send_json(200, {"ok": True}, {"Set-Cookie": "pz_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})

    def dashboard(self, session):
        uid = session["id"]
        with db() as c:
            customers = [dict(x) for x in c.execute("SELECT id,name FROM customers WHERE owner_id=? ORDER BY name", (uid,))]
            projects = [dict(x) for x in c.execute("SELECT id,name,customer_id,active FROM projects WHERE owner_id=? AND is_system=0 ORDER BY name", (uid,))]
            categories = [dict(x) for x in c.execute("SELECT id,name FROM categories WHERE owner_id=? ORDER BY name", (uid,))]
            entries = [dict(x) for x in c.execute("""SELECT e.id,e.project_id,e.category_id,e.is_idle,e.work_session_id,e.started_at,e.ended_at,e.note,CASE WHEN e.is_idle=1 THEN 'unproduktiv' ELSE p.name END project,c.name customer,k.name category
                FROM entries e JOIN projects p ON p.id=e.project_id LEFT JOIN customers c ON c.id=p.customer_id
                JOIN categories k ON k.id=e.category_id WHERE e.owner_id=? ORDER BY e.started_at DESC""", (uid,))]
            work = c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND ended_at IS NULL', (uid,)).fetchone()
            users = [dict(x) for x in c.execute("SELECT id,username,role,active,created_at FROM users ORDER BY username")] if session["role"] == "admin" else []
        return self.send_json(200, {"customers": customers, "projects": projects, "categories": categories, "entries": entries, "users": users, "work": dict(work) if work else None})

    def export_csv(self, session):
        def safe(value):
            text = str(value or "")
            return "'" + text if text[:1] in ("=", "+", "-", "@") else text
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["Kunde", "Projekt", "Zeitkategorie", "Start", "Ende", "Dauer", "Sekunden", "Bemerkung", "Art"])
        with db() as c:
            rows = c.execute("""SELECT e.started_at,e.ended_at,e.note,e.is_idle,p.name project,c.name customer,k.name category
                FROM entries e JOIN projects p ON p.id=e.project_id LEFT JOIN customers c ON c.id=p.customer_id
                JOIN categories k ON k.id=e.category_id WHERE e.owner_id=? ORDER BY e.started_at""", (session["id"],))
            for row in rows:
                seconds = ""
                if row["ended_at"]:
                    seconds = max(0, int((datetime.fromisoformat(row["ended_at"]) - datetime.fromisoformat(row["started_at"])).total_seconds()))
                duration = "" if seconds == "" else "%02d:%02d:%02d" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)
                writer.writerow([safe(row["customer"] or "Ohne Kunde"), safe('unproduktiv' if row['is_idle'] else row["project"]), safe(row["category"]), row["started_at"], row["ended_at"] or "", duration, seconds, safe(row["note"]), 'unproduktiv' if row['is_idle'] else 'Projekt'])
        return self.send_csv(output.getvalue())

    def import_csv(self, session, body):
        raw = str(body.get("csv", ""))
        if not raw or len(raw.encode("utf-8")) > 900_000:
            return self.send_json(400, {"error": "CSV-Datei ist leer oder zu groß"})
        def clean(value):
            value = str(value or "").strip()
            return value[1:] if len(value) > 1 and value[0] == "'" and value[1] in "=+-@" else value
        def parse_date(value):
            value = clean(value)
            for parser in (datetime.fromisoformat, lambda x: datetime.strptime(x, "%d.%m.%Y %H:%M:%S")):
                try: return parser(value)
                except ValueError: pass
            raise ValueError("ungültiges Datum")
        try:
            reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")), delimiter=";")
            required = {"Projekt", "Start", "Ende"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                return self.send_json(400, {"error": "Erwartete Spalten: Kunde;Projekt;Zeitkategorie;Start;Ende;..."})
            imported, skipped, errors = 0, 0, []
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                for line, row in enumerate(reader, 2):
                    c.execute('SAVEPOINT csv_row')
                    try:
                        if row.get('Art') == 'unproduktiv':
                            skipped += 1
                            c.execute('RELEASE csv_row')
                            continue
                        project_name, customer_name = clean(row.get("Projekt")), clean(row.get("Kunde")) or "Ohne Kunde"
                        category_name = clean(row.get("Zeitkategorie")) or "Allgemein"
                        note = clean(row.get("Bemerkung"))[:2000]
                        start, end = parse_date(row.get("Start")), parse_date(row.get("Ende"))
                        if (start.tzinfo is None) != (end.tzinfo is None):
                            raise ValueError("Start und Ende müssen dieselbe Zeitzonenangabe verwenden")
                        if not project_name or end <= start: raise ValueError("Projekt fehlt oder Ende liegt nicht nach Start")
                        customer_id = None
                        if customer_name != "Ohne Kunde":
                            c.execute("INSERT OR IGNORE INTO customers(owner_id,name) VALUES(?,?)", (session["id"], customer_name))
                            customer_id = c.execute("SELECT id FROM customers WHERE owner_id=? AND name=?", (session["id"], customer_name)).fetchone()["id"]
                        c.execute("INSERT OR IGNORE INTO categories(owner_id,name) VALUES(?,?)", (session["id"], category_name))
                        category_id = c.execute("SELECT id FROM categories WHERE owner_id=? AND name=?", (session["id"], category_name)).fetchone()["id"]
                        c.execute("INSERT OR IGNORE INTO projects(owner_id,customer_id,name) VALUES(?,?,?)", (session["id"], customer_id, project_name))
                        project_id = c.execute("SELECT id FROM projects WHERE owner_id=? AND name=?", (session["id"], project_name)).fetchone()["id"]
                        if c.execute('SELECT is_system FROM projects WHERE id=?', (project_id,)).fetchone()['is_system']:
                            raise ValueError('Unproduktive Zeit wird automatisch aus der Arbeitszeit berechnet.')
                        c.execute("UPDATE projects SET customer_id=? WHERE id=?", (customer_id, project_id))
                        start_text, end_text = start.isoformat(), end.isoformat()
                        candidates = c.execute('SELECT started_at,ended_at FROM entries WHERE owner_id=? AND project_id=? AND category_id=? AND note=? AND ended_at IS NOT NULL', (session['id'], project_id, category_id, note))
                        duplicate = any(workday.stamp(r['started_at']) == workday.stamp(start_text) and workday.stamp(r['ended_at']) == workday.stamp(end_text) for r in candidates)
                        if duplicate:
                            skipped += 1
                            c.execute('ROLLBACK TO csv_row')
                            c.execute('RELEASE csv_row')
                            continue
                        workday.overlap(c, session['id'], workday.stamp(start_text), workday.stamp(end_text))
                        c.execute("INSERT INTO entries(owner_id,project_id,category_id,started_at,ended_at,note) VALUES(?,?,?,?,?,?)", (session["id"], project_id, category_id, start_text, end_text, note)); imported += 1
                        c.execute('RELEASE csv_row')
                    except (ValueError, sqlite3.Error) as error:
                        c.execute('ROLLBACK TO csv_row')
                        c.execute('RELEASE csv_row')
                        if len(errors) < 20: errors.append("Zeile %d: %s" % (line, error))
                workday.reconcile(c, session['id'])
            return self.send_json(200, {"imported": imported, "skipped": skipped, "errors": errors})
        except (csv.Error, UnicodeError) as error:
            return self.send_json(400, {"error": "CSV konnte nicht gelesen werden: " + str(error)})

    def add_customer(self, session, body):
        return self.simple_name_insert(session, body, "customers")

    def add_category(self, session, body):
        return self.simple_name_insert(session, body, "categories")

    def simple_name_insert(self, session, body, table):
        name = str(body.get("name", "")).strip()
        if not name or len(name) > 120:
            return self.send_json(400, {"error": "Bitte einen gültigen Namen eingeben"})
        try:
            with db() as c:
                cursor = c.execute("INSERT INTO %s(owner_id,name) VALUES(?,?)" % table, (session["id"], name))
            return self.send_json(201, {"id": cursor.lastrowid, "name": name})
        except sqlite3.IntegrityError:
            return self.send_json(409, {"error": "Name ist bereits vorhanden"})

    def add_project(self, session, body):
        name = str(body.get("name", "")).strip()
        customer_id = body.get("customer_id")
        if not name or len(name) > 120:
            return self.send_json(400, {"error": "Bitte einen gültigen Projektnamen eingeben"})
        with db() as c:
            if customer_id and not c.execute("SELECT 1 FROM customers WHERE id=? AND owner_id=?", (customer_id, session["id"])).fetchone():
                return self.send_json(400, {"error": "Unbekannter Kunde"})
            try:
                cursor = c.execute("INSERT INTO projects(owner_id,customer_id,name) VALUES(?,?,?)", (session["id"], customer_id, name))
            except sqlite3.IntegrityError:
                return self.send_json(409, {"error": "Projekt ist bereits vorhanden"})
        return self.send_json(201, {"id": cursor.lastrowid, "name": name})

    def start_timer(self, session, body):
        return self.work_action(session, body, 'switch')

    def stop_timer(self, session, body):
        return self.work_action(session, body, 'idle')

    def work_action(self, session, body, action):
        try:
            with db() as c:
                workday.transition(c, session['id'], action, body, datetime.now(timezone.utc))
            return self.send_json(200, {'ok': True})
        except ValueError as error:
            return self.send_json(409, {'error': str(error)})

    def edit_entry(self, session, body):
        try:
            with db() as c:
                workday.edit(c, session['id'], body, datetime.now(timezone.utc))
            return self.send_json(200, {'ok': True})
        except (ValueError, KeyError, TypeError) as error:
            return self.send_json(400, {'error': str(error)})

    def project_active(self, session, body):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not body.get('active') and c.execute('SELECT 1 FROM entries WHERE owner_id=? AND project_id=? AND ended_at IS NULL', (session['id'], body.get('id'))).fetchone():
                return self.send_json(409, {'error': 'Bitte zuerst zu einem anderen Projekt wechseln oder das Projekt stoppen.'})
            result = c.execute('UPDATE projects SET active=? WHERE id=? AND owner_id=? AND is_system=0', (int(bool(body.get('active'))), body.get('id'), session['id']))
            if not result.rowcount:
                return self.send_json(404, {'error': 'Projekt nicht gefunden.'})
        return self.send_json(200, {'ok': True})

    def add_user(self, session, body):
        username, password = str(body.get("username", "")).strip(), str(body.get("password", ""))
        role = body.get("role", "user")
        if not username or len(username) > 80 or len(password) < 12 or role not in ("admin", "user"):
            return self.send_json(400, {"error": "Benutzername und Passwort (mindestens 12 Zeichen) prüfen"})
        salt, digest = hash_password(password)
        try:
            with db() as c:
                cursor = c.execute("INSERT INTO users(username,password_salt,password_hash,role,created_at) VALUES(?,?,?,?,?)", (username, salt, digest, role, now_iso()))
                seed_demo(c, cursor.lastrowid)
        except sqlite3.IntegrityError:
            return self.send_json(409, {"error": "Benutzer ist bereits vorhanden"})
        return self.send_json(201, {"id": cursor.lastrowid, "username": username, "role": role})


if __name__ == "__main__":
    init_db()
    print("ProjektZeit Web läuft auf http://%s:%d" % (HOST, PORT))
    ThreadingHTTPServer((HOST, PORT), App).serve_forever()
