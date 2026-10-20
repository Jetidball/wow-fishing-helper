"""Local targeting application, also embedded in the legacy settings notebook."""
import base64
import json
from pathlib import Path
import queue
import tkinter as tk
from tkinter import ttk,filedialog
from .application import Job,Preview
from .profiles import Profile
from .lifecycle import ModelRegistry

class TargetingPanel(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent,padding=8)
        self.preview=Preview();self.job=Job(Path.home()/'wow-fishing-helper'/'logs');self.closed=False
        self.values={};self.status=tk.StringVar(value='Stopped; dry-run default. No automatic model activation.')
        fields=[('profile',''),('registry','data/model-registry'),('hwnd',''),('dataset','data/dataset'),('session','session-1'),('cast','cast-1'),('region','0 0 640 480'),('config','configs/task-training.json'),('output','runs/task-1'),('release',''),('reviewer',''),('weights',''),('training_run','')]
        form=ttk.Frame(self);form.pack(fill='x')
        for index,(name,default) in enumerate(fields):
            row=index//2;col=(index%2)*2
            ttk.Label(form,text=name).grid(row=row,column=col,sticky='w')
            value=tk.StringVar(value=default);self.values[name]=value
            ttk.Entry(form,textvariable=value,width=35).grid(row=row,column=col+1,sticky='ew')
        ttk.Button(form,text='Choose profile',command=self.choose_profile).grid(row=7,column=0)
        ttk.Button(form,text='Allowed windows / metadata',command=self.describe).grid(row=7,column=1)
        self.mode=tk.StringVar(value='dry-run')
        modes=ttk.Combobox(form,textvariable=self.mode,values=['dry-run','move','single-click'],state='readonly')
        modes.grid(row=7,column=2);modes.bind('<<ComboboxSelected>>',lambda event:self.stop())
        controls=ttk.Frame(self);controls.pack(fill='x')
        for text,fn in [('Start preview',self.start),('Arm ONE attempt (3s)',self.arm),('Pause / Stop',self.stop),('Capture (3s delay)',lambda:self.root_after_capture()),('Train',lambda:self.job_command('train')),('Evaluate',lambda:self.job_command('evaluate')),('Rollback',self.rollback),('Cancel job',self.cancel_job)]:
            ttk.Button(controls,text=text,command=lambda f=fn:self.guard(f)).pack(side='left')
        setup=ttk.Frame(self);setup.pack(fill='x')
        for text,fn in [('Select game window',self.select_window),('Use full game area',self.use_window_region),('Open screenshot / select bobber',self.open_screenshot),('Screenshot in 10s / select bobber',self.delayed_screenshot)]:
            ttk.Button(setup,text=text,command=lambda f=fn:self.guard(f)).pack(side='left')
        ttk.Label(self,textvariable=self.status,wraplength=900).pack(fill='x')
        self.image=ttk.Label(self);self.image.pack(fill='both',expand=True)
        self.details=tk.Text(self,height=8);self.details.pack(fill='x')
        for key in ('profile','registry','hwnd'):
            self.values[key].trace_add('write',lambda *args:self.stop())
        self.bind('<Destroy>',self.destroyed,add='+');self.after(150,self.poll)
    def get(self,key):return self.values[key].get().strip()
    def profile(self):return Profile.read(self.get('profile'))
    def guard(self,fn):
        try:fn()
        except Exception as exc:self.status.set(f'{type(exc).__name__}: {exc}')
    def choose_profile(self):
        path=filedialog.askopenfilename(filetypes=[('Task profile','*.json')])
        if path:self.stop();self.values['profile'].set(path)
    def select_window(self):
        self.stop()
        from .window_context import allowed_windows
        rows=allowed_windows(self.profile())
        if not rows:raise ValueError('No allowed game window found. Open the game and check allowed_windows in the profile.')
        top=tk.Toplevel(self);top.title('Select your game window')
        ttk.Label(top,text='Select your game, then click Use selected window.').pack()
        listing=tk.Listbox(top,width=85,height=min(8,len(rows)));listing.pack()
        for row in rows:
            identity=row['window'];listing.insert('end',f"{identity['title']} — {identity['executable']} ({identity['hwnd']})")
        listing.selection_set(0)
        def choose():
            row=rows[listing.curselection()[0]]
            self.values['hwnd'].set(str(row['window']['hwnd']))
            self.use_window_region();top.destroy()
        ttk.Button(top,text='Use selected window',command=lambda:self.guard(choose)).pack()
    def use_window_region(self):
        self.stop()
        from .window_context import query_window
        identity,rect,_=query_window(int(self.get('hwnd')))
        if not self.profile().allows(identity):raise ValueError('Selected window is not allowed')
        self.values['region'].set(f'{int(rect.left)} {int(rect.top)} {int(rect.width)} {int(rect.height)}')
        self.status.set('Capture area set to the full game window; no coordinates needed.')
    def edit_template(self,image,profile):
        from .template_setup import open_crop_dialog
        open_crop_dialog(self,image,profile.template_path(),lambda path:self.status.set(f'Saved {path}. Restart preview to load it.'))
    def template_profile(self):
        profile=self.profile()
        if profile.data['model']['backend']!='template':raise ValueError('Choose a template profile to save bobber templates.')
        return profile
    def open_screenshot(self):
        self.stop();profile=self.template_profile()
        path=filedialog.askopenfilename(title='Open a screenshot containing your bobber',filetypes=[('Screenshots','*.png *.jpg *.jpeg *.bmp')])
        if not path:return
        import cv2 as cv
        import numpy as np
        image=cv.imdecode(np.fromfile(path,dtype=np.uint8),cv.IMREAD_COLOR)
        if image is None:raise ValueError('Screenshot could not be read')
        self.edit_template(image,profile)
    def delayed_screenshot(self):
        self.stop();profile=self.template_profile();hwnd=int(self.get('hwnd'))
        self.screenshot_tick(profile,hwnd,10)
    def screenshot_tick(self,profile,hwnd,seconds):
        self.capture_pending=None
        if self.closed:return
        if seconds:
            self.status.set(f'Screenshot in {seconds}s: focus the game and cast. Stop cancels. Crop later on a frozen picture.')
            self.capture_pending=self.after(1000,lambda:self.screenshot_tick(profile,hwnd,seconds-1))
        else:
            def capture():
                from .template_setup import capture_window
                image=capture_window(profile,hwnd)
                self.status.set('Screenshot ready. Return to the helper and draw a box around your bobber.')
                self.edit_template(image,profile)
            self.guard(capture)
    def describe(self):
        self.stop();p=self.profile()
        from .window_context import allowed_windows
        registry=ModelRegistry(self.get('registry'))
        self.details.delete('1.0','end');self.details.insert('end',json.dumps({'profile':p.data,'sha256':p.digest,'windows':allowed_windows(p),'models':registry.load()['tasks'].get(p.task_id,{})},indent=2,default=str))
    def start(self):self.preview.start(self.profile(),ModelRegistry(self.get('registry')),self.get('hwnd'),self.mode.get());self.status.set('Loading detector; no input until explicitly armed')
    def arm(self):
        if not self.preview.thread or not self.preview.thread.is_alive():raise ValueError('Start preview first')
        self.preview.arm_event.set();self.status.set('One attempt requested. Focus the allowlisted target window within 3 seconds.')
    def stop(self):
        self.preview.stop()
        if getattr(self,'capture_pending',None):
            self.after_cancel(self.capture_pending);self.capture_pending=None
        self.status.set('Paused / stopped; disarmed')
    def base_args(self):return ['--profile',self.get('profile'),'--registry',self.get('registry')]
    def root_after_capture(self):
        self.stop();args=self.base_args()+['record','--dataset',self.get('dataset'),'--session',self.get('session'),'--cast',self.get('cast'),'--hwnd',self.get('hwnd'),'--region',*self.get('region').split()]
        self.status.set('Capture in 3 seconds. Focus target; capture cannot click.')
        self.capture_pending=self.after(3000,lambda:self.guard(lambda:self.job.start(args)))
    def job_command(self,command):
        self.stop();args=self.base_args()+[command,'--dataset',self.get('dataset'),'--output',self.get('output')]
        if command=='train':args+=['--config',self.get('config')]
        if command=='evaluate':
            if self.get('weights'):args+=['--weights',self.get('weights')]
            if self.get('training_run'):args+=['--training-run',self.get('training_run')]
        self.job.start(args)
    def rollback(self):
        self.stop()
        ModelRegistry(self.get('registry')).rollback(self.profile(),self.get('release'),self.get('reviewer'))
        self.status.set('Rolled back; restart preview to reload explicitly approved weights')
    def cancel_job(self):self.job.cancel();self.status.set('Job cancelled; partial output is not approved')
    def poll(self):
        if self.closed:return
        try:
            image,reason=self.preview.frames.get_nowait();self.status.set(reason)
            if image is not None:
                import cv2 as cv
                h,w=image.shape[:2];image=cv.resize(image,(min(900,w),max(1,round(h*min(900,w)/w))))
                _,encoded=cv.imencode('.png',image);self.photo=tk.PhotoImage(data=base64.b64encode(encoded.tobytes()));self.image.configure(image=self.photo)
        except queue.Empty:pass
        if self.job.process:
            state=self.job.status()
            self.details.delete('1.0','end')
            text=self.job.log.read_text(encoding='utf-8',errors='replace')[-12000:]
            self.details.insert('end',f'Job: {state}\nLog: {self.job.log}\n{text}')
        self.after(150,self.poll)
    def shutdown(self):
        self.closed=True;self.preview.stop()
        if getattr(self,'capture_pending',None):self.after_cancel(self.capture_pending)
        self.job.cancel()
    def destroyed(self,event):
        if event.widget is self:self.shutdown()

def main():
    root=tk.Tk();root.title('Visual targeting - local application');root.geometry('1100x850')
    panel=TargetingPanel(root);panel.pack(fill='both',expand=True)
    def close():panel.shutdown();root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);root.bind('<Escape>',lambda event:panel.stop());root.mainloop()

if __name__=='__main__':main()
