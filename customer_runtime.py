"""Runtime extension for customer CRM data, provider history and workshop suggestions."""
import threading
from urllib.parse import urlparse
import customer_data


def install(app):
    original_init = app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c: customer_data.migrate(c)
    app.init_db = init_db

    # Cache every safely normalized provider list for customer history/suggestions.
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

    original_post = app.App.do_POST
    paths={
      '/api/v1/customers/data','/api/v1/customers/assign','/api/v1/customers/profile',
      '/api/v1/customers/detail','/api/v1/customers/activity','/api/v1/customers/phone',
      '/api/v1/customers/contact','/api/v1/customers/contact-phone','/api/v1/customers/device',
      '/api/v1/customers/workshop'
    }
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in paths: return original_post(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict): raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error: return self.send_json(400,{'error':str(error)})
        session=self.require(csrf=True)
        if not session:return
        uid=session['id']
        try:
            with app.db() as c:
                if path=='/api/v1/customers/data':
                    return self.send_json(200,{'customers':customer_data.list_all(c,uid),'links':{p:customer_data.links(c,uid,p) for p in customer_data.PROVIDERS}})
                if path=='/api/v1/customers/workshop':
                    return self.send_json(200,{'suggestions':customer_data.suggestions(c,uid)})
                if path in ('/api/v1/customers/detail','/api/v1/customers/activity'):
                    cid=int(body.get('id'))
                    customers=[x for x in customer_data.list_all(c,uid) if x['id']==cid]
                    if not customers: raise ValueError('Unbekannter Kunde.')
                    return self.send_json(200,{'customer':customers[0],'activity':customer_data.activity(c,uid,cid)})
                if path=='/api/v1/customers/assign':
                    cid=customer_data.assign(c,uid,body);return self.send_json(200,{'ok':True,'customer_id':cid})
                if path=='/api/v1/customers/phone':
                    cid=int(body.get('customer_id'));ok=customer_data.add_company_phone(c,uid,cid,body.get('number'),body.get('label'),body.get('source','manual'))
                    if not ok: raise ValueError('Kundenrufnummern müssen mehr als fünf Ziffern enthalten.')
                    return self.send_json(200,{'ok':True})
                if path=='/api/v1/customers/contact':
                    cid=int(body.get('customer_id'));contact_id=customer_data.add_contact(c,uid,cid,body.get('name'),body.get('email'),body.get('note'),body.get('phones'))
                    return self.send_json(200,{'ok':True,'contact_id':contact_id})
                if path=='/api/v1/customers/contact-phone':
                    ok=customer_data.add_contact_phone(c,uid,int(body.get('contact_id')),body.get('number'),body.get('label'),body.get('source','manual'))
                    if not ok: raise ValueError('Rufnummern müssen mehr als fünf Ziffern enthalten.')
                    return self.send_json(200,{'ok':True})
                if path=='/api/v1/customers/device':
                    customer_data.add_device(c,uid,int(body.get('customer_id')),body.get('provider','teamviewer'),body.get('external_id'),body.get('name'))
                    return self.send_json(200,{'ok':True})
                cid=body.get('id')
                if cid: customer_data.update(c,uid,int(cid),body);cid=int(cid)
                else: cid=customer_data.create(c,uid,body)
                return self.send_json(200,{'ok':True,'customer_id':cid})
        except (ValueError,TypeError) as error: return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST


def serve(app):
    install(app);app.init_db()
    print('ProjektZeit Web läuft auf http://%s:%d'%(app.HOST,app.PORT))
    app.ThreadingHTTPServer((app.HOST,app.PORT),app.App).serve_forever()
