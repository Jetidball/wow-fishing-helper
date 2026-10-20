import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))

@unittest.skipUnless(os.name=='nt','Windows GUI')
class AutomaticTrainingTests(unittest.TestCase):
    def test_prefill_and_single_training_job(self):
        import tkinter as tk
        from visual_targeting.app_gui import TargetingPanel
        root=tk.Tk();root.withdraw()
        panel=TargetingPanel(root);root.update()
        try:
            self.assertTrue(panel.get('reviewer'))
            self.assertEqual(panel.profile().data['model']['backend'],'neural')
            data={'frames':[{'session_id':s,'annotation':{'reviewed':True,'review_source':'human'}} for s in ('one','two')]}
            with patch('visual_targeting.dataset.load',return_value=data),patch('tkinter.messagebox.askyesno',return_value=True),patch.object(panel.job,'start_python') as start:
                panel.train_automatic()
            args=start.call_args.args[0]
            self.assertIn('visual_targeting.autotrain',args)
            self.assertIn('--allow-download',args)
            self.assertNotIn('--live-input',args)
            self.assertEqual(panel.mode.get(),'dry-run')
        finally:panel.shutdown();root.destroy()
    def test_confirmation_cancellation_does_not_launch(self):
        import tkinter as tk
        from visual_targeting.app_gui import TargetingPanel
        root=tk.Tk();root.withdraw();panel=TargetingPanel(root);root.update()
        try:
            data={'frames':[{'session_id':s,'annotation':{'reviewed':True,'review_source':'human'}} for s in ('one','two')]}
            with patch('visual_targeting.dataset.load',return_value=data),patch('tkinter.messagebox.askyesno',return_value=False),patch.object(panel.job,'start_python') as start:
                panel.train_automatic()
            start.assert_not_called()
        finally:panel.shutdown();root.destroy()
