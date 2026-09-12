"""Local Zammad ticket cache with complete, user-owned snapshot refreshes."""
import base64
import json
import re
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

import integrations
import provider_archive
import provider_lists

_JOBS = {}
_LOCK = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS zammad_ticket_cache (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      ticket_id TEXT NOT NULL,
      number TEXT NOT NULL DEFAULT '',
      title TEXT NOT NULL DEFAULT '',
      organization TEXT NOT NULL DEFAULT '',
      state TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL DEFAULT '',
      raw_json LONGTEXT NOT NULL,
      hint_json LONGTEXT NOT NULL,
      sync_generation TEXT NOT NULL DEFAULT '',
      synced_at TEXT NOT NULL DEFAULT '',
      UNIQUE(owner_id,ticket_id)
    );
    CREATE INDEX IF NOT EXISTS idx_zammad_ticket_owner_updated ON zammad_ticket_cache(owner_id,updated_at DESC);
    CREATE TABLE IF NOT EXISTS provider_access_state (
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      provider TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'unknown',
      message TEXT NOT NULL DEFAULT '',
      checked_at TEXT NOT NULL DEFAULT '',
      PRIMARY KEY(owner_id,provider)
    );
    ''')


def _set_access(c, uid, state, message=''):
    c.execute('DELETE FROM provider_access_state WHERE owner_id=? AND provider=?',(uid,'zammad'))
    c.execute('INSERT INTO provider_access_state(owner_id,provider,state,message,checked_at) VALUES(?,?,?,?,?)',
              (uid,'zammad',state,str(message or '')[:500],now_iso()))


def _config(app, uid):
    with app.db() as c:
        row=c.execute('SELECT * FROM integrations WHERE owner_id=? AND provider=?',(uid,'zammad')).fetchone()
        if not row: raise ValueError('Bitte zuerst Zammad in den Einstellungen verknüpfen.')
        return app.integrations.config(c,uid,dict(provider='zammad',domain=row['domain'],username=row['username'],secret=''),app.DATA_DIR)


def _auth(config):
    token=base64.b64encode((config['username']+':'+config['secret']).encode()).decode()
    return {'Authorization':'Basic '+token}


def _ticket_name(ticket):
    org=ticket.get('organization')
    if isinstance(org,dict): return str(org.get('name') or '')
    return str(org or '')


def _normalize(ticket, secret=''):
    raw=provider_lists.safe_raw(ticket,secret)
    customer=ticket.get('customer') if isinstance(ticket.get('customer'),dict) else {}
    organization=_ticket_name(ticket)
    hint={'name':organization or str(customer.get('organization') or customer.get('name') or ''),
          'contact_person':str(customer.get('name') or ''),'email':str(customer.get('email') or ''),'phones':[]}
    return raw,hint


def _state_name(ticket):
    return provider_lists.text(ticket.get('state'),'')


def _upsert(c, uid, ticket, generation, secret='', synced_at=None):
    tid=str(ticket.get('id') or '')
    if not tid: return False
    raw,hint=_normalize(ticket,secret)
    stamp=now_iso() if synced_at is None else str(synced_at or '')
    values=(str(ticket.get('number') or ''),str(ticket.get('title') or ''),_ticket_name(ticket),_state_name(ticket),
            str(ticket.get('created_at') or ''),str(ticket.get('updated_at') or ''),json.dumps(raw,ensure_ascii=False,default=str),
            json.dumps(hint,ensure_ascii=False,default=str),generation,stamp)
    exists=c.execute('SELECT id FROM zammad_ticket_cache WHERE owner_id=? AND ticket_id=?',(uid,tid)).fetchone()
    if exists:
        c.execute('''UPDATE zammad_ticket_cache SET number=?,title=?,organization=?,state=?,created_at=?,updated_at=?,raw_json=?,hint_json=?,sync_generation=?,synced_at=? WHERE owner_id=? AND ticket_id=?''', values+(uid,tid))
    else:
        c.execute('''INSERT INTO zammad_ticket_cache(owner_id,ticket_id,number,title,organization,state,created_at,updated_at,raw_json,hint_json,sync_generation,synced_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (uid,tid)+values)
    return True


def _bootstrap_from_archive(c, uid):
    if c.execute('SELECT 1 FROM zammad_ticket_cache WHERE owner_id=? LIMIT 1',(uid,)).fetchone():
        return 0
    seeded=0
    try:
        events=list(c.execute('''SELECT external_key,raw_json,captured_at FROM provider_events
                                 WHERE owner_id=? AND provider=? ORDER BY captured_at DESC''',(uid,'zammad')))
    except Exception:
        return 0
    seen=set()
    for event in events:
        try:raw=json.loads(event['raw_json'] or '{}')
        except Exception:continue
        if not isinstance(raw,dict):continue
        tid=str(raw.get('id') or '')
        if not tid:
            match=re.match(r'^zammad:(?:id|ticket_id):(\d+)$',str(event['external_key'] or ''))
            if match:tid=match.group(1);raw['id']=tid
        if not tid or tid in seen:continue
        seen.add(tid)
        if _upsert(c,uid,raw,'bootstrap','',synced_at=''):seeded+=1
    return seeded


def cached_list(c, uid):
    seeded=_bootstrap_from_archive(c,uid)
    rows=[];raw_names=set();last_sync=''
    for row in c.execute('''SELECT ticket_id,number,title,organization,state,created_at,updated_at,raw_json,hint_json,synced_at FROM zammad_ticket_cache WHERE owner_id=? ORDER BY updated_at DESC,ticket_id DESC''',(uid,)):
        try: raw=json.loads(row['raw_json']);hint=json.loads(row['hint_json'])
        except Exception: continue
        raw_names.update(str(k) for k in raw.keys())
        last_sync=max(last_sync,row['synced_at'] or '')
        raw['id']=row['ticket_id'];raw['number']=row['number'];raw['title']=row['title'];raw['organization_name']=row['organization']
        raw['status']=row['state'];raw['created_at']=row['created_at'];raw['updated_at']=row['updated_at']
        rows.append({'cells':[row['ticket_id'],row['number'],row['title'],row['organization'],row['state'],row['created_at'],row['updated_at']],
                     'ticket_id':row['ticket_id'],'raw':raw,'external_key':'zammad:id:'+row['ticket_id'],'customer_hint':hint,
                     'cache_status':'current','synced_at':row['synced_at']})
    priority=['id','number','title','organization_name','status','created_at','updated_at']
    ordered=[x for x in priority]
    ordered.extend(sorted(raw_names-set(ordered)-{'organization','state'},key=str.lower))
    note=f'Lokale Zammad-Datenbank · {len(rows)} Tickets'
    if last_sync: note+=f' · zuletzt vollständig aktualisiert {last_sync}'
    elif seeded: note+=' · aus bisherigem lokalen Bestand übernommen; vollständiger Abgleich läuft beim Aktualisieren'
    return {'columns':['ID','Ticketnummer','Titel','Organisation','Status','Erstellt','Geändert'],'raw_columns':ordered,'date_columns':[5,6],
            'rows':rows,'next_offset':None,'note':note,'cache_source':'local','last_sync_at':last_sync}


def _full_refresh(app, uid):
    config=_config(app,uid);client=integrations.Client(config['domain']);headers=_auth(config)
    generation='z-'+__import__('secrets').token_urlsafe(12);received=0;pages=0;current_keys=set();page=1;page_size=50
    while True:
        path='/api/v1/tickets?'+urlencode({'expand':'true','page':page,'per_page':page_size,'sort_by':'updated_at','order_by':'desc'})
        status,payload,message=client.request(path,headers)
        if not 200<=status<300 or not isinstance(payload,list):
            raise ValueError((message or 'Zammad-Tickets konnten nicht vollständig geladen werden.')+' (HTTP %s)'%status)
        pages+=1;archive_rows=[]
        with app.db() as c:
            for ticket in payload:
                if not isinstance(ticket,dict): continue
                if _upsert(c,uid,ticket,generation,config['secret']): received+=1
                tid=str(ticket.get('id') or '')
                if not tid: continue
                raw,hint=_normalize(ticket,config['secret']);key='zammad:id:'+tid;current_keys.add(key)
                archive_rows.append({'raw':raw,'external_key':key,'customer_hint':hint})
            if archive_rows: provider_archive.cache_with_stats(c,uid,'zammad',{'rows':archive_rows})
        if len(payload)<page_size: break
        page+=1
        if page>10000: raise ValueError('Zammad lieferte unerwartet viele Seiten. Abbruch zum Schutz vor Endlosschleifen.')
    with app.db() as c:
        before=c.execute('SELECT COUNT(*) n FROM zammad_ticket_cache WHERE owner_id=?',(uid,)).fetchone()['n']
        c.execute('DELETE FROM zammad_ticket_cache WHERE owner_id=? AND sync_generation<>?',(uid,generation))
        after=c.execute('SELECT COUNT(*) n FROM zammad_ticket_cache WHERE owner_id=?',(uid,)).fetchone()['n']
        for event in list(c.execute('SELECT external_key FROM provider_events WHERE owner_id=? AND provider=?',(uid,'zammad'))):
            if event['external_key'] not in current_keys:
                c.execute('DELETE FROM provider_events WHERE owner_id=? AND provider=? AND external_key=?',(uid,'zammad',event['external_key']))
        _set_access(c,uid,'valid','Zammad-Verbindung erfolgreich geprüft.')
        provider_archive.add_log(c,uid,'zammad','success','full_refresh',
                                 f'Zammad vollständig aktualisiert · {after} Tickets gespeichert',
                                 {'received':received,'pages':pages,'total_records':after,'removed':max(0,before-after)})
    return {'received':received,'pages':pages,'total_records':after,'removed':max(0,before-after),'last_sync_at':now_iso()}


def _auth_error(error):
    text=str(error).lower()
    return any(x in text for x in ('http 401','http 403','anmeldung abgewiesen','zugriff verweigert','passwort','zugangsdaten'))


def start_refresh(app,uid):
    key=f'{uid}:zammad'
    with _LOCK:
        current=_JOBS.get(key)
        if current and current.get('state')=='running': return dict(current)
        job={'id':__import__('secrets').token_urlsafe(10),'provider':'zammad','state':'running','started_at':now_iso(),'finished_at':'','result':None,'error':''}
        _JOBS[key]=job
    def worker():
        try:
            result=_full_refresh(app,uid)
            with _LOCK: job.update(state='success',result=result,finished_at=now_iso())
        except Exception as error:
            try:
                with app.db() as c:
                    _set_access(c,uid,'invalid' if _auth_error(error) else 'unavailable',str(error))
                    provider_archive.add_log(c,uid,'zammad','error','full_refresh','Zammad-Aktualisierung fehlgeschlagen',{'error':str(error)[:500]})
            except Exception:
                pass
            with _LOCK: job.update(state='error',error=str(error),finished_at=now_iso())
    threading.Thread(target=worker,name=f'pz-zammad-refresh-{uid}',daemon=True).start()
    return dict(job)


def job(uid):
    with _LOCK:
        value=_JOBS.get(f'{uid}:zammad')
        return dict(value) if value else {'provider':'zammad','state':'idle','result':None,'error':''}


def install(app):
    original_init=app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:migrate(c)
    app.init_db=init_db

    previous_list=app.App.integration_list
    def integration_list(self,session,body):
        if str(body.get('provider') or '').lower()=='zammad' and not body.get('ticket_id'):
            with app.db() as c:return self.send_json(200,cached_list(c,session['id']))
        return previous_list(self,session,body)
    app.App.integration_list=integration_list

    previous_post=app.App.do_POST
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in ('/api/v1/provider/refresh/start','/api/v1/provider/refresh/job'):return previous_post(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:return self.send_json(400,{'error':str(error)})
        if str(body.get('provider') or '').lower()!='zammad':
            return previous_post(self)
        session=self.require(csrf=True)
        if not session:return
        try:
            if path.endswith('/start'):return self.send_json(202,{'job':start_refresh(app,session['id'])})
            return self.send_json(200,{'job':job(session['id'])})
        except (ValueError,TypeError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST
