"""Local targeting application, also embedded in the legacy settings notebook."""
import base64
import json
from pathlib import Path
import queue
import tkinter as tk
from tkinter import ttk,filedialog
from .application import Job,Preview,log_tail
from .profiles import Profile
from .lifecycle import ModelRegistry
from .input_help import describe,explanation

class TargetingPanel(ttk.Frame):
    def __init__(self,parent,training_parent=None,settings_provider=None):
        super().__init__(parent,padding=8)
        import sys
        self.settings_provider=settings_provider
        self.preview=Preview();self.job=Job(Path.home()/'wow-fishing-helper'/'logs');self.closed=False
        self.values={};self.status=tk.StringVar(value='Stopped. Normal fishing is separate; these tools cannot change its backend.')
        fields=[('profile',str(Path('configs/tasks/fishing-neural-v2.json').resolve()) if Path('configs/tasks/fishing-neural-v2.json').exists() else ''),('registry','data/model-registry'),('hwnd',''),('dataset','data/dataset'),('session','session-1'),('cast','cast-1'),('region','0 0 640 480'),('config','configs/task-training.json'),('output','runs/task-1'),('release',''),('reviewer',__import__('getpass').getuser()),('weights',''),('training_run',''),('python',str(Path('.venv-gpu/Scripts/python.exe').resolve()) if Path('.venv-gpu/Scripts/python.exe').exists() else sys.executable),('export_output','datasets/fishing-v1')]
        for name,default in fields:self.values[name]=tk.StringVar(value=default)
        try:
            latest=json.loads(Path('data/training-latest.json').read_text())
            if latest.get('status')=='completed':
                self.values['weights'].set(latest.get('checkpoint',''))
                self.values['training_run'].set(latest.get('run',''))
        except (OSError,ValueError,TypeError):pass
        self.field_help=tk.StringVar(value='Defaults are already filled. Click or hover any input for its description; advanced fields are optional.')
        if training_parent is None:
            tabs=ttk.Notebook(self);tabs.pack(fill='both',expand=True)
            visual=ttk.Frame(tabs);training_parent=ttk.Frame(tabs)
            tabs.add(visual,text='Visual targeting');tabs.add(training_parent,text='Neural training')
            from .model_results_gui import ModelResultsPanel
            self.model_results=ModelResultsPanel(tabs,on_preview=lambda row:self.guard(lambda:self.preview_model(row)))
            self.model_results.connect(self)
            tabs.add(self.model_results,text='Model results')
            tabs.bind('<<NotebookTabChanged>>',lambda event:self.model_results.refresh() if tabs.select()==str(self.model_results) else None)
        else:visual=self
        ttk.Label(visual,textvariable=self.field_help,wraplength=850,justify='left').pack(fill='x',pady=4)
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
        ttk.Label(training_parent,textvariable=self.field_help,wraplength=820,justify='left').pack(fill='x',padx=8,pady=5)
        def fields_on(parent,fields):
            form=ttk.Frame(parent);form.pack(fill='x',pady=4)
            for row,(name,label) in enumerate(fields):
                ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',padx=4)
                entry=ttk.Entry(form,textvariable=self.values[name],width=58)
                entry.grid(row=row,column=1,sticky='ew',padx=4)
                describe(entry,name,self.values[name].get(),self.field_help.set)
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
        buttons(visual,[('Preview latest trained model (no input)',lambda:self.preview_latest(False)),
                        ('Set up movement-only test',lambda:self.preview_latest(True)),
                        ('Review evaluation / approve model',self.review_latest_evaluation)])
        ttk.Button(visual,text='How to use my trained model — step-by-step guide',command=self.use_model_guide).pack(anchor='w')
        self.mode=tk.StringVar(value='dry-run')
        modes=ttk.Combobox(visual,textvariable=self.mode,values=['dry-run','move','single-click'],state='readonly')
        describe(modes,'mode','dry-run',self.field_help.set)
        modes.pack(anchor='w');modes.bind('<<ComboboxSelected>>',lambda event:self.stop())
        buttons(visual,[('Start preview',self.start),('Arm ONE attempt (3s)',self.arm),('Pause / Stop',self.stop),('Open screenshot / select bobber',self.open_screenshot),('Screenshot in 10s / select bobber',self.delayed_screenshot),('Cancel current job',self.cancel_job)])
        ttk.Label(visual,textvariable=self.status,wraplength=850).pack(fill='x')
        self.image=ttk.Label(visual);self.image.pack(fill='both',expand=True)
        self.details=tk.Text(visual,height=6,wrap='word');self.details.pack(fill='x')

        quick=ttk.LabelFrame(training_parent,text='Start here — train a bobber detector',padding=8)
        quick.pack(fill='x',padx=6,pady=6)
        self.training_progress=tk.StringVar(value='Click Refresh progress to see your next step.')
        ttk.Label(quick,textvariable=self.training_progress,wraplength=820,justify='left').pack(fill='x')
        ttk.Button(quick,text='Train my reviewed pictures — automatic setup (5-epoch first run)',
                   command=lambda:self.guard(self.train_automatic)).pack(fill='x',pady=6)
        self.trained_file=tk.StringVar(value='Training output will be a best.pt model, not a .whl installer.')
        ttk.Label(quick,textvariable=self.trained_file,wraplength=820).pack(fill='x')
        ttk.Button(quick,text='Open trained model folder',command=lambda:self.guard(self.open_trained_folder)).pack(anchor='w')
        ttk.Button(quick,text='Evaluate latest trained model (automatic paths)',command=lambda:self.guard(self.evaluate_latest)).pack(anchor='w')
        buttons(quick,[('1. Record another session',self.record_training_session),('2. Label pictures',self.label_pictures),('3. Prepare training dataset',self.prepare_dataset),('4. Install training support',self.install_training),('5. Start training',self.start_training_easy),('Refresh progress',self.refresh_training_progress)])
        ttk.Label(quick,text='Label several independent sessions. Preparing data and training never clicks in WoW. Advanced fields below are optional adjustments.',wraplength=820).pack(anchor='w')
        ttk.Label(training_parent,text='Neural training: what happens and why',font=('Segoe UI',12,'bold')).pack(anchor='w',padx=8,pady=6)
        explanation=(
            '1. RECORD full scenes in Visual targeting. Each visit gets a new session ID; each cast gets a new cast ID. Capture never clicks.\n'
            '2. LABEL bobber boxes on those frames, including empty negative frames. Import your reviewed labels JSON below. Cropped template pictures alone are not a detection dataset.\n'
            '3. EXPORT by session. This keeps neighboring video frames out of the test set and prevents misleading accuracy. Set Dataset to the exported folder afterward.\n'
            '4. TRAIN from pretrained .pt weights. Epochs = training passes; image size preserves small bobbers; device = CUDA GPU index 0 or 1; CPU fallback is disabled. Training runs in a cancellable child process.\n'
            '5. EVALUATE best.pt on held-out sessions and compare with templates. Reports include overlays and errors; training does not activate the model.\n'
            'Normal fishing lets you select Template or Neural network. Live neural use needs explicit review/approval; candidate previews never activate normal fishing.'
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
            entry=ttk.Entry(controls,textvariable=self.train_values[key],width=24 if key=='model' else 8)
            entry.grid(row=1,column=column)
            describe(entry,key,getattr(default,key),self.field_help.set)
        self.allow_download=tk.BooleanVar(value=False)
        download=ttk.Checkbutton(training_parent,text='Allow official pretrained weight download (use a name such as yolo11n.pt)',variable=self.allow_download)
        download.pack(anchor='w');describe(download,'allow_download',False,self.field_help.set)
        buttons(training_parent,[('Choose neural profile',self.choose_neural_profile),('Import labels JSON (advanced)',self.import_labels),('Export reviewed dataset',self.export_dataset),('Load training config',self.load_train_config),('Check training dataset',self.check_training_data),('Train neural detector',lambda:self.job_command('train')),('Evaluate candidate',lambda:self.job_command('evaluate')),('Install training dependencies',self.install_training),('Cancel training / job',self.cancel_job),('Open training guide',self.training_guide)])
        fields_on(training_parent,[('registry','Model registry'),('release','Previously approved release for rollback')])
        buttons(training_parent,[('Rollback approved model',self.rollback)])
        ttk.Label(training_parent,textvariable=self.status,wraplength=850).pack(fill='x')
        self.training_log=tk.Text(training_parent,height=8,wrap='word');self.training_log.pack(fill='both',expand=True)
        if Path(self.get('config')).is_file():self.guard(self.load_train_config)
        if self.train_values['device'].get()=='cpu':self.train_values['device'].set('0')
        if self.train_values['model'].get()=='weights/yolo11n.pt' and not Path('weights/yolo11n.pt').exists():
            self.train_values['model'].set('yolo11n.pt')
        for key in ('profile','registry','hwnd'):
            self.values[key].trace_add('write',lambda *args:self.stop())
        self.refresh_training_progress()
        from .input_help import install_button_help
        install_button_help(self.winfo_toplevel())
        from .errors import track_tk_errors
        track_tk_errors(self.winfo_toplevel(),self.status.set)
        self.bind('<Destroy>',self.destroyed,add='+');self.poll_timer=self.after(150,self.poll)
    def selected_info(self,row):
        if row is None:raise ValueError('Select a model in the table first.')
        from .deployment import candidate_for_run
        info=candidate_for_run(row['run_dir'],row['evaluation_file'])
        for key,value in (('profile',info['profile']),('weights',info['weights']),('training_run',info['run'])):
            if self.values[key].get()!=str(value):self.values[key].set(str(value))
        return info
    def original_dataset(self,row):
        from .experiments import sha
        wanted=row['run']['dataset_manifest_sha256']
        for path in Path('datasets').glob('*/manifest.json'):
            if sha(path)==wanted:return path.parent
        raise ValueError('Original training dataset is missing or changed. Restore it before refining/evaluating this model.')
    def recommended_step(self,row):
        if row is None:return None,'Train a first model in Neural training, then select it here.'
        if row['run'].get('status')!='completed':return None,'This training run is not complete. Open job log to see progress or errors.'
        from . import dataset as ds
        base=ds.load(self.original_dataset(row))
        path=Path('data/improvement-examples/manifest.json')
        if not path.exists():return 'collect','NEXT: Run & collect improvements. No review pictures have been saved yet.'
        new=ds.load(path.parent)
        if new['classes']!=base['classes']:return None,'Review pictures belong to a different class vocabulary. Select the model used to collect them.'
        existing={r['id'] for r in base['frames']};splits=base['export']['session_splits']
        eligible=[r for r in new['frames'] if r['id'] not in existing and r['annotation']['reviewed'] and r['annotation'].get('review_source')=='human' and splits.get(r['session_id'],'train')=='train']
        pending=sum(not r['annotation']['reviewed'] for r in new['frames'])
        if eligible and not any(r.get('split')=='test' for r in base['frames']):return None,'This baseline has no independent test visit. Train a baseline with three reviewed visits first.'
        if eligible:return 'refine',f'READY: Refine + test with {len(eligible)} newly reviewed pictures. {pending} pictures still await review.'
        if pending:return 'review',f'NEXT: Review {pending} pictures. Unreviewed predictions cannot train the model.'
        if row.get('evaluation') is None:return 'evaluate','NEXT: Evaluate selected model on its independent test visits.'
        return 'collect','NEXT: Collect more examples. The eligible reviewed pictures are already included in this model.'
    def model_action(self,action,row):
        import time,sys
        if action=='stop':self.stop();self.cancel_job();return
        if action=='errors':
            import os
            path=Path('data/logs/application-errors.jsonl').resolve()
            path.parent.mkdir(parents=True,exist_ok=True);path.touch(exist_ok=True)
            os.startfile(str(path));return
        if action=='log':
            import os
            if not self.job.log or not self.job.log.exists():raise ValueError('No job log yet. Run a GPU check, evaluation or refinement first.')
            os.startfile(str(self.job.log.resolve()));return
        if action=='arm':self.arm();return
        if action=='teach_train':self.train_teaching_now();return
        if action=='next':
            action,message=self.recommended_step(row)
            self.status.set(message)
            if action:self.model_action(action,row)
            return
        if action=='gpu':
            self.job.start_python(['-m','visual_targeting.gpu'],python=self.get('python'));self.status.set('Checking CUDA GPUs; see job log. CPU fallback disabled.');return
        if action=='install':
            self.stop();self.job.start_python(['tools/setup_gpu.py'],python=self.get('python'))
            self.status.set('Installing GPU support. Wait for completion, close and reopen the app, then Check GPUs.');return
        info=self.selected_info(row)
        if action in ('fill','collect','move','click','teach') and self.get('hwnd'):
            from .window_context import query_window
            try:
                identity,_,_=query_window(int(self.get('hwnd')))
                if not Profile.read(info['profile']).allows(identity):raise ValueError('Window no longer matches this model.')
            except (OSError,ValueError,RuntimeError):self.values['hwnd'].set('')
        if action in ('fill','collect','move','click','teach') and not self.get('hwnd'):
            from .window_context import allowed_windows
            windows=allowed_windows(Profile.read(info['profile']))
            if len(windows)==1:self.values['hwnd'].set(str(windows[0]['window']['hwnd']))
            else:self.select_window(lambda:self.guard(lambda:self.model_action(action,row)));return
        if action=='fill':
            warning=''
            try:self.values['dataset'].set(str(self.original_dataset(row)))
            except ValueError:warning=' Original training dataset is missing; live inference does not require it.'
            self.use_window_region()
            callback=getattr(self,'use_fishing_callback',None)
            if callback:
                report=callback(info);self.status.set(report['message']+warning)
            else:self.status.set('Preview paths filled. To configure LIVE fishing, open Start Fishing.cmd and use Auto-fill on its Model results tab.'+warning)
            return
        if action=='teach':
            inference=Profile.read(info['profile']).data['model']['device']
            self.train_values['device'].set('0' if inference in ('1','cuda:1') else '1')
            self.teaching_row=row;self.teaching_store=None;self.teaching_trained_count=0
            self._preview_candidate(info,teaching=True);return
        if action=='collect':self._preview_candidate(info,collect='data/improvement-examples');return
        if action=='review':
            if not Path('data/improvement-examples/manifest.json').exists():raise ValueError('No pictures to review yet. Click Run & collect improvements, focus WoW, then Stop and Review.')
            self.stop()
            if self.preview.thread:self.preview.thread.join(timeout=2)
            self.values['dataset'].set('data/improvement-examples');self.label_pictures();return
        if action=='refine':
            step,message=self.recommended_step(row)
            if step!='refine':raise ValueError(message)
            if not self.preview.teaching:self.stop()
            output=Path('runs')/('fishing-refined-'+str(time.time_ns()))
            args=['-u','-m','visual_targeting.improvement','--run',str(info['run']),'--dataset',str(self.original_dataset(row)),
                  '--new-data','data/improvement-examples','--output',str(output),'--device',self.train_values['device'].get()]
            self.job.start_python(args,python=self.get('python'));self.status.set('Refine + test started on GPU. Only human-reviewed new visits are used; old test sessions remain frozen.');return
        if action=='evaluate':
            self.values['dataset'].set(str(self.original_dataset(row)))
            self.values['output'].set(str(Path('runs')/('fishing-evaluation-'+str(time.time_ns()))));self.job_command('evaluate');return
        if action=='approve':self._review_candidate(info);return
        if action=='move':self._preview_candidate(info,True);return
        if action=='fishing':
            active=ModelRegistry(self.get('registry')).active(Profile.read(info['profile']))
            from .experiments import sha
            if sha(active['weights_path'])!=row['run']['checkpoint_sha256']:raise ValueError('Approve the selected model first; a different model is active.')
            callback=getattr(self,'use_fishing_callback',None)
            if callback:callback(info)
            else:raise ValueError('Open Start Fishing.cmd, Model results, then Use selected for fishing. This standalone preview app never casts.')
            return
        if action=='click':
            self.stop()
            active=ModelRegistry(self.get('registry')).active(Profile.read(info['profile']))
            from .experiments import sha
            if sha(active['weights_path'])!=row['run']['checkpoint_sha256']:raise ValueError('Approve this selected model first; another model is currently active.')
            if self.preview.thread:self.preview.thread.join(timeout=1)
            self.mode.set('single-click');self.start()
            self.status.set('Single-click test ready. Arm ONE attempt, then focus WoW within 3 seconds. Moves then left-clicks once; catch is not confirmed.');return
    def evaluate_latest(self):
        import time
        from .deployment import latest_candidate
        self.stop();info=latest_candidate()
        latest=json.loads(Path('data/training-latest.json').read_text())
        self.values['profile'].set(str(info['profile']))
        self.values['weights'].set(str(info['weights']))
        self.values['training_run'].set(str(info['run']))
        self.values['dataset'].set(latest['dataset'])
        output=Path('runs')/('fishing-evaluation-'+str(time.time_ns()))
        self.values['output'].set(str(output))
        self.job_command('evaluate')
        active={'output':str(output),'profile':str(info['profile']),'pid':self.job.process.pid,'log':str(self.job.log)}
        Path('data/evaluation-active.json').write_text(json.dumps(active,indent=2))
        self.status.set('Evaluating latest model on its held-out data; paths filled automatically. Review evaluation after completion. No input or model promotion.')
    def use_model_guide(self):
        import webbrowser
        webbrowser.open((Path.cwd()/'docs/USING-TRAINED-MODEL.html').resolve().as_uri())
    def preview_model(self,row):
        from .deployment import candidate_for_run
        self._preview_candidate(candidate_for_run(row['run_dir'],row['evaluation_file']))
    def preview_latest(self,movement=False):
        from .deployment import latest_candidate
        self._preview_candidate(latest_candidate(),movement)
    def _preview_candidate(self,info,movement=False,collect=None,teaching=False):
        self.stop()
        from .window_context import allowed_windows
        profile=Profile.read(info['profile'])
        self.values['profile'].set(str(info['profile']));self.values['weights'].set(str(info['weights']))
        self.values['training_run'].set(str(info['run']))
        if movement and not info['evaluation']:raise ValueError('Run Evaluate candidate on independent test data first. Candidate preview still works without input.')
        if not self.get('hwnd'):
            windows=allowed_windows(profile)
            if len(windows)==1:self.values['hwnd'].set(str(windows[0]['window']['hwnd']))
            else:
                self.select_window();self.status.set('Select the game window, then press the preview/test button again.');return
        if self.preview.thread and self.preview.thread.is_alive():
            self.preview.thread.join(timeout=1)
        region=None
        if self.settings_provider is not None:
            settings=self.settings_provider()
            if settings is not None and settings.area_of_interest:
                xs=[p[0] for p in settings.area_of_interest];ys=[p[1] for p in settings.area_of_interest]
                region=(min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys))
                self.values['region'].set(' '.join(map(str,region)))
        self.mode.set('move' if movement else 'dry-run')
        self.preview.start(profile,ModelRegistry(self.get('registry')),self.get('hwnd'),self.mode.get(),
                           weights=str(info['weights']),training_run=str(info['run']),
                           evaluation=str(info['evaluation']) if info['evaluation'] else None,region=region,collect=collect,teaching=teaching)
        self.status.set('Movement-only test configured. Check the cross, then click Arm ONE attempt and focus WoW within 3 seconds. No click is permitted.' if movement else 'Candidate neural preview loading. Focus WoW; return here to inspect the latest cross. No input.')
    def review_latest_evaluation(self):
        from .deployment import latest_candidate
        from tkinter import messagebox
        self._review_candidate(latest_candidate())
    def _review_candidate(self,info):
        from tkinter import messagebox
        if not info['evaluation']:raise ValueError('No completed matching test report. Evaluate candidate first.')
        profile=Profile.read(info['profile']);report=json.loads(info['evaluation'].read_text())
        metrics=report['backends']['selected'];gates=profile.data['promotion']
        text=(f"Independent test: precision={metrics['precision']}, recall={metrics['recall']}, "
              f"false detections/cast={metrics['false_detections_per_cast']['mean']}.\n"
              f"Required: precision >= {gates['min_precision']}, recall >= {gates['min_recall']}, false/cast <= {gates['max_false_per_cast']}.")
        registry=ModelRegistry(self.get('registry'))
        self.details.delete('1.0','end');self.details.insert('end',text)
        try:registry._quality(profile,report)
        except ValueError:
            self.status.set('Not approved for automatic fishing: quality thresholds not met. Candidate preview and armed movement-only test remain available.')
            messagebox.showinfo('Model evaluation — more improvement needed',text+'\n\nAutomatic neural fishing remains disabled. Preview/movement tests do not promote the model.',parent=self)
            return
        if not messagebox.askyesno('Approve evaluated model for live use?',text+'\n\nApprove this exact evaluated model? Live controls remain off until you enable them in Normal fishing.',parent=self):return
        release=registry.register(profile,info['weights'],info['run']/'run.json',info['evaluation'])
        registry.promote(profile,release,self.get('reviewer'))
        self.values['profile'].set(str(info['profile']))
        self.status.set(f'Approved release {release}. Select Neural network in Normal fishing and explicitly enable live controls to use it.')
    def open_trained_folder(self):
        import os
        path=Path('data/training-latest.json')
        if not path.is_file():raise ValueError('No completed model yet. Start training and wait for completion.')
        result=json.loads(path.read_text(encoding='utf-8'))
        checkpoint=Path(result['checkpoint'])
        if result.get('status')!='completed' or not checkpoint.is_file():raise ValueError('The last training run has not produced a completed model.')
        os.startfile(str(checkpoint.parent.resolve()))
    def train_automatic(self):
        import time
        from tkinter import messagebox
        self.stop()
        profile=self.training_profile_default()
        if profile.data['model']['backend']!='neural':raise ValueError('Select the neural profile first; the normal fishing backend will not be changed.')
        from . import dataset as ds
        root=self.get('dataset');data=ds.load(root)
        reviewed=[r for r in data['frames'] if r['annotation']['reviewed'] and r['annotation'].get('review_source')=='human']
        sessions=len({r['session_id'] for r in reviewed})
        if sessions<2:raise ValueError('Review pictures from at least two independent sessions first. Use Label pictures.')
        if data.get('export'):raise ValueError('Select the original recording dataset for automatic preparation.')
        allow_download=messagebox.askyesno('Start training',
            f'Train from {len(reviewed)} reviewed pictures in {sessions} sessions?\n'
            'This prepares the data automatically, requires CUDA (no CPU fallback), and trains 5 passes.\n'
            'Official starter weights may be downloaded. No game input or model activation occurs.\n'
            +('There is no independent test session yet; this will be an initial candidate.' if sessions==2 else 'An independent test partition will be kept out of fitting.'),parent=self)
        if not allow_download:return
        output=Path('runs')/('fishing-initial-'+str(time.time_ns()))
        self.values['output'].set(str(output))
        args=['-u','-m','visual_targeting.autotrain','--profile',self.get('profile'),
              '--dataset',root,'--output',str(output),'--allow-download']
        self.job.start_python(args,python=self.get('python'))
        self.status.set('Automatic preparation/training started. Watch the log; Cancel training / job stops this process. No model is activated.')
        self.automatic_output=str(output)
    def training_profile_default(self):
        if not self.get('profile'):
            path=Path('configs/tasks/fishing-neural-v2.json').resolve()
            self.values['profile'].set(str(path))
        return self.profile()
    def refresh_training_progress(self):
        from . import dataset as ds
        try:
            root=Path(self.get('dataset'))
            if not (root/'manifest.json').exists():
                self.training_progress.set('NEXT: Record examples. No recorded dataset exists at the selected path yet.')
                return
            data=ds.load(root);rows=data['frames']
            reviewed=[r for r in rows if r['annotation']['reviewed'] and r['annotation'].get('review_source')=='human']
            sessions=len({r['session_id'] for r in reviewed})
            if not reviewed:next_step='NEXT: Click 2. Label pictures. Draw a box around each bobber and save.'
            elif not data.get('export') and sessions<2:next_step='NEXT: Record and label another independent session for validation.'
            elif not data.get('export'):next_step='READY: Click Train my reviewed pictures for automatic setup. A third reviewed session adds independent testing.'
            else:next_step='NEXT: Install training support if needed, then click 5. Start training. Training never activates a model.'
            self.training_progress.set(f"{len(rows)} recorded pictures | {len(reviewed)} human-reviewed | {sessions} reviewed sessions.\n{next_step}")
        except (OSError,ValueError,KeyError,TypeError) as exc:self.training_progress.set(f'Dataset needs attention: {exc}')
    def label_pictures(self):
        self.stop()
        if self.job.process is not None and self.job.process.poll() is None:raise ValueError('Cancel or finish the recording/training job before labeling.')
        profile=self.training_profile_default()
        if not self.get('reviewer'):
            from tkinter import simpledialog
            name=simpledialog.askstring('Human reviewer','Your name (saved with the labels you review):',parent=self)
            if not name:return
            self.values['reviewer'].set(name)
        from .label_gui import open_labeler
        open_labeler(self,profile,self.get('dataset'),self.get('reviewer'),self.review_changed)
    def review_changed(self):
        self.refresh_training_progress()
        if getattr(self,'results_panel',None):self.results_panel.refresh()
    def record_training_session(self):
        import uuid
        self.stop();self.training_profile_default()
        self.values['session'].set('visit_'+uuid.uuid4().hex[:12])
        self.values['cast'].set('cast_1')
        if not self.get('hwnd'):
            self.select_window()
            self.status.set('Select the game window, then click Record another session again. Recording never casts for you.')
            return
        from . import dataset as ds
        if (Path(self.get('dataset'))/'manifest.json').exists() and ds.load(self.get('dataset')).get('export'):
            self.values['dataset'].set(getattr(self,'raw_training_dataset','data/dataset'))
        self.use_window_region()
        self.root_after_capture(delay_seconds=10)
    def prepare_dataset(self):
        import time
        self.stop()
        profile=self.training_profile_default()
        from .task_workflow import check_dataset
        data,_=check_dataset(profile,self.get('dataset'),human=True,reviewed_only=True)
        reviewed=[r for r in data['frames'] if r['annotation']['reviewed'] and r['annotation'].get('review_source')=='human']
        if len({r['session_id'] for r in reviewed})<3:raise ValueError('Label examples from at least 3 independent sessions before preparing train/validation/test splits.')
        output=Path('datasets')/('fishing-'+str(time.time_ns()))
        self.values['export_output'].set(str(output))
        self.raw_training_dataset=self.get('dataset')
        self.export_dataset()
        self.pending_export=str(output)
    def start_training_easy(self):
        import time
        self.training_profile_default()
        # A neural profile is explicit; do not silently mutate an evaluated template profile.
        if self.profile().data['model']['backend']!='neural':raise ValueError('Choose the fishing neural profile, then Start training. Existing template settings are not changed automatically.')
        from .task_workflow import check_dataset
        check_dataset(self.profile(),self.get('dataset'),human=True,exported=True)
        import sys,importlib.util
        if Path(self.get('python')).resolve()==Path(sys.executable).resolve() and importlib.util.find_spec('ultralytics') is None:
            raise ValueError('Click 4. Install training support and wait for completion, then Start training again.')
        from tkinter import filedialog,messagebox
        model=self.train_values['model'].get().strip()
        if not Path(model).is_file() and not self.allow_download.get():
            download=messagebox.askyesnocancel('Starter model','Download the official yolo11n.pt starter weights when training begins?\nYes: allow download. No: choose your local .pt weights. Cancel: return without training.',parent=self)
            if download is None:return
            if download:
                self.train_values['model'].set('yolo11n.pt');self.allow_download.set(True)
            else:
                path=filedialog.askopenfilename(title='Choose local pretrained .pt weights',filetypes=[('Pretrained model','*.pt')])
                if not path:return
                self.train_values['model'].set(path)
        self.values['output'].set(str(Path('runs')/('fishing-'+str(time.time_ns()))))
        self.job_command('train')
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
        self.job.start_python(['tools/setup_gpu.py'],python=self.get('python'))
        self.status.set('Installing optional training dependencies into the selected Python environment. This does not train or activate a model.')
    def training_guide(self):
        import webbrowser
        webbrowser.open((Path.cwd()/'docs/TRAINING-GUI.html').resolve().as_uri())
    def get(self,key):return self.values[key].get().strip()
    def profile(self):return Profile.read(self.get('profile'))
    def guard(self,fn):
        try:return fn()
        except Exception as exc:
            from .errors import record_error
            event,path=record_error(getattr(fn,'__name__','gui_action'),exc,{key:self.get(key) for key in ('profile','weights','training_run','dataset','output','hwnd')})
            self.status.set(f'{type(exc).__name__}: {exc} | Error {event}; Open error history ({path or "log unavailable"}).')
    def choose_profile(self):
        path=filedialog.askopenfilename(filetypes=[('Task profile','*.json')])
        if path:self.stop();self.values['profile'].set(path)
    def select_window(self,on_selected=None):
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
            if on_selected:on_selected()
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
        dialog=getattr(self,'teaching_dialog',None)
        if dialog is not None:
            self.teaching_dialog=None
            try:dialog.destroy()
            except tk.TclError:pass
        self.preview.stop()
        if getattr(self,'capture_pending',None):
            self.after_cancel(self.capture_pending);self.capture_pending=None
        self.status.set('Paused / stopped; disarmed')
    def base_args(self):return ['--profile',self.get('profile'),'--registry',self.get('registry')]
    def root_after_capture(self,delay_seconds=3):
        self.stop();args=self.base_args()+['record','--dataset',self.get('dataset'),'--session',self.get('session'),'--cast',self.get('cast'),'--hwnd',self.get('hwnd'),'--region',*self.get('region').split()]
        self.status.set(f'Capture in {delay_seconds} seconds. Focus the game and cast manually; recording cannot click.')
        self.capture_pending=self.after(delay_seconds*1000,lambda:self.guard(lambda:self.job.start(args)))
    def job_command(self,command):
        self.stop()
        if self.profile().data['model']['backend']!='neural':raise ValueError('Choose a neural profile before neural training/evaluation. Normal fishing remains unchanged.')
        output=Path(self.get('output')).resolve();dataset=Path(self.get('dataset')).resolve()
        if output.exists() or output.is_relative_to(dataset) or dataset.is_relative_to(output):
            import time
            output=Path('runs')/('fishing-'+command+'-'+str(time.time_ns()))
            self.values['output'].set(str(output))
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
    def train_teaching_now(self):
        row=getattr(self,'teaching_row',None)
        if row is None:raise ValueError('Start Teach missed bobbers first.')
        if self.job.process is not None and self.job.process.poll() is None:raise ValueError('Training is already running. Your next corrections will be included in the following run.')
        self.model_action('refine',row)
        self.teaching_trained_count=self.teaching_store.count if self.teaching_store else 0
    def teaching_request(self):
        if getattr(self,'teaching_dialog',None) is not None:return
        try:request=self.preview.teacher.requests.get_nowait()
        except queue.Empty:return
        if request.done.is_set() or self.preview.stop_event.is_set():return
        from .teaching import CorrectionStore,correction_dialog
        profile=self.profile()
        if getattr(self,'teaching_store',None) is None:
            self.teaching_store=CorrectionStore(profile,self.teaching_row['run']['checkpoint_sha256'])
        def finished(decision):
            self.teaching_dialog=None
            self.preview.teacher.complete(request)
            if decision=='stop':self.stop();return
            if decision in ('save','negative'):
                self.review_changed()
                if self.teaching_store.count-getattr(self,'teaching_trained_count',0)>=5:
                    try:self.train_teaching_now()
                    except ValueError as exc:self.status.set('Correction saved. '+str(exc))
        try:self.teaching_dialog=correction_dialog(self,request,self.teaching_store,self.get('reviewer'),finished,self.train_teaching_now)
        except Exception:
            self.preview.teacher.complete(request);raise
    def poll(self):
        if self.closed:return
        self.guard(self.teaching_request)
        try:
            image,reason=self.preview.frames.get_nowait();self.status.set(reason)
            if image is not None:
                import cv2 as cv
                h,w=image.shape[:2];image=cv.resize(image,(min(900,w),max(1,round(h*min(900,w)/w))))
                _,encoded=cv.imencode('.png',image);self.photo=tk.PhotoImage(data=base64.b64encode(encoded.tobytes()));self.image.configure(image=self.photo)
                if getattr(self,'results_panel',None):
                    small=cv.resize(image,(min(320,image.shape[1]),max(1,round(image.shape[0]*min(320,image.shape[1])/image.shape[1]))))
                    _,png=cv.imencode('.png',small);self.results_panel.photo=tk.PhotoImage(data=base64.b64encode(png.tobytes()));self.results_panel.live.configure(image=self.results_panel.photo)
        except queue.Empty:pass
        if self.job.process:
            state=self.job.status()
            if getattr(self,'results_panel',None):
                job_key=(str(self.job.log),state)
                changed=job_key!=getattr(self,'last_result_job_state',None)
                if changed:
                    self.results_panel.refresh()
                    detail=''
                    if state.startswith('failed'):
                        from .errors import record_error
                        record_error('worker_failed',RuntimeError(log_tail(self.job.log)),{'log':str(self.job.log),'profile':self.get('profile'),'output':self.get('output')})
                    if state.startswith('failed'):
                        lines=[line.strip() for line in log_tail(self.job.log).splitlines() if line.strip()]
                        if lines:detail=' | '+lines[-1]
                    self.status.set('Job: '+state+detail+' | Open job log for details.')
                self.last_result_job_state=job_key
            if getattr(self,'pending_export',None) and state=='completed':
                self.values['dataset'].set(self.pending_export)
                self.pending_export=None
                self.refresh_training_progress()
            elif getattr(self,'pending_export',None) and state.startswith('failed'):
                self.pending_export=None

            try:
                stat=self.job.log.stat();signature=(str(self.job.log),stat.st_size,stat.st_mtime_ns,state)
            except OSError:signature=(str(self.job.log),state)
            if signature!=getattr(self,'last_log_signature',None):
                self.last_log_signature=signature
                text=log_tail(self.job.log)
                for widget in (self.details,self.training_log):
                    # Preserve a user's position while they inspect an older part of the tail.
                    position=widget.yview();follow=not widget.get('1.0','end').strip() or position[1]>=.99
                    widget.delete('1.0','end')
                    widget.insert('end',f'Job: {state}\nLog: {self.job.log}\n{text}')
                    if follow:widget.see('end')
                    else:widget.yview_moveto(position[0])
        latest=Path('data/training-latest.json')
        if latest.exists():
            try:
                result=json.loads(latest.read_text(encoding='utf-8'))
                if result.get('status')=='completed':
                    self.trained_file.set('Trained candidate file: '+result['checkpoint']+' (not automatically activated)')
            except (OSError,ValueError,KeyError):pass
        self.poll_timer=self.after(150,self.poll)
    def shutdown(self):
        if getattr(self,'poll_timer',None):
            try:self.after_cancel(self.poll_timer)
            except tk.TclError:pass
        self.stop()
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
