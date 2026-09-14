"""Worktime state API, pause actions and auditable workday events."""
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import admin_controls
import system_features
import workday

PERMISSIONS=[
    ('worktime.view','Arbeitszeiten ansehen'),
    ('worktime.manual_add','Arbeitszeiten manuell anlegen'),
    ('worktime.edit','Arbeitszeiten bearbeiten'),
    ('worktime.delete','Arbeitszeiten löschen'),
]


def _register_permissions():
    existing={k for group in admin_controls.PERMISSION_CATEGORIES.values() for k,_ in group}
    if 'worktime.view' not in existing:admin_controls.PERMISSION_CATEGORIES['Arbeitszeit']=PERMISSIONS[:]
    admin_controls.ALL_PERMISSIONS.update(k for k,_ in PERMISSIONS)
    admin_controls.DEFAULT_USER_PERMISSIONS.add('worktime.view')
    admin_controls.DEFAULT_ADMIN_PERMISSIONS.update(k for k,_ in PERMISSIONS)


def _state(c,uid):
    work=c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1',(uid,)).fetchone()
    pause=workday.active_pause(c,uid,work['id']) if work else None
    return {'work':dict(work) if work else None,'pause':dict(pause) if pause else None,'state':'pause' if pause else ('working' if work else 'stopped')}


def _audit(c,uid,action,entity_id,changes=None,source='stamp'):
    labels={'begin':'Stempelung · Arbeitsbeginn','end':'Stempelung · Arbeitsende','pause':'Stempelung · Pausenbeginn','resume':'Stempelung · Pausenende'}
    system_features.audit(c,uid,uid,'worktime',entity_id,labels.get(action,action),changes or {},source=source)


def _require(c,uid,permission):
    if permission=='worktime.view':return
    admin_controls.require_permission(c,uid,permission)


def install(app):
    _register_permissions()
    original_init=app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:workday.migrate(c)
    app.init_db=init_db

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
                with app.db() as c:_require(c,uid,'worktime.view');return self.send_json(200,_state(c,uid))
            if path=='/api/v1/worktime/history':
                with app.db() as c:
                    _require(c,uid,'worktime.view');rows=c.execute("""SELECT a.id,a.entity_id,a.action,a.source,a.changes_json,a.created_at,u.username actor FROM audit_events a LEFT JOIN users u ON u.id=a.actor_id WHERE a.owner_id=? AND a.entity_type='worktime' ORDER BY a.id DESC LIMIT 300""",(uid,));out=[]
                    for r in rows:
                        try:changes=json.loads(r['changes_json'])
                        except Exception:changes={}
                        out.append({'id':r['id'],'entity_id':r['entity_id'],'action':r['action'],'source':r['source'],'changes':changes,'created_at':r['created_at'],'actor':r['actor'] or 'System'})
                    return self.send_json(200,{'history':out})
            if path=='/api/v1/worktime/action':
                action=str(body.get('action') or '').lower()
                if action not in ('begin','end','pause','resume'):raise ValueError('Unbekannte Arbeitszeitaktion.')
                with app.db() as c:
                    _require(c,uid,'worktime.view');before=_state(c,uid);workday.transition(c,uid,action,body,datetime.now(timezone.utc));after=_state(c,uid);return self.send_json(200,{**after,'ok':True})
            with app.db() as c:
                permission={'/api/v1/worktime/manual':'worktime.manual_add','/api/v1/worktime/update':'worktime.edit','/api/v1/worktime/delete':'worktime.delete'}[path];_require(c,uid,permission)
                import staff_time as st
                c.execute('BEGIN IMMEDIATE')
                if getattr(c,'dialect','')=='mariadb':c.execute('SELECT id FROM company_write_lock WHERE id=1 FOR UPDATE')
                kind=str(body.get('kind') or 'work');rid=int(body.get('id') or 0)
                table='work_pauses' if kind=='pause' else 'work_sessions'
                row=c.execute(f'SELECT * FROM {table} WHERE id=? AND owner_id=?',(rid,uid)).fetchone() if rid else None
                if path!='/api/v1/worktime/manual' and not row:raise ValueError('Stempelung nicht gefunden.')
                sid=(row['work_session_id'] if row else int(body.get('work_session_id') or 0)) if kind=='pause' else rid
                work=c.execute('SELECT * FROM work_sessions WHERE id=? AND owner_id=?',(sid,uid)).fetchone() if sid else None
                if kind=='pause' and not work:raise ValueError('Arbeitszeit nicht gefunden.')
                if row and (body.get('original_start')!=row['started_at'] or body.get('original_end')!=row['ended_at']):raise ValueError('Stempelung wurde geändert. Bitte Detailansicht neu öffnen.')
                note=str(body.get('note') or '').strip()
                if not note:raise ValueError('Begründung erforderlich.')
                if path=='/api/v1/worktime/delete' and kind!='pause':
                    if c.execute('SELECT 1 FROM entries WHERE work_session_id=? AND is_idle=0',(sid,)).fetchone():raise ValueError('Arbeitszeit enthält Projektzeiten und kann nicht gelöscht werden.')
                    if not work['ended_at']:raise ValueError('Laufende Arbeitszeit zuerst beenden.')
                    for dt in (work['started_at'],work['ended_at']):
                        if c.execute('SELECT 1 FROM staff_month_closures WHERE user_id=? AND month=?',(uid,str(st.parse(dt).astimezone(st.TZ).date())[:7])).fetchone():raise ValueError('Monat abgeschlossen.')
                    pauses=[dict(x) for x in c.execute('SELECT * FROM work_pauses WHERE work_session_id=?',(sid,))]
                    c.execute('DELETE FROM entries WHERE work_session_id=? AND is_idle=1',(sid,));c.execute('DELETE FROM work_pauses WHERE work_session_id=?',(sid,));c.execute('DELETE FROM work_sessions WHERE id=?',(sid,))
                    system_features.audit(c,uid,uid,'worktime',sid,'Arbeitszeit gelöscht',{'day':str(st.parse(work['started_at']).astimezone(st.TZ).date()),'before':dict(work),'pauses_before':pauses,'note':note})
                    return self.send_json(200,{'ok':True})
                data={'user_id':uid,'day':str(st.parse(work['started_at'] if work else body['started_at']).astimezone(st.TZ).date()),'work_id':sid,'original_start':work['started_at'] if work else None,'original_end':work['ended_at'] if work else None,'start':body.get('started_at'),'end':body.get('ended_at'),'note':note}
                if kind=='pause':
                    original=[dict(x) for x in c.execute('SELECT * FROM work_pauses WHERE work_session_id=? ORDER BY started_at,id',(sid,))]
                    pauses=[x for x in original if x['id']!=rid]
                    if path!='/api/v1/worktime/delete':pauses.append({'started_at':body['started_at'],'ended_at':body['ended_at']})
                    data.update(start=work['started_at'],end=work['ended_at'],pauses=pauses,original_pauses=original)
                result=st.correction(c,uid,data)
                return self.send_json(200,result)
        except PermissionError as error:return self.send_json(403,{'error':str(error)})
        except (ValueError,TypeError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST
