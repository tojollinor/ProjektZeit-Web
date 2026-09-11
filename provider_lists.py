"""Normalized provider lists plus safe raw fields for customer assignment."""
import base64
import hashlib
import json
import re
from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
import integrations


def text(value, default='–'):
    if isinstance(value, dict):
        value = value.get('name') or value.get('title')
    return str(value)[:500] if isinstance(value, (str, int, float)) and str(value) else default


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError, TypeError):
        return None


def date(value):
    parsed = stamp(value)
    return parsed.isoformat() if parsed else None


def duration(start, end):
    a, b = stamp(start), stamp(end)
    if not a or not b or b < a:
        return '–'
    seconds = int((b-a).total_seconds())
    return '%02d:%02d:%02d' % (seconds//3600, seconds//60%60, seconds%60)


def get(client, path, headers):
    status, data, message = client.request(path, headers)
    if not 200 <= status < 300 or data is None:
        raise ValueError(message + ' (HTTP %s)' % status)
    return data


def safe_raw(value, secret=''):
    """Keep provider data visible while excluding credentials and unsafe huge/nested values."""
    def clean(v, depth=0):
        if depth > 3:
            return '[verschachtelt]'
        if isinstance(v, dict):
            result = {}
            for key, item in v.items():
                name = str(key)[:120]
                if re.search(r'pass|secret|token|auth|cookie', name, re.I):
                    continue
                result[name] = clean(item, depth+1)
            return result
        if isinstance(v, list):
            return [clean(x, depth+1) for x in v[:40]]
        if isinstance(v, (str, int, float, bool)) or v is None:
            out = str(v)[:2000] if isinstance(v, str) else v
            return out.replace(secret, '[ausgeblendet]') if isinstance(out, str) and secret else out
        return str(v)[:500]
    return clean(value)


def external_key(provider, raw):
    for key in ('id', 'connection_id', 'sessionid', 'deviceid', 'ticket_id', 'number'):
        value = raw.get(key) if isinstance(raw, dict) else None
        if value not in (None, ''):
            return provider + ':' + key + ':' + str(value)[:180]
    wire = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str, separators=(',', ':'))
    return provider + ':sha256:' + hashlib.sha256(wire.encode()).hexdigest()


def raw_columns(records):
    names = set()
    for record in records:
        if isinstance(record, dict):
            names.update(str(k) for k in record.keys())
    priority = ['id','number','title','name','organization_id','organization','customer_id','customer','deviceid','devicename','username','start_date','end_date','duration','state','state_id','created_at','updated_at']
    ordered = [x for x in priority if x in names]
    ordered.extend(sorted(names-set(ordered), key=str.lower))
    return ordered


def teamviewer(config, client):
    headers = {'Authorization': 'Bearer ' + config['secret']}
    now = datetime.now(timezone.utc)
    days = config.get('days', 0)
    if days not in (0, 7, 30, 90, 365):
        raise ValueError('Ungültiger Zeitraum.')
    params = dict(limit=100)
    if days:
        params.update(from_date=(now-timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                      to_date=now.strftime('%Y-%m-%dT%H:%M:%SZ'))
    records, offsets, limited = [], set(), False
    for page in range(5):
        payload = get(client, '/api/v1/reports/connections?' + urlencode(params), headers)
        batch = payload.get('records', payload.get('connections')) if isinstance(payload,dict) else None
        if not isinstance(batch, list):
            raise ValueError('TeamViewer hat keine Verbindungsliste geliefert.')
        records.extend(row for row in batch if isinstance(row,dict))
        offset = payload.get('next_offset')
        if not offset:
            limited = len(batch) >= 100
            break
        if not isinstance(offset,(str,int)) or str(offset) in offsets:
            limited = True
            break
        offsets.add(str(offset));params['offset'] = str(offset)
        limited = page == 4
    records.sort(key=lambda r: stamp(r.get('start_date')) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    rows=[]
    for r in records[:100]:
        raw=safe_raw(r,config['secret'])
        rows.append(dict(cells=[text(r.get('devicename'), 'Unbenanntes Gerät'), text(r.get('username')),
                       date(r.get('start_date')), date(r.get('end_date')), duration(r.get('start_date'),r.get('end_date'))],
                       raw=raw,external_key=external_key('teamviewer',raw),
                       customer_hint={'name': text(r.get('username'), '').strip('–'), 'contact_person':'', 'phones':[],
                                      'device_id': text(r.get('deviceid'), '').strip('–'), 'device_name': text(r.get('devicename'), '').strip('–')}))
    return dict(columns=['Gerätename','Benutzer','Beginn','Ende','Verbindungsdauer'], raw_columns=raw_columns([r['raw'] for r in rows]),
                date_columns=[2,3], rows=rows,
                note=(f'Letzte {days} Tage' if days else 'API-Standardzeitraum (ohne Datumsfilter)') + ' · neueste geladene Verbindungen zuerst · maximal 100 angezeigt.' +
                     (' TeamViewer meldet keine Verbindungen. Bitte Zeitraum, Verbindungsprotokollierung und Zugriff des Script-Tokens auf die Berichte prüfen.' if not rows else '') +
                     (' Die API-Liste ist begrenzt; weitere Verbindungen können vorhanden sein.' if limited else ''))


def zammad(config, client):
    token=base64.b64encode((config['username']+':'+config['secret']).encode()).decode()
    headers={'Authorization':'Basic '+token}
    payload=get(client,'/api/v1/tickets?expand=true&page=1&per_page=100&sort_by=updated_at&order_by=desc',headers)
    if not isinstance(payload,list):
        raise ValueError('Zammad hat keine Ticketliste geliefert.')
    states={'new':'Neu','open':'Offen','closed':'Geschlossen','merged':'Zusammengeführt',
            'pending reminder':'Warten auf Erinnerung','pending close':'Warten auf Schließen','removed':'Entfernt'}
    organizations={};rows=[]
    for ticket in payload[:100]:
        if not isinstance(ticket,dict):continue
        organization=text(ticket.get('organization'), '')
        oid=str(ticket.get('organization_id') or '')
        if not organization and re.fullmatch(r'[1-9][0-9]*',oid):
            if oid not in organizations:
                if len(organizations) < 10:
                    status, item, _ = client.request('/api/v1/organizations/'+oid,headers)
                    organizations[oid]=text(item.get('name'),'Name nicht verfügbar') if status==200 and isinstance(item,dict) else 'Name nicht verfügbar'
                else:organizations[oid]='Name nicht verfügbar'
            organization=organizations[oid]
        state=text(ticket.get('state'))
        tid=str(ticket.get('id') or '')
        raw=safe_raw(ticket,config['secret'])
        customer=ticket.get('customer') if isinstance(ticket.get('customer'),dict) else {}
        rows.append(dict(cells=[text(ticket.get('id')),text(ticket.get('number')),text(ticket.get('title')),
                                organization or 'Keine Organisation',states.get(state.lower(),state),date(ticket.get('updated_at'))],
                         ticket_id=tid if re.fullmatch(r'[1-9][0-9]*',tid) else None,
                         raw=raw,external_key=external_key('zammad',raw),
                         customer_hint={'name': organization or text(customer.get('organization'), '').strip('–') or text(customer.get('name'), '').strip('–'),
                                        'contact_person': text(customer.get('name'), '').strip('–'),
                                        'email': text(customer.get('email'), '').strip('–'), 'phones': []}))
    return dict(columns=['ID','Ticketnummer','Titel','Organisation','Status','Aktualisiert'], raw_columns=raw_columns([r['raw'] for r in rows]),date_columns=[5],rows=rows,
                note='Bis zu 100 Tickets · Klick auf Ticketdetails bleibt verfügbar · Rohdaten enthalten alle von Zammad gelieferten Felder.')


def ticket_detail(config, ticket_id, client_factory=integrations.Client):
    if not re.fullmatch(r'[1-9][0-9]*', str(ticket_id)):
        raise ValueError('Ungültige Ticket-ID.')
    client = client_factory(config['domain'])
    auth = base64.b64encode((config['username']+':'+config['secret']).encode()).decode()
    headers = {'Authorization': 'Basic '+auth}
    ticket = get(client, '/api/v1/tickets/'+str(ticket_id)+'?expand=true', headers)
    articles = get(client, '/api/v1/ticket_articles/by_ticket/'+str(ticket_id)+'?expand=true', headers)
    if not isinstance(ticket, dict) or not isinstance(articles, list):
        raise ValueError('Zammad lieferte keine gültigen Ticketdetails.')
    class PlainText(HTMLParser):
        def __init__(self):
            super().__init__(); self.parts=[]; self.hidden=0
        def handle_starttag(self, tag, attrs):
            if tag in ('script','style'): self.hidden+=1
            if tag in ('br','p','div'): self.parts.append('\n')
        def handle_endtag(self, tag):
            if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
        def handle_data(self, data):
            if not self.hidden: self.parts.append(data)
    for article in articles:
        if isinstance(article,dict) and article.get('content_type') == 'text/html':
            parser=PlainText(); parser.feed(str(article.get('body') or ''))
            article['body']=''.join(parser.parts); article['content_type']='text/plain'
    return safe_raw(dict(ticket=ticket, articles=articles), config['secret'])


def load(config, client_factory=integrations.Client):
    if config['provider'] not in ('teamviewer','zammad'):
        raise ValueError('Für diese Schnittstelle ist keine Live-Liste eingerichtet.')
    client=client_factory(config['domain'])
    return (teamviewer if config['provider']=='teamviewer' else zammad)(config,client)
