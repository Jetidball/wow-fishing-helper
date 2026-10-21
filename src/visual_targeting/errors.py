"""Persistent bounded JSONL error history shared by GUI and worker monitoring."""
import json,logging,threading,traceback,uuid
from datetime import datetime,timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
_lock=threading.Lock()

def record_error(action,exc,context=None,root=Path('data')):
    root=Path(root);path=root/'logs/application-errors.jsonl';event_id=uuid.uuid4().hex[:12]
    event={'id':event_id,'time':datetime.now(timezone.utc).isoformat(),'action':action,'type':type(exc).__name__,'message':str(exc),'context':context or {},'traceback':''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))}
    try:
        with _lock:
            path.parent.mkdir(parents=True,exist_ok=True)
            handler=RotatingFileHandler(path,maxBytes=2*1024*1024,backupCount=3,encoding='utf-8')
            try:handler.emit(logging.LogRecord('application',logging.ERROR,'',0,json.dumps(event,ensure_ascii=True,default=str),(),None))
            finally:handler.close()
    except OSError:return event_id,None
    return event_id,path.resolve()

def track_tk_errors(root,on_error=None):
    if getattr(root,'_errors_tracked',False):return
    root._errors_tracked=True
    def report(kind,exc,tb):
        event,path=record_error('tk_callback',exc.with_traceback(tb))
        if on_error:on_error(f'{exc} | Error {event}; log: {path or "unavailable"}')
    root.report_callback_exception=report
