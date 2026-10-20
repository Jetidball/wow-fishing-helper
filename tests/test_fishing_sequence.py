import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import cv2 as cv
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from fishing.sequence import CastTask,Policy,State
from visual_targeting.contracts import Frame,Box
from visual_targeting.detector import TemplateDetector
from fishing.replay import evaluate_sequences

OWN=[10,10,20,20]
OTHER=[60,10,70,20]

class SequenceTests(unittest.TestCase):
    def frame(self,seq,t,boxes=(OWN,),white=False):
        pixels=np.zeros((50,100),np.uint8)
        for b in boxes:pixels[b[1]:b[3],b[0]:b[2]]=255 if white else 20
        return Frame(seq,t,pixels,Box(0,0,100,50))
    def task(self,pre=(),backend="temporal"):
        return CastTask(0,pre,Policy(reaction_seconds=0),backend)
    def feed(self,task,n,t,boxes=(OWN,),white=False,**kw):
        return task.update(self.frame(n,t,boxes,white),boxes,t,**kw)
    def test_unique_new_target_excludes_other_players_bobber(self):
        task=self.task([OTHER])
        for i in range(1,4):self.feed(task,i,i*.1,[OWN,OTHER])
        self.assertEqual(task.track,OWN)
        self.assertEqual(task.state,State.TRACK)
    def test_ambiguous_postcast_selection_abstains_and_expires(self):
        task=self.task()
        for i in range(1,5):self.assertIsNone(self.feed(task,i,i*.1,[OWN,OTHER],True))
        self.feed(task,5,5.1,[])
        self.assertEqual(task.outcome,"acquisition_expired")
        self.assertFalse(task.proposed)
    def test_lost_track_cannot_transfer_to_other_player(self):
        task=self.task([OTHER]);self.feed(task,1,.1,[OWN,OTHER]);self.feed(task,2,.2,[OWN,OTHER])
        self.assertIsNone(self.feed(task,3,.4,[OTHER],True))
        self.feed(task,4,1.1,[OTHER],True)
        self.assertEqual(task.outcome,"lost_track")
    def test_bright_reflection_is_baseline_not_temporal_bite(self):
        for backend,expected in (("baseline",True),("temporal",False)):
            task=self.task(backend=backend)
            for i in range(1,6):self.feed(task,i,i*.1,white=True)
            self.assertEqual(task.proposed,expected)
    def test_transient_brightness_does_not_trigger(self):
        task=self.task()
        for i in range(1,4):self.feed(task,i,i*.1)
        self.assertIsNone(self.feed(task,4,.4,white=True))
        self.assertIsNone(self.feed(task,5,.5))
        self.assertFalse(task.proposed)
    def test_temporal_bite_one_click_then_independent_confirmation(self):
        task=self.task()
        for i in range(1,4):self.feed(task,i,i*.1)
        self.assertIsNone(self.feed(task,4,.4,white=True))
        action=self.feed(task,5,.5,white=True)
        self.assertEqual(action["event_id"],1)
        self.assertFalse(task.click_issued)
        task.acknowledge_click(True,.5)
        for i in range(6,10):self.assertIsNone(self.feed(task,i,i*.1,white=True))
        self.assertIsNone(task.outcome)
        self.feed(task,10,1,white=True,catch_confirmed=True)
        self.assertEqual(task.outcome,"catch_confirmed")
    def test_click_without_confirmation_is_not_a_catch(self):
        task=self.task(backend="baseline")
        self.feed(task,1,.1,white=True);self.feed(task,2,.2,white=True)
        task.acknowledge_click(True,.2)
        self.feed(task,3,3.3,[])
        self.assertEqual(task.outcome,"click_unconfirmed")
    def test_rejected_click_and_unknown_ownership(self):
        task=self.task(None);self.assertEqual(task.outcome,"ownership_unknown")
        task=self.task(backend="baseline")
        self.feed(task,1,.1,white=True);self.feed(task,2,.2,white=True)
        task.acknowledge_click(False,.2);self.assertEqual(task.outcome,"click_rejected")
    def test_stale_duplicates_and_pause_cannot_trigger(self):
        task=self.task()
        self.feed(task,1,.1);self.feed(task,2,.2)
        task.update(self.frame(3,.3,white=True),[OWN],2)
        self.assertFalse(task.proposed)
        self.assertEqual(task.outcome,"lost_track")
        task=self.task();self.feed(task,1,.1,cancelled=True)
        self.assertEqual(task.outcome,"aborted")
    def test_duplicate_frame_does_not_count_as_temporal_evidence(self):
        task=self.task()
        for i in range(1,4):self.feed(task,i,i*.1)
        self.feed(task,4,.4,white=True)
        for _ in range(5):self.feed(task,4,.4,white=True)
        self.assertFalse(task.proposed)
    def test_stale_frame_cannot_contribute_bite_evidence(self):
        task=self.task()
        for i in range(1,4):self.feed(task,i,i*.1)
        task.update(self.frame(4,.31,white=True),[OWN],.82)
        self.assertEqual(task.reason,"stale_frame")
        self.assertFalse(task.proposed)
    def test_capture_failure_ticks_confirmation_deadline(self):
        task=self.task(backend="baseline")
        self.feed(task,1,.1,white=True);self.feed(task,2,.2,white=True)
        task.acknowledge_click(True,.2)
        task.update(None,[],3.3)
        self.assertEqual(task.outcome,"click_unconfirmed")
    def test_runner_honors_cancel_event_without_opening_capture(self):
        from fishing.task import FishingTask
        from settings import Settings
        guard=SimpleNamespace(paused=threading.Event(),check_and_pause=lambda s:False)
        stop=threading.Event();stop.set();factory=Mock()
        task=FishingTask(Settings(),precast=[],guard=guard,cancelled=stop,capture_factory=factory)
        self.assertEqual(task.run(),"aborted")
        factory.assert_not_called()

    def test_template_candidates_expose_multiple_bobbers(self):
        rng=np.random.default_rng(42)
        template=np.zeros((20,20),np.uint8);template[4:16,4:16]=rng.integers(0,255,(12,12),dtype=np.uint8)
        img=np.zeros((50,100),np.uint8);img[10:30,10:30]=template;img[10:30,60:80]=template
        detector=TemplateDetector([cv.Canny(template,80,180)],.9,(80,180))
        candidates=detector.candidates(Frame(1,1,img,Box(0,0,100,50)))
        self.assertEqual(len(candidates),2)
    def test_desktop_facade_defaults_to_no_live_input(self):
        from visual_targeting.input import DesktopFacade,DryRunInput
        with patch.dict("os.environ",{},clear=True):
            self.assertIs(type(DesktopFacade().adapter),DryRunInput)
    def test_stats_count_clicks_separately_from_confirmed_catches(self):
        from stats import Stats
        stats=Stats();stats.record_cast("click_unconfirmed",1)
        self.assertEqual(stats.snapshot()["catches"],0)
        self.assertEqual(stats.snapshot()["clicks_issued"],1)
        stats.record_cast("catch_confirmed",1)
        self.assertEqual(stats.snapshot()["catches"],1)
    def test_runner_dry_run_never_calls_mouse_or_move(self):
        from fishing.task import FishingTask
        from settings import Settings
        s=Settings();s.top_left=(0,0);s.bot_right=(100,50)
        capture=Mock();capture.__enter__=Mock(return_value=capture);capture.__exit__=Mock(return_value=False)
        capture.grab.return_value=cv.cvtColor(self.frame(0,0,white=True).pixels,cv.COLOR_GRAY2BGRA)
        detector=Mock();detector.candidates.return_value=[OWN]
        guard=SimpleNamespace(paused=threading.Event(),check_and_pause=lambda s:False)
        ticks=iter(np.arange(0,20,.01));mouse=Mock();move=Mock()
        task=FishingTask(s,detector,precast=[],bite_backend="baseline",policy=Policy(reaction_seconds=0),
             capture_factory=lambda:capture,guard=guard,mouse=mouse,move=move,clock=lambda:float(next(ticks)),wait_key=lambda _: -1)
        self.assertEqual(task.run(),"click_proposed")
        mouse.rightClick.assert_not_called();move.assert_not_called()

    def test_labeled_sequences_compare_reflections_and_other_players(self):
        # Image-driven segmentation fixture isolates task policy from detector accuracy.
        class FixtureDetector:
            def candidates(self,frame):
                gray=cv.cvtColor(frame.pixels,cv.COLOR_BGR2GRAY)
                n,_,stats,_=cv.connectedComponentsWithStats((gray>0).astype(np.uint8))
                return [[int(x),int(y),int(x+w),int(y+h)] for x,y,w,h,area in stats[1:]]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sequences=[]
            for scenario in ("own_bite_with_other_player","bright_reflection","ambiguous_new_bobbers"):
                def save(name,t,boxes,white=False):
                    image=self.frame(0,t,boxes,white).pixels
                    cv.imwrite(str(root/name),image)
                    return {"image":name,"time":t}
                preboxes=[OTHER] if scenario!="ambiguous_new_bobbers" else []
                pre=save(scenario+"-pre.png",0,preboxes)
                rows=[]
                for i in range(1,10):
                    white=scenario=="bright_reflection" or (scenario=="own_bite_with_other_player" and i>=4)
                    row=save(f"{scenario}-{i}.png",i*.1,[OWN,OTHER],white)
                    row["own_box"]=OWN
                    if scenario=="own_bite_with_other_player" and i>=4:row["bite_event"]="bite-1"
                    if scenario=="own_bite_with_other_player" and i==9:row["catch_confirmed"]=True
                    rows.append(row)
                sequences.append(dict(id=scenario,scenario=scenario,precast=pre,cast_time=0,frames=rows))
            labels=root/"sequences.json";labels.write_text(json.dumps(sequences))
            report=evaluate_sequences(labels,FixtureDetector(),Policy(reaction_seconds=0))
            self.assertFalse(report["live_input_enabled"])
            temporal=report["backends"]["temporal"]
            baseline=report["backends"]["baseline"]
            self.assertEqual(temporal["click_proposals"],1)
            self.assertEqual(temporal["wrong_or_false_clicks"],0)
            self.assertEqual(temporal["missed_bite_events"],0)
            self.assertEqual(baseline["wrong_or_false_clicks"],1)  # static reflection only

if __name__=="__main__":unittest.main()
