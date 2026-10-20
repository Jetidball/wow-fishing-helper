import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
os.environ['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
from visual_targeting.application import Job,Preview

class ApplicationTests(unittest.TestCase):
    def test_latest_frame_and_disarm(self):
        p=Preview();p.publish('old','old');p.publish('new','new')
        self.assertEqual(p.frames.qsize(),1);self.assertEqual(p.frames.get_nowait(),('new','new'))
        p.arm_event.set();p.stop();self.assertFalse(p.arm_event.is_set());self.assertTrue(p.stop_event.is_set())
    def test_invalid_mode(self):
        with self.assertRaises(ValueError):Preview().start(None,None,1,'automatic')
    def test_process_failure_and_cancel(self):
        actual=subprocess.Popen
        with tempfile.TemporaryDirectory() as root:
            job=Job(root)
            def failed(command,**kw):return actual([sys.executable,'-c',"print('explicit failure');raise SystemExit(7)"],**kw)
            with patch('visual_targeting.application.subprocess.Popen',side_effect=failed):job.start([])
            job.process.wait(timeout=10)
            self.assertIn('failed (exit 7)',job.status());self.assertIn('explicit failure',job.log.read_text())
            def slow(command,**kw):return actual([sys.executable,'-c','import time;time.sleep(60)'],**kw)
            with patch('visual_targeting.application.subprocess.Popen',side_effect=slow):job.start([])
            with self.assertRaises(ValueError):job.start([])
            job.cancel();self.assertIsNotNone(job.process.poll());self.assertTrue(job.stream.closed)
    def test_imports_have_no_training_or_input(self):
        p=subprocess.run([sys.executable,'-c',"import sys;import visual_targeting.app_gui;assert 'ultralytics' not in sys.modules;assert 'torch' not in sys.modules;assert 'visual_targeting.windows_mouse' not in sys.modules"],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
    @unittest.skipUnless(os.name=='nt','Windows GUI smoke')
    def test_panel(self):
        import tkinter as tk
        from visual_targeting.app_gui import TargetingPanel
        root=tk.Tk();root.withdraw()
        try:
            panel=TargetingPanel(root);panel.pack();root.update()
            self.assertEqual(panel.mode.get(),'dry-run');panel.shutdown();self.assertTrue(panel.preview.stop_event.is_set())
        finally:root.destroy()
