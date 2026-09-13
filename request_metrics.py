"""Request-local timing counters. Never retain SQL, parameters or identities."""
from contextvars import ContextVar
from time import perf_counter
_state=ContextVar('request_metrics',default=None)
def reset():_state.set({'start':perf_counter(),'db_connect':0.0,'db_query':0.0,'queries':0,'auth':0.0})
def add(key,seconds):
    state=_state.get()
    if state is not None:state[key]=state.get(key,0)+seconds

def header():
    state=_state.get()
    if state is None:return ''
    values={k:state[k]*1000 for k in ('db_connect','db_query','auth')}
    values['app']=(perf_counter()-state['start'])*1000
    return ', '.join(f'{k};dur={v:.2f}' for k,v in values.items())+f', queries;desc="{state["queries"]}"'
