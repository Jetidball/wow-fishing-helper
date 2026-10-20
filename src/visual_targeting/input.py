"""The only module allowed to send mouse/keyboard input to the desktop."""
import os
import time
from collections import deque
from threading import Event, RLock
from .contracts import Action, Point

class Cancelled(Exception):
    pass

class DryRunInput:
    def __init__(self, capacity=256, cancelled=None, clock=time.monotonic):
        if capacity < 1:
            raise ValueError("history must be bounded and positive")
        self.actions = deque(maxlen=capacity)
        self.cancelled = cancelled if cancelled is not None else Event()
        self.clock = clock
        self._lock = RLock()
        self._position = (0, 0)

    def execute(self, action: Action) -> bool:
        with self._lock:
            if self.cancelled.is_set() and action.kind != "release_all":
                return False
            if action.captured_at is not None and self.clock() - action.captured_at > 1.0:
                return False
            self.actions.append(action)
            if action.point:
                self._position = (action.point.x, action.point.y)
            return True

    def release_all(self):
        self.execute(Action("release_all", self.clock()))

    def position(self):
        return self._position

    def size(self):
        return (1920, 1080)

class WindowsInput(DryRunInput):
    def __init__(self, **kwargs):
        if os.name != "nt":
            raise RuntimeError("Windows input is available only on Windows")
        super().__init__(**kwargs)
        import pyautogui
        self.desktop = pyautogui
        self.held = set()

    def execute(self, action):
        with self._lock:
            if not super().execute(action):
                return False
            d, a = self.desktop, action
            try:
                if a.kind == "move":
                    d.moveTo(a.point.x, a.point.y, duration=a.duration, tween=d.easeInOutQuad)
                elif a.kind == "click":
                    d.click(button=a.button)
                elif a.kind == "press":
                    d.press(list(a.keys))
                elif a.kind == "hotkey":
                    d.hotkey(*a.keys)
                elif a.kind == "text":
                    d.typewrite(a.keys[0], interval=a.interval)
                elif a.kind == "scroll":
                    d.scroll(a.amount)
                elif a.kind == "key_down":
                    self.held.update(a.keys)
                    for key in a.keys:
                        d.keyDown(key)
                elif a.kind == "key_up":
                    for key in a.keys:
                        d.keyUp(key)
                        self.held.discard(key)
                elif a.kind == "release_all":
                    self._release()
                return True
            except BaseException:
                self._release()
                raise

    def _release(self):
        # Cleanup must work even if the cursor is at the failsafe corner.
        prior = self.desktop.FAILSAFE
        self.desktop.FAILSAFE = False
        try:
            for key in tuple(self.held):
                self.desktop.keyUp(key)
                self.held.discard(key)
        finally:
            self.desktop.FAILSAFE = prior

    def position(self):
        return self.desktop.position()

    def size(self):
        return self.desktop.size()

class DesktopFacade:
    """Compatibility bridge for GUI/setup and the existing humanized movement policy."""
    easeInOutQuad = None
    def __init__(self):
        self._adapter = None
        self.cancelled = Event()

    @property
    def adapter(self):
        if self._adapter is None:
            cls = WindowsInput if os.environ.get("FISHING_LIVE_INPUT") == "1" and os.environ.get("FISHING_DRY_RUN") != "1" else DryRunInput
            self._adapter = cls(cancelled=self.cancelled)
        return self._adapter

    def configure(self, adapter):
        if self._adapter is not None:
            self._adapter.release_all()
        self._adapter = adapter
        self.cancelled = adapter.cancelled

    def send(self, kind, **kwargs):
        if not self.adapter.execute(Action(kind, time.monotonic(), **kwargs)):
            raise Cancelled()

    def moveTo(self, x, y, duration=0, tween=None):
        self.send("move", point=Point(int(x), int(y)), duration=duration)
    def click(self): self.send("click")
    def rightClick(self): self.send("click", button="right")
    def press(self, key): self.send("press", keys=(key,))
    def keyDown(self, key): self.send("key_down", keys=(key,))
    def keyUp(self, key): self.send("key_up", keys=(key,))
    def hotkey(self, *keys): self.send("hotkey", keys=keys)
    def typewrite(self, text, interval=0): self.send("text", keys=(text,), interval=interval)
    def scroll(self, amount): self.send("scroll", amount=amount)
    def position(self): return self.adapter.position()
    def size(self): return self.adapter.size()
    def release_all(self):
        if self._adapter is not None:
            self._adapter.release_all()
    def cancel(self):
        self.cancelled.set()
        self.release_all()
    def sleep(self, seconds):
        if self.cancelled.wait(max(0, seconds)):
            raise Cancelled()

desktop = DesktopFacade()
