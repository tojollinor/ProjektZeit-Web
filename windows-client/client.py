"""ProjektZeit Windows client. No credentials are written to disk."""
import json
import queue
import secrets
import threading
import time
import tkinter as tk
from tkinter import ttk
import urllib.request
import urllib.error
from urllib.parse import urlsplit, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import webbrowser


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def server_origin(value):
    value = value.strip().rstrip('/')
    if '://' not in value:
        value = 'https://' + value
    p = urlsplit(value)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.path or p.query or p.fragment or '\\' in value or any(c.isspace() for c in value)):
        raise ValueError('Bitte eine HTTPS-Serveradresse ohne Unterpfad eingeben.')
    return value


class Client:
    def __init__(self, root):
        self.root, self.events = root, queue.Queue()
        self.token, self.origin, self.busy = '', '', False
        root.title('ProjektZeit · Windows')
        root.geometry('480x530')
        root.minsize(430, 510)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background='#182231', foreground='#edf2f7', font=('Segoe UI', 10))
        style.configure('TEntry', fieldbackground='#ffffff', foreground='#172033')
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='ProjektZeit', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        self.server = self.entry(frame, 'ProjektZeit-Server', 'https://projektzeit.itomi.de')
        self.user = self.entry(frame, 'ProjektZeit-Benutzer')
        self.password = self.entry(frame, 'ProjektZeit-Passwort', secret=True)
        self.buttons = []
        self.button(frame, 'Anmelden', self.login)
        self.pbx = self.entry(frame, 'STARFACE-Domain', 'https://starface.it-walther.de')
        self.button(frame, 'STARFACE im Browser verknüpfen', self.oauth)
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=8)
        self.button(row, 'Arbeitsbeginn', lambda: self.action('/api/v1/work/begin'), side='left')
        self.button(row, 'Arbeitsende', lambda: self.action('/api/v1/work/end'), side='right')
        self.button(frame, 'Webübersicht öffnen', self.open_web)
        self.button(frame, 'Abmelden', self.logout)
        self.status = ttk.Label(frame, text='Bitte am ProjektZeit-Server anmelden.', wraplength=420)
        self.status.pack(fill='x', pady=12)
        root.after(100, self.poll)

    def entry(self, frame, title, value='', secret=False):
        ttk.Label(frame, text=title).pack(anchor='w', pady=(8, 2))
        entry = ttk.Entry(frame, show='*' if secret else '')
        entry.insert(0, value)
        entry.pack(fill='x')
        return entry

    def button(self, frame, text, command, **pack):
        b = ttk.Button(frame, text=text, command=command)
        b.pack(fill='x', pady=3, **pack)
        self.buttons.append(b)

    def api(self, path, body):
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        request = urllib.request.Request(self.origin + path, json.dumps(body).encode(), headers)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
                return json.loads(response.read(1_000_000))
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read(10000)).get('error', 'Anfrage abgewiesen.')
            except (ValueError, AttributeError):
                message = 'Anfrage abgewiesen (HTTP %s).' % error.code
            raise ValueError(message) from None
        except OSError:
            raise ValueError('Server nicht erreichbar oder TLS-Zertifikat ungültig.') from None

    def run(self, operation):
        if self.busy:
            return
        self.busy = True
        for b in self.buttons:
            b.configure(state='disabled')
        self.status.configure(text='Bitte warten …')
        def worker():
            try:
                message = operation()
            except Exception as error:
                message = str(error) if isinstance(error, ValueError) else 'Vorgang fehlgeschlagen. Bitte erneut versuchen.'
            self.events.put(message)
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            self.status.configure(text=self.events.get_nowait())
            self.busy = False
            for b in self.buttons:
                b.configure(state='normal')
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def login(self):
        try:
            origin = server_origin(self.server.get())
        except ValueError as error:
            self.status.configure(text=str(error)); return
        username, password = self.user.get(), self.password.get()
        self.password.delete(0, 'end')
        def operation():
            if self.token:
                self.api('/api/v1/auth/revoke', {})
            self.token, self.origin = '', origin
            self.token = self.api('/api/v1/auth/token', dict(username=username, password=password, client_name='ProjektZeit Windows'))['access_token']
            return 'Angemeldet. STARFACE-Verknüpfung benötigt ProjektZeit-Adminrechte.'
        self.run(operation)

    def action(self, path):
        def operation():
            if not self.token:
                raise ValueError('Bitte zuerst anmelden.')
            self.api(path, {})
            return 'Arbeitszeit auf dem Server aktualisiert.'
        self.run(operation)

    def open_web(self):
        if self.origin:
            webbrowser.open(self.origin)

    def logout(self):
        def operation():
            if self.token:
                self.api('/api/v1/auth/revoke', {})
            self.token = ''
            return 'Abgemeldet.'
        self.run(operation)

    def oauth(self):
        domain = self.pbx.get().strip()
        def operation():
            if not self.token:
                raise ValueError('Bitte zuerst bei ProjektZeit anmelden.')
            result = {}
            expected = ''
            class Callback(BaseHTTPRequestHandler):
                def setup(self):
                    super().setup()
                    self.connection.settimeout(5)

                def log_message(self, *args):
                    pass

                def do_GET(handler):
                    parsed = urlsplit(handler.path)
                    query = parse_qs(parsed.query)
                    valid = (len(handler.path) < 12000 and parsed.path == '/callback'
                             and len(query.get('state', [])) == 1
                             and secrets.compare_digest(query['state'][0], expected)
                             and (len(query.get('code', [])) == 1 or len(query.get('error', [])) == 1))
                    handler.send_response(200 if valid else 400)
                    handler.send_header('Content-Type', 'text/plain; charset=utf-8')
                    handler.send_header('Cache-Control', 'no-store')
                    handler.send_header('Referrer-Policy', 'no-referrer')
                    handler.end_headers()
                    handler.wfile.write(('Anmeldung empfangen. Bitte zum Windows-Client wechseln.' if valid else 'Ungültige Rückleitung.').encode())
                    if valid:
                        result.update({k: query[k][0] for k in ('state', 'code', 'error') if k in query})
            with ThreadingHTTPServer(('127.0.0.1', 0), Callback) as listener:
                listener.timeout = 1
                reply = self.api('/api/v1/integrations/starface/start', dict(domain=domain, redirect_uri='http://127.0.0.1:%s/callback' % listener.server_port))
                url = reply['url']
                parsed = urlsplit(url)
                if parsed.scheme != 'https' or parsed.username or parsed.password:
                    raise ValueError('Ungültige STARFACE-Anmeldeadresse vom Server.')
                expected = parse_qs(parsed.query)['state'][0]
                webbrowser.open(url)
                deadline = time.monotonic() + 300
                while not result and time.monotonic() < deadline:
                    listener.handle_request()
                if not result:
                    raise ValueError('Anmeldung nach 5 Minuten abgelaufen. Bitte erneut starten.')
            self.api('/api/v1/integrations/starface/finish', result)
            return 'STARFACE verknüpft! Tokens liegen verschlüsselt auf dem Webserver. Der Client kann geschlossen werden.'
        self.run(operation)


if __name__ == '__main__':
    root = tk.Tk()
    Client(root)
    root.mainloop()
