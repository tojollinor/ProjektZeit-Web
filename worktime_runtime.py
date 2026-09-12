"""Worktime state API, pause actions and auditable workday events."""
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import admin_controls
import system_features
import workday


def _state(c, uid):
    work=c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1',(uid,)).fetchone()
    pause=workday.active_pause(c,uid,work['id']) if work else None
    return {'work':dict(work) if work else None,'pause':dict(pause) if pause else None,
            'state':'pause' if pause else ('working' if work else 'stopped')}


def _audit(c, uid, action, entity_id, changes=None, source='stamp'):
    labels={'begin':'Stempelung · Arbeitsbeginn','end':'Stempelung · Arbeitsende','pause':'Stempelung · Pausenbeginn','resume':'Stempelung · Pausenende'}
    system_features.audit(c,uid,uid,'worktime',entity_id,labels.get(action,action),changes or {},source=source)


def _manager(c,uid):
    return admin_controls.is_superadmin(c,uid) or bool(c.execute("SELECT 1 FROM users WHERE id=? AND role='admin'",(uid,)).fetchone())


def install(app):
    original_init=app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:workday.migrate(c)
    app.init_db=init_db

    original_work_action=app.App.work_action
    def work_action(self,session,body,action):
        uid=session['id']
        before=None
        with app.db() as c:before=_state(c,uid)
        result=original_work_action(self,session,body,action)
        if action in ('begin','end'):
            try:
                with app.db() as c:
                    after=_state(c,uid);entity=(after.get('work') or before.get('work') or {}).get('id') or 'current'
                    if before['state']!=after['state']:_audit(c,uid,action,entity,{'state':{'old':before['state'],'new':after['state']}})
            except Exception:pass
        return result
    app.App.work_action=work_action

    previous_post=app.App.do_POST
    owned={'/api/v1/worktime/state','/api/v1/worktime/action','/api/v1/worktime/history','/api/v1/worktime/manual','/api/v1/worktime/update','/api/v1/worktime/delete'}
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in owned:return previous_post(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:return self.send_json(400,{'error':str(error)})
        session=self.require(csrf=True)
        if not session:return
        uid=session['id']
        try:
            if path=='/api/v1/worktime/state':
                with app.db() as c:return self.send_json(200,_state(c,uid))
            if path=='/api/v1/worktime/history':
                with app.db() as c:
                    rows=c.execute("""SELECT a.id,a.entity_id,a.action,a.source,a.changes_json,a.created_at,u.username actor
                                      FROM audit_events a LEFT JOIN users u ON u.id=a.actor_id
                                      WHERE a.owner_id=? AND a.entity_type='worktime' ORDER BY a.id DESC LIMIT 300""",(uid,))
                    out=[]
                    for r in rows:
                        try:changes=json.loads(r['changes_json'])
                        except Exception:changes={}
                        out.append({'id':r['id'],'entity_id':r['entity_id'],'action':r['action'],'source':r['source'],'changes':changes,'created_at':r['created_at'],'actor':r['actor'] or 'System'})
                    return self.send_json(200,{'history':out})
            if path=='/api/v1/worktime/action':
                action=str(body.get('action') or '').lower()
                if action not in ('begin','end','pause','resume'):raise ValueError('Unbekannte Arbeitszeitaktion.')
                with app.db() as c:
                    before=_state(c,uid);workday.transition(c,uid,action,body,datetime.now(timezone.utc));after=_state(c,uid)
                    entity=(after.get('work') or before.get('work') or {}).get('id') or 'current'
                    _audit(c,uid,action,entity,{'state':{'old':before['state'],'new':after['state']}})
                    return self.send_json(200,{**after,'ok':True})
            with app.db() as c:
                if not _manager(c,uid):raise PermissionError('Dafür fehlt die Berechtigung zur manuellen Arbeitszeitbearbeitung.')
                if path=='/api/v1/worktime/manual':
                    kind=str(body.get('kind') or 'work');a=workday.stamp(str(body.get('started_at')));b=workday.stamp(str(body.get('ended_at')))
                    if b<=a:raise ValueError('Ende muss nach Beginn liegen.')
                    if kind=='pause':
                        sid=int(body.get('work_session_id') or 0);work=c.execute('SELECT * FROM work_sessions WHERE id=? AND owner_id=?',(sid,uid)).fetchone()
                        if not work:raise ValueError('Arbeitszeit nicht gefunden.')
                        rid=c.execute('INSERT INTO work_pauses(owner_id,work_session_id,started_at,ended_at) VALUES(?,?,?,?)',(uid,sid,workday.iso(a),workday.iso(b))).lastrowid
                        workday.reconcile(c,uid);system_features.audit(c,uid,uid,'worktime',sid,'Hinzugefügt · Pause',{'started_at':workday.iso(a),'ended_at':workday.iso(b)},source='manual');return self.send_json(200,{'ok':True,'id':rid})
                    rid=c.execute('INSERT INTO work_sessions(owner_id,started_at,ended_at) VALUES(?,?,?)',(uid,workday.iso(a),workday.iso(b))).lastrowid
                    workday.reconcile(c,uid);system_features.audit(c,uid,uid,'worktime',rid,'Hinzugefügt · Arbeitszeit',{'started_at':workday.iso(a),'ended_at':workday.iso(b)},source='manual');return self.send_json(200,{'ok':True,'id':rid})
                if path=='/api/v1/worktime/update':
                    kind=str(body.get('kind') or 'work');rid=int(body.get('id'));a=workday.stamp(str(body.get('started_at')));b=workday.stamp(str(body.get('ended_at')))
                    if b<=a:raise ValueError('Ende muss nach Beginn liegen.')
                    table='work_pauses' if kind=='pause' else 'work_sessions';row=c.execute(f'SELECT * FROM {table} WHERE id=? AND owner_id=?',(rid,uid)).fetchone()
                    if not row:raise ValueError('Stempelung nicht gefunden.')
                    old={'started_at':row['started_at'],'ended_at':row['ended_at']};new={'started_at':workday.iso(a),'ended_at':workday.iso(b)}
                    c.execute(f'UPDATE {table} SET started_at=?,ended_at=? WHERE id=?',(new['started_at'],new['ended_at'],rid));workday.reconcile(c,uid)
                    target=row['work_session_id'] if kind=='pause' else rid;label='Bearbeitet · Pause' if kind=='pause' else 'Bearbeitet · Arbeitszeit'
                    system_features.audit(c,uid,uid,'worktime',target,label,{'started_at':{'old':old['started_at'],'new':new['started_at']},'ended_at':{'old':old['ended_at'],'new':new['ended_at']}},source='manual');return self.send_json(200,{'ok':True})
                if path=='/api/v1/worktime/delete':
                    kind=str(body.get('kind') or 'work');rid=int(body.get('id'));table='work_pauses' if kind=='pause' else 'work_sessions';row=c.execute(f'SELECT * FROM {table} WHERE id=? AND owner_id=?',(rid,uid)).fetchone()
                    if not row:raise ValueError('Stempelung nicht gefunden.')
                    target=row['work_session_id'] if kind=='pause' else rid;label='Gelöscht · Pause' if kind=='pause' else 'Gelöscht · Arbeitszeit'
                    snapshot=dict(row);c.execute(f'DELETE FROM {table} WHERE id=?',(rid,));workday.reconcile(c,uid);system_features.audit(c,uid,uid,'worktime',target,label,snapshot,source='manual');return self.send_json(200,{'ok':True})
        except PermissionError as error:return self.send_json(403,{'error':str(error)})
        except (ValueError,TypeError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST
