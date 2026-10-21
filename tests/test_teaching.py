import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import numpy as np
from visual_targeting.teaching import MissTeacher,CorrectionStore,CorrectionRequest,correction_dialog
from visual_targeting.contracts import Frame,Box
from visual_targeting.profiles import Profile
from visual_targeting import dataset as ds

class TeachingTests(unittest.TestCase):
    def frame(self):return Frame(3,time.monotonic(),np.full((40,60,3),100,np.uint8),Box(-100,5,60,40),'bgr')
    def profile(self):return Profile.read('configs/tasks/fishing-neural-v2.json')
    def test_miss_prompt_is_bounded_and_cancelable(self):
        teacher=MissTeacher(delay=2);frame=self.frame()
        self.assertIsNone(teacher.consider(frame,'missing_or_ambiguous',0))
        request=teacher.consider(frame,'missing_or_ambiguous',2)
        self.assertIsNotNone(request);self.assertIsNone(teacher.consider(frame,'missing_or_ambiguous',3))
        self.assertFalse(np.shares_memory(frame.pixels,request.frame.pixels));self.assertTrue(np.any(request.frame.pixels))
        teacher.stop();self.assertTrue(request.done.is_set());self.assertTrue(teacher.requests.empty())
    def test_found_or_stale_frames_do_not_trigger_teaching(self):
        teacher=MissTeacher(delay=2)
        teacher.consider(self.frame(),'missing_or_ambiguous',0)
        for reason in ('preview_ready','processing_stale','stale_frame'):
            self.assertIsNone(teacher.consider(self.frame(),reason,3))
            self.assertIsNone(teacher.consider(self.frame(),'missing_or_ambiguous',4))
    def test_saved_corrections_are_human_reviewed_with_crop_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CorrectionStore(self.profile(),'model-sha',tmp)
            boxes=[dict(class_id=0,space='frame_pixels',x=4,y=5,width=8,height=9)]
            first=store.save(self.frame(),boxes,'reviewer');second=store.save(self.frame(),[],'reviewer')
            data=ds.validate(tmp);self.assertEqual(len(data['sessions']),1)
            self.assertEqual([r['annotation']['review_source'] for r in data['frames']],['human','human'])
            self.assertEqual(data['frames'][0]['annotation']['boxes'],boxes)
            self.assertNotEqual(first,second)
    def test_correction_dialog_all_buttons_have_tooltips_and_skip_saves_nothing(self):
        import tkinter as tk
        from tkinter import ttk
        with tempfile.TemporaryDirectory() as tmp:
            root=tk.Tk();root.withdraw();store=CorrectionStore(self.profile(),'sha',tmp);done=[]
            top=correction_dialog(root,CorrectionRequest(self.frame()),store,'reviewer',done.append)
            root.update();buttons=[]
            def walk(w):
                for child in w.winfo_children():
                    if isinstance(child,ttk.Button):buttons.append(child);self.assertTrue(child.input_description)
                    walk(child)
            walk(top)
            next(b for b in buttons if b.cget('text')=='Skip & continue').invoke()
            self.assertEqual(done,['skip']);self.assertFalse((Path(tmp)/'manifest.json').exists());root.destroy()
    def test_background_refinement_does_not_stop_active_teaching(self):
        import tkinter as tk
        from visual_targeting.app_gui import TargetingPanel
        root=tk.Tk();root.withdraw();panel=TargetingPanel(root);root.update()
        try:
            panel.preview.teaching=True
            with patch.object(panel,'selected_info',return_value={'run':Path('runs/fake')}),patch.object(panel,'original_dataset',return_value=Path('datasets/fake')),patch.object(panel,'recommended_step',return_value=('refine','ready')),patch.object(panel,'stop') as stopped,patch.object(panel.job,'start_python') as started:
                panel.model_action('refine',{})
                stopped.assert_not_called();started.assert_called_once()
                self.assertIn('visual_targeting.improvement',started.call_args.args[0])
        finally:panel.shutdown();root.destroy()
    def test_teaching_setting_migrates_and_persists(self):
        from settings import Settings
        s=Settings();s.apply({});self.assertFalse(s.teach_on_miss)
        s.apply({'teachOnMiss':True});self.assertTrue(s.to_dict()['teachOnMiss'])

    def test_dialog_saves_drawn_box_and_resumes_without_game_input(self):
        import tkinter as tk
        from tkinter import ttk
        with tempfile.TemporaryDirectory() as tmp:
            root=tk.Tk();root.withdraw();store=CorrectionStore(self.profile(),'sha',tmp);done=[]
            top=correction_dialog(root,CorrectionRequest(self.frame()),store,'human',done.append)
            root.update()
            canvas=next(w for w in top.winfo_children() if isinstance(w,tk.Canvas))
            canvas.event_generate('<ButtonPress-1>',x=4,y=5)
            canvas.event_generate('<B1-Motion>',x=14,y=18)
            canvas.event_generate('<ButtonRelease-1>',x=14,y=18)
            frame=next(w for w in top.winfo_children() if isinstance(w,ttk.Frame))
            next(b for b in frame.winfo_children() if b.cget('text')=='Save correction & continue').invoke()
            self.assertEqual(done,['save'])
            data=ds.validate(tmp);box=data['frames'][0]['annotation']['boxes'][0]
            self.assertEqual((box['x'],box['y'],box['width'],box['height']),(4,5,10,13))
            root.destroy()
    def test_main_app_has_tooltips_on_every_button(self):
        import tkinter as tk
        from tkinter import ttk
        from gui import App
        from settings import Settings
        app=App(Settings());app.root.withdraw();app.root.update()
        try:
            def walk(w):
                for child in w.winfo_children():
                    if isinstance(child,(tk.Button,ttk.Button,tk.Checkbutton,ttk.Checkbutton,tk.Radiobutton,ttk.Radiobutton)):
                        self.assertTrue(getattr(child,'input_description',''),str(child.cget('text')))
                    walk(child)
            walk(app.root)
            self.assertFalse(app.live_controls.get())
        finally:app.cancel()
