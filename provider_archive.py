"""Persistent provider archive, sync logs, debug snapshots and CRM helpers."""
import base64
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import customer_data
import integrations
import provider_lists
import starface_calls

BERLIN = ZoneInfo('Europe/Berlin')
LEVELS = ('info', 'success', 'warning', 'error')
PROVIDERS = ('starface', 'teamviewer', 'zammad')


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS operation_logs (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      category TEXT NOT NULL,
      level TEXT NOT NULL,
      action TEXT NOT NULL,
      message TEXT NOT NULL,
      details_json LONGTEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS provider_sync_state (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      provider TEXT NOT NULL,
      oldest_at TEXT NOT NULL DEFAULT '',
      newest_at TEXT NOT NULL DEFAULT '',
      last_sync_at TEXT NOT NULL DEFAULT '',
      total_records INTEGER NOT NULL DEFAULT 0,
      UNIQUE(owner_id,provider)
    );
    CREATE TABLE IF NOT EXISTS zammad_organizations (
      id INTEGER PRIMARY KEY,
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      external_id TEXT NOT NULL,
      name TEXT NOT NULL,
      raw_json LONGTEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(owner_id,external_id)
    );
    ''')


def add_log(c, uid, category, level, action, message, details=None):
    category = str(category or 'system').strip().lower()[:40]
    level = level if level in LEVELS else 'info'
    action = str(action or '')[:120]
    message = str(message or '')[:1000]
    payload = json.dumps(details or {}, ensure_ascii=False, default=str)
    c.execute('INSERT INTO operation_logs(owner_id,category,level,action,message,details_json,created_at) VALUES(?,?,?,?,?,?,?)',
              (uid, category, level, action, message, payload, now_iso()))


def list_logs(c, uid, category='', level='', limit=300):
    limit = max(1, min(int(limit or 300), 1000))
    rows = c.execute('SELECT id,category,level,action,message,details_json,created_at FROM operation_logs WHERE owner_id=? ORDER BY id DESC', (uid,))
    out=[]
    for row in rows:
        if category and row['category'] != category: continue
        if level and row['level'] != level: continue
        try: details=json.loads(row['details_json'])
        except Exception: details={}
        out.append(dict(id=row['id'], category=row['category'], level=row['level'], action=row['action'], message=row['message'], details=details, created_at=row['created_at']))
        if len(out) >= limit: break
    return out


def _keys(result):
    return [str(r.get('external_key')) for r in (result.get('rows') or []) if isinstance(r,dict) and r.get('external_key')]


def cache_with_stats(c, uid, provider, result):
    keys=_keys(result)
    existing=set()
    if keys:
        for row in c.execute('SELECT external_key FROM provider_events WHERE owner_id=? AND provider=?',(uid,provider)):
            if row['external_key'] in keys: existing.add(row['external_key'])
    customer_data.cache_rows(c,uid,provider,result)
    return {'received':len(keys),'new':len([k for k in keys if k not in existing]),'existing':len([k for k in keys if k in existing])}


def _event_bounds(c, uid, provider):
    rows=list(c.execute('SELECT occurred_at FROM provider_events WHERE owner_id=? AND provider=? AND occurred_at<>? ORDER BY occurred_at',(uid,provider,'')))
    return ((rows[0]['occurred_at'] if rows else ''),(rows[-1]['occurred_at'] if rows else ''))


def update_sync_state(c, uid, provider):
    oldest,newest=_event_bounds(c,uid,provider)
    total=c.execute('SELECT COUNT(*) n FROM provider_events WHERE owner_id=? AND provider=?',(uid,provider)).fetchone()['n']
    c.execute('DELETE FROM provider_sync_state WHERE owner_id=? AND provider=?',(uid,provider))
    c.execute('INSERT INTO provider_sync_state(owner_id,provider,oldest_at,newest_at,last_sync_at,total_records) VALUES(?,?,?,?,?,?)',
              (uid,provider,oldest,newest,now_iso(),total))
    return {'provider':provider,'oldest_at':oldest,'newest_at':newest,'last_sync_at':now_iso(),'total_records':total}


def sync_states(c, uid):
    found={r['provider']:dict(r) for r in c.execute('SELECT provider,oldest_at,newest_at,last_sync_at,total_records FROM provider_sync_state WHERE owner_id=?',(uid,))}
    return [found.get(p,{'provider':p,'oldest_at':'','newest_at':'','last_sync_at':'','total_records':0}) for p in ('starface','teamviewer')]


def _starface_page(config, rpc, offset, page_size=100):
    now=datetime.now(timezone.utc)
    earliest=datetime(2000,1,1,tzinfo=timezone.utc)
    payload=rpc.call('callList.getCallList',(now.replace(tzinfo=None),earliest.replace(tzinfo=None),'','','NON_GROUP','startTime','DESCENDING',offset,page_size))
    if not isinstance(payload,dict) or not isinstance(payload.get('entries'),list):
        raise ValueError('STARFACE lieferte keine gültige History-Seite.')
    rows=[]
    for item in payload['entries']:
        if not isinstance(item,dict) or item.get('direction') not in ('INBOUND','OUTBOUND') or item.get('groupId'):
            continue
        raw=starface_calls._scrub(starface_calls._plain(item),config['secret'])
        description=item.get('callDescription') if isinstance(item.get('callDescription'),str) else ''
        rows.append({'raw':raw,'external_key':starface_calls._external_key(item),'customer_hint':starface_calls._scrub(starface_calls._customer_hint(description,item),config['secret'])})
    total=payload.get('totalCount')
    next_offset=offset+len(payload['entries'])
    more=len(payload['entries'])>=page_size and (type(total) is not int or next_offset<total)
    return {'rows':rows}, (next_offset if more else None), total


def sync_starface(db_factory, uid, config, full=True):
    rpc=starface_calls.UciClient(config)
    if rpc.call('connection.login') is not True:
        raise ValueError('STARFACE-UCI-Anmeldung abgewiesen.')
    received=new=existing=pages=0
    try:
        offset=0
        while True:
            result,next_offset,total=_starface_page(config,rpc,offset)
            with db_factory() as c:
                stats=cache_with_stats(c,uid,'starface',result)
            received+=stats['received'];new+=stats['new'];existing+=stats['existing'];pages+=1
            if next_offset is None or pages>=1000: break
            offset=next_offset
    finally:
        try: rpc.call('connection.logout')
        except Exception: pass
    with db_factory() as c:
        state=update_sync_state(c,uid,'starface')
        level='warning' if pages>=1000 else 'success'
        message=f'STARFACE History synchronisiert · {received} geprüft · {new} neu · {existing} bereits vorhanden'
        add_log(c,uid,'starface',level,'history_sync',message,{'pages':pages,**state})
    return {'provider':'starface','received':received,'new':new,'existing':existing,'pages':pages,**state}


def _teamviewer_page(config, client, params):
    headers={'Authorization':'Bearer '+config['secret']}
    status,payload,message=client.request('/api/v1/reports/connections?'+urlencode(params),headers)
    if not 200<=status<300 or not isinstance(payload,dict):
        raise ValueError((message or 'TeamViewer History nicht erreichbar.')+' (HTTP %s)'%status)
    batch=payload.get('records',payload.get('connections'))
    if not isinstance(batch,list): raise ValueError('TeamViewer hat keine Verbindungsliste geliefert.')
    rows=[]
    for item in batch:
        if not isinstance(item,dict): continue
        raw=provider_lists.safe_raw(item,config['secret'])
        rows.append({'raw':raw,'external_key':provider_lists.external_key('teamviewer',raw),'customer_hint':{
            'name':provider_lists.text(item.get('username'),'').strip('–'),'contact_person':'','phones':[],
            'device_id':provider_lists.text(item.get('deviceid'),'').strip('–'),'device_name':provider_lists.text(item.get('devicename'),'').strip('–')}})
    return {'rows':rows}, payload.get('next_offset'), len(batch)


def sync_teamviewer(db_factory, uid, config, full=True):
    client=integrations.Client(config['domain'])
    now=datetime.now(timezone.utc)
    params={'limit':100}
    if full:
        params.update(from_date='2000-01-01T00:00:00Z',to_date=now.strftime('%Y-%m-%dT%H:%M:%SZ'))
    else:
        params.update(from_date=(now-timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ'),to_date=now.strftime('%Y-%m-%dT%H:%M:%SZ'))
    received=new=existing=pages=0;seen=set()
    while True:
        try:
            result,next_offset,batch_count=_teamviewer_page(config,client,params)
        except ValueError:
            if pages==0 and full:
                params={'limit':100}
                result,next_offset,batch_count=_teamviewer_page(config,client,params)
            else: raise
        with db_factory() as c: stats=cache_with_stats(c,uid,'teamviewer',result)
        received+=stats['received'];new+=stats['new'];existing+=stats['existing'];pages+=1
        if not next_offset or batch_count<100 or str(next_offset) in seen or pages>=1000: break
        seen.add(str(next_offset));params['offset']=str(next_offset)
    with db_factory() as c:
        state=update_sync_state(c,uid,'teamviewer')
        level='warning' if pages>=1000 else 'success'
        message=f'TeamViewer History synchronisiert · {received} geprüft · {new} neu · {existing} bereits vorhanden'
        add_log(c,uid,'teamviewer',level,'history_sync',message,{'pages':pages,**state})
    return {'provider':'teamviewer','received':received,'new':new,'existing':existing,'pages':pages,**state}


def refresh_zammad_organizations(c, uid, config, max_pages=100):
    auth=base64.b64encode((config['username']+':'+config['secret']).encode()).decode()
    headers={'Authorization':'Basic '+auth};client=integrations.Client(config['domain'])
    received=0
    for page in range(1,max_pages+1):
        status,payload,message=client.request(f'/api/v1/organizations?page={page}&per_page=100',headers)
        if not 200<=status<300 or not isinstance(payload,list):
            raise ValueError((message or 'Zammad-Organisationen konnten nicht geladen werden.')+' (HTTP %s)'%status)
        if not payload: break
        for item in payload:
            if not isinstance(item,dict) or item.get('id') in (None,''): continue
            oid=str(item['id']);name=str(item.get('name') or oid)[:250]
            raw=provider_lists.safe_raw(item,config['secret'])
            c.execute('DELETE FROM zammad_organizations WHERE owner_id=? AND external_id=?',(uid,oid))
            c.execute('INSERT INTO zammad_organizations(owner_id,external_id,name,raw_json,updated_at) VALUES(?,?,?,?,?)',(uid,oid,name,json.dumps(raw,ensure_ascii=False,default=str),now_iso()))
            received+=1
        if len(payload)<100: break
    add_log(c,uid,'zammad','success','organizations_sync',f'Zammad-Organisationen aktualisiert · {received} geladen',{'received':received})
    return received


def zammad_organizations(c, uid):
    return [dict(id=r['external_id'],name=r['name']) for r in c.execute('SELECT external_id,name FROM zammad_organizations WHERE owner_id=? ORDER BY name',(uid,))]


def phone_update(c, uid, body):
    scope=str(body.get('scope') or 'company')
    pid=int(body.get('id'))
    number=customer_data.valid_phone(body.get('number'))
    label=str(body.get('label') or 'Sonstige')[:40]
    if not number: raise ValueError('Rufnummern müssen mehr als fünf Ziffern enthalten.')
    if scope=='contact':
        row=c.execute('SELECT id FROM customer_contact_phones WHERE id=? AND owner_id=?',(pid,uid)).fetchone()
        if not row: raise ValueError('Rufnummer nicht gefunden.')
        c.execute('UPDATE customer_contact_phones SET number=?,label=? WHERE id=?',(number,label,pid))
    else:
        row=c.execute('SELECT id FROM customer_phones WHERE id=? AND owner_id=?',(pid,uid)).fetchone()
        if not row: raise ValueError('Rufnummer nicht gefunden.')
        c.execute('UPDATE customer_phones SET number=?,label=? WHERE id=?',(number,label,pid))


def phone_delete(c, uid, body):
    scope=str(body.get('scope') or 'company');pid=int(body.get('id'))
    table='customer_contact_phones' if scope=='contact' else 'customer_phones'
    c.execute(f'DELETE FROM {table} WHERE id=? AND owner_id=?',(pid,uid))


def _parse_time(value):
    if isinstance(value,datetime): return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value: return None
    text=str(value)
    for parser in (lambda v:datetime.fromisoformat(v.replace('Z','+00:00')),lambda v:datetime.strptime(v,'%Y%m%dT%H:%M:%S').replace(tzinfo=timezone.utc)):
        try:
            dt=parser(text);return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError: pass
    return None


def customer_timeline(c, uid, customer_id, day):
    try: local_day=datetime.strptime(str(day),'%Y-%m-%d').date()
    except ValueError: raise ValueError('Ungültiger Tag.') from None
    start_local=datetime.combine(local_day,datetime.min.time(),BERLIN)
    end_local=start_local+timedelta(days=1)
    out=[]
    for event in customer_data.activity(c,uid,customer_id,limit=100000):
        if event['provider'] not in ('starface','teamviewer'): continue
        raw=event.get('raw') or {}
        start=_parse_time(raw.get('startTime') or raw.get('start_date') or event.get('occurred_at'))
        if not start: continue
        if event['provider']=='starface':
            seconds=raw.get('duration');end=start+timedelta(seconds=seconds) if type(seconds) is int and seconds>=0 else start+timedelta(seconds=1)
        else:
            end=_parse_time(raw.get('end_date')) or start+timedelta(seconds=1)
        local_start=start.astimezone(BERLIN);local_end=end.astimezone(BERLIN)
        if local_end<=start_local or local_start>=end_local: continue
        out.append({'provider':event['provider'],'start':start.isoformat(),'end':end.isoformat(),'summary':event.get('summary',''),'raw':raw,'external_key':event.get('external_key','')})
    out.sort(key=lambda x:x['start'])
    return out


def debug_raw(uid, provider, config, c=None):
    if provider=='teamviewer':
        client=integrations.Client(config['domain']);headers={'Authorization':'Bearer '+config['secret']}
        status,payload,message=client.request('/api/v1/reports/connections?limit=100',headers)
        if not 200<=status<300: raise ValueError(message or 'TeamViewer Debug-Abfrage fehlgeschlagen.')
        data=provider_lists.safe_raw(payload,config['secret'])
        return {'provider':provider,'endpoint':'/api/v1/reports/connections?limit=100','http_status':status,'fetched_at':now_iso(),'data':data}
    if provider=='zammad':
        auth=base64.b64encode((config['username']+':'+config['secret']).encode()).decode();headers={'Authorization':'Basic '+auth};client=integrations.Client(config['domain'])
        status_t,tickets,msg=client.request('/api/v1/tickets?expand=true&page=1&per_page=100&sort_by=updated_at&order_by=desc',headers)
        status_o,orgs,msg_o=client.request('/api/v1/organizations?page=1&per_page=100',headers)
        if not 200<=status_t<300: raise ValueError(msg or 'Zammad Debug-Abfrage fehlgeschlagen.')
        return {'provider':provider,'endpoint':['/api/v1/tickets?...','/api/v1/organizations?page=1&per_page=100'],'http_status':[status_t,status_o],'fetched_at':now_iso(),'data':{'tickets':provider_lists.safe_raw(tickets,config['secret']),'organizations':provider_lists.safe_raw(orgs,config['secret']) if 200<=status_o<300 else {'error':msg_o}}}
    result=starface_calls.load({**config,'days':7,'offset':0,'call_type':'all'})
    return {'provider':provider,'endpoint':'STARFACE UCI callList.getCallList + bereinigte Rohobjekte','http_status':200,'fetched_at':now_iso(),'data':{'server':starface_calls.server_info(config),'rows':[r.get('raw') for r in result.get('rows',[])]}}
