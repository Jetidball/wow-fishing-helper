"""One cast's foreground/geometry/freshness-guarded right-click and hover movement."""
from visual_targeting.windows_mouse import WindowsMouse
from visual_targeting.guarded_mouse import GuardedMouse
from visual_targeting.geometry import Rect,Letterbox,Transforms
from visual_targeting.window_context import query_window
from visual_targeting.cursor_feedback import gear_matches

class RightMouse(WindowsMouse):
    def click(self):return super().click(button='right')

class FishingDispatch:
    def __init__(self,settings,cancelled,profile,*,api=None,probe=query_window,button="right"):
        self.settings=settings;self.button=button;self.api=api or (WindowsMouse() if button=="left" else RightMouse())
        hwnd=self.api.foreground()
        identity,client,_=probe(hwnd)
        if not profile.allows(identity):raise ValueError('Fishing game is not foreground or not allowed by the selected profile')
        self.geometry=self.api.geometry(hwnd)
        monitor=settings.get_monitor();roi=Rect(monitor['left'],monitor['top'],monitor['width'],monitor['height'])
        if not self.geometry.client.encloses(roi):raise ValueError('Fishing area is outside the game. Pick it again after moving/resizing the window.')
        dpi=self.geometry.dpi
        crop=Rect((roi.left-self.geometry.client.left)*96/dpi,(roi.top-self.geometry.client.top)*96/dpi,roi.width*96/dpi,roi.height*96/dpi)
        self.transforms=Transforms()
        self.transforms.bind(self.geometry,crop,Letterbox.fit(int(roi.width),int(roi.height),int(roi.width),int(roi.height)))
        self.mouse=GuardedMouse(self.api,self.transforms,mode='single-click',cancelled=cancelled,max_age=profile.data['max_frame_age'])
        if not self.mouse.arm():raise ValueError(self.mouse.reason)
        self.reason='armed';self.roi=roi
    def move(self,frame,point):
        if (frame.bounds.left,frame.bounds.top,frame.bounds.width,frame.bounds.height)!=(self.roi.left,self.roi.top,self.roi.width,self.roi.height):
            self.reason='frame_crop_changed';return False
        target=self.transforms.active.target(point[0]-self.roi.left,point[1]-self.roi.top,frame.sequence,frame.captured_at,space='crop')
        accepted=self.mouse.execute(target,'move');self.reason=self.mouse.reason
        if accepted:
            from humanize import set_bot_pos
            set_bot_pos((target.x,target.y))
        return accepted
    def click(self,frame,point):
        if not self.move(frame,point):return False
        if self.button=="right" and self.settings.require_gear_cursor and not gear_matches(self.settings):
            self.reason='gear_not_confirmed';return False
        target=self.transforms.active.target(point[0]-self.roi.left,point[1]-self.roi.top,frame.sequence,frame.captured_at,space='crop')
        accepted=self.mouse.execute(target,'click');self.reason=self.mouse.reason
        return accepted


def click_fishing_ability(settings,cancelled,profile):
    """Left-click the configured action-bar point with fresh foreground geometry."""
    import numpy as np,time
    from mss import mss
    from types import SimpleNamespace
    from visual_targeting.contracts import Frame,Box
    api=WindowsMouse()
    identity,client,_=query_window(api.foreground())
    if not profile.allows(identity):raise ValueError('WoW must be foreground before casting')
    roi=Rect(**settings.get_monitor())
    if not client.encloses(roi):raise ValueError('Fishing area no longer lies inside the game. Pick it again.')
    monitor=dict(left=int(client.left),top=int(client.top),width=int(client.width),height=int(client.height))
    captured=time.monotonic()
    with mss() as capture:image=np.array(capture.grab(monitor))
    frame=Frame(0,captured,image,Box(**monitor),'bgra')
    view=SimpleNamespace(get_monitor=lambda:monitor,require_gear_cursor=False)
    dispatch=FishingDispatch(view,cancelled,profile,api=api,button='left')
    if not dispatch.click(frame,settings.cast_location):raise ValueError('Cast rejected: '+dispatch.reason)
