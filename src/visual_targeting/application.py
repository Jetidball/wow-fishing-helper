"""Owned jobs and latest-only preview. Importing this module never loads input APIs."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import queue

def preview_image(pixels,target,left,top):
    """UI annotations must never enter the source frame used for training."""
    import cv2 as cv
    display=pixels.copy()
    if target:cv.drawMarker(display,(target.x-int(left),target.y-int(top)),(0,255,0),cv.MARKER_CROSS,20,2)
    return display

def log_tail(path,limit=12000):
    """Bounded reads even when a training log has grown to gigabytes."""
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-limit))
            return stream.read(limit).decode('utf-8',errors='replace')
    except OSError as exc:return 'Log unavailable: '+str(exc)

class Job:
    def __init__(self, directory):
        self.directory=Path(directory);self.process=None;self.stream=None;self.log=None
    def start(self, arguments, python=None):
        self.start_python(['-m','visual_targeting.task_cli',*map(str,arguments)],python=python)
    def start_python(self, arguments, python=None):
        if self.process is not None and self.process.poll() is None:raise ValueError('A job is already running')
        self.directory.mkdir(parents=True,exist_ok=True)
        self.log=self.directory/(time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns())+'.log')
        self.stream=self.log.open('w',encoding='utf-8')
        options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}
        environment=os.environ.copy()
        environment['PYTHONPATH']=str(Path(__file__).resolve().parent.parent)+os.pathsep+environment.get('PYTHONPATH','')
        try:self.process=subprocess.Popen([str(python or sys.executable),*map(str,arguments)],stdout=self.stream,stderr=subprocess.STDOUT,env=environment,**options)
        except Exception:self.stream.close();raise
    def status(self):
        if self.process is None:return 'idle'
        result=self.process.poll()
        if result is None:return 'running'
        if self.stream and not self.stream.closed:self.stream.close()
        return 'completed' if result==0 else f'failed (exit {result}); see {self.log}'
    def cancel(self):
        if self.process and self.process.poll() is None:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
            else:
                import signal
                os.killpg(self.process.pid,signal.SIGTERM)
            self.process.wait(timeout=10)
        if self.stream and not self.stream.closed:self.stream.close()

class Preview:
    def __init__(self):
        self.stop_event=threading.Event();self.arm_event=threading.Event();self.frames=queue.Queue(maxsize=1);self.thread=None
        from .teaching import MissTeacher
        self.teacher=MissTeacher();self.teaching=False
        self.mode='dry-run';self.reason='stopped';self.action_result=''
    def publish(self,image,reason):
        self.reason=reason
        try:self.frames.get_nowait()
        except queue.Empty:pass
        self.frames.put_nowait((image,reason))
    def stop(self):
        self.arm_event.clear();self.stop_event.set();self.teaching=False;self.teacher.stop()
    def start(self,profile,registry,hwnd,mode='dry-run',*,weights=None,training_run=None,evaluation=None,region=None,collect=None,teaching=False):
        if self.thread and self.thread.is_alive():raise ValueError('Stop the previous preview first')
        if mode not in ('dry-run','move','single-click'):raise ValueError('Invalid mode')
        self.teaching=teaching
        from .teaching import MissTeacher
        self.teacher=MissTeacher()
        self.mode=mode;self.action_result='';self.stop_event.clear();self.arm_event.clear()
        self.thread=threading.Thread(target=self.run,args=(profile,registry,int(hwnd),weights,training_run,evaluation,region,collect),daemon=True);self.thread.start()
    def run(self,profile,registry,hwnd,weights=None,training_run=None,evaluation=None,region=None,collect=None):
        try:
            import cv2 as cv
            import numpy as np
            from mss import mss
            from .profiles import make_detector,TaskSession
            from .window_context import query_window
            from .geometry import Transforms,Rect,Letterbox
            from .contracts import Frame,Box
            from .windows_mouse import WindowsMouse
            from .guarded_mouse import GuardedMouse
            if weights and self.mode=="move":
                from .profiles import evaluated_movement_candidate
                detector=evaluated_movement_candidate(profile,weights,training_run,evaluation)
            elif weights and self.mode!="dry-run":
                raise ValueError('Candidate weights allow dry-run preview or evaluated movement-only; clicks require a promoted model.')
            else:detector=make_detector(profile,registry,weights=weights,candidate=weights is not None)
            collector=None
            if collect:
                from .improvement import ExampleCollector
                collector=ExampleCollector(collect,profile,getattr(detector,'artifact_sha256',None))
            session=TaskSession(profile,detector,queue=collector)
            api=WindowsMouse();transforms=Transforms();mouse=None;deadline=None
            with mss() as capture:
                sequence=0
                while not self.stop_event.is_set():
                    identity,client,foreground=query_window(hwnd)
                    if not profile.allows(identity):raise ValueError('Window is outside profile allowlist')
                    capture_rect=Rect(*region) if region is not None else client
                    if not client.encloses(capture_rect):raise ValueError('Saved fishing area is outside the game. Pick the area again after moving/resizing the window.')
                    geometry=api.geometry(hwnd)
                    if transforms.active is None or transforms.active.window!=geometry:
                        transforms.invalidate('window_changed');self.arm_event.clear();mouse=None;deadline=None
                        transforms.bind(geometry,Rect((capture_rect.left-client.left)*96/geometry.dpi,(capture_rect.top-client.top)*96/geometry.dpi,capture_rect.width*96/geometry.dpi,capture_rect.height*96/geometry.dpi),Letterbox.fit(int(capture_rect.width),int(capture_rect.height),int(capture_rect.width),int(capture_rect.height)))
                    if self.arm_event.is_set():
                        self.arm_event.clear();self.action_result='';deadline=time.monotonic()+3
                    if foreground!=hwnd:
                        mouse=None
                        if deadline is not None and time.monotonic()>=deadline:deadline=None
                        self.publish(None,'Arming: focus target window' if deadline is not None else 'Paused: target window is not foreground');self.stop_event.wait(.1);continue
                    captured=time.monotonic()
                    image=np.array(capture.grab(dict(left=int(capture_rect.left),top=int(capture_rect.top),width=int(capture_rect.width),height=int(capture_rect.height))))[:,:,:3].copy()
                    frame=Frame(sequence,captured,image,Box(int(capture_rect.left),int(capture_rect.top),image.shape[1],image.shape[0]),'bgr');sequence+=1
                    target=session.preview(frame,identity,transforms.active,time.monotonic())
                    reason=session.reason
                    if self.teaching:
                        request=self.teacher.consider(frame,reason,time.monotonic())
                        if request:
                            self.arm_event.clear();mouse=None;deadline=None
                            self.publish(frame.pixels,'Teaching paused: draw a box on the missed bobber, then save and continue.')
                            while not request.done.is_set() and not self.stop_event.wait(.1):pass
                            continue  # Discard old targets; reacquire on a new frame after the human finishes.
                    display=preview_image(image,target,capture_rect.left,capture_rect.top)
                    if self.arm_event.is_set():
                        self.arm_event.clear();deadline=time.monotonic()+3;reason='Arming in 3 seconds; focus target and release input'
                    if deadline is not None:
                        reason=f'Arming: {max(0,deadline-time.monotonic()):.1f}s'
                        if time.monotonic()>=deadline:
                            deadline=None;mouse=GuardedMouse(api,transforms,mode=self.mode,cancelled=self.stop_event,max_age=profile.data['max_frame_age'])
                            if not mouse.arm():reason=mouse.reason;mouse=None
                    if mouse is not None:
                        if target:
                            ok=session.execute(mouse,target,'move',identity,time.monotonic())
                            if ok and self.mode=='single-click':ok=session.execute(mouse,target,'click',identity,time.monotonic())
                            reason=mouse.reason if ok else 'Action rejected: '+mouse.reason+'; profile/model/outcome policy also applies'
                            if ok:
                                from .cursor_feedback import cursor_identity
                                try:
                                    handle,observed_hwnd=cursor_identity()
                                    reason+=f'; observed cursor handle={handle} (gear identity requires calibration)'
                                except (OSError,ValueError,RuntimeError):pass
                            if ok and self.mode=='single-click':reason+='; catch/outcome UNCONFIRMED'
                        else:reason='Arming consumed: '+session.reason
                        self.action_result=reason
                        mouse=None  # Every arm permits one attempt, never a continuous click loop.
                    if collector:
                        collector.add(profile,frame,'periodic_sample')
                        reason+=f' | Review pictures saved: {collector.count}/360'
                    if self.action_result:reason+=' | Last attempt: '+self.action_result
                    self.publish(display,reason);self.stop_event.wait(.1)
        except Exception as exc:
            from .errors import record_error
            event,path=record_error('preview_failed',exc,{'hwnd':hwnd,'mode':self.mode,'weights':str(weights),'profile':profile.digest})
            self.publish(None,f'{type(exc).__name__}: {exc} | Error {event}; Open error history.')
        finally:self.arm_event.clear();self.stop_event.set()
