"""Miss correction for the normal fishing loop; training never changes its loaded model."""
import atexit,json,time,getpass
from pathlib import Path
from .application import Job
from .teaching import CorrectionStore,CorrectionRequest,correction_dialog

_session=None
class NormalTeacher:
    def __init__(self,profile,model_sha):
        self.profile=profile;self.model_sha=model_sha;self.store=CorrectionStore(profile,model_sha)
        self.job=Job(Path('data/teaching-logs'));self.trained_count=0;self.root=None
        atexit.register(self.job.cancel)
    def train(self):
        if self.job.process is not None and self.job.process.poll() is None:raise ValueError('Training already running; additional corrections stay saved for the next run.')
        from .model_results import model_results
        from .experiments import sha
        rows,_=model_results('.')
        row=next((r for r in rows if r['run'].get('checkpoint_sha256')==self.model_sha and r['run'].get('profile_sha256')==self.profile.digest),None)
        if row is None:raise ValueError('Cannot locate this model training run. Saved corrections are available in Model results.')
        dataset=next((p.parent for p in Path('datasets').glob('*/manifest.json') if sha(p)==row['run']['dataset_manifest_sha256']),None)
        if dataset is None:raise ValueError('Original dataset missing. Corrections are saved; restore the dataset before training.')
        output=Path('runs')/('fishing-taught-'+str(time.time_ns()))
        import sys
        python=Path('.venv-gpu/Scripts/python.exe')
        self.job.start_python(['-u','-m','visual_targeting.improvement','--run',str(row['run_dir']),'--dataset',str(dataset),
            '--new-data',str(self.store.root),'--output',str(output),'--device','0' if self.profile.data['model']['device'] in ('1','cuda:1') else '1'],python=str(python.resolve()) if python.exists() else sys.executable)
        self.trained_count=self.store.count
    def ask(self,settings,frame,cancelled=None):
        import tkinter as tk
        from loguru import logger
        if self.root is None:self.root=tk.Tk();self.root.withdraw()
        request=CorrectionRequest(frame)
        def finished(decision):
            if decision=='stop':settings.teach_on_miss=False
            if decision in ('save','negative') and self.store.count-self.trained_count>=5:
                try:self.train();logger.info('Background teaching refinement started: {}',self.job.log)
                except ValueError as exc:logger.warning('Correction saved; training: {}',exc)
        dialog=correction_dialog(self.root,request,self.store,getpass.getuser(),finished,self.train)
        def check_stop():
            if not dialog.winfo_exists():return
            if cancelled is not None and cancelled.is_set():dialog.destroy();return
            dialog.after(100,check_stop)
        check_stop();self.root.wait_window(dialog)
        # Human mouse movement can set takeover pause. Keep that pause until the user presses F9.
        logger.info('Teaching finished: {} saved corrections. Current model unchanged. If paused, focus WoW and press F9.',self.store.count)

def handle_miss(settings,detector,frame,cancelled=None):
    global _session
    if settings.detector_backend!='neural':return
    from .profiles import Profile
    from settings import resolve_path
    from .input import desktop
    desktop.release_all()
    profile=Profile.read(resolve_path(settings.neural_profile));digest=getattr(detector,'artifact_sha256',None)
    if _session is None or (_session.profile.digest,_session.model_sha)!=(profile.digest,digest):_session=NormalTeacher(profile,digest)
    _session.ask(settings,frame,cancelled)
