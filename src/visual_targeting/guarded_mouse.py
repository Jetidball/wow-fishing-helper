"""Guarded mouse protocol. Default dry-run; no fishing integration or desktop imports."""
import math
import time
from threading import Event,RLock

class GuardedMouse:
    def __init__(self,api,transforms,*,mode="dry-run",cancelled=None,clock=time.monotonic,max_age=.5,takeover_pixels=2):
        if mode not in ("dry-run","move","single-click"):raise ValueError("invalid mode")
        if not math.isfinite(max_age) or max_age<=0 or not math.isfinite(takeover_pixels) or takeover_pixels<0:raise ValueError("invalid limits")
        self.api=api;self.transforms=transforms;self.mode=mode
        self.cancelled=cancelled if cancelled is not None else Event();self.clock=clock
        self.max_age=max_age;self.takeover_pixels=takeover_pixels;self.armed=False
        self.expected=None;self.input_token=None;self.clicked=False;self.moved=None;self.reason="not_armed";self.lock=RLock()
    def arm(self):
        try:return self._arm()
        except (OSError,ValueError,RuntimeError) as exc:return self.reject("native_error: "+str(exc))
    def _arm(self):
        with self.lock:
            transform=self.transforms.active
            if self.cancelled.is_set() or transform is None:return self.reject("cancelled_or_unbound")
            current=self.api.geometry(transform.window.hwnd)
            if not self.transforms.valid(transform.identity,current):return self.reject("invalid_transform")
            if self.api.foreground()!=current.hwnd:return self.reject("not_foreground")
            if self.api.buttons_down():return self.reject("button_already_held")
            self.expected=self.api.cursor();self.input_token=self.api.last_input()
            self.armed=True;self.clicked=False;self.moved=None;self.reason="armed";return True
    def reject(self,reason):self.reason=reason;self.armed=False;return False
    def gate(self,target):
        if self.cancelled.is_set():return self.reject("cancelled")
        if not self.armed:return self.reject("not_armed")
        age=self.clock()-target.captured_at
        if not 0<=age<=self.max_age:return self.reject("stale_or_future_frame")
        transform=self.transforms.active
        if transform is None:return self.reject("invalid_transform")
        current=self.api.geometry(transform.window.hwnd)
        if not self.transforms.valid(target.transform_id,current):return self.reject("invalid_transform")
        if self.api.foreground()!=current.hwnd:return self.reject("not_foreground")
        if not all(rect.contains(target.x,target.y) for rect in (current.client,current.desktop,current.monitor,transform.desktop_crop)):return self.reject("out_of_bounds")
        if self.api.window_at(target.x,target.y)!=current.hwnd:return self.reject("occluded_or_other_window")
        if self.api.buttons_down():return self.reject("button_already_held")
        if math.dist(self.api.cursor(),self.expected)>self.takeover_pixels or self.api.last_input()!=self.input_token:
            self.cancelled.set();return self.reject("user_takeover")
        return True
    def execute(self,target,kind="move"):
        with self.lock:
            if kind not in ("move","click"):return self.reject("unsupported_action")
            try:
                if not self.gate(target):return False
                if kind=="click" and (self.mode!="single-click" or self.clicked or self.moved!=(target.x,target.y,target.transform_id) or math.dist(self.api.cursor(),(target.x,target.y))>2):return self.reject("click_not_armed_or_move_unverified")
                if self.mode=="dry-run":self.reason="dry_run";return True
                if kind=="move":
                    self.api.move(target.x,target.y)
                    actual=self.api.cursor()
                    if math.dist(actual,(target.x,target.y))>2:return self.reject("movement_mismatch")
                    self.expected=actual;self.input_token=self.api.last_input()
                    if not self.gate(target):return False
                    self.moved=(target.x,target.y,target.transform_id);self.reason="moved";return True
                # Consume the one-shot budget before attempting native injection: never retry.
                self.clicked=True
                self.api.click()
                self.expected=self.api.cursor();self.input_token=self.api.last_input()
                self.armed=False;self.reason="click_issued";return True
            except (OSError,ValueError,RuntimeError) as exc:
                self.reject("native_error: "+str(exc));return False
