"""Runtime extension for customer CRM data, provider history, admin controls and workshop suggestions."""
import json
import threading
from urllib.parse import urlparse

import admin_controls
import customer_data
import provider_archive
import starface_directory


def install(app):
    app.MFA_ENABLED=True
    original_init = app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:
            customer_data.migrate(c)
            starface_directory.migrate(c)
            provider_archive.migrate(c)
            admin_controls.migrate(c)
            __import__("auth_mfa").migrate(c)
    app.init_db = init_db

    context = threading.local()
    original_integration_list = app.App.integration_list
    original_sf_load = app.starface_calls.load
    original_provider_load = app.provider_lists.load
    original_login = app.App.login

    def cache(provider, result):
        uid=getattr(context,'uid',None)
        if uid and isinstance(result,dict):
            with app.db() as c:
                stats=provider_archive.cache_with_stats(c,uid,provider,result)
                if provider in ('starface','teamviewer'):
                    state=provider_archive.update_sync_state(c,uid,provider)
                    provider_archive.add_log(c,uid,provider,'success','refresh',
                        f'{provider.upper() if provider=="starface" else "TeamViewer"} aktualisiert · {stats["received"]} geprüft · {stats["new"]} neu',
                        {**stats,**state})
        return result

    def sf_load(config,*args,**kwargs): return cache('starface',original_sf_load(config,*args,**kwargs))
    def provider_load(config,*args,**kwargs): return cache(config.get('provider',''),original_provider_load(config,*args,**kwargs))
    def integration_list(self,session,body):
        context.uid=session['id']
        try: return original_integration_list(self,session,body)
        finally: context.uid=None
    app.starface_calls.load=sf_load
    app.provider_lists.load=provider_load
    app.App.integration_list=integration_list

    def login(self, body, native=False):
        username=str(body.get('username','')).strip()
        with app.db() as c:
            row=c.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
            uid=row['id'] if row else None
            before=c.execute('SELECT COUNT(*) n FROM sessions WHERE user_id=?',(uid,)).fetchone()['n'] if uid else 0
        result=original_login(self,body,native=native)
        if uid:
            try:
                with app.db() as c:
                    after=c.execute('SELECT COUNT(*) n FROM sessions WHERE user_id=?',(uid,)).fetchone()['n']
                    if after>before:admin_controls.mark_login(c,uid)
            except Exception:pass
        return result
    app.App.login=login

    def dashboard(self,session):
        uid=session['id']
        import time_workspace
        query=__import__('urllib.parse',fromlist=['parse_qs']).parse_qs(urlparse(self.path).query)
        begin,finish=time_workspace.bounds({'day':query.get('day',[None])[0]})
        with app.db(read_only=True) as c:
            customers=customer_data.choices(c,uid)
            projects=[dict(x) for x in c.execute('SELECT id,name,customer_id,active FROM projects WHERE owner_id=? AND is_system=0 ORDER BY name',(uid,))]
            categories=[dict(x) for x in c.execute('SELECT id,name FROM categories WHERE owner_id=? ORDER BY name',(uid,))]
            entries=[dict(x) for x in c.execute('''SELECT e.id,e.project_id,e.category_id,e.is_idle,e.work_session_id,e.started_at,e.ended_at,e.note,CASE WHEN e.is_idle=1 THEN 'unproduktiv' ELSE p.name END project,c.name customer,k.name category
                FROM entries e JOIN projects p ON p.id=e.project_id LEFT JOIN customers c ON c.id=p.customer_id
                JOIN categories k ON k.id=e.category_id WHERE e.owner_id=? AND (e.ended_at IS NULL OR (e.started_at<? AND e.ended_at>?)) ORDER BY e.started_at DESC LIMIT 1001''',(uid,time_workspace.iso(finish),time_workspace.iso(begin)))]
            today_start,today_end=time_workspace.bounds({})
            now=time_workspace.datetime.now(time_workspace.timezone.utc)
            today_seconds=0
            for item in c.execute('SELECT started_at,ended_at FROM entries WHERE owner_id=? AND is_idle=0 AND started_at<? AND (ended_at IS NULL OR ended_at>?)',(uid,time_workspace.iso(today_end),time_workspace.iso(today_start))):
                a=time_workspace.parse(item['started_at']);b=time_workspace.parse(item['ended_at']) or now
                if a and b:today_seconds+=max(0,int((min(b,today_end).astimezone(time_workspace.timezone.utc)-max(a,today_start).astimezone(time_workspace.timezone.utc)).total_seconds()))
            work=c.execute('SELECT * FROM work_sessions WHERE owner_id=? AND ended_at IS NULL',(uid,)).fetchone()
            can_create_categories=admin_controls.can(c,uid,'categories.create')
            users=[]
            if session['role']=='admin':
                superuser=admin_controls.is_superadmin(c,uid)
                for x in c.execute('SELECT id,username,role,active,created_at FROM users ORDER BY username'):
                    if not superuser and admin_controls.is_superadmin(c,x['id']):continue
                    users.append(dict(x))
        return self.send_json(200,{'can_create_categories':can_create_categories,'customers':customers,'projects':projects,'categories':categories,'entries':entries[:1000],'entries_truncated':len(entries)>1000,'today_seconds':today_seconds,'users':users,'work':dict(work) if work else None})
    app.App.dashboard=dashboard

    def integration_config(uid,provider):
        with app.db() as c:
            if provider=='starface':
                return app.starface_oauth.access(c,uid,app.DATA_DIR)
            row=c.execute('SELECT * FROM integrations WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()
            if not row: raise ValueError('Bitte zuerst die Schnittstelle in den Einstellungen verknüpfen.')
            return app.integrations.config(c,uid,dict(provider=provider,domain=row['domain'],username=row['username'],secret=''),app.DATA_DIR)

    def refresh_teamviewer(uid):
        try:
            config=integration_config(uid,'teamviewer');config['days']=0
            result=original_provider_load(config)
            with app.db() as c: provider_archive.cache_with_stats(c,uid,'teamviewer',result)
        except (ValueError,OSError): pass

    def refresh_zammad_orgs(uid,force=False):
        try:
            with app.db() as c:
                if not force and c.execute('SELECT 1 FROM zammad_organizations WHERE owner_id=? LIMIT 1',(uid,)).fetchone(): return
            config=integration_config(uid,'zammad')
            with app.db() as c: provider_archive.refresh_zammad_organizations(c,uid,config)
        except (ValueError,OSError): pass

    def available_teamviewer_devices(c,uid):
        found={}
        for r in c.execute('''SELECT e.raw_json,e.captured_at FROM provider_events e WHERE e.id IN (SELECT MAX(p.id) FROM provider_events p JOIN event_intervals i ON i.owner_id=p.owner_id AND i.provider=p.provider AND i.external_key=p.external_key WHERE p.owner_id=? AND p.provider=? AND i.match_value<>'' GROUP BY i.match_value)''',(uid,'teamviewer')):
            try: raw=json.loads(r['raw_json'])
            except Exception: continue
            value=next((raw.get(k) for k in ('deviceid','device_id','partner_id','remotecontrol_id') if raw.get(k) not in (None,'')),None)
            if value is None: continue
            key=str(value)
            if key not in found: found[key]={'id':key,'name':str(raw.get('devicename') or raw.get('device_name') or key),'last_seen':str(raw.get('start_date') or r['captured_at'] or '')}
        return sorted(found.values(),key=lambda x:(x['id'],x['name'].casefold()))

    def current_devices(c,uid,customer_id):
        devices=[dict(r) for r in c.execute('SELECT id,provider,external_id,name FROM customer_devices WHERE customer_id=? ORDER BY id',(customer_id,))]
        tv={x['id']:x for x in available_teamviewer_devices(c,uid)}
        for device in devices:
            device['current_name']=device['name'];device['last_seen']=''
            if device['provider']=='teamviewer' and str(device['external_id']) in tv:
                current=tv[str(device['external_id'])];device['current_name']=current['name'];device['last_seen']=current['last_seen']
        return devices

    def available_zammad_orgs(c,uid):
        stored=provider_archive.zammad_organizations(c,uid)
        if stored:return stored
        found={}
        for r in c.execute('SELECT raw_json,hint_json FROM provider_events WHERE owner_id=? AND provider=? ORDER BY captured_at DESC',(uid,'zammad')):
            try: raw=json.loads(r['raw_json']);hint=json.loads(r['hint_json'])
            except Exception: continue
            oid=raw.get('organization_id') or raw.get('organizationId')
            if oid in (None,''): continue
            key=str(oid);org=raw.get('organization')
            name=str(org.get('name') or '') if isinstance(org,dict) else str(org or '')
            found.setdefault(key,{'id':key,'name':name or str(hint.get('name') or key)})
        return sorted(found.values(),key=lambda x:x['name'].casefold())

    def assigned_zammad_orgs(c,uid,customer_id):
        result=[]
        for r in c.execute('SELECT external_key,label FROM customer_provider_links WHERE owner_id=? AND customer_id=? AND provider=?',(uid,customer_id,'zammad')):
            key=str(r['external_key'])
            if key.startswith('zammad:organization:'):result.append({'id':key.split(':',2)[2],'name':r['label']})
        return result

    def zammad_tickets(c,uid,customer_id):
        ids={x['id'] for x in assigned_zammad_orgs(c,uid,customer_id)};out=[]
        if not ids:return out
        for r in c.execute('SELECT e.occurred_at,e.summary,e.raw_json FROM provider_events e JOIN event_organizations o ON o.owner_id=e.owner_id AND o.provider=e.provider AND o.external_key=e.external_key WHERE e.owner_id=? AND o.organization_id IN ('+','.join('?' for _ in ids)+') ORDER BY e.occurred_at DESC LIMIT 500',(uid,*sorted(ids))):
            try: raw=json.loads(r['raw_json'])
            except Exception: continue
            oid=str(raw.get('organization_id') or raw.get('organizationId') or '')
            if oid in ids:out.append({'occurred_at':r['occurred_at'],'summary':r['summary'],'raw':raw})
        return out[:500]

    original_post = app.App.do_POST
    paths={
      '/api/v1/customers/data','/api/v1/customers/assign','/api/v1/customers/profile','/api/v1/customers/detail','/api/v1/customers/activity',
      '/api/v1/customers/phone','/api/v1/customers/phone/update','/api/v1/customers/phone/delete','/api/v1/customers/contact',
      '/api/v1/customers/contact-phone','/api/v1/customers/device','/api/v1/customers/workshop','/api/v1/customers/zammad-organization',
      '/api/v1/customers/timeline','/api/v1/customers/master','/api/v1/starface/users','/api/v1/starface/users/save','/api/v1/archive/sync','/api/v1/archive/status',
      '/api/v1/logs/list','/api/v1/debug/raw','/api/v1/zammad/organizations/refresh',
      '/api/v1/admin/user/active','/api/v1/admin/user/mfa-reset','/api/v1/admin/context','/api/v1/admin/role/save','/api/v1/admin/role/clone','/api/v1/admin/role/delete','/api/v1/admin/role/reset-user',
      '/api/v1/admin/user/profile','/api/v1/admin/user/roles','/api/v1/admin/policies/save','/api/v1/admin/super/settings',
      '/api/v1/admin/smtp/save','/api/v1/admin/smtp/test','/api/v1/admin/smtp/check','/api/v1/admin/user/create'
    }

    def do_POST(self):
        path=urlparse(self.path).path
        if path not in paths:return original_post(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:return self.send_json(400,{'error':str(error)})
        session=self.require(csrf=True)
        if not session:return
        uid=session['id']
        try:
            if path=='/api/v1/admin/user/active':
                with app.db() as c:
                    target,active=admin_controls.set_user_active(c,uid,body)
                    if not active:
                        c.execute("UPDATE session_activity SET ended_at=?,end_reason='Benutzer deaktiviert' WHERE user_id=? AND ended_at=''",(app.now_iso(),target))
                        c.execute('DELETE FROM session_mfa WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=?)',(target,))
                        c.execute('DELETE FROM native_sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=?)',(target,))
                        c.execute('DELETE FROM sessions WHERE user_id=?',(target,))
                        c.execute("UPDATE api_tokens SET revoked_at=? WHERE owner_id=? AND revoked_at=''",(app.now_iso(),target))
                    __import__('system_features').audit(c,uid,uid,'user',target,'activated' if active else 'deactivated',{})
                return self.send_json(200,{'ok':True,'active':active})
            if path=='/api/v1/admin/user/create':
                with app.db() as c:ident=admin_controls.create_user(c,uid,body,app.hash_password)
                return self.send_json(200,{'ok':True,'id':ident})
            if path=='/api/v1/admin/context':
                with app.db() as c:return self.send_json(200,admin_controls.admin_context(c,uid))
            if path=='/api/v1/admin/role/save':
                with app.db() as c:rid=admin_controls.save_role(c,uid,body);return self.send_json(200,{'ok':True,'role_id':rid})
            if path=='/api/v1/admin/role/clone':
                with app.db() as c:rid=admin_controls.clone_role(c,uid,body.get('id'));return self.send_json(200,{'ok':True,'role_id':rid})
            if path=='/api/v1/admin/role/delete':
                with app.db() as c:admin_controls.delete_role(c,uid,body.get('id'));return self.send_json(200,{'ok':True})
            if path=='/api/v1/admin/role/reset-user':
                with app.db() as c:admin_controls.reset_user_role(c,uid);return self.send_json(200,{'ok':True})
            if path=='/api/v1/admin/user/profile':
                with app.db() as c:admin_controls.update_user_profile(c,uid,body);return self.send_json(200,{'ok':True})
            if path=='/api/v1/admin/user/roles':
                with app.db() as c:admin_controls.assign_roles(c,uid,body.get('user_id'),body.get('role_ids'));return self.send_json(200,{'ok':True})
            if path=='/api/v1/admin/policies/save':
                with app.db() as c:
                    admin_controls.require_permission(c,uid,'security.policies.edit')
                    values=body.get('policies') if isinstance(body.get('policies'),dict) else {}
                    previous=admin_controls.policy_values(c)
                    mode=values.get('two_factor_mode',previous['two_factor_mode'])
                    if mode not in ('optional','required','roles'):raise ValueError('Ungültiger 2FA-Modus.')
                    if 'email_mfa_code_length' in values:
                        values['email_mfa_code_length']=int(values['email_mfa_code_length'])
                        if not 6<=values['email_mfa_code_length']<=12:raise ValueError('E-Mail-Codes müssen 6 bis 12 Zeichen lang sein.')
                    if values.get('email_mfa_code_kind',previous['email_mfa_code_kind']) not in ('numeric','alphanumeric'):
                        raise ValueError('Ungültige Zeichenart für E-Mail-Codes.')
                    if 'two_factor_required_roles' in values:
                        if not isinstance(values['two_factor_required_roles'],list):raise ValueError('Bitte gültige Rollen für die 2FA-Pflicht auswählen.')
                        existing={r['role_key'] for r in c.execute('SELECT role_key FROM role_definitions')}
                        values['two_factor_required_roles']=sorted({str(key) for key in values['two_factor_required_roles']} & existing)
                    if mode=='roles' and not values.get('two_factor_required_roles',previous['two_factor_required_roles']):
                        raise ValueError('Bitte mindestens eine Rolle für die 2FA-Pflicht auswählen.')
                    email_keys={'email_mfa_code_length','email_mfa_code_kind','email_password_reset_allowed','email_verify_required','notify_password_change','notify_email_change','notify_two_factor_change'}
                    email_service=__import__('email_runtime')
                    if any(key in values and values[key]!=previous[key] for key in email_keys) and not email_service.smtp_configured(c):
                        raise ValueError('E-Mail ist nicht eingerichtet.')
                    link_keys={'email_password_reset_allowed','email_verify_required'}
                    if any(key in values and bool(values[key]) and values[key]!=previous[key] for key in link_keys) and not email_service.link_features_configured(c):
                        raise ValueError('Für E-Mail-Links fehlt die öffentliche ProjektZeit-Adresse (APP_PUBLIC_URL).')
                    if values.get('email_verify_required',previous['email_verify_required']) and not previous['email_verify_required']:
                        missing=c.execute("""SELECT u.username FROM users u LEFT JOIN user_profiles p ON p.user_id=u.id
                                             WHERE u.active=1 AND (p.email IS NULL OR TRIM(p.email)='') ORDER BY u.id LIMIT 1""").fetchone()
                        if missing:raise ValueError('Vor der verpflichtenden E-Mail-Bestätigung braucht jeder aktive Benutzer eine E-Mail-Adresse (fehlt bei: '+missing['username']+').')
                    for key,default in admin_controls.POLICY_DEFAULTS.items():
                        if key in values and values[key]!=previous[key]:admin_controls.set_setting(c,'policy.'+key,values[key])
                    roles_changed=values.get('two_factor_required_roles',previous['two_factor_required_roles'])!=previous['two_factor_required_roles']
                    if mode!=previous['two_factor_mode'] or roles_changed:
                        c.execute("UPDATE session_activity SET ended_at=?,end_reason='2FA-Richtlinie geändert' WHERE ended_at=''",(app.now_iso(),))
                        c.execute('DELETE FROM session_mfa');c.execute('DELETE FROM native_sessions');c.execute('DELETE FROM sessions')
                    return self.send_json(200,{'ok':True,'policies':admin_controls.policy_values(c)})
            if path=='/api/v1/admin/user/mfa-reset':
                with app.db() as c:
                    admin_controls.require_permission(c,uid,'security.2fa.reset_user')
                    target=int(body.get('user_id') or 0)
                    if target==uid:raise ValueError('Eigene 2FA nicht über die Benutzerverwaltung zurücksetzen. Bitte Wiederherstellungscode verwenden.')
                    user=c.execute('SELECT role FROM users WHERE id=?',(target,)).fetchone()
                    if not user:raise ValueError('Benutzer nicht gefunden.')
                    if user['role']=='admin' or not admin_controls.setting(c,'security.admin_may_reset_2fa',True):
                        admin_controls.require_permission(c,uid,'system.options.edit')
                    c.execute('DELETE FROM session_mfa WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=?)',(target,))
                    c.execute('DELETE FROM native_sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=?)',(target,))
                    c.execute('DELETE FROM sessions WHERE user_id=?',(target,))
                    c.execute('DELETE FROM user_mfa WHERE user_id=?',(target,))
                    __import__('email_runtime').reset_email_mfa(c,target)
                    __import__('email_runtime').two_factor_changed(c,app.DATA_DIR,target,False)
                    __import__('system_features').audit(c,uid,uid,'user',target,'mfa_reset',{})
                return self.send_json(200,{'ok':True})
            if path=='/api/v1/admin/super/settings':
                with app.db() as c:
                    admin_controls.require_permission(c,uid,'system.options.edit')
                    admin_controls.set_setting(c,'security.admin_may_reset_2fa',bool(body.get('admin_may_reset_2fa')))
                    return self.send_json(200,{'ok':True})
            if path=='/api/v1/admin/smtp/save':
                with app.db() as c:admin_controls.save_smtp(c,uid,body,app.DATA_DIR);return self.send_json(200,{'ok':True,'smtp':admin_controls.smtp_public(c)})
            if path in ('/api/v1/admin/smtp/test','/api/v1/admin/smtp/check'):
                with app.db(read_only=True) as c:
                    admin_controls.require_permission(c,uid,'smtp.test');settings,password=admin_controls._smtp_credentials(c,app.DATA_DIR);settings=dict(settings)
                result=__import__('smtp_service').check(settings,password,recipient=str(body.get('recipient') or '') if path.endswith('/test') else None)
                return self.send_json(200,result)
            if path=='/api/v1/customers/master':
                cid=int(body.get('customer_id'))
                with app.db() as c:
                    if body.get('save'):
                        admin_controls.save_customer_master(c,uid,cid,body)
                    return self.send_json(200,{'master':admin_controls.customer_master(c,uid,cid)})
            if path=='/api/v1/archive/sync':
                provider=str(body.get('provider') or '').lower()
                if provider not in ('starface','teamviewer'):raise ValueError('History-Sync ist nur für STARFACE und TeamViewer verfügbar.')
                if not app.integrations.TEST_LOCK.acquire(blocking=False):return self.send_json(429,{'error':'Es läuft bereits eine Schnittstellenabfrage.'})
                try:
                    config=integration_config(uid,provider)
                    result=provider_archive.sync_starface(app.db,uid,config,True) if provider=='starface' else provider_archive.sync_teamviewer(app.db,uid,config,True)
                    return self.send_json(200,result)
                finally:app.integrations.TEST_LOCK.release()
            if path=='/api/v1/archive/status':
                with app.db() as c:return self.send_json(200,{'states':provider_archive.sync_states(c,uid)})
            if path=='/api/v1/logs/list':
                with app.db() as c:
                    category,level=str(body.get('category') or ''),str(body.get('level') or '')
                    return self.send_json(200,{'logs':provider_archive.list_logs(c,uid,category,level,body.get('limit',25)),'total':provider_archive.count_logs(c,uid,category,level)})
            if path=='/api/v1/debug/raw':
                provider=str(body.get('provider') or '').lower()
                if provider not in provider_archive.PROVIDERS:raise ValueError('Unbekannter Debug-Dienst.')
                config=integration_config(uid,provider)
                result=provider_archive.debug_raw(uid,provider,config)
                with app.db() as c:provider_archive.add_log(c,uid,provider,'info','debug_raw',f'{provider} Rohdaten abgerufen',{'endpoint':result.get('endpoint'),'http_status':result.get('http_status')})
                return self.send_json(200,result)
            if path=='/api/v1/zammad/organizations/refresh':
                config=integration_config(uid,'zammad')
                with app.db() as c:
                    count=provider_archive.refresh_zammad_organizations(c,uid,config)
                    return self.send_json(200,{'ok':True,'count':count,'organizations':provider_archive.zammad_organizations(c,uid)})
            if path=='/api/v1/starface/users/save':
                with app.db() as c:
                    starface_directory.save_manual(c,uid,body.get('extension'),body.get('name'))
                    return self.send_json(200,{'ok':True,'users':starface_directory.list_all(c,uid)})
            if path=='/api/v1/starface/users':
                auto={'imported':0,'errors':[],'sources':[]}
                try:
                    config=integration_config(uid,'starface')
                    with app.db() as c:auto=starface_directory.refresh(c,uid,config);users=starface_directory.list_all(c,uid)
                except (ValueError,OSError) as error:
                    auto['errors'].append(str(error))
                    with app.db() as c:users=starface_directory.list_all(c,uid)
                return self.send_json(200,{'users':users,'auto':auto})
            if path in ('/api/v1/customers/detail','/api/v1/customers/activity'):
                with app.db(read_only=True) as c:
                    cid=int(body.get('id'));customer=customer_data.get_one(c,uid,cid)
                    customer['master']=admin_controls.customer_master(c,uid,cid)
                    return self.send_json(200,{'customer':customer,'activity':customer_data.activity(c,uid,cid),'teamviewer_devices':available_teamviewer_devices(c,uid), 'zammad_organizations':provider_archive.zammad_organizations(c,uid),'zammad_assigned':assigned_zammad_orgs(c,uid,cid),'zammad_tickets':zammad_tickets(c,uid,cid)})
            with app.db() as c:
                if path=='/api/v1/customers/data':return self.send_json(200,{'customers':customer_data.list_all(c,uid),'links':{p:customer_data.links(c,uid,p) for p in customer_data.PROVIDERS}})
                if path=='/api/v1/customers/workshop':return self.send_json(200,{'suggestions':customer_data.suggestions(c,uid),'teamviewer_devices':available_teamviewer_devices(c,uid)})

                if path=='/api/v1/customers/timeline':
                    cid=int(body.get('id'));return self.send_json(200,{'events':provider_archive.customer_timeline(c,uid,cid,body.get('day'))})
                if path=='/api/v1/customers/zammad-organization':
                    cid=int(body.get('customer_id'));oid=str(body.get('organization_id') or '').strip();name=str(body.get('name') or oid).strip()
                    if not oid or not customer_data._customer(c,uid,cid):raise ValueError('Ungültige Zammad-Organisation.')
                    key='zammad:organization:'+oid;c.execute('DELETE FROM customer_provider_links WHERE owner_id=? AND provider=? AND external_key=?',(uid,'zammad',key));c.execute('INSERT INTO customer_provider_links(owner_id,customer_id,provider,external_key,label) VALUES(?,?,?,?,?)',(uid,cid,'zammad',key,name));return self.send_json(200,{'ok':True})
                if path=='/api/v1/customers/assign':cid=customer_data.assign(c,uid,body);return self.send_json(200,{'ok':True,'customer_id':cid})
                if path=='/api/v1/customers/phone/update':provider_archive.phone_update(c,uid,body);return self.send_json(200,{'ok':True})
                if path=='/api/v1/customers/phone/delete':provider_archive.phone_delete(c,uid,body);return self.send_json(200,{'ok':True})
                if path=='/api/v1/customers/phone':
                    cid=int(body.get('customer_id'));ok=customer_data.add_company_phone(c,uid,cid,body.get('number'),body.get('label'),body.get('source','manual'))
                    if not ok:raise ValueError('Kundenrufnummern müssen mehr als fünf Ziffern enthalten.')
                    return self.send_json(200,{'ok':True})
                if path=='/api/v1/customers/contact':cid=int(body.get('customer_id'));contact_id=customer_data.add_contact(c,uid,cid,body.get('name'),body.get('email'),body.get('note'),body.get('phones'));return self.send_json(200,{'ok':True,'contact_id':contact_id})
                if path=='/api/v1/customers/contact-phone':
                    ok=customer_data.add_contact_phone(c,uid,int(body.get('contact_id')),body.get('number'),body.get('label'),body.get('source','manual'))
                    if not ok:raise ValueError('Rufnummern müssen mehr als fünf Ziffern enthalten.')
                    return self.send_json(200,{'ok':True})
                if path=='/api/v1/customers/device':customer_data.add_device(c,uid,int(body.get('customer_id')),body.get('provider','teamviewer'),body.get('external_id'),body.get('name'));return self.send_json(200,{'ok':True})
                cid=body.get('id')
                if cid:customer_data.update(c,uid,int(cid),body);cid=int(cid)
                else:cid=customer_data.create(c,uid,body)
                return self.send_json(200,{'ok':True,'customer_id':cid})
        except PermissionError as error:
            return self.send_json(403,{'error':str(error)})
        except (ValueError,TypeError,OSError) as error:
            try:
                if path.startswith('/api/v1/archive/') or path=='/api/v1/debug/raw':
                    with app.db() as c:provider_archive.add_log(c,uid,str(body.get('provider') or 'system'),'error','request_failed',str(error),{'path':path})
            except Exception:pass
            return self.send_json(400,{'error':str(error) if isinstance(error,(ValueError,TypeError)) else 'Schnittstelle nicht erreichbar.'})
    app.App.do_POST=do_POST


def serve(app):
    install(app);app.init_db()
    print('ProjektZeit Web läuft auf http://%s:%d'%(app.HOST,app.PORT))
    app.ThreadingHTTPServer((app.HOST,app.PORT),app.App).serve_forever()
