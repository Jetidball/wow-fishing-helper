"""Read-only window identity/geometry for allowlisting recordings. No mouse APIs."""
import os
import ctypes as c
from ctypes import wintypes as w
from .profiles import WindowIdentity
from .geometry import Rect


def query_window(hwnd):
    if os.name!="nt":raise RuntimeError("window recording is Windows-only")
    user=c.WinDLL("user32",use_last_error=True);kernel=c.WinDLL("kernel32",use_last_error=True)
    specs={"GetWindowTextLengthW":([w.HWND],c.c_int),"GetWindowTextW":([w.HWND,w.LPWSTR,c.c_int],c.c_int),
        "GetWindowThreadProcessId":([w.HWND,c.POINTER(w.DWORD)],w.DWORD),"GetClientRect":([w.HWND,c.POINTER(w.RECT)],w.BOOL),
        "ClientToScreen":([w.HWND,c.POINTER(w.POINT)],w.BOOL),"GetForegroundWindow":([],w.HWND),
        "IsWindowVisible":([w.HWND],w.BOOL),"IsIconic":([w.HWND],w.BOOL),
        "SetThreadDpiAwarenessContext":([c.c_void_p],c.c_void_p)}
    for name,(args,result) in specs.items():getattr(user,name).argtypes=args;getattr(user,name).restype=result
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)];kernel.QueryFullProcessImageNameW.restype=w.BOOL
    kernel.CloseHandle.argtypes=[w.HANDLE];kernel.CloseHandle.restype=w.BOOL
    if not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):raise ValueError("window hidden/minimized")
    title=c.create_unicode_buffer(user.GetWindowTextLengthW(hwnd)+1);user.GetWindowTextW(hwnd,title,len(title))
    pid=w.DWORD();user.GetWindowThreadProcessId(hwnd,c.byref(pid))
    handle=kernel.OpenProcess(0x1000,False,pid.value)
    if not handle:raise c.WinError(c.get_last_error())
    try:
        length=w.DWORD(32768);executable=c.create_unicode_buffer(length.value)
        if not kernel.QueryFullProcessImageNameW(handle,0,executable,c.byref(length)):raise c.WinError(c.get_last_error())
    finally:kernel.CloseHandle(handle)
    prior=user.SetThreadDpiAwarenessContext(c.c_void_p(-4))
    if not prior:raise OSError("DPI context unavailable")
    try:
        rect=w.RECT();point=w.POINT()
        if not user.GetClientRect(hwnd,c.byref(rect)) or not user.ClientToScreen(hwnd,c.byref(point)):raise c.WinError(c.get_last_error())
        client=Rect(point.x,point.y,rect.right,rect.bottom)
    finally:user.SetThreadDpiAwarenessContext(prior)
    return WindowIdentity(int(hwnd),title.value,executable.value),client,int(user.GetForegroundWindow() or 0)


def allowed_windows(profile):
    if os.name!="nt":raise RuntimeError("window listing is Windows-only")
    user=c.WinDLL("user32",use_last_error=True);callback_type=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.EnumWindows.argtypes=[callback_type,w.LPARAM];user.EnumWindows.restype=w.BOOL
    rows=[]
    def visit(hwnd,param):
        try:
            identity,client,foreground=query_window(int(hwnd))
            if profile.allows(identity):rows.append({"window":vars(identity),"client":vars(client),"foreground":foreground==identity.hwnd})
        except (OSError,ValueError):pass
        return True
    callback=callback_type(visit)
    if not user.EnumWindows(callback,0):raise c.WinError(c.get_last_error())
    return rows
