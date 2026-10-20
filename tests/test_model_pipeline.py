import copy
import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from visual_targeting import dataset as ds
from visual_targeting.contracts import Box,Frame
from visual_targeting.experiments import TrainConfig,exported_dataset,train
from visual_targeting.evaluation import metrics,latest_queue_age,evaluate,match
from visual_targeting.neural import NeuralDetector

class MetricsTests(unittest.TestCase):
    def row(self,i,truth,predictions,service=2):
        return dict(id=str(i),session_id="session",cast_id="cast",sequence=i,elapsed_seconds=i*.01,
                    captured_at=10+i*.01,capture_finished_at=10+i*.01,truth=truth,predictions=predictions,
                    inference_ms=1,service_ms=service)
    def test_metrics_count_misses_false_detections_and_points(self):
        p=lambda box,score:dict(box=box,score=score,point=[(box[0]+box[2])/2,(box[1]+box[3])/2])
        rows=[self.row(0,[[0,0,4,4]],[p([0,0,4,4],.9),p([10,10,14,14],.5)]),
              self.row(1,[],[p([8,8,12,12],.8)]),self.row(2,[[0,0,40,40]],[])]
        m=metrics(rows)
        self.assertEqual((m["tp"],m["fp"],m["fn"]),(1,2,1))
        self.assertAlmostEqual(m["precision"],1/3)
        self.assertEqual(m["recall"],.5)
        self.assertAlmostEqual(m["ap50"],51/101)
        self.assertEqual(m["small_targets"]["count"],1)
        self.assertEqual(m["small_targets"]["missed"],0)
        self.assertEqual(m["false_detections_per_cast"]["mean"],2)
        self.assertEqual(m["click_point_error"]["samples"],1)
        self.assertEqual(m["click_point_error"]["p95_px"],0)
    def test_no_positives_reports_undefined_ap_not_perfect_accuracy(self):
        m=metrics([self.row(0,[],[])])
        self.assertIsNone(m["map50_95"])
        self.assertIsNone(m["recall"])
        self.assertIsNone(m["click_point_error"]["p95_px"])
    def test_bounded_latest_frame_age_accounts_for_backlog_and_drops(self):
        result=latest_queue_age([self.row(i,[],[],200) for i in range(3)])
        self.assertEqual(result["dropped_frames"],1)
        self.assertEqual(result["processed_frames"],2)
        self.assertAlmostEqual(result["p95_frame_age_ms"],371)
        self.assertFalse(result["live_measurement"])
    def test_duplicate_prediction_cannot_match_one_bobber_twice(self):
        pred=[dict(box=[0,0,10,10],score=.9),dict(box=[0,0,10,10],score=.8)]
        pairs,fp,fn=match(pred,[[0,0,10,10]])
        self.assertEqual((len(pairs),fp,fn),(1,[1],[]))

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.raw=self.base/"raw";self.data=self.base/"export"
        rng=np.random.default_rng(42)
        for session in ("a","b","c"):
            capture=MagicMock();capture.__enter__.return_value=capture
            capture.grab.return_value=rng.integers(0,256,(30,40,4),dtype=np.uint8)
            clock=itertools.count(10,.001)
            ds.record(self.raw,session,"one",(0,0,40,30),max_frames=2,capture_factory=lambda:capture,
                      clock=lambda:next(clock),sleep=lambda _:None)
        data=ds.load(self.raw)
        ds.annotate(self.raw,[dict(frame_id=r["id"],boxes=[dict(class_id=0,space="frame_pixels",x=4,y=4,width=14,height=16)]) for r in data["frames"]])
        ds.export_yolo(self.raw,self.data)
        self.weights=self.base/"pretrained.pt";self.weights.write_bytes(b"test weights")

    def test_train_saves_provenance_and_never_exposes_test_to_trainer(self):
        model=Mock();model.ckpt_path=str(self.weights)
        def fit(**kwargs):
            weights=Path(kwargs["project"])/"fit/weights";weights.mkdir(parents=True)
            (weights/"best.pt").write_bytes(b"mock fitted weights")
        model.train.side_effect=fit
        output=self.base/"train-run"
        checkpoint=train(self.data,output,TrainConfig(model=str(self.weights),epochs=1),model_factory=lambda _:model)
        self.assertTrue(checkpoint.is_file())
        run=json.loads((output/"run.json").read_text())
        self.assertEqual(run["status"],"completed")
        self.assertFalse(run["live_input_enabled"])
        self.assertFalse(run["test_used_for_training"])
        self.assertEqual(model.train.call_args.kwargs["seed"],42)
        self.assertTrue(model.train.call_args.kwargs["deterministic"])
        self.assertNotIn("test:",(output/"data.yaml").read_text())
        heldout={r["image"] for r in ds.load(self.data)["frames"] if r["split"]=="test"}
        used=(output/"train.txt").read_text()+(output/"val.txt").read_text()
        self.assertTrue(all(image not in used.replace("\\","/") for image in heldout))
        self.assertTrue(run["pretrained_sha256"])
        self.assertTrue((output/"requirements-run.txt").is_file())

    def test_failed_training_is_recorded_and_missing_weights_do_not_download(self):
        with self.assertRaises(ValueError):train(self.data,self.base/"missing",TrainConfig(model="missing.pt"),model_factory=Mock())
        model=Mock();model.ckpt_path=str(self.weights);model.train.side_effect=RuntimeError("mock failure")
        output=self.base/"failed"
        with self.assertRaises(RuntimeError):train(self.data,output,TrainConfig(model=str(self.weights)),model_factory=lambda _:model)
        self.assertEqual(json.loads((output/"run.json").read_text())["status"],"failed")

    def test_label_tampering_is_rejected_before_training(self):
        row=ds.load(self.data)["frames"][0]
        (self.data/"labels"/row["split"]/(row["id"]+".txt")).write_text("0 .9 .9 .1 .1")
        with self.assertRaises(ValueError):exported_dataset(self.data)

    def test_evaluation_compares_identical_frames_without_training_and_saves_overlays(self):
        backend=Mock();backend.predict.return_value=[]
        report=evaluate(self.data,self.base/"report",{"one":backend,"two":backend},warmup=1,overlay_limit=1)
        self.assertEqual(report["backends"]["one"]["frame_ids"],report["backends"]["two"]["frame_ids"])
        backend.train.assert_not_called()
        self.assertEqual(len(list((self.base/"report/one").glob("*.png"))),1)
        self.assertFalse(report["live_input_enabled"])
        self.assertEqual(report["status"],"completed")
        heldout=report["sessions"]
        with self.assertRaises(ValueError):evaluate(self.data,self.base/"leak",{"one":backend},provenance={"train_sessions":heldout})
        with self.assertRaises(ValueError):evaluate(self.data,self.base/"bad",{"one":backend},split="train")

    def test_neural_maps_model_results_to_frame_coordinates_without_input(self):
        result=Mock()
        result.boxes.xyxy.detach.return_value.cpu.return_value.numpy.return_value=np.array([[1,2,9,10]])
        result.boxes.conf.detach.return_value.cpu.return_value.numpy.return_value=np.array([.8])
        model=Mock();model.names={0:"bobber"};model.predict.return_value=[result]
        detector=NeuralDetector(self.weights,model_factory=lambda _:model)
        frame=Frame(0,1,np.zeros((20,20,3),np.uint8),Box(0,0,20,20),"bgr")
        self.assertEqual(detector.predict(frame)[0]["point"],[5,6])
        self.assertFalse(model.predict.call_args.kwargs["show"])
        self.assertFalse(model.predict.call_args.kwargs["save"])
        model.names={0:"person"}
        with self.assertRaises(ValueError):NeuralDetector(self.weights,model_factory=lambda _:model)

    def test_evaluate_cli_is_offline_and_template_sources_are_training_only(self):
        tool=ROOT/"tools/model.py"
        args=[str(tool),"evaluate","--dataset",str(self.data),"--output",str(self.base/"cli"),"--backend","template","--warmup","0","--overlays","1"]
        script="import runpy,sys; sys.argv="+repr(args)+";runpy.run_path("+repr(str(tool))+",run_name='__main__'); assert not any(n in sys.modules for n in ('pyautogui','visual_targeting.input','fishing.task','torch','ultralytics','mss'))"
        subprocess.run([sys.executable,"-c",script],capture_output=True,text=True,check=True)
        report=json.loads((self.base/"cli/report.json").read_text())
        train_sessions={r["session_id"] for r in ds.load(self.data)["frames"] if r["split"]=="train"}
        self.assertTrue(all(s["session_id"] in train_sessions for s in report["template_sources"]))

    def test_config_rejects_unknown_and_invalid_training_options(self):
        with self.assertRaises(ValueError):TrainConfig(epochs=0)
        with self.assertRaises(ValueError):TrainConfig(model="model.yaml")
        with self.assertRaises(ValueError):TrainConfig(deterministic="false")

if __name__=="__main__":unittest.main()
