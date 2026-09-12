"""Fast provider views backed by the local archive plus background refresh jobs.

STARFACE and TeamViewer history is durable and user-owned. Losing provider access
never deletes cached events. A known invalid provider login hides the cache until
a later refresh succeeds again.
"""
import json
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import provider_archive
import provider_lists
import starface_calls

_JOBS = {}
_LOCK = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS provider_access_state (
      owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      provider TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'unknown',
      message TEXT NOT NULL DEFAULT '',
      checked_at TEXT NOT NULL DEFAULT '',
      PRIMARY KEY(owner_id,provider)
    );
    ''')


def _set_state(c, uid, provider, state, message=''):
    c.execute('DELETE FROM provider_access_state WHERE owner_id=? AND provider=?', (uid, provider))
    c.execute('INSERT INTO provider_access_state(owner_id,provider,state,message,checked_at) VALUES(?,?,?,?,?)',
              (uid, provider, state, str(message or '')[:500], now_iso()))


def access_state(c, uid, provider):
    row = c.execute('SELECT state,message,checked_at FROM provider_access_state WHERE owner_id=? AND provider=?',
                    (uid, provider)).fetchone()
    if not row:
        return {'state':'unknown','message':'','checked_at':''}
    return dict(row)


def _credentials_present(c, uid, provider):
    if provider == 'starface':
        return bool(c.execute('SELECT 1 FROM oauth_tokens WHERE owner_id=?', (uid,)).fetchone())
    if provider == 'teamviewer':
        row = c.execute('SELECT secret FROM integrations WHERE owner_id=? AND provider=?', (uid, provider)).fetchone()
        return bool(row and row['secret'])
    return False


def provider_visible(c, uid, provider):
    if not _credentials_present(c, uid, provider):
        return False, {'state':'missing','message':'Keine aktive Verbindung vorhanden.','checked_at':''}
    state = access_state(c, uid, provider)
    return state['state'] != 'invalid', state


def _parse_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    for parser in (
        lambda v: datetime.fromisoformat(v.replace('Z', '+00:00')),
        lambda v: datetime.strptime(v, '%Y%m%dT%H:%M:%S').replace(tzinfo=timezone.utc),
    ):
        try:
            dt = parser(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    return None


def _event_rows(c, uid, provider):
    rows = []
    username_row = c.execute('SELECT username FROM users WHERE id=?', (uid,)).fetchone()
    imported_by = username_row['username'] if username_row else str(uid)
    for row in c.execute('''SELECT external_key,occurred_at,raw_json,hint_json,captured_at
                            FROM provider_events WHERE owner_id=? AND provider=?
                            ORDER BY occurred_at DESC,captured_at DESC''', (uid, provider)):
        try:
            raw = json.loads(row['raw_json']) if row['raw_json'] else {}
            hint = json.loads(row['hint_json']) if row['hint_json'] else {}
        except Exception:
            continue
        rows.append({'external_key':row['external_key'], 'occurred_at':row['occurred_at'], 'raw':raw,
                     'customer_hint':hint, 'captured_at':row['captured_at'], 'imported_by':imported_by})
    return rows


def _starface_cached(c, uid, body):
    days = body.get('days', 30)
    if days not in (7,30,90,365):
        days = 30
    mode = str(body.get('call_type') or 'all')
    if mode not in ('all','inbound','outbound','missed'):
        mode = 'all'
    try:
        offset = max(0, min(int(body.get('offset') or 0), 100000))
    except (TypeError, ValueError):
        offset = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = []
    raw_names = set()
    for event in _event_rows(c, uid, 'starface'):
        raw = event['raw']
        start = _parse_time(raw.get('startTime') or event.get('occurred_at'))
        if start and start < cutoff:
            continue
        direction = str(raw.get('direction') or '')
        result = str(raw.get('result') or '')
        if direction not in ('INBOUND','OUTBOUND') or raw.get('groupId'):
            continue
        if mode == 'inbound' and direction != 'INBOUND':
            continue
        if mode == 'outbound' and direction != 'OUTBOUND':
            continue
        if mode == 'missed' and not (direction == 'INBOUND' and result == 'MISSED'):
            continue
        seconds = raw.get('duration')
        valid_duration = type(seconds) is int and 0 <= seconds <= 31536000
        end = start + timedelta(seconds=seconds) if start and valid_duration else None
        status = {'ANSWERED':'Beantwortet','MISSED':'Verpasst' if direction=='INBOUND' else 'Nicht erreicht'}.get(result, result or 'Unbekannt')
        seconds_text = '%02d:%02d:%02d' % (seconds//3600, seconds//60%60, seconds%60) if valid_duration else 'Nicht geliefert'
        caller = str(raw.get('callerNumber') or 'Unbekannt')[:500]
        called = str(raw.get('calledNumber') or 'Unbekannt')[:500]
        description = str(raw.get('callDescription') or '')[:500]
        raw_names.update(str(k) for k in raw.keys())
        items.append({'cells':['Eingehend' if direction=='INBOUND' else 'Ausgehend', status[:100], caller, called,
                               description, start.isoformat() if start else None, end.isoformat() if end else None, seconds_text],
                      'duration_seconds':seconds if valid_duration else None, 'end_calculated':bool(end),
                      'raw':raw, 'external_key':event['external_key'], 'customer_hint':event['customer_hint'],
                      'imported_by':event['imported_by']})
    total = len(items)
    page = items[offset:offset+100]
    return {'columns':['Richtung','Status','Anrufer','Angerufene Rufnummer','Name / Beschreibung','Anrufbeginn','Ende (berechnet)','Dauer'],
            'raw_columns':sorted(raw_names,key=str.lower), 'date_columns':[5,6], 'rows':page,
            'next_offset':offset+100 if offset+100 < total else None,
            'note':f'Lokale Datenbank · persönliche Anrufe · letzte {days} Tage · {total} gespeichert.'}


def _teamviewer_cached(c, uid, body):
    days = body.get('days', 0)
    if days not in (0,7,30,90,365):
        days = 0
    try:
        offset = max(0, min(int(body.get('offset') or 0), 100000))
    except (TypeError, ValueError):
        offset = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    items=[];raw_names=set()
    for event in _event_rows(c, uid, 'teamviewer'):
        raw=event['raw'];start=_parse_time(raw.get('start_date') or event.get('occurred_at'))
        if cutoff and start and start < cutoff: continue
        raw_names.update(str(k) for k in raw.keys())
        items.append({'cells':[provider_lists.text(raw.get('devicename'),'Unbenanntes Gerät'), provider_lists.text(raw.get('username')),
                               provider_lists.date(raw.get('start_date')), provider_lists.date(raw.get('end_date')),
                               provider_lists.duration(raw.get('start_date'),raw.get('end_date'))],
                      'raw':raw,'external_key':event['external_key'],'customer_hint':event['customer_hint'],
                      'imported_by':event['imported_by']})
    total=len(items);page=items[offset:offset+100]
    return {'columns':['Gerätename','Benutzer','Beginn','Ende','Verbindungsdauer'],
            'raw_columns':sorted(raw_names,key=str.lower), 'date_columns':[2,3], 'rows':page,
            'next_offset':offset+100 if offset+100 < total else None,
            'note':('Lokale Datenbank' + (f' · letzte {days} Tage' if days else ' · gesamter lokaler Bestand') + f' · {total} gespeichert.')}


def cached_list(c, uid, provider, body):
    visible, state = provider_visible(c, uid, provider)
    if not visible:
        base = _starface_cached(c, uid, body) if provider == 'starface' else _teamviewer_cached(c, uid, body)
        base['rows'] = [];base['next_offset'] = None
        base['note'] = 'Gespeicherte Daten sind vorhanden, werden aber erst nach Wiederherstellung der Provider-Verbindung angezeigt.'
        base['access_state'] = state
        return base
    result = _starface_cached(c, uid, body) if provider == 'starface' else _teamviewer_cached(c, uid, body)
    result['access_state'] = state
    return result


def _auth_failure(error):
    text=str(error).lower()
    needles=('401','403','token','oauth','anmeldung abgewiesen','nicht angemeldet','neu anmelden','bitte zuerst','client-konfiguration wurde geändert')
    return any(n in text for n in needles)


def _copy_job(job):
    return json.loads(json.dumps(job,default=str))


def start_refresh(app, uid, provider, days=0):
    provider=str(provider or '').lower()
    if provider not in ('starface','teamviewer'):
        raise ValueError('Hintergrund-Aktualisierung ist nur für STARFACE und TeamViewer verfügbar.')
    key=f'{uid}:{provider}'
    with _LOCK:
        current=_JOBS.get(key)
        if current and current.get('state')=='running':
            return _copy_job(current)
        job={'id':__import__('secrets').token_urlsafe(10),'provider':provider,'state':'running','started_at':now_iso(),
             'finished_at':'','result':None,'error':'','access':'unknown'}
        _JOBS[key]=job

    def worker():
        try:
            feature=__import__('feature_runtime')
            config=feature.integration_config(app,uid,provider)
            if provider=='starface':
                value=days if days in (7,30,90,365) else 30
                config.update(days=value,offset=0,call_type='all')
                result=starface_calls.load(config)
            else:
                value=days if days in (0,7,30,90,365) else 0
                config['days']=value
                result=provider_lists.load(config)
            with app.db() as c:
                stats=provider_archive.cache_with_stats(c,uid,provider,result)
                sync=provider_archive.update_sync_state(c,uid,provider)
                _set_state(c,uid,provider,'valid','Verbindung erfolgreich geprüft.')
                provider_archive.add_log(c,uid,provider,'success','background_refresh',
                    f'{"STARFACE" if provider=="starface" else "TeamViewer"} im Hintergrund aktualisiert · {stats["received"]} geprüft · {stats["new"]} neu',
                    {**stats,**sync})
            with _LOCK:
                job.update(state='success',access='valid',result={**stats,**sync},finished_at=now_iso())
        except Exception as error:
            invalid=_auth_failure(error)
            try:
                with app.db() as c:
                    if invalid:
                        _set_state(c,uid,provider,'invalid',str(error))
                    provider_archive.add_log(c,uid,provider,'warning' if invalid else 'error','background_refresh',
                        'Provider-Zugang ist nicht gültig.' if invalid else 'Provider-Aktualisierung fehlgeschlagen.',
                        {'error':str(error)[:500]})
            except Exception:
                pass
            with _LOCK:
                job.update(state='error',access='invalid' if invalid else 'unavailable',error=str(error),finished_at=now_iso())
    threading.Thread(target=worker,name=f'pz-provider-refresh-{provider}-{uid}',daemon=True).start()
    return _copy_job(job)


def refresh_job(uid, provider):
    with _LOCK:
        job=_JOBS.get(f'{uid}:{str(provider or "").lower()}')
        return _copy_job(job) if job else {'provider':provider,'state':'idle','result':None,'error':'','access':'unknown'}


def install(app):
    original_init=app.init_db
    def init_db(create_admin=True):
        original_init(create_admin)
        with app.db() as c:migrate(c)
    app.init_db=init_db

    previous_list=app.App.integration_list
    def integration_list(self,session,body):
        provider=str(body.get('provider') or '').lower()
        if provider in ('starface','teamviewer') and body.get('info_only') is not True:
            with app.db() as c:
                return self.send_json(200,cached_list(c,session['id'],provider,body))
        return previous_list(self,session,body)
    app.App.integration_list=integration_list

    previous_post=app.App.do_POST
    paths={'/api/v1/provider/refresh/start','/api/v1/provider/refresh/job','/api/v1/provider/access'}
    def do_POST(self):
        path=urlparse(self.path).path
        if path not in paths:return previous_post(self)
        try:
            body=self.json_body()
            if not isinstance(body,dict):raise ValueError('Eine JSON-Struktur ist erforderlich.')
        except Exception as error:return self.send_json(400,{'error':str(error)})
        session=self.require(csrf=True)
        if not session:return
        uid=session['id'];provider=str(body.get('provider') or '').lower()
        try:
            if path=='/api/v1/provider/refresh/start':
                return self.send_json(202,{'job':start_refresh(app,uid,provider,body.get('days',0))})
            if path=='/api/v1/provider/refresh/job':
                return self.send_json(200,{'job':refresh_job(uid,provider)})
            if path=='/api/v1/provider/access':
                with app.db() as c:
                    visible,state=provider_visible(c,uid,provider)
                    return self.send_json(200,{'provider':provider,'visible':visible,'state':state})
        except (ValueError,TypeError) as error:return self.send_json(400,{'error':str(error)})
    app.App.do_POST=do_POST
