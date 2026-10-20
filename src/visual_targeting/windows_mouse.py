"""Standard Win32 user-mode mouse IO. No custom driver, focus changes or fishing imports."""
import os
import ctypes as c
from ctypes import wintypes as w
from contextlib import contextmanager
from .geometry import Rect,WindowGeometry

class MOUSEINPUT(c.Structure):
    _fields_=[("dx",w.LONG),("dy",w.LONG),("mouseData",w.DWORD),("dwFlags",w.DWORD),("time",w.DWORD),("dwExtraInfo",c.c_size_t)]
class KEYBDINPUT(c.Structure):
    _fields_=[("wVk",w.WORD),("wScan",w.WORD),("dwFlags",w.DWORD),("time",w.DWORD),("dwExtraInfo",c.c_size_t)]
class HARDWAREINPUT(c.Structure):
    _fields_=[("uMsg",w.DWORD),("wParamL",w.WORD),("wParamH",w.WORD)]
class INPUTUNION(c.Union):_fields_=[("mi",MOUSEINPUT),("ki",KEYBDINPUT),("hi",HARDWAREINPUT)]
class INPUT(c.Structure):_fields_=[("type",w.DWORD),("u",INPUTUNION)]
class LASTINPUTINFO(c.Structure):_fields_=[("cbSize",w.UINT),("dwTime",w.DWORD)]
class MONITORINFO(c.Structure):_fields_=[("cbSize",w.DWORD),("rcMonitor",w.RECT),("rcWork",w.RECT),("dwFlags",w.DWORD)]

class WindowsMouse:
    def __init__(self):
        if os.name!="nt":raise RuntimeError("Windows only")
        self.user=c.WinDLL("user32",use_last_error=True)
        specs={
          "SetThreadDpiAwarenessContext":([c.c_void_p],c.c_void_p),
          "GetForegroundWindow":([],w.HWND),"GetAncestor":([w.HWND,w.UINT],w.HWND),
          "GetClientRect":([w.HWND,c.POINTER(w.RECT)],w.BOOL),
          "ClientToScreen":([w.HWND,c.POINTER(w.POINT)],w.BOOL),
          "IsWindowVisible":([w.HWND],w.BOOL),"IsIconic":([w.HWND],w.BOOL),
          "GetDpiForWindow":([w.HWND],w.UINT),
          "MonitorFromWindow":([w.HWND,w.DWORD],w.HANDLE),
          "GetMonitorInfoW":([w.HANDLE,c.POINTER(MONITORINFO)],w.BOOL),
          "GetSystemMetrics":([c.c_int],c.c_int),
          "GetCursorPos":([c.POINTER(w.POINT)],w.BOOL),
          "SetCursorPos":([c.c_int,c.c_int],w.BOOL),
          "GetLastInputInfo":([c.POINTER(LASTINPUTINFO)],w.BOOL),
          "WindowFromPoint":([w.POINT],w.HWND),"GetAsyncKeyState":([c.c_int],c.c_short),
          "SendInput":([w.UINT,c.POINTER(INPUT),c.c_int],w.UINT)}
        for name,(args,result) in specs.items():
            fn=getattr(self.user,name);fn.argtypes=args;fn.restype=result
        self.revision=0
    @contextmanager
    def dpi_scope(self):
        prior=self.user.SetThreadDpiAwarenessContext(c.c_void_p(-4))  # PER_MONITOR_AWARE_V2
        if not prior:raise OSError("cannot establish per-monitor DPI context")
        try:yield
        finally:self.user.SetThreadDpiAwarenessContext(prior)
    def root(self,hwnd):return int(self.user.GetAncestor(hwnd,2) or hwnd)
    def foreground(self):return int(self.user.GetForegroundWindow() or 0)
    def geometry(self,hwnd):
        with self.dpi_scope():
            if not self.user.IsWindowVisible(hwnd) or self.user.IsIconic(hwnd):raise ValueError("window hidden/minimized/destroyed")
            rect=w.RECT();origin=w.POINT(0,0)
            if not self.user.GetClientRect(hwnd,c.byref(rect)) or not self.user.ClientToScreen(hwnd,c.byref(origin)):raise c.WinError(c.get_last_error())
            monitor=self.user.MonitorFromWindow(hwnd,2);info=MONITORINFO();info.cbSize=c.sizeof(info)
            if not self.user.GetMonitorInfoW(monitor,c.byref(info)):raise c.WinError(c.get_last_error())
            r=info.rcMonitor
            desktop=Rect(*(self.user.GetSystemMetrics(i) for i in (76,77,78,79)))
            return WindowGeometry(int(hwnd),Rect(origin.x,origin.y,rect.right-rect.left,rect.bottom-rect.top),int(self.user.GetDpiForWindow(hwnd)),Rect(r.left,r.top,r.right-r.left,r.bottom-r.top),desktop,self.revision)
    def cursor(self):
        with self.dpi_scope():
            p=w.POINT()
            if not self.user.GetCursorPos(c.byref(p)):raise c.WinError(c.get_last_error())
            return p.x,p.y
    def last_input(self):
        info=LASTINPUTINFO();info.cbSize=c.sizeof(info)
        if not self.user.GetLastInputInfo(c.byref(info)):raise c.WinError(c.get_last_error())
        return int(info.dwTime)
    def buttons_down(self):return any(self.user.GetAsyncKeyState(k)&0x8000 for k in (1,2,4,5,6))
    def window_at(self,x,y):
        with self.dpi_scope():return self.root(self.user.WindowFromPoint(w.POINT(x,y)))
    def move(self,x,y):
        with self.dpi_scope():
            if not self.user.SetCursorPos(x,y):raise c.WinError(c.get_last_error())
    def click(self,button="left"):
        if button not in ("left","right"):raise ValueError("unsupported mouse button")
        def event(flags):return INPUT(0,INPUTUNION(mi=MOUSEINPUT(0,0,0,flags,0,0)))
        down,up_flag=(2,4) if button=="left" else (8,16)
        pair=(INPUT*2)(event(down),event(up_flag))  # one complete click pair
        sent=self.user.SendInput(2,pair,c.sizeof(INPUT))
        if sent!=2:
            # Release a partially delivered press; never resend the down event.
            up=(INPUT*1)(event(up_flag));self.user.SendInput(1,up,c.sizeof(INPUT))
            raise OSError("SendInput did not deliver the complete click pair")
