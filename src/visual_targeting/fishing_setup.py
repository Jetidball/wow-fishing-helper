"""One-picture setup for the existing fishing loop; no desktop input."""
import base64
import tkinter as tk
from tkinter import ttk
from .template_setup import crop_box,save_template

def setup_result(water,cast,left,top):
    x1,y1,x2,y2=water
    return {'area_of_interest':[(left+x1,top+y1),(left+x2,top+y1),(left+x2,top+y2),(left+x1,top+y2)],
            'cast_location':(left+cast[0],top+cast[1])}

def open_fishing_setup(parent,directory,on_done):
    import cv2 as cv
    import numpy as np
    from mss import mss
    with mss() as capture:
        monitor=dict(capture.monitors[0])
        image=np.array(capture.grab(monitor))[:,:,:3].copy()
    parent.deiconify()
    top=tk.Toplevel(parent);top.title('Fishing setup — one picture, three choices')
    heading=tk.StringVar()
    ttk.Label(top,textvariable=heading,font=('Segoe UI',12,'bold')).pack(padx=15,pady=8)
    ttk.Label(top,text='The picture is frozen. Take your time. Back lets you redo a selection.').pack()
    h,w=image.shape[:2];scale=min(1,(parent.winfo_screenwidth()-100)/w,(parent.winfo_screenheight()-250)/h)
    shown=cv.resize(image,(max(1,round(w*scale)),max(1,round(h*scale))))
    _,png=cv.imencode('.png',shown)
    photo=tk.PhotoImage(data=base64.b64encode(png.tobytes()))
    canvas=tk.Canvas(top,width=shown.shape[1],height=shown.shape[0],highlightthickness=0)
    canvas.pack();canvas.create_image(0,0,anchor='nw',image=photo);canvas.photo=photo
    state={'step':0};message=tk.StringVar();ttk.Label(top,textvariable=message).pack()
    auto=tk.BooleanVar(value=False)
    ttk.Checkbutton(top,text='I enabled Auto Loot in WoW (required for this simple setup)',variable=auto).pack()
    instructions=['1 of 3: Drag a rectangle around the WATER where your bobber lands.',
                  '2 of 3: Drag a tight rectangle around YOUR BOBBER.',
                  '3 of 3: Click the FISHING ABILITY icon on your action bar.']
    def update():
        heading.set(instructions[state['step']]);message.set('')
        for key in ('start','end'):
            state.pop(key,None)
        canvas.delete('selection')
        next_button.configure(text='Save setup' if state['step']==2 else 'Next')
    def begin(event):
        state['start']=(event.x,event.y);state['end']=state['start']
        canvas.delete('selection')
        if state['step']==2:
            canvas.create_oval(event.x-5,event.y-5,event.x+5,event.y+5,outline='#00ff88',width=2,tags='selection')
        else:canvas.create_rectangle(event.x,event.y,event.x,event.y,outline='#00ff88',width=2,tags='selection')
    def drag(event):
        if 'start' in state and state['step']!=2:
            state['end']=(event.x,event.y)
            canvas.coords('selection',*state['start'],*state['end'])
    def finish():
        try:
            if 'start' not in state:raise ValueError('Select the marked item on the picture first.')
            if state['step']<2:
                box=crop_box(state['start'],state['end'],scale,w,h)
                state['water' if state['step']==0 else 'bobber']=box
                if state['step']==1:
                    x1,y1,x2,y2=state['water'];a,b,c,d=box
                    if not (x1<=a<c<=x2 and y1<=b<d<=y2):raise ValueError('The bobber must be inside the water area. Use Back to enlarge the water area.')
                state['step']+=1;update()
            else:
                if not auto.get():raise ValueError('Enable Auto Loot in WoW and confirm the checkbox, or cancel and use advanced loot settings.')
                x,y=state['start']
                cast=(min(w-1,max(0,round(x/scale))),min(h-1,max(0,round(y/scale))))
                result=setup_result(state['water'],cast,monitor['left'],monitor['top'])
                path=save_template(image,state['bobber'],directory)
                result['template']=path
                on_done(result);top.destroy()
        except Exception as exc:message.set(str(exc))
    def back():
        state['step']=max(0,state['step']-1);update()
    canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',drag)
    buttons=ttk.Frame(top);buttons.pack(pady=10)
    ttk.Button(buttons,text='Back',command=back).pack(side='left',padx=8)
    next_button=ttk.Button(buttons,text='Next',command=finish);next_button.pack(side='left',padx=8)
    def cancel():on_done(None);top.destroy()
    ttk.Button(buttons,text='Cancel',command=cancel).pack(side='left',padx=8)
    top.protocol('WM_DELETE_WINDOW',cancel);top.bind('<Escape>',lambda event:cancel())
    update();top.lift();top.focus_set()
    from .input_help import install_button_help
    install_button_help(top)
    return top
