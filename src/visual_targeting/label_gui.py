"""Human-only frame labeling. No detector, mouse adapter, capture or model imports."""
import base64
import copy
import tkinter as tk
from tkinter import ttk
from . import dataset as ds

def annotation_box(start,end,scale,width,height,class_id):
    import math
    if not math.isfinite(scale) or scale<=0:raise ValueError("Invalid display scale")
    # Unlike template crops, tiny objects can legitimately be smaller than 4 pixels.
    x1,x2=sorted((max(0,min(width,round(start[0]/scale))),max(0,min(width,round(end[0]/scale)))))
    y1,y2=sorted((max(0,min(height,round(start[1]/scale))),max(0,min(height,round(end[1]/scale)))))
    if x1==x2 or y1==y2:raise ValueError('Drag a box with positive width and height')
    return dict(class_id=class_id,space='frame_pixels',x=x1,y=y1,width=x2-x1,height=y2-y1)

def open_labeler(parent,profile,dataset,reviewer,on_change=None):
    import cv2 as cv
    from .review_store import ReviewStore
    if not reviewer.strip():raise ValueError('Enter your name as the reviewer')
    store=ReviewStore(profile,dataset);data=store.data
    rows=sorted(data['frames'],key=lambda r:(r['annotation']['reviewed'],r['session_id'],r['cast_id'],r['sequence']))
    if not rows:raise ValueError('Record some frames first')
    top=tk.Toplevel(parent);top.title('Label training pictures — human review')
    title=tk.StringVar();message=tk.StringVar();chosen=tk.StringVar(value=profile.data['target_class'])
    ttk.Label(top,textvariable=title,font=('Segoe UI',11,'bold')).pack()
    ttk.Label(top,text='Draw tight boxes around ALL visible bobbers, including other players. Skip uncertain pictures.').pack()
    ttk.Label(top,text='Exclude splash spray, ripples and fishing line. A negative means no object of ANY listed class is visible.').pack()
    ttk.Combobox(top,textvariable=chosen,values=data['classes'],state='readonly').pack(anchor='w')
    canvas=tk.Canvas(top,highlightthickness=0);canvas.pack()
    ttk.Label(top,textvariable=message,wraplength=900).pack()
    state={'index':0,'boxes':[]}
    def render():
        row=rows[state['index']]
        image=store.image(row['id'])
        if image is None:raise ValueError('Cannot read recorded frame')
        h,w=image.shape[:2];scale=min(1,(top.winfo_screenwidth()-100)/w,(top.winfo_screenheight()-260)/h)
        shown=cv.resize(image,(max(1,round(w*scale)),max(1,round(h*scale))))
        rgb=cv.cvtColor(shown,cv.COLOR_BGR2RGB)
        ppm=f'P6\n{rgb.shape[1]} {rgb.shape[0]}\n255\n'.encode()+rgb.tobytes()
        state.update(width=w,height=h,scale=scale)
        state['photo']=tk.PhotoImage(data=ppm,format='PPM')
        canvas.configure(width=shown.shape[1],height=shown.shape[0])
        canvas.delete('all');canvas.create_image(0,0,anchor='nw',image=state['photo'])
        state['boxes']=copy.deepcopy(row['annotation']['boxes'])
        title.set(f"Picture {state['index']+1}/{len(rows)} — session {row['session_id']} — {'reviewed' if row['annotation']['reviewed'] else 'not reviewed'}")
        redraw()
    def redraw():
        canvas.delete('box');scale=state['scale']
        for b in state['boxes']:
            x,y=b['x']*scale,b['y']*scale
            canvas.create_rectangle(x,y,x+b['width']*scale,y+b['height']*scale,outline='#00ff88',width=2,tags='box')
            canvas.create_text(x,y,anchor='sw',text=data['classes'][b['class_id']],fill='#00ff88',tags='box')
        message.set(f"{len(state['boxes'])} boxes. Nothing is saved until you click Save boxes or Explicit negative.")
    def begin(event):
        state['start']=(event.x,event.y);canvas.delete('drag')
        canvas.create_rectangle(event.x,event.y,event.x,event.y,outline='yellow',width=2,tags='drag')
    def drag(event):
        if 'start' in state:canvas.coords('drag',*state['start'],event.x,event.y)
    def end(event):
        try:
            if 'start' not in state:return
            box=annotation_box(state.pop('start'),(event.x,event.y),state['scale'],state['width'],state['height'],data['classes'].index(chosen.get()))
            state['boxes'].append(box);canvas.delete('drag');redraw()
        except ValueError as exc:message.set(str(exc))
    def advance(delta=1):
        state.pop('start',None)
        next_index=state['index']+delta
        if next_index>=len(rows):
            message.set('End of dataset. Close this window and record more independent sessions, or prepare the dataset.')
            return
        state['index']=max(0,next_index);render()
    def save(negative=False):
        try:
            if not negative and not state['boxes']:raise ValueError('Draw at least one box, or explicitly choose Negative if no listed object is visible.')
            boxes=[] if negative else state['boxes']
            row=rows[state['index']]
            store.save(row['id'],boxes,reviewer)
            row['annotation'].update(boxes=copy.deepcopy(boxes),reviewed=True,review_source='human',reviewer=reviewer)
            if on_change:on_change()
            advance()
        except (ValueError,OSError,KeyError) as exc:message.set(str(exc))
    def undo():
        if state['boxes']:state['boxes'].pop()
        redraw()
    canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',end)
    buttons=ttk.Frame(top);buttons.pack()
    for i,(text,fn) in enumerate([('Save boxes → next',save),('Explicit negative → next',lambda:save(True)),('Skip (unreviewed)',advance),('Previous',lambda:advance(-1)),('Undo box',undo),('Close',top.destroy)]):
        ttk.Button(buttons,text=text,command=fn).grid(row=i//3,column=i%3,padx=4,pady=5)
    top.bind('<KeyRelease-Return>',lambda event:save())
    top.bind('<KeyRelease-n>',lambda event:save(True))
    top.bind('<KeyRelease-space>',lambda event:advance())
    top.bind('<KeyRelease-BackSpace>',lambda event:undo())
    ttk.Label(top,text='Shortcuts: Enter = save, N = explicit negative, Space = skip, Backspace = undo.').pack()
    try:render()
    except Exception:
        top.destroy();raise
    top.lift();top.focus_set()
    return top
