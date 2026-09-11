"""Normalized read-only provider lists. Credentials stay on the server."""
import base64
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
    rows = [dict(cells=[text(r.get('devicename'), 'Unbenanntes Gerät'), text(r.get('username')),
                       date(r.get('start_date')), date(r.get('end_date')), duration(r.get('start_date'),r.get('end_date'))]) for r in records[:100]]
    return dict(columns=['Gerätename','Benutzer','Beginn','Ende','Verbindungsdauer'], date_columns=[2,3], rows=rows,
                note=(f'Letzte {days} Tage' if days else 'API-Standardzeitraum (ohne Datumsfilter)') + ' · neueste geladene Verbindungen zuerst · maximal 100 angezeigt.' +
                     (' TeamViewer meldet keine Verbindungen. Bitte Zeitraum, Verbindungsprotokollierung und Zugriff des Script-Tokens auf die Berichte prüfen. Ein gültiger Token allein garantiert keine Berichtsdaten.' if not rows else '') +
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
                # Expansion normally resolves this; cap fallback calls to avoid
                # an unbounded request fan-out for older Zammad installations.
                if len(organizations) < 10:
                    status, item, _ = client.request('/api/v1/organizations/'+oid,headers)
                    organizations[oid]=text(item.get('name'),'Name nicht verfügbar') if status==200 and isinstance(item,dict) else 'Name nicht verfügbar'
                else:organizations[oid]='Name nicht verfügbar'
            organization=organizations[oid]
        state=text(ticket.get('state'))
        tid=str(ticket.get('id') or '')
        rows.append(dict(cells=[text(ticket.get('id')),text(ticket.get('number')),text(ticket.get('title')),
                                organization or 'Keine Organisation',states.get(state.lower(),state),date(ticket.get('updated_at'))],
                         ticket_id=tid if re.fullmatch(r'[1-9][0-9]*',tid) else None))
    return dict(columns=['ID','Ticketnummer','Titel','Organisation','Status','Aktualisiert'],date_columns=[5],rows=rows,
                note='Bis zu 100 Tickets · Klick öffnet die Ticketdetails und Nachrichten in ProjektZeit.')


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
    # HTML bodies are returned as data and displayed as inert text by the UI.
    def scrub(value):
        if isinstance(value, dict):
            return {k: scrub(v) for k,v in value.items() if not any(s in k.lower() for s in ('password','token','secret'))}
        if isinstance(value, list): return [scrub(v) for v in value]
        if isinstance(value, str) and config['secret']: return value.replace(config['secret'], '[ausgeblendet]')
        return value
    return scrub(dict(ticket=ticket, articles=articles))


def load(config, client_factory=integrations.Client):
    if config['provider'] not in ('teamviewer','zammad'):
        raise ValueError('Für diese Schnittstelle ist keine Live-Liste eingerichtet.')
    client=client_factory(config['domain'])
    result=(teamviewer if config['provider']=='teamviewer' else zammad)(config,client)
    # Filter any accidental reflection of the configured secret in API fields.
    for row in result['rows']:
        row['cells']=[value.replace(config['secret'],'[ausgeblendet]') if isinstance(value,str) else value for value in row['cells']]
    return result
