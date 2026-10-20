import itertools,sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import MagicMock,patch
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from visual_targeting import dataset as ds
from visual_targeting.review_store import ReviewStore
from visual_targeting.profiles import Profile

class ReviewStoreTests(unittest.TestCase):
    def collect(self,root):
        profile=Profile.read(Path(__file__).parents[1]/'configs/tasks/fishing-neural-v2.json')
        capture=MagicMock();capture.__enter__.return_value=capture
        capture.grab.return_value=np.zeros((30,40,4),np.uint8)
        ticks=itertools.count(10,.001)
        ds.record(root,'visit','cast',(0,0,40,30),fps=30,duration=5,max_frames=3,
                  capture_factory=lambda:capture,clock=lambda:next(ticks),sleep=lambda _:None,
                  classes=profile.data['allowed_classes'],metadata={'task_id':profile.task_id})
        return profile
    def test_review_validates_only_selected_picture_and_caches_decode(self):
        with tempfile.TemporaryDirectory() as root:
            profile=self.collect(root);store=ReviewStore(profile,root)
            first=next(iter(store.rows))
            with patch('visual_targeting.review_store.ds.validate',wraps=ds.validate) as validate:
                store.image(first);store.image(first)
                store.save(first,[],'human')
                self.assertEqual(validate.call_count,1)
                self.assertEqual(len(validate.call_args.args[1]['frames']),1)
            frames=ds.load(root)['frames']
            self.assertEqual(frames[0]['annotation']['reviewer'],'human')
            self.assertFalse(frames[1]['annotation']['reviewed'])
            ds.validate(root)  # Full validation still succeeds after incremental edits.
    def test_external_edits_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            profile=self.collect(root);store=ReviewStore(profile,root);first=next(iter(store.rows))
            path=Path(root)/'manifest.json'
            path.write_text(path.read_text()+' ')
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'another process'):store.save(first,[],'human')
            self.assertEqual(path.read_bytes(),before)
    def test_changed_image_is_rejected_even_after_caching(self):
        with tempfile.TemporaryDirectory() as root:
            profile=self.collect(root);store=ReviewStore(profile,root);first=next(iter(store.rows))
            store.image(first)
            path=ds.image_path(root,store.rows[first]['image']);path.write_bytes(path.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'Picture changed'):store.save(first,[],'human')
            self.assertFalse(ds.load(root)['frames'][0]['annotation']['reviewed'])
