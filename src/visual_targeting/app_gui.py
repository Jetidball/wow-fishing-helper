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
    def __init__(self,parent,training_parent=None,settings_provider=None):
        super().__init__(parent,padding=8)
        import sys
        self.settings_provider=settings_provider
        self.preview=Preview();self.job=Job(Path.home()/'wow-fishing-helper'/'logs');self.closed=False
        self.values={};self.status=tk.StringVar(value='Stopped. Normal fishing is separate; these tools cannot change its backend.')
        fields=[('profile',''),('registry','data/model-registry'),('hwnd',''),('dataset','data/dataset'),('session','session-1'),('cast','cast-1'),('region','0 0 640 480'),('config','configs/task-training.json'),('output','runs/task-1'),('release',''),('reviewer',''),('weights',''),('training_run',''),('python',sys.executable),('export_output','datasets/fishing-v1')]
        for name,default in fields:self.values[name]=tk.StringVar(value=default)
        if training_parent is None:
            tabs=ttk.Notebook(self);tabs.pack(fill='both',expand=True)
            visual=ttk.Frame(tabs);training_parent=ttk.Frame(tabs)
            tabs.add(visual,text='Visual targeting');tabs.add(training_parent,text='Neural training')
        else:visual=self
        training_shell=training_parent
        training_canvas=tk.Canvas(training_shell,highlightthickness=0,height=620)
        training_scroll=ttk.Scrollbar(training_shell,orient='vertical',command=training_canvas.yview)
        training_scroll.pack(side='right',fill='y');training_canvas.pack(side='left',fill='both',expand=True)
        training_canvas.configure(yscrollcommand=training_scroll.set)
        training_parent=ttk.Frame(training_canvas)
        training_window=training_canvas.create_window((0,0),window=training_parent,anchor='nw')
        training_parent.bind('<Configure>',lambda event:training_canvas.configure(scrollregion=training_canvas.bbox('all')))
        training_canvas.bind('<Configure>',lambda event:training_canvas.itemconfigure(training_window,width=event.width))
        self.training_parent=training_parent
        def fields_on(parent,fields):
            form=ttk.Frame(parent);form.pack(fill='x',pady=4)
            for row,(name,label) in enumerate(fields):
                ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',padx=4)
                ttk.Entry(form,textvariable=self.values[name],width=58).grid(row=row,column=1,sticky='ew',padx=4)
            form.columnconfigure(1,weight=1)
        def buttons(parent,actions):
            row=ttk.Frame(parent);row.pack(fill='x',pady=3)
            for index,(text,fn) in enumerate(actions):
                ttk.Button(row,text=text,command=lambda f=fn:self.guard(f)).grid(row=index//3,column=index%3,sticky='ew',padx=2,pady=2)
                row.columnconfigure(index%3,weight=1)
        ttk.Label(visual,text='Visual targeting: inspect detections and record data',font=('Segoe UI',12,'bold')).pack(anchor='w')
        ttk.Label(visual,text='This is separate from normal fishing. Import shared settings explicitly; normal casting/bite/timing settings stay in Normal fishing.',wraplength=850).pack(anchor='w')
        fields_on(visual,[('profile','Task profile'),('registry','Model registry'),('hwnd','Game window'),('dataset','Recording dataset'),('session','Session / visit ID'),('cast','Cast ID'),('region','Capture area (left top width height)')])
        buttons(visual,[('Choose profile',self.choose_profile),('Select game window',self.select_window),('Use normal fishing settings',self.import_normal_settings),('Window / model metadata',self.describe),('Use full game area',self.use_window_region),('Record 30 seconds (no clicks)',self.root_after_capture)])
        self.mode=tk.StringVar(value='dry-run')
        modes=ttk.Combobox(visual,textvariable=self.mode,values=['dry-run','move','single-click'],state='readonly')
        modes.pack(anchor='w');modes.bind('<<ComboboxSelected>>',lambda event:self.stop())
        buttons(visual,[('Start preview',self.start),('Arm ONE attempt (3s)',self.arm),('Pause / Stop',self.stop),('Open screenshot / select bobber',self.open_screenshot),('Screenshot in 10s / select bobber',self.delayed_screenshot),('Cancel current job',self.cancel_job)])
        ttk.Label(visual,textvariable=self.status,wraplength=850).pack(fill='x')
        self.image=ttk.Label(visual);self.image.pack(fill='both',expand=True)
        self.details=tk.Text(visual,height=6,wrap='word');self.details.pack(fill='x')

        ttk.Label(training_parent,text='Neural training: what happens and why',font=('Segoe UI',12,'bold')).pack(anchor='w',padx=8,pady=6)
        explanation=(
            '1. RECORD full scenes in Visual targeting. Each visit gets a new session ID; each cast gets a new cast ID. Capture never clicks.\n'
            '2. LABEL bobber boxes on those frames, including empty negative frames. Import your reviewed labels JSON below. Cropped template pictures alone are not a detection dataset.\n'
            '3. EXPORT by session. This keeps neighboring video frames out of the test set and prevents misleading accuracy. Set Dataset to the exported folder afterward.\n'
            '4. TRAIN from pretrained .pt weights. Epochs = training passes; image size preserves small bobbers; device = cpu or a configured CUDA GPU index such as 0. Training runs in a cancellable child process.\n'
            '5. EVALUATE best.pt on held-out sessions and compare with templates. Reports include overlays and errors; training does not activate the model.\n'
            'Normal fishing still uses your existing template/bite/casting loop. Neural weights need explicit review/promotion for neural previews; they are not automatically installed into normal fishing.'
        )
        helpbox=tk.Text(training_parent,height=10,wrap='word')
        helpbox.insert('1.0',explanation);helpbox.configure(state='disabled');helpbox.pack(fill='x',padx=8)
        fields_on(training_parent,[('profile','Training / evaluation profile'),('dataset','Dataset (exported folder for training)'),('reviewer','Human reviewer name'),('export_output','New exported dataset folder'),('python','Training Python executable'),('config','Training configuration JSON'),('output','NEW training / evaluation output folder'),('weights','Candidate best.pt (evaluation only)'),('training_run','Training run folder (evaluation)')])
        self.train_values={}
        from .experiments import TrainConfig
        default=TrainConfig()
        controls=ttk.Frame(training_parent);controls.pack(fill='x')
        for column,key in enumerate(('model','epochs','imgsz','batch','device')):
            ttk.Label(controls,text=key).grid(row=0,column=column)
            self.train_values[key]=tk.StringVar(value=str(getattr(default,key)))
            ttk.Entry(controls,textvariable=self.train_values[key],width=24 if key=='model' else 8).grid(row=1,column=column)
        self.allow_download=tk.BooleanVar(value=False)
        ttk.Checkbutton(training_parent,text='Allow official pretrained weight download (use a name such as yolo11n.pt)',variable=self.allow_download).pack(anchor='w')
        buttons(training_parent,[('Choose neural profile',self.choose_neural_profile),('Import human labels JSON',self.import_labels),('Export reviewed dataset',self.export_dataset),('Load training config',self.load_train_config),('Check training dataset',self.check_training_data),('Train neural detector',lambda:self.job_command('train')),('Evaluate candidate',lambda:self.job_command('evaluate')),('Install training dependencies',self.install_training),('Cancel training / job',self.cancel_job),('Open training guide',self.training_guide)])
        fields_on(training_parent,[('registry','Model registry'),('release','Previously approved release for rollback')])
        buttons(training_parent,[('Rollback approved model',self.rollback)])
        ttk.Label(training_parent,textvariable=self.status,wraplength=850).pack(fill='x')
        self.training_log=tk.Text(training_parent,height=8,wrap='word');self.training_log.pack(fill='both',expand=True)
        if Path(self.get('config')).is_file():self.guard(self.load_train_config)
        for key in ('profile','registry','hwnd'):
            self.values[key].trace_add('write',lambda *args:self.stop())
        self.bind('<Destroy>',self.destroyed,add='+');self.poll_timer=self.after(150,self.poll)
    def import_normal_settings(self):
        self.stop()
        if self.settings_provider is None:raise ValueError('Open Start Fishing.cmd to import the original Settings. Standalone targeting has no normal Settings instance.')
        settings=self.settings_provider()
        if settings is None:raise ValueError('Correct the invalid normal fishing setting first.')
        from .settings_bridge import import_fishing_settings
        base=self.profile() if self.get('profile') else Profile.read(Path.cwd()/'configs/tasks/fishing-v1.json')
        path,region,report=import_fishing_settings(settings,base,Path.cwd()/'data/profiles')
        self.values['profile'].set(str(path))
        if region:self.values['region'].set(region)
        self.details.delete('1.0','end');self.details.insert('end',json.dumps(report,indent=2))
        self.status.set('Imported img_dir, match_threshold, canny_thresholds and area_of_interest. Normal settings were not overwritten. See mapping below.')
    def choose_neural_profile(self):
        self.stop()
        path=filedialog.askopenfilename(title='Choose a neural profile (fishing-neural-v2.json)',initialdir='configs/tasks',filetypes=[('Task profile','*.json')])
        if path:
            profile=Profile.read(path)
            if profile.data['model']['backend']!='neural':raise ValueError('Select fishing-neural-v2.json or another neural profile for neural evaluation.')
            self.values['profile'].set(path)
    def import_labels(self):
        self.stop()
        if not self.get('reviewer'):raise ValueError('Enter your human reviewer name first.')
        path=filedialog.askopenfilename(title='Import manually reviewed annotations',filetypes=[('Labels JSON','*.json')])
        if path:self.job.start(self.base_args()+['label','--dataset',self.get('dataset'),'--annotations',path,'--reviewer',self.get('reviewer')])
    def export_dataset(self):
        self.stop()
        self.job.start(self.base_args()+['export','--dataset',self.get('dataset'),'--output',self.get('export_output')])
        self.status.set('Exporting reviewed data by session. When completed, set Dataset to the exported folder.')
    def load_train_config(self):
        from .experiments import TrainConfig
        config=TrainConfig.read(self.get('config'))
        for key,value in self.train_values.items():value.set(str(getattr(config,key)))
        self.status.set('Loaded training values from config. These are training settings, not mouse/casting settings.')
    def check_training_data(self):
        self.stop()
        self.job.start(self.base_args()+['validate','--dataset',self.get('dataset')],python=self.get('python'))
        self.status.set('Checking reviewed annotations and session splits; no training or game input.')
    def install_training(self):
        self.stop()
        self.job.start_python(['-m','pip','install','.[training]'],python=self.get('python'))
        self.status.set('Installing optional training dependencies into the selected Python environment. This does not train or activate a model.')
    def training_guide(self):
        import webbrowser
        webbrowser.open((Path.cwd()/'docs/TRAINING-GUI.html').resolve().as_uri())
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
        self.stop()
        if self.profile().data['model']['backend']!='neural':raise ValueError('Choose a neural profile before neural training/evaluation. Normal fishing remains unchanged.')
        args=self.base_args()+[command,'--dataset',self.get('dataset'),'--output',self.get('output')]
        if command=='train':
            from dataclasses import replace,asdict
            import time
            from .experiments import TrainConfig
            config=replace(TrainConfig.read(self.get('config')),**{key:(int(value.get()) if key in ('epochs','imgsz','batch') else value.get().strip()) for key,value in self.train_values.items()})
            folder=Path('data/training-configs');folder.mkdir(parents=True,exist_ok=True)
            snapshot=folder/(str(time.time_ns())+'.json')
            snapshot.write_text(json.dumps(asdict(config),indent=2),encoding='utf-8')
            args+=['--config',str(snapshot)]
            if self.allow_download.get():args+=['--allow-download']
        if command=='evaluate':
            if not self.get('weights') or not self.get('training_run'):raise ValueError('Evaluation needs best.pt and its training run folder for provenance checking.')
            args+=['--weights',self.get('weights'),'--training-run',self.get('training_run')]
        self.job.start(args,python=self.get('python'))
        self.status.set(f'{command.title()} job started. See log below; Cancel training / job stops the owned process tree. No model is activated.')
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
            text=self.job.log.read_text(encoding='utf-8',errors='replace')[-12000:]
            for widget in (self.details,self.training_log):
                widget.delete('1.0','end')
                widget.insert('end',f'Job: {state}\nLog: {self.job.log}\n{text}')
        self.poll_timer=self.after(150,self.poll)
    def shutdown(self):
        if getattr(self,'poll_timer',None):
            try:self.after_cancel(self.poll_timer)
            except tk.TclError:pass
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
