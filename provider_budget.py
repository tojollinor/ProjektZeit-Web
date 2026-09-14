"""Company-wide persistent provider request budget, including manual requests."""
import contextlib
import os
import sqlite3
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
import database

_root=None
probe_remaining=None
_hosts={}
DEFAULTS={'teamviewer':3600,'zammad':3600,'starface':3600}

@contextlib.contextmanager
def connection():
    if database.is_maria():
        import pymysql
        conn=pymysql.connect(host=os.environ.get('DB_HOST','db'),port=int(os.environ.get('DB_PORT','3306')),user=os.environ.get('DB_USER','projektzeit'),password=os.environ['DB_PASSWORD'],database=os.environ.get('DB_NAME','projektzeit'),charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor,autocommit=False,connect_timeout=5)
        c=database.MariaConnection(conn)
    else:
        conn=sqlite3.connect(Path(_root)/'provider-budget.sqlite3',timeout=5);conn.row_factory=sqlite3.Row;c=conn
    try:yield c;conn.commit()
    except BaseException:conn.rollback();raise
    finally:conn.close()

def initialize(root,create=True):
    global _root
    _root=Path(root);_root.mkdir(parents=True,exist_ok=True)
    if not create:return
    with connection() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS provider_budget_state(provider VARCHAR(32) PRIMARY KEY,cap INTEGER NOT NULL,blocked_until INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS provider_budget_requests(id INTEGER PRIMARY KEY,provider VARCHAR(32) NOT NULL,at_second INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_budget_window ON provider_budget_requests(provider,at_second);''')
        for provider,cap in DEFAULTS.items():c.execute('INSERT OR IGNORE INTO provider_budget_state(provider,cap) VALUES(?,?)',(provider,cap))

def register(origin,provider):
    host=urlsplit(origin).hostname
    if host and provider in DEFAULTS:_hosts[host.lower()]=provider

def provider_for(host):
    host=host.lower()
    if host=='webapi.teamviewer.com' or host.endswith('.teamviewer.com'):return 'teamviewer'
    return _hosts.get(host)

def reserve(provider,clock=None):
    if _root is None or not provider:return
    global probe_remaining
    if probe_remaining is not None:
        if probe_remaining<=0:raise ValueError('Diagnose-Abfragebudget erreicht.')
        probe_remaining-=1
    clock=int(clock or time.time())
    with connection() as c:
        maria=getattr(c,'dialect','')=='mariadb'
        if not maria:c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM provider_budget_state WHERE provider=?'+(' FOR UPDATE' if maria else ''),(provider,)).fetchone()
        if not row:raise ValueError('Providerbudget nicht eingerichtet.')
        if row['blocked_until']>clock:raise ValueError('Provider meldet eine Wartezeit. Abgleich wird später fortgesetzt.')
        c.execute('DELETE FROM provider_budget_requests WHERE provider=? AND at_second<=?',(provider,clock-86400))
        used=c.execute('SELECT COUNT(*) n FROM provider_budget_requests WHERE provider=?',(provider,)).fetchone()['n']
        cap=min(row['cap'],3600) if provider=='teamviewer' else row['cap']
        if used>=cap:raise ValueError('Unternehmensweites 24-Stunden-Abfragelimit erreicht. Lokale Daten bleiben verfügbar.')
        c.execute('INSERT INTO provider_budget_requests(provider,at_second) VALUES(?,?)',(provider,clock))

def backoff(provider,value):
    if _root is None or not provider:return
    clock=int(time.time())
    try:until=clock+max(60,int(value))
    except (ValueError,TypeError):
        try:until=max(clock+60,int(parsedate_to_datetime(value).timestamp()))
        except Exception:until=clock+300
    with connection() as c:c.execute('UPDATE provider_budget_state SET blocked_until=CASE WHEN blocked_until>? THEN blocked_until ELSE ? END WHERE provider=?',(until,until,provider))

def snapshot():
    if _root is None:return []
    with connection() as c:return [dict(r) for r in c.execute('SELECT s.*, (SELECT COUNT(*) FROM provider_budget_requests r WHERE r.provider=s.provider AND r.at_second>?) used FROM provider_budget_state s',(int(time.time())-86400,))]

def set_cap(provider,cap):
    cap=int(cap)
    if provider not in DEFAULTS or not 1<=cap<=(3600 if provider=='teamviewer' else 50000):raise ValueError('Abfragelimit ungültig; TeamViewer höchstens 3600 pro Unternehmen.')
    with connection() as c:c.execute('UPDATE provider_budget_state SET cap=? WHERE provider=?',(cap,provider))

def install_transport():
    import integrations
    if getattr(integrations.Connection,'_company_budget',False):return
    request=integrations.Connection.request;response=integrations.Connection.getresponse
    def send(self,*args,**kwargs):
        self._budget_provider=provider_for(self.host);reserve(self._budget_provider)
        return request(self,*args,**kwargs)
    def receive(self,*args,**kwargs):
        result=response(self,*args,**kwargs)
        if result.status==429:backoff(getattr(self,'_budget_provider',None),result.getheader('Retry-After'))
        return result
    integrations.Connection.request=send;integrations.Connection.getresponse=receive;integrations.Connection._company_budget=True
