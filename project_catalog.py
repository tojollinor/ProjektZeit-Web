"""Owned project tags, repeat projects and local duration comparisons."""
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse
import system_features
import time_workspace


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS project_tags (
      id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL,
      customer_id INTEGER NOT NULL DEFAULT 0, name VARCHAR(120) NOT NULL,
      active INTEGER NOT NULL DEFAULT 1, UNIQUE(owner_id,customer_id,name));
    CREATE TABLE IF NOT EXISTS project_tag_links (
      project_id INTEGER NOT NULL, tag_id INTEGER NOT NULL,
      PRIMARY KEY(project_id,tag_id));
    CREATE INDEX IF NOT EXISTS idx_project_tag_links_tag ON project_tag_links(tag_id,project_id);
    CREATE TABLE IF NOT EXISTS project_origins (
      project_id INTEGER PRIMARY KEY, template_id INTEGER NOT NULL,
      created_at VARCHAR(40) NOT NULL);
    ''')


def project(c, uid, pid):
    row = c.execute('SELECT * FROM projects WHERE id=? AND owner_id=? AND is_system=0', (int(pid), uid)).fetchone()
    if not row:
        raise PermissionError('Projekt nicht zugänglich.')
    return dict(row)


def name_value(body):
    name = str(body.get('name') or '').strip()
    if not name or len(name) > 120:
        raise ValueError('Bitte einen Namen mit 1 bis 120 Zeichen eingeben.')
    return name


def save_tag(c, uid, body):
    name = name_value(body)
    ident = int(body.get('id') or 0)
    cid = int(body.get('customer_id') or 0)
    if cid and not c.execute('SELECT 1 FROM customers WHERE id=? AND owner_id=?', (cid, uid)).fetchone():
        raise PermissionError('Kunde nicht zugänglich.')
    if ident:
        old = c.execute('SELECT * FROM project_tags WHERE id=? AND owner_id=?', (ident, uid)).fetchone()
        if not old:
            raise PermissionError('Tag nicht zugänglich.')
        if old['customer_id'] != cid:
            raise ValueError('Der Kundenbereich eines bestehenden Tags bleibt erhalten.')
    if c.execute('SELECT 1 FROM project_tags WHERE owner_id=? AND customer_id=? AND name=? AND id<>?', (uid, cid, name, ident)).fetchone():
        raise ValueError('Dieses Tag existiert in diesem Kundenbereich bereits.')
    active = body.get('active', True)
    if not isinstance(active, bool):
        raise ValueError('Ungültiger Tagstatus.')
    if ident:
        c.execute('UPDATE project_tags SET name=?,active=? WHERE id=? AND owner_id=?', (name, int(active), ident, uid))
    else:
        ident = c.execute('INSERT INTO project_tags(owner_id,customer_id,name,active) VALUES(?,?,?,?)', (uid, cid, name, int(active))).lastrowid
    system_features.audit(c, uid, uid, 'project_tag', ident, 'Tag gespeichert', {'name': name, 'active': active})
    return {'ok': True, 'id': ident}


def assign_tags(c, uid, body):
    p = project(c, uid, body.get('project_id'))
    raw = body.get('tags')
    if not isinstance(raw, list) or len(raw) > 50:
        raise ValueError('Höchstens 50 Tags je Projekt auswählen.')
    ids = sorted(set(int(x) for x in raw))
    existing = {r['tag_id'] for r in c.execute('SELECT tag_id FROM project_tag_links WHERE project_id=?', (p['id'],))}
    valid = {r['id'] for r in c.execute('SELECT id,active FROM project_tags WHERE owner_id=? AND customer_id IN (0,?)', (uid, p['customer_id'] or 0)) if r['active'] or r['id'] in existing}
    if not set(ids).issubset(valid):
        raise ValueError('Tag nicht verfügbar oder einem anderen Kunden zugeordnet.')
    c.execute('DELETE FROM project_tag_links WHERE project_id=?', (p['id'],))
    for ident in ids:
        c.execute('INSERT INTO project_tag_links(project_id,tag_id) VALUES(?,?)', (p['id'], ident))
    system_features.audit(c, uid, uid, 'project', p['id'], 'Tags zugeordnet', {'tags': ids})
    return {'ok': True}


def clone(c, uid, body):
    p = project(c, uid, body.get('project_id'))
    name = name_value(body)
    if c.execute('SELECT 1 FROM projects WHERE owner_id=? AND name=?', (uid, name)).fetchone():
        raise ValueError('Ein Projekt mit diesem Namen existiert bereits.')
    if p['customer_id'] and not c.execute('SELECT 1 FROM customers WHERE id=? AND owner_id=?', (p['customer_id'], uid)).fetchone():
        raise PermissionError('Kunde nicht zugänglich.')
    ident = c.execute("INSERT INTO projects(owner_id,customer_id,name,active,status,billing_state) VALUES(?,?,?,1,'active','')", (uid, p['customer_id'], name)).lastrowid
    c.execute('INSERT INTO project_origins VALUES(?,?,?)', (ident, p['id'], time_workspace.iso(datetime.now(timezone.utc))))
    c.execute('''INSERT INTO project_tag_links(project_id,tag_id)
      SELECT ?,t.id FROM project_tag_links l JOIN project_tags t ON t.id=l.tag_id
      WHERE l.project_id=? AND t.owner_id=? AND t.active=1 AND t.customer_id IN (0,?)''', (ident, p['id'], uid, p['customer_id'] or 0))
    system_features.audit(c, uid, uid, 'project', ident, 'Aus Projekt erstellt', {'template_id': p['id']})
    return {'ok': True, 'project_id': ident}


def catalog(c, uid, body):
    projects = [dict(r) for r in c.execute('''SELECT p.id,p.name,p.customer_id,p.status,p.billing_state,
      COALESCE(cu.name,'') customer,o.template_id FROM projects p
      LEFT JOIN customers cu ON cu.id=p.customer_id AND cu.owner_id=p.owner_id
      LEFT JOIN project_origins o ON o.project_id=p.id
      WHERE p.owner_id=? AND p.is_system=0 ORDER BY p.name''', (uid,))]
    tags = [dict(r) for r in c.execute('''SELECT t.*,COALESCE(cu.name,'') customer FROM project_tags t
      LEFT JOIN customers cu ON cu.id=t.customer_id AND cu.owner_id=t.owner_id
      WHERE t.owner_id=? ORDER BY t.name,t.id''', (uid,))]
    links = [dict(r) for r in c.execute('''SELECT l.project_id,l.tag_id FROM project_tag_links l
      JOIN projects p ON p.id=l.project_id JOIN project_tags t ON t.id=l.tag_id AND t.owner_id=p.owner_id
      WHERE p.owner_id=? AND p.is_system=0 AND t.customer_id IN (0,COALESCE(p.customer_id,0))''', (uid,))]
    spans = defaultdict(list)
    # Two bulk queries, independent of project count. Completed intervals only;
    # provider overlap with manually tracked work counts once within a project.
    for r in c.execute('''SELECT e.project_id,e.started_at,e.ended_at FROM entries e
      JOIN projects p ON p.id=e.project_id AND p.owner_id=e.owner_id
      WHERE e.owner_id=? AND p.is_system=0 AND e.is_idle=0 AND e.ended_at IS NOT NULL''', (uid,)):
        spans[r['project_id']].append({'start': r['started_at'], 'end': r['ended_at']})
    for r in c.execute('''SELECT a.project_id,i.started_at,i.ended_at FROM event_intervals i
      JOIN provider_assignments a ON a.owner_id=i.owner_id AND a.provider=i.provider AND a.external_key=i.external_key
      JOIN projects p ON p.id=a.project_id AND p.owner_id=i.owner_id
      WHERE i.owner_id=? AND p.is_system=0 AND i.ended_at IS NOT NULL''', (uid,)):
        spans[r['project_id']].append({'start': r['started_at'], 'end': r['ended_at']})
    for p in projects:
        p['seconds'] = time_workspace.union_seconds(spans[p['id']])
    customers = [dict(r) for r in c.execute('SELECT id,name FROM customers WHERE owner_id=? ORDER BY name', (uid,))]
    return {'projects': projects, 'tags': tags, 'links': links, 'customers': customers}


HANDLERS = {'list': catalog, 'tags/save': save_tag, 'tags/assign': assign_tags, 'clone': clone}


def install(app):
    original_init = app.init_db
    def init(create_admin=True):
        original_init(create_admin)
        with app.db() as c:
            migrate(c)
    app.init_db = init
    previous = app.App.do_POST
    def post(self):
        path = urlparse(self.path).path
        handler = HANDLERS.get(path.removeprefix('/api/v1/project-catalog/')) if path.startswith('/api/v1/project-catalog/') else None
        if handler is None:
            return previous(self)
        session = self.require(csrf=True)
        if not session:
            return
        try:
            body = self.json_body()
            if not isinstance(body, dict):
                raise ValueError('JSON-Objekt erforderlich.')
            with app.db() as c:
                result = handler(c, session['id'], body)
            return self.send_json(200, result)
        except PermissionError as error:
            return self.send_json(403, {'error': str(error)})
        except (ValueError, TypeError, KeyError) as error:
            return self.send_json(400, {'error': str(error)})
    app.App.do_POST = post
