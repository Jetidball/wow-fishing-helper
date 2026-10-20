"""Read-only Windows cursor identity. A calibrated shape is evidence, never a bite."""
import ctypes as c
from ctypes import wintypes as w
import os

class CURSORINFO(c.Structure):
    _fields_=[('cbSize',w.DWORD),('flags',w.DWORD),('hCursor',w.HANDLE),('ptScreenPos',w.POINT)]

def cursor_identity():
    if os.name!='nt':raise RuntimeError('Cursor calibration is Windows-only')
    user=c.WinDLL('user32',use_last_error=True)
    user.GetCursorInfo.argtypes=[c.POINTER(CURSORINFO)];user.GetCursorInfo.restype=w.BOOL
    user.GetForegroundWindow.argtypes=[];user.GetForegroundWindow.restype=w.HWND
    info=CURSORINFO();info.cbSize=c.sizeof(info)
    if not user.GetCursorInfo(c.byref(info)):raise c.WinError(c.get_last_error())
    if not info.flags&1 or not info.hCursor:raise ValueError('Windows cursor is hidden; hardware cursor calibration is unavailable')
    return int(info.hCursor),int(user.GetForegroundWindow() or 0)

def gear_matches(settings,read=cursor_identity):
    if not getattr(settings,'gear_cursor_handle',0) or not getattr(settings,'normal_cursor_handle',0):return False
    try:
        handle,hwnd=read()
        return bool(settings.gear_cursor_handle and settings.normal_cursor_handle and
                    settings.gear_cursor_handle!=settings.normal_cursor_handle and
                    handle==settings.gear_cursor_handle and hwnd==settings.gear_window_hwnd)
    except (OSError,ValueError,RuntimeError):return False
