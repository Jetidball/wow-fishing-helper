import copy
import json
import itertools
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,MagicMock
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from visual_targeting.profiles import Profile,WindowIdentity,TaskSession,make_detector
from visual_targeting.lifecycle import ReviewQueue,ModelRegistry
from visual_targeting.contracts import Frame,Box,Detection,Point
from visual_targeting.geometry import Rect,WindowGeometry,Letterbox,Transforms
from visual_targeting import dataset as ds
from visual_targeting.task_workflow import record_task,label,train_task,evaluate_task,check_dataset
from visual_targeting.experiments import TrainConfig,sha
from visual_targeting.local_demo import run_demo
ROOT=Path(__file__).resolve().parents[1]

def profile(neural=False):
    d=json.loads((ROOT/"configs/tasks/local-confirm-v1.json").read_text())
    if neural:d["model"]["backend"]="neural"
    return Profile(d)

class ProfileTests(unittest.TestCase):
    def scene(self,score=.95,label="confirm_button"):
        p=profile();frame=Frame(1,10,np.zeros((100,200,3),np.uint8),Box(-800,100,200,100),"bgr")
        window=WindowIdentity(42,"Fishing helper - local mouse verification only",r"C:\Python312\python.exe")
        geometry=WindowGeometry(42,Rect(-800,100,200,100),96,Rect(-1920,0,1920,1080),Rect(-1920,0,3840,1080))
        transform=Transforms().bind(geometry,Rect(0,0,200,100),Letterbox.fit(200,100,640,640))
        detector=Mock();detector.detect.return_value=Detection(1,10,10.1,Box(-750,120,50,40),Point(-725,140),score,label)
        return p,frame,window,transform,detector
    def test_anchor_windows_classes_and_provenance(self):
        p,frame,window,t,detector=self.scene();session=TaskSession(p,detector)
        target=session.preview(frame,window,t,10.1)
        self.assertEqual((target.x,target.y),(-720,140))
        wrong=WindowIdentity(42,window.title,"other.exe")
        self.assertIsNone(session.preview(frame,wrong,t,10.1))
        detector.detect.return_value=Detection(1,10,10.1,Box(-750,120,50,40),Point(-725,140),.99,"bobber")
        self.assertIsNone(session.preview(frame,window,t,10.1))
    def test_stale_frames_no_inference_and_outcomes_need_postclick_evidence(self):
        p,frame,window,t,d=self.scene();s=TaskSession(p,d)
        self.assertIsNone(s.preview(frame,window,t,11));d.detect.assert_not_called()
        self.assertIsNone(s.check_outcome(window,"local_event","target_2_released",10,10.1))
        s.preview(frame,window,t,10.1)
        s.mark_click(True,10.2)
        self.assertIsNone(s.preview(frame,window,t,10.25))
        self.assertIsNone(s.check_outcome(window,"local_event","target_2_released",10.1,10.3))
        self.assertEqual(s.check_outcome(window,"local_event","target_2_released",10.3,10.3),"confirmed")
        s=TaskSession(p,d);s.preview(frame,window,t,10.1);s.mark_click(True,10.2)
        self.assertEqual(s.check_outcome(window,"local_event","wrong",13.3,13.3),"unconfirmed")
    def test_policy_dispatch_keeps_mouse_interface_and_rejects_wider_freshness(self):
        p,f,w,t,d=self.scene();s=TaskSession(p,d);target=s.preview(f,w,t,10.1)
        mouse=Mock(max_age=1,mode="single-click")
        self.assertFalse(s.execute(mouse,target,"move",w,10.1));mouse.execute.assert_not_called()
        mouse.max_age=.5;mouse.execute.return_value=True
        self.assertTrue(s.execute(mouse,target,"move",w,10.1))
        self.assertTrue(s.execute(mouse,target,"click",w,10.2));self.assertIsNotNone(s.clicked_at)
        self.assertIsNone(s.preview(f,w,t,10.3))
    def test_schema_versions_and_unknown_live_flags_rejected(self):
        p=profile();same=Profile(copy.deepcopy(p.data));self.assertEqual(p.digest,same.digest)
        for key,value in (("schema_version",2),("click_anchor",[1,.5]),("confidence",float("nan"))):
            d=copy.deepcopy(p.data);d[key]=value
            with self.assertRaises(ValueError):Profile(d)
        d=copy.deepcopy(p.data);d["live_input_enabled"]=True
        with self.assertRaises(ValueError):Profile(d)
        d=copy.deepcopy(p.data);d["profile_version"]=2;self.assertNotEqual(Profile(d).digest,p.digest)
    def test_failed_new_preview_invalidates_old_target(self):
        p,f,w,t,d=self.scene();s=TaskSession(p,d);target=s.preview(f,w,t,10.1)
        d.detect.return_value=None
        self.assertIsNone(s.preview(f,w,t,10.2))
        mouse=Mock(max_age=.5,mode="single-click")
        self.assertFalse(s.execute(mouse,target,"click",w,10.3));mouse.execute.assert_not_called()
    def test_unpromoted_neural_weights_need_explicit_offline_candidate_path(self):
        with self.assertRaises(ValueError):make_detector(profile(True),weights="unpromoted.pt")
    def test_candidate_detector_cannot_be_dispatched_to_input(self):
        p,f,w,t,d=self.scene();d.offline_only=True;s=TaskSession(p,d);target=s.preview(f,w,t,10.1)
        mouse=Mock(max_age=.5,mode="single-click")
        self.assertFalse(s.execute(mouse,target,"move",w,10.1));mouse.execute.assert_not_called()
    def test_mismatched_crop_scale_rejected_before_mouse(self):
        p,f,w,t,d=self.scene()
        t=Transforms().bind(t.window,t.crop_logical,Letterbox.fit(100,50,640,640))
        with self.assertRaises(ValueError):TaskSession(p,d).preview(f,w,t,10.1)
    def test_second_task_uses_existing_interfaces_without_real_input(self):
        with tempfile.TemporaryDirectory() as directory:
            result=run_demo(profile(),Path(directory)/"demo")
            self.assertTrue(result["passed"]);self.assertEqual(result["simulated_clicks"],1)
            self.assertEqual(result["crop_point"],[461,240]);self.assertFalse(result["live_input_enabled"])
            self.assertFalse(result["registry_modified"]);self.assertFalse(result["training_data_created"])

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.queue=ReviewQueue(self.root/"queue",capacity=2);self.p=profile()
        self.frame=Frame(1,10,np.zeros((20,30,3),np.uint8),Box(0,0,30,20),"bgr")
    def add(self):return self.queue.add(self.p,self.frame,"low_confidence",suggestion={"box":[1,1,5,5]},source={"session_id":"visit1","cast_id":"cast1"})
    def test_pending_suggestions_never_export_or_auto_accept(self):
        item=self.add();self.assertIsNone(self.add())
        self.assertEqual(self.queue.load()["items"][0]["status"],"pending")
        with self.assertRaises(ValueError):self.queue.export(self.p,self.root/"data")
        with self.assertRaises(ValueError):self.queue.decide(self.p,item,"accept","human")
        self.assertFalse((self.root/"data").exists())
    def test_explicit_human_negative_exports_with_original_session(self):
        item=self.add();self.queue.decide(self.p,item,"accept","reviewer",[])
        self.assertEqual(self.queue.export(self.p,self.root/"data"),1)
        data=ds.validate(self.root/"data");row=data["frames"][0]
        self.assertEqual(row["session_id"],"visit1");self.assertEqual(row["annotation"]["boxes"],[])
        self.assertEqual(row["annotation"]["review_source"],"human");self.assertEqual(data["classes"],["confirm_button"])
        check_dataset(self.p,self.root/"data",human=True)
    def test_changed_images_and_wrong_profile_rejected(self):
        item=self.add();data=copy.deepcopy(self.p.data);data["profile_version"]=2
        with self.assertRaises(ValueError):self.queue.decide(Profile(data),item,"accept","reviewer",[])
        self.queue.decide(self.p,item,"accept","reviewer",[])
        entry=self.queue.load()["items"][0];(self.queue.root/entry["image"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):self.queue.export(self.p,self.root/"data")
    def test_review_overlay_does_not_approve_or_change_source(self):
        item=self.add();row=self.queue.load()["items"][0];source=(self.queue.root/row["image"]).read_bytes()
        output=self.root/"review.png";self.queue.preview(item,output)
        self.assertTrue(output.is_file());self.assertEqual(self.queue.load()["items"][0]["status"],"pending")
        self.assertEqual((self.queue.root/row["image"]).read_bytes(),source)
    def test_uncertainty_from_preview_is_pending(self):
        p,f,w,t,d=ProfileTests().scene(score=.8);session=TaskSession(p,d,self.queue)
        self.assertIsNotNone(session.preview(f,w,t,10.1,source={"session_id":"visit1"}))
        self.assertEqual(self.queue.load()["items"][0]["status"],"pending")

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        data=copy.deepcopy(profile(True).data);data["allowed_classes"]=["confirm_button","status_mark"];self.p=Profile(data)
        self.raw=self.root/"raw";self.export=self.root/"export";rng=np.random.default_rng(5)
        for session in ("a","b","c"):
            capture=MagicMock();capture.__enter__.return_value=capture
            capture.grab.return_value=rng.integers(0,240,(50,70,4),dtype=np.uint8)
            ticks=itertools.count(10,.001)
            ds.record(self.raw,session,"cast1",(0,0,70,50),max_frames=2,capture_factory=lambda:capture,
                clock=lambda:next(ticks),sleep=lambda _:None,classes=self.p.data["allowed_classes"],metadata={"task_id":self.p.task_id})
        self.updates=[{"frame_id":r["id"],"boxes":[{"class_id":i,"space":"frame_pixels","x":4+i*25,"y":4,"width":20,"height":20} for i in (0,1)]} for r in ds.load(self.raw)["frames"]]
        label(self.p,self.raw,self.updates,"reviewer")
        ds.export_yolo(self.raw,self.export)
    def test_all_detections_are_scored_even_when_click_policy_would_abstain(self):
        for update in self.updates:
            update['boxes'].append({'class_id':0,'space':'frame_pixels','x':50,'y':4,'width':15,'height':20})
        label(self.p,self.raw,self.updates,'reviewer')
        self.export=self.root/'export-multiple';ds.export_yolo(self.raw,self.export)
        out,best,_=self.train()
        class Backend:
            def detections(inner,frame):
                return [Detection(frame.sequence,frame.captured_at,frame.captured_at+.001,Box(x,4,w,20),Point(x+w//2,14),.99,'confirm_button') for x,w in ((4,20),(50,15))]
            def detect(inner,frame):raise AssertionError('Single-target policy must not measure all-object recall')
        report=evaluate_task(self.p,self.export,self.root/'eval-multiple',weights=best,training_run=out,detector=Backend())
        metrics=report['backends']['selected']
        self.assertEqual(metrics['recall'],1);self.assertEqual(metrics['precision'],1)
        self.assertEqual(metrics['selection_policy']['ambiguous_frames'],metrics['frames'])
        self.assertEqual(report['detection_metrics_version'],2)

    def test_generic_classes_export_and_human_review_required(self):
        data=ds.validate(self.export);self.assertEqual(data["classes"],["confirm_button","status_mark"])
        row=data["frames"][0];text=(self.export/"labels"/row["split"]/(row["id"]+".txt")).read_text()
        self.assertTrue(text.startswith("0 "));self.assertIn("\n1 ",text)
        # Old programmatic labels without a new explicit review remove prior human provenance.
        ds.annotate(self.raw,[self.updates[0]])
        with self.assertRaises(ValueError):check_dataset(self.p,self.raw,human=True)
    def train(self):
        weights=self.root/"pretrained.pt";weights.write_bytes(b"fake pretrained")
        model=Mock();model.ckpt_path=str(weights)
        def fit(**kwargs):
            folder=Path(kwargs["project"])/"fit/weights";folder.mkdir(parents=True);(folder/"best.pt").write_bytes(b"fake fitted")
        model.train.side_effect=fit;out=self.root/"run"
        best=train_task(self.p,self.export,out,TrainConfig(model=str(weights),epochs=1),model_factory=lambda _:model)
        return out,best,model
    def test_train_records_profile_review_and_generic_names_without_promotion(self):
        out,best,model=self.train();run=json.loads((out/"run.json").read_text())
        self.assertEqual(run["profile_sha256"],self.p.digest);self.assertEqual(run["data_review_source"],"human")
        self.assertIn("status_mark",(out/"data.yaml").read_text());self.assertFalse(run["live_input_enabled"])
        self.assertFalse((self.root/"registry").exists())
    def test_evaluate_same_heldout_frames_and_does_not_register_injected_test_backend(self):
        out,best,_=self.train();backend=Mock()
        def detect(frame):return Detection(frame.sequence,frame.captured_at,frame.captured_at+.001,Box(4,4,20,20),Point(14,14),.99,"confirm_button")
        backend.detect.side_effect=detect
        report=evaluate_task(self.p,self.export,self.root/"evaluation",weights=best,training_run=out,detector=backend)
        self.assertEqual(report["status"],"completed");self.assertFalse(report["live_input_enabled"])
        self.assertEqual(report["backends"]["selected"]["frame_ids"],report["backends"]["template"]["frame_ids"])
        self.assertEqual(report["backends"]["selected"]["recall"],1)
        backend.train.assert_not_called()
        with self.assertRaises(ValueError):ModelRegistry(self.root/"registry").register(self.p,best,out/"run.json",self.root/"evaluation/report.json")
    def test_record_task_checks_allowed_window_and_focus_without_mouse(self):
        root=self.root/"recorded";window=WindowIdentity(42,"Fishing helper - local mouse verification only","python.exe")
        capture=MagicMock();capture.__enter__.return_value=capture;capture.grab.return_value=np.zeros((20,30,4),np.uint8)
        probe=lambda hwnd:(window,Rect(0,0,100,100),42)
        self.assertEqual(record_task(self.p,root,"visit","cast",42,(0,0,30,20),max_frames=1,probe=probe,capture_factory=lambda:capture),1)
        self.assertEqual(ds.load(root)["sessions"]["visit"]["casts"]["cast"]["metadata"]["task_id"],self.p.task_id)
        with self.assertRaises(ValueError):record_task(self.p,self.root/"blocked","s","c",42,(0,0,30,20),probe=lambda h:(window,Rect(0,0,100,100),99),capture_factory=lambda:capture)

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.p=profile(True);self.registry=ModelRegistry(self.root/"registry")
    def candidate(self,name="one",precision=.99,**changes):
        weights=self.root/(name+".pt");weights.write_bytes(name.encode());digest=sha(weights)
        run={"task_id":self.p.task_id,"status":"completed","profile_sha256":self.p.digest,"checkpoint_sha256":digest,"data_review_source":"human","human_review_sha256":"b"*64,"dataset_manifest_sha256":"c"*64,"train_sessions":["train"],"val_sessions":["val"]}
        report=dict(run,selected_backend="neural",split="test",frame_ids=["f"],sessions=["test"],training_provenance_verified=True,backends={"selected":{"precision":precision,"recall":1,"false_detections_per_cast":{"mean":0}}})
        report.update(changes)
        r=self.root/(name+"-run.json");e=self.root/(name+"-eval.json");r.write_text(json.dumps(run));e.write_text(json.dumps(report))
        return weights,r,e
    def register(self,name="one",**kw):return self.registry.register(self.p,*self.candidate(name,**kw))
    def test_register_does_not_activate_and_rollback_only_approved(self):
        first=self.register()
        with self.assertRaises(ValueError):self.registry.active(self.p)
        self.registry.promote(self.p,first,"human");second=self.register("two");self.registry.promote(self.p,second,"human")
        third=self.register("three")
        with self.assertRaises(ValueError):self.registry.rollback(self.p,third,"human")
        self.registry.rollback(self.p,first,"human")
        self.assertEqual(self.registry.active(self.p)["release"],first)
    def test_unevaluated_self_labeled_leaked_and_failed_evidence_rejected(self):
        for changes in ({"checkpoint_sha256":"other"},{"data_review_source":"self"},{"sessions":["train"]},{"status":"failed"},{"training_provenance_verified":False},{"selected_backend":"template"}):
            with self.assertRaises(ValueError):self.register("bad",**changes)
    def test_bad_metrics_or_changed_artifacts_cannot_promote(self):
        release=self.register(precision=.5)
        with self.assertRaises(ValueError):self.registry.promote(self.p,release,"human")
        release=self.register("good");self.registry.promote(self.p,release,"human")
        (self.registry.root/"releases"/release/"weights.pt").write_bytes(b"modified")
        with self.assertRaises(ValueError):self.registry.active(self.p)
    def test_nonfinite_quality_cannot_be_promoted(self):
        release=self.register(precision=float("nan"))
        with self.assertRaises(ValueError):self.registry.promote(self.p,release,"human")
        self.assertIsNone(self.registry.load()["tasks"][self.p.task_id]["active"])
    def test_profile_version_content_cannot_be_reused(self):
        self.register();data=copy.deepcopy(self.p.data);data["click_anchor"]=[.5,.5];other=Profile(data)
        weights,r,e=self.candidate("other");run=json.loads(r.read_text());report=json.loads(e.read_text())
        run["profile_sha256"]=other.digest;report["profile_sha256"]=other.digest;r.write_text(json.dumps(run));e.write_text(json.dumps(report))
        with self.assertRaises(ValueError):self.registry.register(other,weights,r,e)

class CommandTests(unittest.TestCase):
    def test_record_cli_never_imports_input_even_when_capture_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            tool=ROOT/"tools/task.py";p=ROOT/"configs/tasks/local-confirm-v1.json"
            args=[str(tool),"--profile",str(p),"record","--dataset",str(Path(directory)/"raw"),"--session","visit1","--cast","cast1","--hwnd","42","--region","0","0","30","20","--max-frames","1"]
            script="""import builtins,runpy,sys,types
import numpy as np
from unittest.mock import MagicMock
sys.path.insert(0,"""+repr(str(ROOT/"src"))+""")
from visual_targeting.profiles import WindowIdentity
from visual_targeting.geometry import Rect
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name in ('visual_targeting.input','visual_targeting.windows_mouse','pyautogui','pynput','fishing.task','humanize'):
        raise AssertionError('capture loaded input: '+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
window=WindowIdentity(42,'Fishing helper - local mouse verification only','python.exe')
sys.modules['visual_targeting.window_context']=types.SimpleNamespace(query_window=lambda h:(window,Rect(0,0,100,100),42))
capture=MagicMock();capture.__enter__.return_value=capture;capture.grab.return_value=np.zeros((20,30,4),np.uint8)
sys.modules['mss']=types.SimpleNamespace(mss=lambda:capture)
"""
            script+="sys.argv="+repr(args)+";runpy.run_path("+repr(str(tool))+",run_name='__main__')"
            result=subprocess.run([sys.executable,"-c",script],check=True,capture_output=True,text=True)
            self.assertEqual(json.loads(result.stdout)["saved"],1)
    def test_task_cli_describe_loads_no_input_capture_or_ml_modules(self):
        tool=ROOT/"tools/task.py";p=ROOT/"configs/tasks/local-confirm-v1.json"
        script="import sys,runpy;sys.argv="+repr([str(tool),"--profile",str(p),"describe"])+";runpy.run_path("+repr(str(tool))+",run_name='__main__');assert not any(n in sys.modules for n in ('visual_targeting.input','visual_targeting.windows_mouse','pyautogui','pynput','mss','torch','ultralytics'))"
        subprocess.run([sys.executable,"-c",script],check=True,capture_output=True,text=True)

if __name__=="__main__":unittest.main()
