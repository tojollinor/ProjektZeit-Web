"""Runtime extension for customer CRM data, provider history and workshop suggestions."""
import json
import threading
from urllib.parse import urlparse
import customer_data
import starface_directory


def install(app):
    original_init = app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:
            customer_data.migrate(c)
            starface_directory.migrate(c)
    app.init_db = init_db

    context = threading.local()
    original_integration_list = app.App.integration_list
    original_sf_load = app.starface_calls.load
    original_provider_load = app.provider_lists.load
    def cache(provider, result):
        uid=getattr(context,'uid',None)
        if uid and isinstance(result,dict):
            with app.db() as c: customer_data.cache_rows(c,uid,provider,result)
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

    def refresh_teamviewer(uid):
        try:
            with app.db() as c:
                row=c.execute('SELECT * FROM integrations WHERE owner_id=? AND provider=?',(uid,'teamviewer')).fetchone()
                if not row:return
                config=app.integrations.config(c,uid,dict(provider='teamviewer',domain=row['domain'],username=row['username'],secret=''),app.DATA_DIR)
            config['days']=0
            result=original_provider_load(config)
            with app.db() as c: customer_data.cache_rows(c,uid,'teamviewer',result)
        except (ValueError,OSError): pass

    def available_teamviewer_devices(c,uid):
        found={}
        for r in c.execute('SELECT raw_json,captured_at FROM provider_events WHERE owner_id=? AND provider=? ORDER BY captured_at DESC',(uid,'teamviewer')):
            try: raw=json.loads(r['raw_json'])
            except Exception: continue
            value=next((raw.get(k) for k in ('deviceid','device_id','partner_id','remotecontrol_id') if raw.get(k) not in (None,'')),None)
            if value is None: continue
            key=str(value)
            if key not in found: found[key]={'id':key,'name':str(raw.get('devicename') or raw.get('device_name') or key),'last_seen':str(raw.get('start_date') or r['captured_at'] or '')}
        return list(found.values())

    def current_devices(c,uid,customer_id):
        devices=[dict(r) for r in c.execute('SELECT id,provider,external_id,name FROM customer_devices WHERE owner_id=? AND customer_id=? ORDER BY id',(uid,customer_id))]
        tv={x['id']:x for x in available_teamviewer_devices(c,uid)}
        for device in devices:
            device['current_name']=device['name'];device['last_seen']=''
            if device['provider']=='teamviewer' and str(device['external_id']) in tv:
                current=tv[str(device['external_id'])];device['current_name']=current['name'];device['last_seen']=current['last_seen']
        return devices

    def available_zammad_orgs(c,uid):
        found={}
        for r in c.execute('SELECT raw_json,hint_json,captured_at FROM provider_events WHERE owner_id=? AND provider=? ORDER BY captured_at DESC',(uid,'zammad')):
            try: raw=json.loads(r['raw_json']);hint=json.loads(r['hint_json'])
            except Exception: continue
            oid=raw.get('organization_id') or raw.get('organizationId')
            if oid in (None,''): continue
            key=str(oid);org=raw.get('organization')
            if isinstance(org,dict): name=str(org.get('name') or '')
            else: name=str(org or '')
            name=name or str(hint.get('name') or key)
            if key not in found: found[key]={'id':key,'name':name}
        return list(found.values())

    def assigned_zammad_orgs(c,uid,customer_id):
        result=[]
        for r in c.execute('SELECT external_key,label FROM customer_provider_links WHERE owner_id=? AND customer_id=? AND provider=?',(uid,customer_id,'zammad')):
            key=str(r['external_key'])
            if key.startswith('zammad:organization:'): result.append({'id':key.split(':',2)[2],'name':r['label']})
        return result

    def zammad_tickets(c,uid,customer_id):
        ids={x['id'] for x in assigned_zammad_orgs(c,uid,customer_id)};out=[]
        if not ids:return out
        for r in c.execute('SELECT occurred_at,summary,raw_json FROM provider_events WHERE owner_id=? AND provider=? ORDER BY captured_at DESC',(uid,'zammad')):
            try: raw=json.loads(r['raw_json'])
            except Exception: continue
            oid=str(raw.get('organization_id') or raw.get('organizationId') or '')
            if oid in ids: out.append({'occurred_at':r['occurred_at'],'summary':r['summary'],'raw':raw})
        return out[:200]

    original_post = app.App.do_POST
    paths={'/api/v1/customers/data','/api/v1/customers/assign','/api/v1/customers/profile','/api/v1/customers/detail','/api/v1/customers/activity','/api/v1/customers/phone','/api/v1/customers/contact','/api/v1/customers/contact-phone','/api/v1/customers/device','/api/v1/customers/workshop','/api/v1/customers/zammad-organization','/api/v1/starface/users','/api/v1/starface/users/save'}
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
            if path=='/api/v1/starface/users/save':
                with app.db() as c: starface_directory.save_manual(c,uid,body.get('extension'),body.get('name'));return self.send_json(200,{'ok':True,'users':starface_directory.list_all(c,uid)})
            if path=='/api/v1/starface/users':
                auto={'imported':0,'errors':[]}
                try:
                    with app.db() as c: config=app.starface_oauth.access(c,uid,app.DATA_DIR)
                    with app.db() as c: auto=starface_directory.refresh(c,uid,config);users=starface_directory.list_all(c,uid)
                except (ValueError,OSError) as error:
                    auto['errors'].append(str(error))
                    with app.db() as c: users=starface_directory.list_all(c,uid)
                return self.send_json(200,{'users':users,'auto':auto})
            if path in ('/api/v1/customers/detail','/api/v1/customers/activity'):refresh_teamviewer(uid)
            with app.db() as c:
                if path=='/api/v1/customers/data':return self.send_json(200,{'customers':customer_data.list_all(c,uid),'links':{p:customer_data.links(c,uid,p) for p in customer_data.PROVIDERS}})
                if path=='/api/v1/customers/workshop':return self.send_json(200,{'suggestions':customer_data.suggestions(c,uid),'teamviewer_devices':available_teamviewer_devices(c,uid)})
                if path in ('/api/v1/customers/detail','/api/v1/customers/activity'):
                    cid=int(body.get('id'));customers=[x for x in customer_data.list_all(c,uid) if x['id']==cid]
                    if not customers:raise ValueError('Unbekannter Kunde.')
                    customer=customers[0];customer['devices']=current_devices(c,uid,cid)
                    return self.send_json(200,{'customer':customer,'activity':customer_data.activity(c,uid,cid),'teamviewer_devices':available_teamviewer_devices(c,uid),'zammad_organizations':available_zammad_orgs(c,uid),'zammad_assigned':assigned_zammad_orgs(c,uid,cid),'zammad_tickets':zammad_tickets(c,uid,cid)})
                if path=='/api/v1/customers/zammad-organization':
                    cid=int(body.get('customer_id'));oid=str(body.get('organization_id') or '').strip();name=str(body.get('name') or oid).strip()
                    if not oid or not customer_data._customer(c,uid,cid):raise ValueError('Ungültige Zammad-Organisation.')
                    key='zammad:organization:'+oid;c.execute('DELETE FROM customer_provider_links WHERE owner_id=? AND provider=? AND external_key=?',(uid,'zammad',key));c.execute('INSERT INTO customer_provider_links(owner_id,customer_id,provider,external_key,label) VALUES(?,?,?,?,?)',(uid,cid,'zammad',key,name));return self.send_json(200,{'ok':True})
                if path=='/api/v1/customers/assign':cid=customer_data.assign(c,uid,body);return self.send_json(200,{'ok':True,'customer_id':cid})
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
        except (ValueError,TypeError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST


def serve(app):
    install(app);app.init_db()
    print('ProjektZeit Web läuft auf http://%s:%d'%(app.HOST,app.PORT))
    app.ThreadingHTTPServer((app.HOST,app.PORT),app.App).serve_forever()
