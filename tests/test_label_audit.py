import json,tempfile,unittest
from pathlib import Path
from visual_targeting.label_audit import audit_labels

class AuditTests(unittest.TestCase):
    def test_flags_possible_reflections_without_changing_human_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            boxes=[dict(class_id=0,x=10,y=10,width=20,height=10),dict(class_id=0,x=12,y=35,width=20,height=10)]
            data={'version':1,'classes':['bobber'],'sessions':{},'frames':[{'id':'frame1','session_id':'visit','image':'image.png','annotation':{'boxes':boxes}}]}
            path=root/'manifest.json';path.write_text(json.dumps(data));before=path.read_bytes()
            result=audit_labels(root)
            self.assertEqual(result['flagged'],1);self.assertFalse(result['labels_changed']);self.assertEqual(path.read_bytes(),before)
            self.assertIn('check whether',result['findings'][0]['reasons'][0])
