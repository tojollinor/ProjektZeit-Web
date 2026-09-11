"""Read the linked user's STARFACE 10 call history using OAuth and UCI XML-RPC.

Protocol sources:
https://knowledge.starface.de/pages/viewpage.action?pageId=46568050
https://api.starface.de/uci-3.0.5/de/starface/integration/uci/java/v30/ucp/messages/requests/UcpCallListRequests.html
https://api.starface.de/uci-3.0.5/de/starface/integration/uci/java/v30/values/CallListEntryProperties.html
"""
import re
import ssl
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from urllib.parse import urlencode, urlsplit
from xml.parsers.expat import ExpatError
from xmlrpc.client import dumps, loads, Fault
import integrations

PREFIX = 'ucp.v30.requests.'


def _safe_debug_text(raw, secret):
    """Return a short diagnostic preview without exposing OAuth credentials."""
    if not raw:
        return '(leer)'
    try:
        text = raw[:4096].decode('utf-8', errors='replace')
    except Exception:
        return '(nicht als Text lesbar)'
    if secret:
        text = text.replace(secret, '[TOKEN AUSGEBLENDET]')
    text = re.sub(r'(?i)(de\.vertico\.starface\.jwt=)[^&\s"\'<>]+', r'\1[TOKEN AUSGEBLENDET]', text)
    text = re.sub(r'(?i)(authorization\s*[:=]\s*bearer\s+)[^\s"\'<>]+', r'\1[TOKEN AUSGEBLENDET]', text)
    text = re.sub(r'(?i)([?&](?:code|token|access_token|refresh_token|id_token)=)[^&\s"\'<>]+', r'\1[AUSGEBLENDET]', text)
    text = ' '.join(text.split())
    return text[:1200] or '(nur Leerraum)'


def _response_kind(raw):
    head = raw.lstrip()[:200].lower()
    if head.startswith(b'<?xml') or b'<methodresponse' in head:
        return 'XML/XML-RPC'
    if head.startswith(b'<!doctype html') or b'<html' in head:
        return 'HTML'
    if head.startswith((b'{', b'[')):
        return 'JSON/Text'
    if not raw:
        return 'leer'
    return 'unbekannt'


def _debug_summary(response, raw, secret):
    content_type = response.getheader('Content-Type') or '(nicht gesetzt)'
    location = response.getheader('Location') or ''
    if secret:
        location = location.replace(secret, '[TOKEN AUSGEBLENDET]')
    location = re.sub(r'(?i)([?&](?:code|token|access_token|refresh_token|id_token|de\.vertico\.starface\.jwt)=)[^&\s]+', r'\1[AUSGEBLENDET]', location)
    bits = [
        'HTTP %s' % response.status,
        'Content-Type: %s' % content_type[:160],
        'Antworttyp: %s' % _response_kind(raw),
        'Größe: %s Byte' % len(raw),
    ]
    if location:
        bits.append('Location: %s' % location[:300])
    bits.append('Vorschau: %s' % _safe_debug_text(raw, secret))
    return ' · '.join(bits)


class UciClient:
    def __init__(self, config):
        origin = integrations.domain(config['domain'], 'starface')
        target = urlsplit(origin)
        self.host, self.port = target.hostname, target.port or 443
        self.secret = config['secret']
        # STARFACE 10 specifies this query parameter for OAuth XML-RPC.
        # Never log this path or include it in user-facing errors.
        self.path = '/xml-rpc?' + urlencode({'de.vertico.starface.jwt': self.secret})
        self.cookies = {}

    def call(self, method, params=()):
        if method not in ('connection.login', 'connection.logout', 'callList.getCallList'):
            raise ValueError('Nicht unterstützte STARFACE-Abfrage.')
        body = dumps(tuple(params), methodname=PREFIX+method, allow_none=True).encode()
        conn = integrations.Connection(self.host, self.port, timeout=8, context=ssl.create_default_context())
        headers = {'Content-Type': 'text/xml', 'Accept': 'text/xml', 'User-Agent': 'ProjektZeit/0.7.0'}
        if self.cookies:
            headers['Cookie'] = '; '.join(k+'='+v for k,v in self.cookies.items())
        try:
            conn.request('POST', self.path, body=body, headers=headers)
            response = conn.getresponse()
            for key, value in response.getheaders():
                if key.lower() == 'set-cookie':
                    jar = SimpleCookie(); jar.load(value)
                    self.cookies.update({k: m.value for k,m in jar.items()})
            chunks, size, started = [], 0, time.monotonic()
            while True:
                if time.monotonic()-started > 12:
                    raise ValueError('Zeitlimit beim Lesen der STARFACE-Anrufliste.')
                chunk = response.read1(16384)
                if not chunk: break
                size += len(chunk)
                if size > 1048576:
                    raise ValueError('STARFACE-Anrufliste ist zu groß. Kürzeren Zeitraum wählen.')
                chunks.append(chunk)
            raw = b''.join(chunks)
            debug = _debug_summary(response, raw, self.secret)
            if response.status != 200:
                raise ValueError('STARFACE-Anrufliste nicht erreichbar. STARFACE-Debug: ' + debug)
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                raise ValueError('Ungültige XML-Antwort von STARFACE. STARFACE-Debug: ' + debug)
            try:
                result, _ = loads(raw, use_builtin_types=True)
            except Fault as error:
                # Fault strings can contain credentials/URLs. Only expose the numeric code.
                code = error.faultCode if type(error.faultCode) is int else 'unbekannt'
                raise ValueError('STARFACE hat die UCI-Abfrage abgewiesen (Code %s). API-/UCI-Berechtigung des verknüpften Benutzers prüfen. STARFACE-Debug: %s' % (code, debug)) from None
            except (ExpatError, ValueError, TypeError):
                raise ValueError('STARFACE lieferte keine gültige XML-RPC-Antwort. STARFACE-Debug: ' + debug) from None
            if len(result) != 1:
                raise ValueError('Unerwartete STARFACE-Antwort. STARFACE-Debug: ' + debug)
            return result[0]
        except OSError:
            raise ValueError('STARFACE für Anruflisten nicht erreichbar. Netzwerk und TLS-Verbindung prüfen.') from None
        finally:
            conn.close()


def server_info(config, client_factory=integrations.Client):
    headers = {'Authorization': 'Bearer '+config['secret'], 'X-Version': '2'}
    try:
        status, payload, _ = client_factory(config['domain']).request('/rest/server/version', headers)
        version = payload.get('version') if isinstance(payload, dict) else payload
        # Display only a version number, never arbitrary server response content.
        if status == 200 and isinstance(version, str) and re.fullmatch(r'\d+(?:\.\d+){1,5}(?:[-+][a-zA-Z0-9._-]+)?', version):
            return {'version': version, 'version_note': ''}
        return {'version': None, 'version_note': 'Version nicht verfügbar' + (' (keine Berechtigung).' if status == 403 else '.')}
    except (OSError, ValueError):
        return {'version': None, 'version_note': 'Versionsabfrage derzeit nicht erreichbar.'}


def start_time(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            return start_time(datetime.fromisoformat(value.replace('Z', '+00:00')))
        except ValueError:
            pass
    return None


def load(config, rpc_factory=UciClient):
    days, offset = config.get('days', 30), config.get('offset', 0)
    if type(days) is not int or days not in (7, 30, 90, 365):
        raise ValueError('Ungültiger Zeitraum für die Anrufliste.')
    if type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError('Ungültige Seite der Anrufliste.')
    mode = config.get('call_type', 'all')
    filters = {'all': ('', ''), 'inbound': ('INBOUND', ''), 'outbound': ('OUTBOUND', ''), 'missed': ('INBOUND', 'MISSED')}
    if not isinstance(mode, str) or mode not in filters:
        raise ValueError('Ungültiger Anruffilter.')
    direction_filter, result_filter = filters[mode]
    now = datetime.now(timezone.utc)
    rpc = rpc_factory(config)
    if rpc.call('connection.login') is not True:
        raise ValueError('STARFACE-UCI-Anmeldung abgewiesen. Berechtigungen prüfen.')
    try:
        payload = rpc.call('callList.getCallList', (
            now.replace(tzinfo=None), (now-timedelta(days=days)).replace(tzinfo=None),
            direction_filter, result_filter, 'NON_GROUP', 'startTime', 'DESCENDING', offset, 100))
    finally:
        try: rpc.call('connection.logout')
        except (ValueError, OSError): pass
    if not isinstance(payload, dict) or not isinstance(payload.get('entries'), list):
        raise ValueError('STARFACE lieferte keine gültige Anrufliste.')
    rows, skipped = [], 0
    for item in payload['entries'][:100]:
        if not isinstance(item, dict) or item.get('direction') not in ('INBOUND', 'OUTBOUND') or item.get('groupId'):
            skipped += 1
            continue
        direction, result = item['direction'], item.get('result')
        if (direction_filter and direction != direction_filter) or (result_filter and result != result_filter):
            skipped += 1
            continue
        start = start_time(item.get('startTime'))
        seconds = item.get('duration')
        valid_duration = type(seconds) is int and 0 <= seconds <= 31536000
        try:
            end = start + timedelta(seconds=seconds) if start and valid_duration else None
        except OverflowError:
            end = None
        number = item.get('calledNumber')
        number = number if isinstance(number, str) and number else 'Unbekannt'
        seconds_text = ('%02d:%02d:%02d' % (seconds//3600, seconds//60%60, seconds%60)) if valid_duration else 'Nicht geliefert'
        result = str(item.get('result') or '')
        status = {'ANSWERED': 'Beantwortet', 'MISSED': 'Verpasst' if direction == 'INBOUND' else 'Nicht erreicht'}.get(result, result or 'Unbekannt')
        caller = item.get('callerNumber')
        caller = caller if isinstance(caller, str) and caller else 'Unbekannt'
        description = item.get('callDescription')
        description = description if isinstance(description, str) else ''
        cells = ['Eingehend' if direction == 'INBOUND' else 'Ausgehend', status[:100], caller[:500], number[:500], description[:500], start.isoformat() if start else None, end.isoformat() if end else None, seconds_text]
        cells = [v.replace(config['secret'], '[ausgeblendet]') if isinstance(v, str) and config['secret'] else v for v in cells]
        rows.append({'cells': cells, 'duration_seconds': seconds if valid_duration else None, 'end_calculated': bool(end)})
    total = payload.get('totalCount')
    next_offset = offset + len(payload['entries'])
    has_more = len(payload['entries']) >= 100 and (type(total) is not int or next_offset < total)
    return {'columns': ['Richtung', 'Status', 'Anrufer', 'Angerufene Rufnummer', 'Name / Beschreibung', 'Anrufbeginn', 'Ende (berechnet)', 'Dauer'],
            'date_columns': [5, 6], 'rows': rows, 'next_offset': next_offset if has_more else None,
            'note': f'Persönliche Anrufe (ohne Gruppenanrufe) · letzte {days} Tage · Dauer laut STARFACE, ohne Abzug der Klingelzeit. Ende = Beginn + Dauer.' +
                    (' Keine Anrufe im gewählten Zeitraum.' if not rows and not skipped else '') +
                    (' Nicht zum persönlichen Anruffilter passende Einträge wurden ausgeblendet.' if skipped else '')}
