"""Runtime for dashboard, project lifecycle, bookkeeping and session management."""
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import admin_controls
import system_features

PROJECT_STATUSES = {"active": "Aktiv", "parked": "Geparkt", "closed": "Geschlossen"}
BILLING_STATES = {"": "Nicht vorgemerkt", "pending": "Zur Abrechnung", "in_progress": "In Bearbeitung", "billed": "Abgerechnet"}
PERMISSIONS = {
    "Buchhaltung": [
        ("bookkeeping.view", "Buchhaltung ansehen"),
        ("bookkeeping.manage", "Abrechnungsstatus bearbeiten"),
    ],
    "Logs": [
        ("logs.view_own", "Eigene Logs ansehen"),
        ("logs.view_team", "Team-Logs ansehen"),
        ("logs.view_all", "Alle Logs ansehen"),
    ],
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _register_permissions():
    for category, items in PERMISSIONS.items():
        existing = {key for values in admin_controls.PERMISSION_CATEGORIES.values() for key, _ in values}
        target = admin_controls.PERMISSION_CATEGORIES.setdefault(category, [])
        for key, label in items:
            if key not in existing:
                target.append((key, label))
                existing.add(key)
            admin_controls.ALL_PERMISSIONS.add(key)
    admin_controls.DEFAULT_USER_PERMISSIONS.add("logs.view_own")
    admin_controls.DEFAULT_ADMIN_PERMISSIONS.update({
        "bookkeeping.view", "bookkeeping.manage",
        "logs.view_own", "logs.view_team", "logs.view_all",
    })


def _columns(c, table):
    if getattr(c, "dialect", "") == "mariadb":
        return {r["COLUMN_NAME"] for r in c.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=?", (table,)
        )}
    return {r["name"] for r in c.execute("PRAGMA table_info(%s)" % table)}


def migrate(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS session_activity (
      token_hash VARCHAR(64) PRIMARY KEY,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      client_type VARCHAR(32) NOT NULL DEFAULT 'web',
      client_name VARCHAR(160) NOT NULL DEFAULT '',
      ip_address VARCHAR(80) NOT NULL DEFAULT '',
      user_agent VARCHAR(500) NOT NULL DEFAULT '',
      created_at VARCHAR(40) NOT NULL,
      last_active_at VARCHAR(40) NOT NULL,
      ended_at VARCHAR(40) NOT NULL DEFAULT '',
      end_reason VARCHAR(80) NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_session_activity_user ON session_activity(user_id,last_active_at);
    CREATE TABLE IF NOT EXISTS dashboard_preferences (
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      layout_json LONGTEXT NOT NULL,
      updated_at VARCHAR(40) NOT NULL
    );
    """)
    cols = _columns(c, "projects")
    additions = [
        ("status", "VARCHAR(24) NOT NULL DEFAULT 'active'"),
        ("billing_state", "VARCHAR(24) NOT NULL DEFAULT ''"),
        ("status_updated_at", "VARCHAR(40) NOT NULL DEFAULT ''"),
    ]
    for name, definition in additions:
        if name not in cols:
            c.execute(f"ALTER TABLE projects ADD COLUMN {name} {definition}")
    c.execute("UPDATE projects SET status=CASE WHEN active=1 THEN 'active' ELSE 'closed' END WHERE status IS NULL OR status=''")
    stamp = now_iso()
    for row in list(c.execute("SELECT token_hash FROM session_activity WHERE ended_at=''")):
        if not c.execute("SELECT 1 FROM sessions WHERE token_hash=?", (row["token_hash"],)).fetchone():
            c.execute("UPDATE session_activity SET ended_at=?,end_reason='Abgelaufen' WHERE token_hash=?",
                      (stamp, row["token_hash"]))


def _touch_session(app, handler, session):
    if not session:
        return
    token_hash = session.get("token_hash")
    if not token_hash:
        return
    try:
        with app.db() as c:
            native = c.execute("SELECT client_name FROM native_sessions WHERE token_hash=?", (token_hash,)).fetchone()
            client_type = "windows" if native else "web"
            client_name = (native["client_name"] if native else handler.headers.get("User-Agent", "Browser")) or client_type
            client_name = str(client_name)[:160]
            stamp = now_iso()
            row = c.execute("SELECT token_hash FROM session_activity WHERE token_hash=?", (token_hash,)).fetchone()
            if row:
                c.execute("""UPDATE session_activity SET last_active_at=?,client_type=?,client_name=?,ip_address=?,
                             user_agent=?,ended_at='',end_reason='' WHERE token_hash=?""",
                          (stamp, client_type, client_name, str(handler.client_address[0])[:80],
                           str(handler.headers.get("User-Agent", ""))[:500], token_hash))
            else:
                c.execute("""INSERT INTO session_activity(token_hash,user_id,client_type,client_name,ip_address,user_agent,
                             created_at,last_active_at,ended_at,end_reason) VALUES(?,?,?,?,?,?,?,?,'','')""",
                          (token_hash, session["id"], client_type, client_name, str(handler.client_address[0])[:80],
                           str(handler.headers.get("User-Agent", ""))[:500], stamp, stamp))
    except Exception:
        pass


def _session_rows(c, uid, current_hash):
    now = int(time.time())
    stamp = now_iso()
    for row in list(c.execute("""SELECT a.token_hash FROM session_activity a
                                LEFT JOIN sessions s ON s.token_hash=a.token_hash
                                WHERE a.user_id=? AND a.ended_at='' AND (s.token_hash IS NULL OR s.expires_at<=?)""",
                              (uid, now))):
        c.execute("UPDATE session_activity SET ended_at=?,end_reason='Abgelaufen' WHERE token_hash=?",
                  (stamp, row["token_hash"]))
    connected, history = [], []
    rows = c.execute("""SELECT a.*,s.expires_at FROM session_activity a LEFT JOIN sessions s ON s.token_hash=a.token_hash
                        WHERE a.user_id=? ORDER BY a.last_active_at DESC""", (uid,))
    current_time = datetime.now(timezone.utc)
    for r in rows:
        try:
            last = datetime.fromisoformat(str(r["last_active_at"]).replace("Z", "+00:00"))
            recent = (current_time - last).total_seconds() <= 180
        except Exception:
            recent = False
        out = {
            "id": r["token_hash"][:16],
            "token_hash": r["token_hash"],
            "client_type": r["client_type"],
            "client_name": r["client_name"],
            "ip_address": r["ip_address"],
            "created_at": r["created_at"],
            "last_active_at": r["last_active_at"],
            "ended_at": r["ended_at"],
            "end_reason": r["end_reason"],
            "current": r["token_hash"] == current_hash,
            "activity": "active" if recent and not r["ended_at"] else "inactive",
        }
        (history if r["ended_at"] else connected).append(out)
    return connected, history[:200]


def _project_context(c, uid):
    rows = []
    for r in c.execute("""SELECT p.id,p.name,p.customer_id,p.active,p.status,p.billing_state,p.status_updated_at,
                          COALESCE(cu.name,'') customer
                          FROM projects p LEFT JOIN customers cu ON cu.id=p.customer_id
                          WHERE p.owner_id=? AND p.is_system=0
                          ORDER BY CASE p.status WHEN 'active' THEN 0 WHEN 'parked' THEN 1 ELSE 2 END,p.name""", (uid,)):
        rows.append(dict(r))
    return rows


def _dashboard_prefs(c, uid):
    row = c.execute("SELECT layout_json FROM dashboard_preferences WHERE user_id=?", (uid,)).fetchone()
    default = ["stats", "missed_calls"]
    if not row:
        return default
    try:
        values = [str(x) for x in json.loads(row["layout_json"]) if str(x) in ("stats", "missed_calls")]
        return values or default
    except Exception:
        return default


def _bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "ja", "y")


def _missed_calls(c, uid):
    result = []
    for r in c.execute("""SELECT external_key,occurred_at,summary,raw_json,captured_at
                          FROM provider_events WHERE owner_id=? AND provider='starface'
                          ORDER BY occurred_at DESC,captured_at DESC""", (uid,)):
        try:
            raw = json.loads(r["raw_json"] or "{}")
        except Exception:
            continue
        direction = str(raw.get("direction") or "").upper()
        status = str(raw.get("result") or "").upper()
        called_back = raw.get("calledBack", raw.get("calledback", raw.get("called_back", False)))
        if direction != "INBOUND" or status != "MISSED" or _bool(called_back):
            continue
        result.append({
            "external_key": r["external_key"],
            "occurred_at": raw.get("startTime") or r["occurred_at"],
            "number": str(raw.get("callerNumber") or ""),
            "name": str(raw.get("callDescription") or r["summary"] or ""),
            "called_back": False,
            "called_back_by": str(raw.get("calledBackAuthor") or raw.get("calledbackauthor") or ""),
            "called_back_at": str(raw.get("calledBackModified") or raw.get("calledbackmodified") or ""),
        })
        if len(result) >= 100:
            break
    return result


def install(app):
    _register_permissions()
    original_init = app.init_db

    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:
            migrate(c)
    app.init_db = init_db

    original_current_session = app.App.current_session

    def current_session(self):
        session = original_current_session(self)
        _touch_session(app, self, session)
        return session
    app.App.current_session = current_session

    original_logout = app.App.logout

    def logout(self, session, body):
        try:
            with app.db() as c:
                c.execute("UPDATE session_activity SET ended_at=?,end_reason='Abgemeldet' WHERE token_hash=? AND ended_at=''",
                          (now_iso(), session["token_hash"]))
        except Exception:
            pass
        return original_logout(self, session, body)
    app.App.logout = logout

    try:
        pc = __import__("provider_cache_runtime")
        old_cached = pc.cached_list
        def cached_list(c, uid, provider, body):
            result = old_cached(c, uid, provider, body)
            row = c.execute("SELECT last_sync_at FROM provider_sync_state WHERE owner_id=? AND provider=?", (uid, provider)).fetchone()
            result["note"] = ("zuletzt aktualisiert " + str(row["last_sync_at"])) if row and row["last_sync_at"] else ""
            result["last_sync_at"] = str(row["last_sync_at"]) if row and row["last_sync_at"] else ""
            return result
        pc.cached_list = cached_list
    except Exception:
        pass
    try:
        zc = __import__("zammad_cache_runtime")
        old_zcached = zc.cached_list
        def zcached_list(c, uid):
            result = old_zcached(c, uid)
            last = str(result.get("last_sync_at") or "")
            result["note"] = ("zuletzt aktualisiert " + last) if last else ""
            return result
        zc.cached_list = zcached_list
    except Exception:
        pass

    previous_post = app.App.do_POST
    paths = {
        "/api/v1/next/context", "/api/v1/projects/status", "/api/v1/bookkeeping/list",
        "/api/v1/bookkeeping/status", "/api/v1/dashboard/preferences", "/api/v1/sessions/list",
        "/api/v1/sessions/disconnect", "/api/v1/starface/missed", "/api/v1/provider/refresh/start",
        "/api/v1/provider/refresh/job", "/api/v1/logs/list",
    }

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in paths:
            return previous_post(self)
        try:
            body = self.json_body()
            if not isinstance(body, dict):
                raise ValueError("Eine JSON-Struktur ist erforderlich.")
        except Exception as error:
            return self.send_json(400, {"error": str(error)})
        session = self.require(csrf=True)
        if not session:
            return
        uid = session["id"]
        try:
            if path in ("/api/v1/provider/refresh/start", "/api/v1/provider/refresh/job") and str(body.get("provider") or "").lower() != "starface":
                return previous_post(self)
            if path == "/api/v1/provider/refresh/start":
                feature = __import__("feature_runtime")
                ux = __import__("ux_runtime")
                config = feature.integration_config(app, uid, "starface")
                return self.send_json(202, {"job": ux.start_history_job(app.db, uid, "starface", config)})
            if path == "/api/v1/provider/refresh/job":
                ux = __import__("ux_runtime")
                return self.send_json(200, {"job": ux.history_job(uid, "starface")})
            with app.db() as c:
                if path == "/api/v1/logs/list":
                    if not (admin_controls.can(c, uid, "logs.view_own") or admin_controls.can(c, uid, "logs.view_team") or admin_controls.can(c, uid, "logs.view_all") or admin_controls.can(c, uid, "logs.view")):
                        raise PermissionError("Dafür fehlt die Berechtigung.")
                    pa = __import__("provider_archive")
                    return self.send_json(200, {"logs": pa.list_logs(c, uid, str(body.get("category") or ""), str(body.get("level") or ""), body.get("limit", 300))})
                if path == "/api/v1/next/context":
                    return self.send_json(200, {
                        "permissions": sorted(admin_controls.permissions_for_user(c, uid)),
                        "is_superadmin": admin_controls.is_superadmin(c, uid),
                        "projects": _project_context(c, uid),
                        "dashboard": {"widgets": _dashboard_prefs(c, uid)},
                    })
                if path == "/api/v1/projects/status":
                    pid = int(body.get("project_id") or 0)
                    status = str(body.get("status") or "")
                    if status not in PROJECT_STATUSES:
                        raise ValueError("Ungültiger Projektstatus.")
                    row = c.execute("SELECT * FROM projects WHERE id=? AND owner_id=? AND is_system=0", (pid, uid)).fetchone()
                    if not row:
                        raise ValueError("Projekt nicht gefunden.")
                    if status != "active" and c.execute(
                        "SELECT 1 FROM entries WHERE owner_id=? AND project_id=? AND ended_at IS NULL", (uid, pid)
                    ).fetchone():
                        raise ValueError("Das Projekt läuft gerade. Bitte zuerst die laufende Zeiterfassung beenden.")
                    old = str(row["status"] or ("active" if row["active"] else "closed"))
                    billing = str(row["billing_state"] or "")
                    if status == "closed" and _bool(body.get("send_to_billing")):
                        billing = "pending"
                    c.execute("""UPDATE projects SET status=?,active=?,billing_state=?,status_updated_at=? WHERE id=? AND owner_id=?""",
                              (status, 1 if status == "active" else 0, billing, now_iso(), pid, uid))
                    system_features.audit(c, uid, uid, "project", pid, "Status geändert",
                                          {"status": {"old": old, "new": status},
                                           "billing_state": {"old": row["billing_state"], "new": billing}})
                    return self.send_json(200, {"ok": True, "status": status, "billing_state": billing})
                if path == "/api/v1/bookkeeping/list":
                    admin_controls.require_permission(c, uid, "bookkeeping.view")
                    rows = []
                    for r in c.execute("""SELECT p.id,p.name,p.status,p.billing_state,p.status_updated_at,
                                         COALESCE(cu.name,'') customer
                                         FROM projects p LEFT JOIN customers cu ON cu.id=p.customer_id
                                         WHERE p.owner_id=? AND p.is_system=0 AND p.billing_state<>''
                                         ORDER BY CASE p.billing_state WHEN 'pending' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END,
                                                  p.status_updated_at DESC,p.name""", (uid,)):
                        rows.append(dict(r))
                    return self.send_json(200, {"projects": rows})
                if path == "/api/v1/bookkeeping/status":
                    admin_controls.require_permission(c, uid, "bookkeeping.manage")
                    pid = int(body.get("project_id") or 0)
                    value = str(body.get("billing_state") or "")
                    if value not in BILLING_STATES:
                        raise ValueError("Ungültiger Abrechnungsstatus.")
                    row = c.execute("SELECT billing_state FROM projects WHERE id=? AND owner_id=? AND is_system=0", (pid, uid)).fetchone()
                    if not row:
                        raise ValueError("Projekt nicht gefunden.")
                    c.execute("UPDATE projects SET billing_state=?,status_updated_at=? WHERE id=? AND owner_id=?",
                              (value, now_iso(), pid, uid))
                    system_features.audit(c, uid, uid, "project", pid, "Abrechnungsstatus geändert",
                                          {"billing_state": {"old": row["billing_state"], "new": value}})
                    return self.send_json(200, {"ok": True})
                if path == "/api/v1/dashboard/preferences":
                    widgets = body.get("widgets") if isinstance(body.get("widgets"), list) else []
                    widgets = [str(x) for x in widgets if str(x) in ("stats", "missed_calls")]
                    if not widgets:
                        widgets = ["stats"]
                    c.execute("DELETE FROM dashboard_preferences WHERE user_id=?", (uid,))
                    c.execute("INSERT INTO dashboard_preferences(user_id,layout_json,updated_at) VALUES(?,?,?)",
                              (uid, json.dumps(widgets), now_iso()))
                    return self.send_json(200, {"widgets": widgets})
                if path == "/api/v1/sessions/list":
                    connected, history = _session_rows(c, uid, session["token_hash"])
                    return self.send_json(200, {"connected": connected, "history": history})
                if path == "/api/v1/sessions/disconnect":
                    token_hash = str(body.get("token_hash") or "")
                    row = c.execute("SELECT token_hash FROM session_activity WHERE token_hash=? AND user_id=? AND ended_at=''",
                                    (token_hash, uid)).fetchone()
                    if not row:
                        raise ValueError("Sitzung nicht gefunden oder bereits getrennt.")
                    c.execute("UPDATE session_activity SET ended_at=?,end_reason='Manuell getrennt' WHERE token_hash=?",
                              (now_iso(), token_hash))
                    c.execute("DELETE FROM native_sessions WHERE token_hash=?", (token_hash,))
                    c.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
                    return self.send_json(200, {"ok": True, "current": token_hash == session["token_hash"]})
                if path == "/api/v1/starface/missed":
                    return self.send_json(200, {"calls": _missed_calls(c, uid), "server_write_supported": False})
        except PermissionError as error:
            return self.send_json(403, {"error": str(error)})
        except (ValueError, TypeError) as error:
            return self.send_json(400, {"error": str(error)})
    app.App.do_POST = do_POST
