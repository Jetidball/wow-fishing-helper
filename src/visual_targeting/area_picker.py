"""Frozen desktop area selection for legacy settings; never sends game input."""
import base64
import tkinter as tk
from tkinter import ttk
from .template_setup import crop_box

def desktop_points(start,end,scale,width,height,left,top,polygon=False):
    x1,y1,x2,y2=crop_box(start,end,scale,width,height)
    corners=[(left+x1,top+y1),(left+x2,top+y2)]
    if polygon:
        return [corners[0],(left+x2,top+y1),corners[1],(left+x1,top+y2)]
    return corners

def desktop_location(position,scale,width,height,left,top):
    import math
    if not math.isfinite(scale) or scale<=0:raise ValueError('Invalid display scale')
    x,y=position
    if not (0<=x<width*scale and 0<=y<height*scale):raise ValueError('Click inside the screenshot')
    return (left+min(width-1,round(x/scale)),top+min(height-1,round(y/scale)))

def pick_desktop_area(parent,label,on_done,polygon=False,point=False):
    """Call after settings is minimized; cancellation returns None."""
    import cv2 as cv
    import numpy as np
    from mss import mss
    with mss() as capture:
        monitor=dict(capture.monitors[0])
        image=np.array(capture.grab(monitor))[:,:,:3].copy()
    parent.deiconify()
    top=tk.Toplevel(parent);top.title('Select '+label)
    ttk.Label(top,text=('Click the location on this frozen screenshot, then Use this location.' if point else 'Drag a rectangle on this frozen screenshot. Click Use this area when ready.')).pack()
    h,w=image.shape[:2]
    scale=min(1,(parent.winfo_screenwidth()-100)/w,(parent.winfo_screenheight()-230)/h)
    shown=cv.resize(image,(max(1,round(w*scale)),max(1,round(h*scale))))
    _,png=cv.imencode('.png',shown)
    photo=tk.PhotoImage(data=base64.b64encode(png.tobytes()))
    canvas=tk.Canvas(top,width=shown.shape[1],height=shown.shape[0],highlightthickness=0)
    canvas.pack();canvas.create_image(0,0,anchor='nw',image=photo);canvas.photo=photo
    state={};message=tk.StringVar(value='Click once; no timed hovering is needed.' if point else 'Draw one rectangle; no timed points are needed.')
    ttk.Label(top,textvariable=message).pack()
    def begin(event):
        state['start']=(event.x,event.y);state['end']=state['start']
        if 'rectangle' in state:canvas.delete(state['rectangle'])
        if point:
            state['rectangle']=canvas.create_oval(event.x-5,event.y-5,event.x+5,event.y+5,outline='#00ff88',width=2)
        else:
            state['rectangle']=canvas.create_rectangle(event.x,event.y,event.x,event.y,outline='#00ff88',width=2)
    def drag(event):
        if 'start' not in state or point:return
        state['end']=(event.x,event.y)
        canvas.coords(state['rectangle'],*state['start'],*state['end'])
    def finish(value):
        top.destroy();on_done(value)
    def save():
        try:
            if 'start' not in state:raise ValueError('Click a location on the picture first.' if point else 'Drag a rectangle on the picture first.')
            value=(desktop_location(state['start'],scale,w,h,monitor['left'],monitor['top']) if point else
                   desktop_points(state['start'],state['end'],scale,w,h,monitor['left'],monitor['top'],polygon))
            finish(value)
        except ValueError as exc:message.set(str(exc))
    canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',drag)
    buttons=ttk.Frame(top);buttons.pack()
    ttk.Button(buttons,text='Use this location' if point else 'Use this area',command=save).pack(side='left',padx=10,pady=8)
    ttk.Button(buttons,text='Cancel',command=lambda:finish(None)).pack(side='left')
    top.protocol('WM_DELETE_WINDOW',lambda:finish(None))
    top.bind('<Escape>',lambda event:finish(None))
    top.lift();top.focus_set()
    return top


def request_desktop_area(label, polygon=False, cancelled=None, point=False):
    """Synchronous startup picker, called on the program's main thread."""
    root=tk.Tk();root.withdraw()
    result=[None]
    def done(value):
        result[0]=value
        root.quit()
    try:
        pick_desktop_area(root,label,done,polygon,point=point)
        root.withdraw()
        def poll_cancel():
            if cancelled is not None and cancelled.is_set():
                root.quit()
            else:
                root.after(100,poll_cancel)
        root.after(100,poll_cancel)
        root.mainloop()
    finally:
        root.destroy()
    return result[0]
