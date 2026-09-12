"""Small request-path performance optimizations."""
import threading
import time


def install(app):
    try:
        runtime=__import__('next_batch_runtime')
        original=runtime._touch_session
    except Exception:
        return
    lock=threading.Lock();last={}
    def touch(app_,handler,session):
        if not session or not session.get('token_hash'):
            return
        token=session['token_hash'];now=time.monotonic()
        with lock:
            previous=last.get(token,0)
            if now-previous<20:
                return
            last[token]=now
            if len(last)>512:
                cutoff=now-3600
                for key,value in list(last.items()):
                    if value<cutoff:last.pop(key,None)
        return original(app_,handler,session)
    runtime._touch_session=touch
