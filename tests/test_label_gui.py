import itertools,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from visual_targeting.label_gui import annotation_box
from visual_targeting import dataset as ds
from visual_targeting.profiles import Profile

class LabelGuiTests(unittest.TestCase):
    def test_box_transform_and_tiny_targets(self):
        box=annotation_box((20,30),(10,10),.5,100,100,0)
        self.assertEqual((box['x'],box['y'],box['width'],box['height']),(20,20,20,40))
        self.assertEqual(annotation_box((1,1),(2,2),1,10,10,0)['width'],1)
        with self.assertRaises(ValueError):annotation_box((1,1),(1,1),1,10,10,0)
        with self.assertRaises(ValueError):annotation_box((1,1),(2,2),0,10,10,0)

    @unittest.skipUnless(os.name=='nt','Windows GUI')
    def test_explicit_human_boxes_and_negative_save_no_automatic_labels(self):
        import tkinter as tk
        from visual_targeting.label_gui import open_labeler
        profile=Profile.read(Path(__file__).parents[1]/'configs/tasks/fishing-neural-v2.json')
        capture=MagicMock();capture.__enter__.return_value=capture
        capture.grab.return_value=np.zeros((100,100,4),np.uint8)
        ticks=itertools.count(10,.001)
        with tempfile.TemporaryDirectory() as directory:
            ds.record(directory,'visit_1','cast_1',(0,0,100,100),fps=30,duration=10,max_frames=2,
                      capture_factory=lambda:capture,clock=lambda:next(ticks),sleep=lambda _:None,
                      classes=profile.data['allowed_classes'],metadata={'task_id':profile.task_id})
            root=tk.Tk();root.withdraw()
            try:
                top=open_labeler(root,profile,directory,'Human');root.update()
                def widgets(parent):
                    for child in parent.winfo_children():
                        yield child
                        yield from widgets(child)
                def button(text):
                    return next(w for w in widgets(top) if w.winfo_class()=='TButton' and w.cget('text')==text)
                button('Save boxes → next').invoke()
                self.assertFalse(ds.load(directory)['frames'][0]['annotation']['reviewed'])
                canvas=next(w for w in widgets(top) if isinstance(w,tk.Canvas))
                canvas.event_generate('<ButtonPress-1>',x=10,y=20)
                canvas.event_generate('<ButtonRelease-1>',x=30,y=50);root.update()
                button('Save boxes → next').invoke()
                first=ds.load(directory)['frames'][0]['annotation']
                self.assertEqual(first['review_source'],'human')
                self.assertEqual(first['reviewer'],'Human')
                self.assertEqual(first['boxes'][0]['width'],20)
                button('Explicit negative → next').invoke()
                second=ds.load(directory)['frames'][1]['annotation']
                self.assertTrue(second['reviewed']);self.assertEqual(second['boxes'],[])
            finally:root.destroy()
