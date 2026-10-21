"""Human corrections during inference. No desktop input and no automatic promotion."""
import copy,json,queue,threading,time
from dataclasses import dataclass,field,replace
from pathlib import Path
from . import dataset as ds
from .improvement import ExampleCollector

@dataclass
class CorrectionRequest:
    frame:object
    done:threading.Event=field(default_factory=threading.Event)

class MissTeacher:
    def __init__(self,delay=2):
        self.delay=delay;self.since=None;self.requests=queue.Queue(maxsize=1);self.pending=None
    def consider(self,frame,reason,now):
        if reason!='missing_or_ambiguous':self.since=None;return None
        if self.since is None:self.since=now;return None
        if self.pending or now-self.since<self.delay:return None
        request=CorrectionRequest(replace(frame,pixels=frame.pixels.copy()))
        self.pending=request;self.requests.put_nowait(request);return request
    def complete(self,request):
        request.done.set()
        if self.pending is request:self.pending=None
        self.since=None
    def stop(self):
        if self.pending:self.complete(self.pending)
        while True:
            try:self.requests.get_nowait()
            except queue.Empty:break

class CorrectionStore:
    def __init__(self,profile,model_sha,root='data/improvement-examples'):
        self.profile=profile;self.root=Path(root);self.count=0
        self.collector=ExampleCollector(root,profile,model_sha,max_frames=10000,interval=0,max_seconds=86400)
    def save(self,frame,boxes,reviewer):
        ds.boxes_valid(boxes,frame.bounds.width,frame.bounds.height,self.profile.data['allowed_classes'])
        if not reviewer.strip():raise ValueError('A human reviewer name is required')
        # Do not permit a negative that silently substitutes for an unknown/missing box.
        saved=self.collector.add(self.profile,frame,'human_missed_bobber_correction')
        if saved is None:raise ValueError('Teaching visit limit reached. Stop and start a new visit.')
        data=ds.load(self.root)
        row=next(r for r in data['frames'] if r['session_id']==self.collector.session and r['cast_id']=='observation_'+str(saved-1))
        from .review_store import ReviewStore
        ReviewStore(self.profile,self.root).save(row['id'],boxes,reviewer)
        self.count+=1
        return row['id']

def correction_dialog(parent,request,store,reviewer,on_done,train_now=None):
    """Only frozen pixels and human boxes. Never clicks the game or injects an old target."""
    import tkinter as tk
    from tkinter import ttk
    import cv2 as cv
    from .label_gui import annotation_box
    from .input_help import install_button_help,InputHint
    top=tk.Toplevel(parent);top.title('Teach the model: where is the missed bobber?')
    frame=request.frame;image=frame.pixels
    if frame.format=='gray':image=cv.cvtColor(image,cv.COLOR_GRAY2BGR)
    elif frame.format=='bgra':image=cv.cvtColor(image,cv.COLOR_BGRA2BGR)
    h,w=image.shape[:2];scale=min(1,(top.winfo_screenwidth()-100)/w,(top.winfo_screenheight()-280)/h)
    shown=cv.cvtColor(cv.resize(image,(max(1,round(w*scale)),max(1,round(h*scale)))),cv.COLOR_BGR2RGB)
    photo=tk.PhotoImage(data=f'P6\n{shown.shape[1]} {shown.shape[0]}\n255\n'.encode()+shown.tobytes(),format='PPM')
    ttk.Label(top,text='Detection is paused. Drag a tight box around EVERY visible bobber, then Save correction & continue.',wraplength=1000).pack()
    ttk.Label(top,text='This is a frozen picture. Your box teaches the model; it never triggers a game click. Include other players’ bobbers; exclude ripples and reflections.',wraplength=1000).pack()
    ttk.Label(top,text='After saving, focus WoW again. If mouse takeover paused fishing, press F9 to resume.',wraplength=1000).pack()
    chosen=tk.StringVar(value=store.profile.data['target_class'])
    classes=ttk.Combobox(top,textvariable=chosen,values=store.profile.data['allowed_classes'],state='readonly')
    classes.pack();InputHint(classes,'Class of the box you draw. Normally bobber; choose loot only for a visible loot object.')
    canvas=tk.Canvas(top,width=shown.shape[1],height=shown.shape[0],highlightthickness=0);canvas.pack();canvas.create_image(0,0,image=photo,anchor='nw');canvas.photo=photo
    boxes=[];start=[];message=tk.StringVar(value='Draw boxes. Enter saves; Backspace removes the last box; Esc skips this example.')
    ttk.Label(top,textvariable=message,wraplength=1000).pack()
    def redraw():
        canvas.delete('box')
        for b in boxes:canvas.create_rectangle(b['x']*scale,b['y']*scale,(b['x']+b['width'])*scale,(b['y']+b['height'])*scale,outline='#00ff88',width=2,tags='box')
        message.set(str(len(boxes))+' boxes. Nothing is saved until you press Save.')
    def begin(event):
        start[:]=[event.x,event.y];canvas.delete('drag');canvas.create_rectangle(event.x,event.y,event.x,event.y,outline='yellow',tags='drag')
    def drag(event):
        if start:canvas.coords('drag',*start,event.x,event.y)
    def end(event):
        try:
            if start:boxes.append(annotation_box(start,(event.x,event.y),scale,w,h,store.profile.data['allowed_classes'].index(chosen.get())))
            start.clear();canvas.delete('drag');redraw()
        except ValueError as exc:message.set(str(exc))
    closed=False
    def finish(decision):
        nonlocal closed
        if closed:return
        try:
            if decision=='save':
                if not boxes:raise ValueError('Draw a box first, or explicitly choose No bobber here.')
                store.save(frame,boxes,reviewer)
            elif decision=='negative':store.save(frame,[],reviewer)
        except (OSError,ValueError,KeyError) as exc:message.set('Could not save: '+str(exc));return
        closed=True;top.destroy();on_done(decision)
    def undo():
        if boxes:boxes.pop()
        redraw()
    def train():
        try:train_now();message.set('Background training requested. Save this correction before it can be included in the next run.')
        except Exception as exc:message.set('Training: '+str(exc))
    canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',end)
    actions=[('Save correction & continue',lambda:finish('save')),('No bobber here & continue',lambda:finish('negative')),('Undo box',undo),('Skip & continue',lambda:finish('skip')),('Stop teaching',lambda:finish('stop'))]
    if train_now:actions.append(('Train now in background',train))
    buttons=ttk.Frame(top);buttons.pack()
    for i,(text,fn) in enumerate(actions):ttk.Button(buttons,text=text,command=fn).grid(row=i//3,column=i%3,padx=5,pady=5)
    top.bind('<KeyRelease-Return>',lambda e:finish('save'));top.bind('<KeyRelease-BackSpace>',lambda e:undo());top.bind('<Escape>',lambda e:finish('skip'))
    top.protocol('WM_DELETE_WINDOW',lambda:finish('skip'))
    install_button_help(top);top.lift();top.focus_force()
    return top
