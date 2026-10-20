"""Installed-package smoke: no screen capture, model loading, training or input."""
import importlib.metadata as md
import json,sys,tkinter as tk
from pathlib import Path
from visual_targeting.app_gui import TargetingPanel
assert 'ultralytics' not in sys.modules and 'torch' not in sys.modules
root=tk.Tk();root.withdraw()
panel=TargetingPanel(root);panel.pack();root.update()
assert panel.mode.get()=='dry-run'
panel.shutdown();root.destroy()
assert 'visual_targeting.windows_mouse' not in sys.modules
from visual_targeting.application import Job
import tempfile
with tempfile.TemporaryDirectory() as directory:
    job=Job(directory);job.start(['--help']);job.process.wait(timeout=20)
    assert job.status()=='completed',job.log.read_text()
report={'worker_cli':True,'passed':True,'python':sys.version,'package':md.version('visual-targeting'),'gui_smoke':True,'live_input_enabled':False,'environment':sys.prefix}
Path(sys.argv[1]).write_text(json.dumps(report,indent=2))
print(json.dumps(report))
