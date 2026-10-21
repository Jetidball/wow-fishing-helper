"""Read-only screenshot acquisition and manual template cropping; no input adapter."""
import math
from pathlib import Path
import time
import uuid

def crop_box(start, end, scale, width, height):
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError('Invalid display scale')
    x1,x2=sorted((round(start[0]/scale),round(end[0]/scale)))
    y1,y2=sorted((round(start[1]/scale),round(end[1]/scale)))
    x1,x2=max(0,min(width,x1)),max(0,min(width,x2))
    y1,y2=max(0,min(height,y1)),max(0,min(height,y2))
    if x2-x1 < 4 or y2-y1 < 4:
        raise ValueError('Draw a larger box around the bobber (at least 4 by 4 pixels)')
    return x1,y1,x2,y2

def save_template(image, box, directory):
    import cv2 as cv
    x1,y1,x2,y2=box
    if not (0 <= x1 < x2 <= image.shape[1] and 0 <= y1 < y2 <= image.shape[0]):
        raise ValueError('Crop is outside the screenshot')
    crop=image[y1:y2,x1:x2]
    edge=cv.Canny(cv.cvtColor(crop,cv.COLOR_BGR2GRAY),100,200)
    if not edge.size or edge.max()==edge.min():
        raise ValueError('This crop has no usable edges. Select the bobber more closely.')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/('bobber-'+uuid.uuid4().hex+'.png')
    # Unicode-safe on Windows, and exclusive create prevents overwriting templates.
    ok,encoded=cv.imencode('.png',crop)
    if not ok:raise ValueError('Could not encode template')
    with path.open('xb') as stream:stream.write(encoded.tobytes())
    return path

def capture_window(profile, hwnd):
    import numpy as np
    from mss import mss
    from .window_context import query_window
    before,rect,foreground=query_window(hwnd)
    if not profile.allows(before):raise ValueError('Selected window is not allowed by this profile')
    if foreground!=hwnd:raise ValueError('Game was not in front. Try again, or open a saved screenshot.')
    with mss() as capture:
        image=np.array(capture.grab(dict(left=int(rect.left),top=int(rect.top),width=int(rect.width),height=int(rect.height))))[:,:,:3].copy()
    after,new_rect,foreground=query_window(hwnd)
    if after!=before or new_rect!=rect or foreground!=hwnd:
        raise ValueError('Window changed during capture. Try again.')
    return image

def open_crop_dialog(parent, image, directory, on_saved):
    import base64
    import cv2 as cv
    import tkinter as tk
    from tkinter import ttk
    top=tk.Toplevel(parent);top.title('Select bobber on frozen screenshot')
    ttk.Label(top,text='Drag a tight box around YOUR bobber. Take your time; the picture is frozen.').pack()
    h,w=image.shape[:2]
    scale=min(1, (top.winfo_screenwidth()-100)/w,(top.winfo_screenheight()-230)/h)
    displayed=cv.resize(image,(max(1,round(w*scale)),max(1,round(h*scale))))
    _,png=cv.imencode('.png',displayed)
    photo=tk.PhotoImage(data=base64.b64encode(png.tobytes()))
    canvas=tk.Canvas(top,width=displayed.shape[1],height=displayed.shape[0],highlightthickness=0)
    canvas.pack();canvas.create_image(0,0,anchor='nw',image=photo);canvas.photo=photo
    state={};message=tk.StringVar(value='No box selected yet')
    ttk.Label(top,textvariable=message).pack()
    def begin(event):
        state['start']=(event.x,event.y);state['end']=(event.x,event.y)
        if 'rect' in state:canvas.delete(state['rect'])
        state['rect']=canvas.create_rectangle(event.x,event.y,event.x,event.y,outline='#00ff88',width=2)
    def drag(event):
        if 'start' not in state:return
        state['end']=(event.x,event.y)
        canvas.coords(state['rect'],*state['start'],*state['end'])
        message.set('Click Save bobber template, or draw a different box.')
    canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',drag)
    def save():
        try:
            if 'start' not in state:raise ValueError('Draw a box around the bobber first')
            box=crop_box(state['start'],state['end'],scale,w,h)
            path=save_template(image,box,directory)
            on_saved(path);top.destroy()
        except Exception as exc:message.set(str(exc))
    buttons=ttk.Frame(top);buttons.pack()
    ttk.Button(buttons,text='Save bobber template',command=save).pack(side='left',padx=8,pady=8)
    ttk.Button(buttons,text='Cancel',command=top.destroy).pack(side='left')
    top.bind('<Escape>',lambda event:top.destroy())
    from .input_help import install_button_help
    install_button_help(top)
    return top
