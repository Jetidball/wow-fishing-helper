import unittest,tempfile,copy,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import numpy as np
from visual_targeting import dataset as ds
from visual_targeting.gpu import require_gpu
from visual_targeting.improvement import ExampleCollector,prepare_refinement
from visual_targeting.profiles import Profile
from visual_targeting.contracts import Frame,Box

class ImprovementTests(unittest.TestCase):
    def test_gpu_refuses_cpu_missing_cuda_and_invalid_index(self):
        cuda=SimpleNamespace(is_available=lambda:True,device_count=lambda:2)
        torch=SimpleNamespace(cuda=cuda)
        for device in ('cpu','auto','-1','0,1','3'):
            with self.assertRaises(ValueError):require_gpu(device,torch)
        self.assertEqual(require_gpu('cuda:1',torch),'1')
        torch.cuda.is_available=lambda:False
        with self.assertRaises(ValueError):require_gpu('0',torch)
    def record(self,root,session,review=True):
        capture=MagicMock();capture.__enter__.return_value=capture
        capture.grab.return_value=np.full((20,30,4),100,np.uint8)
        ds.record(root,session,'cast1',(0,0,30,20),max_frames=1,capture_factory=lambda:capture)
        row=ds.load(root)['frames'][-1]
        if review:ds.annotate(root,[{'frame_id':row['id'],'boxes':[dict(class_id=0,space='frame_pixels',x=2,y=3,width=6,height=7)]}],reviewer='human')
        return row
    def test_refinement_preserves_old_splits_and_excludes_unreviewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'raw';new=root/'new'
            for session in ('one','two','three'):self.record(raw,session)
            ds.export_yolo(raw,root/'base');base=ds.load(root/'base')
            self.record(new,'four');unreviewed=self.record(new,'five',False)
            output=prepare_refinement(root/'base',new,root/'refined')
            result=ds.validate(output)
            for row in base['frames']:
                other=next(r for r in result['frames'] if r['id']==row['id'])
                self.assertEqual(other['split'],row['split']);self.assertEqual(other['annotation'],row['annotation'])
            self.assertNotIn(unreviewed['id'],[r['id'] for r in result['frames']])
            self.assertEqual(result['export']['session_splits']['four'],'train')
            self.assertEqual(len(ds.load(raw)['frames']),3)
    def test_refinement_requires_new_human_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'raw'
            for session in ('one','two','three'):self.record(raw,session)
            ds.export_yolo(raw,root/'base')
            with self.assertRaisesRegex(ValueError,'No new human-reviewed'):prepare_refinement(root/'base',raw,root/'refined')
    def test_collector_is_bounded_unreviewed_and_preserves_crop(self):
        profile=Profile.read('configs/tasks/fishing-neural-v2.json')
        with tempfile.TemporaryDirectory() as tmp:
            collector=ExampleCollector(tmp,profile,'abc',max_frames=1,interval=0)
            frame=Frame(3,1,np.full((20,30,3),100,np.uint8),Box(-50,10,30,20),'bgr')
            self.assertEqual(collector.add(profile,frame,'missing_or_ambiguous'),1)
            self.assertIsNone(collector.add(profile,frame,'periodic'))
            data=ds.validate(tmp);row=data['frames'][0]
            self.assertFalse(row['annotation']['reviewed']);self.assertEqual(row['annotation']['boxes'],[])
            self.assertEqual(row['crop_transform']['screen_to_frame'],[[1,0,50],[0,1,-10],[0,0,1]])
            metadata=data['sessions'][row['session_id']]['casts'][row['cast_id']]['metadata']
            self.assertTrue(metadata['human_review_required']);self.assertTrue(metadata['cast_id_is_observation_not_game_cast'])

    def test_results_actions_are_explained_and_do_not_arm_automatically(self):
        import tkinter as tk
        from tkinter import ttk
        from visual_targeting.app_gui import TargetingPanel
        root=tk.Tk();root.withdraw();panel=TargetingPanel(root);root.update()
        try:
            actions=[w for w in panel.model_results.winfo_children() if isinstance(w,ttk.LabelFrame)][0]
            buttons=actions.winfo_children()
            self.assertGreaterEqual(len(buttons),13)
            for button in buttons:self.assertTrue(button.input_description)
            self.assertFalse(panel.preview.arm_event.is_set())
            with patch.object(panel,'selected_info',return_value={'profile':Path('configs/tasks/fishing-neural-v2.json')}),patch('visual_targeting.app_gui.ModelRegistry') as registry:
                registry.return_value.active.side_effect=ValueError('not approved')
                with self.assertRaisesRegex(ValueError,'not approved'):panel.model_action('click',{'run':{'checkpoint_sha256':'x'}})
            self.assertEqual(panel.mode.get(),'dry-run')
            self.assertFalse(panel.preview.arm_event.is_set())
        finally:panel.shutdown();root.destroy()
