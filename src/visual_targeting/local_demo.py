"""Second task in the local target application. All mouse actions are simulated."""
from pathlib import Path
import json
import hashlib
import sys
import cv2 as cv
import numpy as np
from .contracts import Box,Frame
from .geometry import Rect,WindowGeometry,Letterbox,Transforms
from .profiles import Profile,WindowIdentity,make_detector,TaskSession
from .guarded_mouse import GuardedMouse
from .dataset import atomic_json


def run_demo(profile,output,*,show=False,verify=True):
    output=Path(output)
    if output.exists():raise ValueError("fresh demo output required")
    if profile.task_id!="local_confirm" or profile.data["model"]["backend"]!="template":raise ValueError("local app demo expects its local_confirm template profile")
    image=np.full((400,600,3),(35,25,20),np.uint8)
    cv.circle(image,(120,100),18,(30,110,240),-1)
    cv.putText(image,"Distractor: float",(35,145),cv.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
    cv.rectangle(image,(400,219),(500,261),(230,115,30),-1)
    cv.rectangle(image,(400,219),(500,261),(255,255,255),1)
    cv.putText(image,"CONFIRM",(405,245),cv.FONT_HERSHEY_SIMPLEX,.52,(255,255,255),1)
    before=image.copy()
    # Author-defined scene geometry is synthetic ground truth, not self-labeled training data.
    template=cv.Canny(image[216:265,397:504],100,200)
    detector=make_detector(profile,templates=[template])
    window=WindowGeometry(1,Rect(-800,100,600,400),120,Rect(-1920,0,1920,1080),Rect(-1920,0,3840,1080))
    identity=WindowIdentity(1,"Fishing helper - local mouse verification only",sys.executable)
    registry=Transforms();transform=registry.bind(window,Rect(0,0,480,320),Letterbox.fit(600,400,640,640))
    frame=Frame(0,10,before,Box(-800,100,600,400),"bgr")
    task=TaskSession(profile,detector);target=task.preview(frame,identity,transform,10.1)
    if target is None:raise ValueError("demo profile abstained: "+task.reason)
    events=[]
    class LocalMouse:
        def __init__(self):self.point=(-790,110);self.token=0;self.clicks=0
        def geometry(self,hwnd):return window
        def foreground(self):return 1
        def window_at(self,x,y):return 1
        def buttons_down(self):return False
        def cursor(self):return self.point
        def last_input(self):return self.token
        def move(self,x,y):self.point=(x,y);self.token+=1
        def click(self):
            self.clicks+=1;self.token+=1
            x,y=self.point[0]+800,self.point[1]-100
            if 400<=x<=500 and 219<=y<=261:
                events.append("target_2_released")
                cv.rectangle(image,(400,219),(500,261),(60,170,50),-1)
                cv.putText(image,"DONE",(418,245),cv.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
    api=LocalMouse();mouse=GuardedMouse(api,registry,mode="single-click",max_age=profile.data["max_frame_age"],clock=lambda:10.1)
    moved=mouse.arm() and task.execute(mouse,target,"move",identity,10.1)
    accepted=moved and task.execute(mouse,target,"click",identity,10.2)
    outcome=task.check_outcome(identity,"local_event",events[-1] if events else "none",10.3,10.3)
    ax,ay=target.x+800,target.y-100
    cv.drawMarker(before,(ax,ay),(0,255,255),cv.MARKER_CROSS,11,1)
    report={"schema_version":1,"task_id":profile.task_id,"profile_version":profile.data["profile_version"],"profile_sha256":profile.digest,
        "detector_interface":"detect(Frame) -> Detection | None","mouse_interface":"GuardedMouse.execute(Target, kind)",
        "model_artifact_sha256":detector.artifact_sha256,"model_source":"author-defined synthetic app fixture, not a promoted model",
        "click_anchor":profile.data["click_anchor"],"desktop_point":[target.x,target.y],"crop_point":[ax,ay],
        "simulated_clicks":api.clicks,"outcome":outcome,"passed":moved and accepted and outcome=="confirmed" and api.clicks==1,
        "live_input_enabled":False,"mouse_backend":"local_simulated","registry_modified":False,"training_data_created":False,
        "source_sha256":{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ("local_demo.py","profiles.py","detector.py","guarded_mouse.py")}}
    output.mkdir(parents=True)
    cv.imwrite(str(output/"preview.png"),before);cv.imwrite(str(output/"outcome.png"),image)
    atomic_json(output/"report.json",report)
    if show:
        import tkinter as tk
        import base64
        root=tk.Tk();root.title(identity.title)
        tk.Label(root,text="Task profile: local_confirm v1 | preview and simulated outcome only | no desktop input").pack()
        for pixels in (before,image):
            png=cv.imencode(".png",pixels)[1].tobytes();photo=tk.PhotoImage(data=base64.b64encode(png))
            label=tk.Label(root,image=photo);label.image=photo;label.pack(side="left")
        root.bind("<Escape>",lambda _:root.destroy())
        if verify:root.after(2000,root.destroy)
        root.mainloop()
    return report
