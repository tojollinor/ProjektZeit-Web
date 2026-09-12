"""Small compatibility fixes layered after final_batch_runtime."""
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import final_batch_runtime as final
import system_features


def _parse(value):
    if not value:return None
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None


def install(app):
    # final_batch_runtime wraps workday.reconcile before app.init_db runs. On an existing
    # database, workday.migrate performs an initial reconcile before the new total columns
    # have been added. Skip only that premature totals update; final.migrate adds the
    # columns immediately afterwards and recomputes every existing work session.
    old_recompute=final.recompute_work_totals
    def safe_recompute(c,uid=None):
        try:columns=final._columns(c,'work_sessions')
        except Exception:return None
        if not {'pause_seconds','net_seconds'}.issubset(columns):return None
        return old_recompute(c,uid)
    final.recompute_work_totals=safe_recompute

    # Existing customer APIs keep their shape, but archived state is now visible to the UI.
    try:
        cd=__import__('customer_data');old_list=cd.list_all
        def list_all(c,uid):
            rows=old_list(c,uid);states={r['id']:bool(r['archived']) for r in c.execute('SELECT id,archived FROM customers WHERE owner_id=?',(uid,))}
            for row in rows:row['archived']=states.get(row['id'],False)
            return rows
        cd.list_all=list_all
    except Exception:pass

    # An identity link created without retroactive assignment only matches entries whose event time
    # starts at/after the link creation time. This makes the UI's Ja/Nein question meaningful.
    old_ensure=final._ensure_assignment
    def ensure_assignment(c,uid,provider,event):
        key=event.get('external_key') or ''
        current=c.execute('SELECT * FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key)).fetchone()
        if current:return dict(current)
        typ,val=final._provider_identifier(provider,event.get('raw') or {},event.get('customer_hint') or {})
        if not typ or not val:return {'owner_id':uid,'provider':provider,'external_key':key,'customer_id':None,'project_id':None,'match_type':typ,'match_value':val}
        link=c.execute('SELECT customer_id,created_at FROM customer_identity_links WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',(uid,provider,typ,val)).fetchone()
        if not link:return {'owner_id':uid,'provider':provider,'external_key':key,'customer_id':None,'project_id':None,'match_type':typ,'match_value':val}
        event_row=c.execute('SELECT occurred_at,captured_at FROM provider_events WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key)).fetchone()
        event_time=_parse(event_row['occurred_at'] if event_row else '') or _parse(event_row['captured_at'] if event_row else '')
        created=_parse(link['created_at'])
        if created and event_time and event_time<created:
            return {'owner_id':uid,'provider':provider,'external_key':key,'customer_id':None,'project_id':None,'match_type':typ,'match_value':val}
        c.execute('INSERT INTO provider_assignments(owner_id,provider,external_key,customer_id,project_id,match_type,match_value,assigned_by,assigned_at) VALUES(?,?,?,?,NULL,?,?,NULL,?)',(uid,provider,key,link['customer_id'],typ,val,final.now_iso()))
        return dict(c.execute('SELECT * FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key)).fetchone())
    final._ensure_assignment=ensure_assignment

    previous=app.App.do_POST
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in ('/api/v1/provider/assign/customer','/api/v1/customers/link/add'):
            return previous(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:return self.send_json(400,{'error':str(error)})
        if body.get('bulk',True) is not False:
            # Re-run the already parsed body through the previous handler is impossible because the
            # request stream is consumed. Handle both paths here for deterministic bulk behavior too.
            bulk=True
        else:bulk=False
        session=self.require(csrf=True)
        if not session:return
        uid=session['id']
        try:
            with app.db() as c:
                if path=='/api/v1/provider/assign/customer':
                    provider=str(body.get('provider') or '').lower();key=str(body.get('external_key') or '');cid=int(body.get('customer_id'));final._valid_customer(c,uid,cid)
                    ev=c.execute('SELECT raw_json,hint_json FROM provider_events WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,key)).fetchone()
                    if not ev:raise ValueError('Eintrag nicht gefunden.')
                    raw=json.loads(ev['raw_json'] or '{}');hint=json.loads(ev['hint_json'] or '{}');typ,val=final._provider_identifier(provider,raw,hint)
                    if not typ or not val:raise ValueError('Für diesen Eintrag wurde kein stabiles Zuordnungsmerkmal gefunden.')
                    display=str(raw.get('devicename') or hint.get('device_name') or '')[:500]
                    c.execute('DELETE FROM customer_identity_links WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',(uid,provider,typ,val))
                    c.execute('INSERT INTO customer_identity_links(owner_id,customer_id,provider,link_type,link_value,display_name,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(uid,cid,provider,typ,val,display,uid,final.now_iso()))
                    matched=0
                    events=list(c.execute('SELECT external_key,raw_json,hint_json FROM provider_events WHERE owner_id=? AND provider=?',(uid,provider))) if bulk else [dict(external_key=key,raw_json=ev['raw_json'],hint_json=ev['hint_json'])]
                    for event in events:
                        try:et,evv=final._provider_identifier(provider,json.loads(event['raw_json'] or '{}'),json.loads(event['hint_json'] or '{}'))
                        except Exception:continue
                        if et==typ and evv==val:
                            old=c.execute('SELECT project_id FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,event['external_key'])).fetchone();pid=old['project_id'] if old else None
                            c.execute('DELETE FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,event['external_key']))
                            c.execute('INSERT INTO provider_assignments(owner_id,provider,external_key,customer_id,project_id,match_type,match_value,assigned_by,assigned_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid,provider,event['external_key'],cid,pid,typ,val,uid,final.now_iso()));matched+=1
                    system_features.audit(c,uid,uid,'customer',cid,'provider_assigned',{'provider':provider,'type':typ,'value':val,'matched':matched,'retroactive':bulk})
                    return self.send_json(200,{'ok':True,'matched':matched,'match_type':typ,'match_value':val})
                import admin_controls
                admin_controls.require_permission(c,uid,'customers.edit');cid=int(body.get('customer_id'));final._valid_customer(c,uid,cid)
                provider=str(body.get('provider') or '').lower();typ=str(body.get('link_type') or '').lower();val=str(body.get('link_value') or '').strip();display=str(body.get('display_name') or '')[:500]
                if provider not in ('zammad','starface','teamviewer') or typ not in ('email','phone','teamviewer_id') or not val:raise ValueError('Ungültige Verknüpfung.')
                if typ=='email':val=val.lower()
                previous_link=c.execute('SELECT customer_id FROM customer_identity_links WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',(uid,provider,typ,val)).fetchone()
                c.execute('DELETE FROM customer_identity_links WHERE owner_id=? AND provider=? AND link_type=? AND link_value=?',(uid,provider,typ,val));cur=c.execute('INSERT INTO customer_identity_links(owner_id,customer_id,provider,link_type,link_value,display_name,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(uid,cid,provider,typ,val,display,uid,final.now_iso()))
                matched=0
                if bulk:
                    for event in list(c.execute('SELECT external_key,raw_json,hint_json FROM provider_events WHERE owner_id=? AND provider=?',(uid,provider))):
                        try:et,evv=final._provider_identifier(provider,json.loads(event['raw_json'] or '{}'),json.loads(event['hint_json'] or '{}'))
                        except Exception:continue
                        if et==typ and evv==val:
                            old=c.execute('SELECT project_id FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,event['external_key'])).fetchone();pid=old['project_id'] if old else None
                            c.execute('DELETE FROM provider_assignments WHERE owner_id=? AND provider=? AND external_key=?',(uid,provider,event['external_key']))
                            c.execute('INSERT INTO provider_assignments(owner_id,provider,external_key,customer_id,project_id,match_type,match_value,assigned_by,assigned_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid,provider,event['external_key'],cid,pid,typ,val,uid,final.now_iso()));matched+=1
                system_features.audit(c,uid,uid,'customer',cid,'provider_link_added',{'provider':provider,'type':typ,'value':val,'matched':matched,'retroactive':bulk,'moved_from_customer':previous_link['customer_id'] if previous_link else None})
                return self.send_json(200,{'ok':True,'id':cur.lastrowid,'matched':matched})
        except PermissionError as error:return self.send_json(403,{'error':str(error)})
        except (ValueError,TypeError,json.JSONDecodeError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST
