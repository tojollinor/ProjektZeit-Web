"""Per-user encrypted API configuration and bounded, read-only diagnostics."""
import base64
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from http.cookies import SimpleCookie
from cryptography.fernet import Fernet, InvalidToken

PROVIDERS = ('teamviewer', 'starface', 'zammad')
KEY_LOCK = threading.Lock()
TEST_LOCK = threading.BoundedSemaphore(3)


def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS integrations (
        owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        provider TEXT NOT NULL, domain TEXT NOT NULL, username TEXT NOT NULL,
        secret TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(owner_id,provider))''')


def cipher(data_dir):
    with KEY_LOCK:
        key = os.environ.get('INTEGRATION_KEY', '').strip()
        if not key:
            path = Path(data_dir) / 'integration.key'
            if not path.exists():
                # Exclusive creation avoids silently replacing an existing key.
                try:
                    with path.open('xb') as f:
                        os.chmod(path, 0o600)
                        f.write(Fernet.generate_key())
                except FileExistsError:
                    pass
            key = path.read_bytes()
        try:
            return Fernet(key)
        except (ValueError, TypeError):
            raise ValueError('Der Integrationsschlüssel ist ungültig. Serverkonfiguration prüfen.') from None


def domain(value, provider):
    value = str(value or '').strip().rstrip('/')
    if '://' not in value:
        value = 'https://' + value
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
        allowed_path = '/rest' if provider == 'starface' else '/api/v1'
        if parsed.path not in ('', allowed_path):
            raise ValueError()
        host = parsed.hostname.encode('idna').decode('ascii').lower()
        if '%' in host or any(ord(c) < 33 for c in value) or (port is not None and not 1 <= port <= 65535):
            raise ValueError()
        if provider == 'teamviewer' and (host != 'webapi.teamviewer.com' or port not in (None,443)):
            raise ValueError('Für TeamViewer bitte https://webapi.teamviewer.com verwenden.')
        origin = '[' + host + ']' if ':' in host else host
        return 'https://' + origin + (':' + str(port) if port and port != 443 else '')
    except (ValueError, UnicodeError) as error:
        if str(error).startswith('Für TeamViewer'):
            raise
        raise ValueError('Bitte eine HTTPS-Domain ohne Login, Query oder Unterseite eingeben (z. B. https://telefon.firma.de).') from None


def list_configs(c, uid):
    rows = {r['provider']: r for r in c.execute('SELECT * FROM integrations WHERE owner_id=?', (uid,))}
    return [dict(provider=p,domain=rows[p]['domain'] if p in rows else ('https://webapi.teamviewer.com' if p=='teamviewer' else ''),
                 username=rows[p]['username'] if p in rows else '',has_secret=p in rows,updated_at=rows[p]['updated_at'] if p in rows else None) for p in PROVIDERS]


def config(c, uid, body, data_dir):
    provider = body.get('provider')
    if provider not in PROVIDERS:
        raise ValueError('Unbekannte Schnittstelle.')
    origin = domain(body.get('domain'), provider)
    username = str(body.get('username', '')).strip()
    if len(username)>250 or ':' in username or any(ord(ch)<32 for ch in username):
        raise ValueError('Benutzername ist ungültig.')
    if not username and provider != 'teamviewer':
        raise ValueError('Benutzername / Login-ID fehlt.')
    secret = body.get('secret', '')
    if not isinstance(secret,str) or len(secret)>4096:
        raise ValueError('Zugangsdaten sind ungültig.')
    if not secret:
        row = c.execute('SELECT * FROM integrations WHERE owner_id=? AND provider=?', (uid,provider)).fetchone()
        # Never send a saved credential to a newly typed host or account.
        if not row or row['domain']!=origin or row['username']!=username:
            raise ValueError('Bitte Passwort bzw. API-Token eingeben. Bei geänderter Domain oder Benutzername ist eine erneute Eingabe erforderlich.')
        try:
            secret = cipher(data_dir).decrypt(row['secret'].encode()).decode()
        except InvalidToken:
            raise ValueError('Gespeicherte Zugangsdaten konnten nicht entschlüsselt werden. Schlüssel prüfen oder neu eingeben.') from None
    if provider=='teamviewer' and any(ord(ch)<33 for ch in secret):
        raise ValueError('Der API-Token darf keine Leerzeichen oder Zeilenumbrüche enthalten.')
    return dict(provider=provider,domain=origin,username=username,secret=secret)


def save(c, uid, body, data_dir):
    data = config(c,uid,body,data_dir)
    encrypted = cipher(data_dir).encrypt(data['secret'].encode()).decode()
    store(c, uid, data['provider'], data['domain'], data['username'], encrypted)


def store(c, uid, provider, origin, username, encrypted):
    c.execute('DELETE FROM integrations WHERE owner_id=? AND provider=?', (uid, provider))
    c.execute("INSERT INTO integrations VALUES(?,?,?,?,?,?)",
              (uid, provider, origin, username, encrypted, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))


def allowed_address(address):
    ip = ipaddress.ip_address(address)
    if ip.version==6 and ip.ipv4_mapped:
        ip=ip.ipv4_mapped
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return False
    # LAN installations are supported; local services and cloud metadata are not.
    lan = any(ip in ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','fc00::/7') if ip.version==ipaddress.ip_network(n).version)
    return ip.is_global or lan


class Connection(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host,self.port,type=socket.SOCK_STREAM)
        if not addresses or any(not allowed_address(a[4][0]) for a in addresses):
            raise ValueError('Dieses Ziel ist nicht erlaubt (Loopback, Link-Local oder reserviertes Netz).')
        # Pin the validated IP for this connection; keep hostname for TLS/SNI.
        self.sock = socket.create_connection((addresses[0][4][0],self.port),self.timeout)
        self.sock = self._context.wrap_socket(self.sock,server_hostname=self.host)


class Client:
    def __init__(self, origin):
        parsed=urlsplit(origin)
        self.host,self.port=parsed.hostname,parsed.port or 443
        self.cookies={}

    def request(self,path,headers=None,body=None,allow_discovery_redirect=False):
        started=time.monotonic()
        conn=Connection(self.host,self.port,timeout=8,context=ssl.create_default_context())
        outgoing={'Accept':'application/json','Content-Type':'application/json','User-Agent':'ProjektZeit/0.7.0',**(headers or {})}
        if self.cookies:
            outgoing['Cookie']='; '.join(k+'='+v for k,v in self.cookies.items())
        try:
            encoded = None
            if body is not None:
                encoded = (urlencode(body) if outgoing['Content-Type'] == 'application/x-www-form-urlencoded' else json.dumps(body)).encode()
            conn.request('POST' if body is not None else 'GET',path,body=encoded,headers=outgoing)
            response=conn.getresponse()
            if 300 <= response.status < 400:
                if allow_discovery_redirect and body is None:
                    return response.status, {'redirect': response.getheader('Location', '')}, 'Discovery-Weiterleitung'
                raise ValueError('Weiterleitung abgewiesen. Bitte die endgültige API-Domain eintragen.')
            for key,value in response.getheaders():
                if key.lower()=='set-cookie':
                    jar=SimpleCookie();jar.load(value)
                    self.cookies.update({k:m.value for k,m in jar.items()})
            chunks=[];size=0
            while True:
                if time.monotonic()-started>12:
                    raise TimeoutError()
                chunk=response.read1(16384)
                if not chunk: break
                size+=len(chunk)
                if size>262144:
                    raise ValueError('Antwort größer als 256 KB. Die Datenprobe konnte nicht vollständig geprüft werden.')
                chunks.append(chunk)
            payload=b''.join(chunks)
            if not 200 <= response.status < 300:
                hints={401:'Anmeldung abgewiesen. Zugangsdaten und API-Anmeldung prüfen.',403:'Zugriff verweigert. API-Berechtigungen prüfen.',404:'API-Endpunkt nicht vorhanden. Domain und Serverversion prüfen.',429:'Zu viele Anfragen. Bitte später erneut testen.'}
                return response.status,None,hints.get(response.status,'Der Dienst meldet einen HTTP-Fehler.')
            try:
                return response.status,json.loads(payload),'OK'
            except (ValueError,UnicodeError):
                return response.status,None,'Keine gültige JSON-Antwort. Möglicherweise wurde eine Login-Webseite geliefert.'
        finally:
            conn.close()


SAFE_FIELDS={'id','userid','user_id','login','name','firstname','lastname','email','number','title','customer_id','organization_id','state_id','created_at','updated_at','start','end','start_date','end_date','duration','deviceid','devicename','username','sessionid','remotecontrol_id','billing_state','version','firstName','lastName','loginId'}


def preview(value,secrets):
    """Whitelist preview fields; never return raw provider payloads or auth headers."""
    def scrub(v):
        text=str(v)
        for secret in secrets:
            if secret: text=text.replace(secret,'[ausgeblendet]')
        return text[:300]
    rows=value if isinstance(value,list) else [value]
    result=[]
    for row in rows[:5]:
        if isinstance(row,dict):
            result.append({k:scrub(v) if isinstance(v,str) else v for k,v in row.items() if k in SAFE_FIELDS and isinstance(v,(str,int,float,bool,type(None)))})
    return result


def diagnose(data, client_factory=Client):
    started=time.monotonic();steps=[];secrets=[data['secret']]
    client=client_factory(data['domain'])
    def call(label,path,headers=None,body=None,show=True):
        begin=time.monotonic()
        status,payload,message=client.request(path,headers,body)
        entry=dict(name=label,path=path,status=status,ok=payload is not None,message=message,duration_ms=round((time.monotonic()-begin)*1000))
        if show and payload is not None:
            value=payload.get('records',payload.get('connections',payload)) if isinstance(payload,dict) else payload
            entry.update(count=len(value) if isinstance(value,list) else 1,preview=preview(value,secrets))
            sample=value[0] if isinstance(value,list) and value else value
            entry['fields']=[str(k)[:80] for k in sample.keys() if not re.search('pass|secret|token|auth|cookie',str(k),re.I) and not any(secret in str(k) for secret in secrets if secret)][:35] if isinstance(sample,dict) else []
            if not isinstance(payload,(dict,list)):
                entry.update(ok=False,message='Unerwartetes Datenformat: Objekt oder Liste erwartet.')
        steps.append(entry)
        return payload
    try:
        p=data['provider']
        if p=='teamviewer':
            headers={'Authorization':'Bearer '+data['secret']}
            secrets.append(headers['Authorization'])
            ping=call('Token prüfen','/api/v1/ping',headers,show=False)
            if not isinstance(ping,dict) or ping.get('token_valid') is not True:
                if ping is not None: steps[-1].update(ok=False,message='Token wurde nicht als gültig bestätigt.')
            else:
                call('Fernwartungsverbindungen','/api/v1/reports/connections?limit=5',headers)
        elif p=='zammad':
            authorization=base64.b64encode((data['username']+':'+data['secret']).encode()).decode()
            secrets.extend([authorization,'Basic '+authorization])
            headers={'Authorization':'Basic '+authorization}
            me=call('Benutzer prüfen','/api/v1/users/me',headers)
            if isinstance(me,dict) and me.get('id'):
                call('Tickets lesen','/api/v1/tickets?page=1&per_page=5',headers)
            elif me is not None: steps[-1].update(ok=False,message='Benutzerantwort enthält keine ID.')
        elif p == 'starface' and data.get('oauth'):
            headers = {'Authorization': 'Bearer ' + data['secret'], 'X-Version': '2'}
            secrets.append(headers['Authorization'])
            call('STARFACE-Benutzer lesen (OAuth)', '/rest/users', headers)
        else:
            headers={'X-Version':'2'}
            challenge=call('Anmeldung vorbereiten','/rest/login',headers,show=False)
            if isinstance(challenge,dict) and challenge.get('nonce') and challenge.get('loginType'):
                username,nonce,password=data['username'],str(challenge['nonce']),data['secret']
                mode=challenge['loginType']
                if mode=='Internal':
                    secret=username+':'+hashlib.sha512((username+nonce+hashlib.sha512(password.encode()).hexdigest()).encode()).hexdigest()
                elif mode in ('ActiveDirectory','Active Directory','AD'):
                    secret=base64.b64encode((username+nonce+password).encode()).decode()
                else:
                    raise ValueError('Die STARFACE meldet einen nicht unterstützten Login-Typ. REST-Konfiguration prüfen.')
                secrets.append(secret)
                login=call('Benutzer anmelden','/rest/login',headers,dict(loginType=mode,nonce=nonce,secret=secret),show=False)
                if isinstance(login,dict) and login.get('authToken'):
                    secrets.append(str(login['authToken']))
                    call('Benutzerdaten lesen','/rest/users',{'X-Version':'2','authToken':str(login['authToken'])})
                elif login is not None: steps[-1].update(ok=False,message='Anmeldung lieferte keinen authToken.')
            elif challenge is not None: steps[-1].update(ok=False,message='Antwort enthält keine gültige REST-Login-Challenge.')
    except (TimeoutError,socket.timeout):
        steps.append(dict(name='Verbindung',ok=False,message='Zeitüberschreitung. Erreichbarkeit und Firewall prüfen.'))
    except ssl.SSLError:
        steps.append(dict(name='TLS',ok=False,message='Zertifikatsprüfung fehlgeschlagen. Vertrauenswürdiges Zertifikat bzw. interne CA auf dem Server einrichten.'))
    except (OSError,http.client.HTTPException):
        steps.append(dict(name='Verbindung',ok=False,message='Dienst nicht erreichbar. Domain, Port und DNS prüfen.'))
    except ValueError as error:
        steps.append(dict(name='Verbindung',ok=False,message=str(error)))
    good=bool(steps) and all(step['ok'] for step in steps)
    notes={'starface':'Die REST-Probe prüft Anmeldung und Benutzerdaten. Anrufbeginn, Anrufende und Gesprächsdauer sind damit noch nicht nachgewiesen; dafür ist die passende UCI-/Anruflisten-Schnittstelle deiner STARFACE zu prüfen.',
           'teamviewer':'Verbindungsberichte benötigen entsprechende Token-Rechte und eine unterstützte Lizenz. Eine leere Liste bestätigt noch keine verwertbaren Sitzungszeiten.',
           'zammad':'Ticket-IDs, Kundenbezug und Zeitfelder dienen als Datenprobe. Erstellungs-/Änderungszeitpunkte sind keine automatisch erfasste Arbeitsdauer.'}
    groups={'teamviewer': [('Verbindungs-ID',['id','sessionid']),('Startzeit',['start_date','start']),('Endzeit',['end_date','end']),('Gerätebezug',['deviceid','devicename','remotecontrol_id'])],
            'zammad':[('Ticket-ID',['id','number']),('Kundenbezug',['customer_id','organization_id']),('Titel',['title']),('Zeitstempel',['created_at','updated_at'])],
            'starface':[('Benutzer-ID',['id','userId','userid']),('Login-ID',['login','loginId']),('Name',['name','firstName','firstname'])]}
    fields=set(steps[-1].get('fields',[])) if steps else set()
    checks=[dict(name=name,found=bool(fields.intersection(aliases))) for name,aliases in groups[data['provider']]]
    return dict(ok=good,steps=steps,checks=checks,duration_ms=round((time.monotonic()-started)*1000),note=notes[data['provider']],checked_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
