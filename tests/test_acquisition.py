import ast,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from fishing.sequence import CastTask,Policy,State
from visual_targeting.contracts import Frame,Box

class AcquisitionTests(unittest.TestCase):
    def frame(self,sequence,t):
        return Frame(sequence,t,np.zeros((50,100),np.uint8),Box(0,0,100,50))
    def test_landing_wait_does_not_consume_observation_window(self):
        task=CastTask(0,[],Policy(acquire_seconds=5),acquisition_started=3)
        task.update(self.frame(1,5.1),[[10,10,20,20]],5.1)
        task.update(self.frame(2,5.2),[[10,10,20,20]],5.2)
        self.assertEqual(task.state,State.TRACK)
    def test_cast_deadline_still_bounds_delayed_search(self):
        task=CastTask(0,[],Policy(acquire_seconds=10,cast_seconds=5),acquisition_started=4)
        task.update(self.frame(1,5.1),[],5.1)
        self.assertEqual(task.outcome,'no_bite')
    def test_ambiguous_and_precast_rejections_have_different_explanations(self):
        own=[10,10,20,20];other=[60,10,70,20]
        task=CastTask(0,[])
        task.update(self.frame(1,.1),[own,other],.1)
        self.assertEqual(task.reason,'ambiguous_target')
        self.assertEqual(task.eligible_count,2)
        task.update(None,[],5.1)
        self.assertEqual(task.last_reason,'ambiguous_target')
        task=CastTask(0,[own])
        task.update(self.frame(1,.1),[own],.1)
        self.assertEqual(task.reason,'only_precast_targets')
        self.assertEqual(task.excluded_count,1)
    def test_stale_frame_is_not_accepted(self):
        task=CastTask(0,[])
        task.update(self.frame(1,.1),[[10,10,20,20]],.7)
        self.assertEqual(task.stale_frames,1)
        self.assertEqual(task.hits,0)
    def test_settings_migration_preserves_old_values_and_new_timeout(self):
        from settings import Settings
        settings=Settings();settings.apply({'matchThreshold':.8,'autoLoot':True})
        self.assertEqual(settings.acquire_timeout,8)
        settings.apply({'acquireTimeout':11})
        self.assertEqual(settings.acquire_timeout,11)
        self.assertEqual(settings.match_threshold,.8)
    def test_failure_report_includes_score_and_local_image(self):
        from fishing.diagnostics import save_acquisition_report
        from settings import Settings
        settings=Settings();settings.top_left=(0,0);settings.bot_right=(100,50)
        task=CastTask(0,[]);task.update(self.frame(1,.1),[],.1);task.update(None,[],5.1)
        with tempfile.TemporaryDirectory() as directory:
            report=save_acquisition_report(settings,task,self.frame(2,5.1),directory=directory)
            self.assertEqual(report['last_reason'],'missing_target')
            self.assertTrue(Path(report['image_path']).is_file())
            self.assertEqual(json.loads(Path(report['report_path']).read_text())['outcome'],'acquisition_expired')
    def test_gui_adapter_controls_tracker_live_mode_and_force_dry_run_wins(self):
        from visual_targeting.input import DryRunInput,WindowsInput
        source=ast.parse((Path(__file__).parents[1]/'src/state_machine.py').read_text())
        node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='synchronize_input_mode')
        adapter=SimpleNamespace(adapter=DryRunInput())
        adapter.configure=lambda value:setattr(adapter,'adapter',value)
        env={'pag':adapter,'DryRunInput':DryRunInput}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'state_machine.py','exec'),env)
        self.assertFalse(env['synchronize_input_mode']())
        # Construct only a type marker: no Windows API or real input initialization.
        adapter.adapter=object.__new__(WindowsInput)
        self.assertTrue(env['synchronize_input_mode']())
        self.assertFalse(env['synchronize_input_mode'](force_dry_run=True))
        self.assertIs(type(adapter.adapter),DryRunInput)

    def test_runner_search_budget_starts_after_landing_wait_and_saves_evidence(self):
        import threading
        from unittest.mock import MagicMock,patch
        from fishing.task import FishingTask
        from fishing.diagnostics import save_acquisition_report
        from settings import Settings
        settings=Settings();settings.top_left=(0,0);settings.bot_right=(100,50)
        current=[3.0]
        def wait(milliseconds):
            current[0]+=.25
            return -1
        capture=MagicMock();capture.__enter__.return_value=capture
        capture.grab.return_value=np.zeros((50,100,4),np.uint8)
        detector=Mock();detector.candidates.return_value=[]
        guard=SimpleNamespace(paused=threading.Event(),check_and_pause=lambda settings:False)
        with tempfile.TemporaryDirectory() as directory:
            def report(*args,**kwargs):
                return save_acquisition_report(*args,**kwargs,directory=directory)
            with patch('fishing.diagnostics.save_acquisition_report',side_effect=report):
                task=FishingTask(settings,detector,precast=[],cast_started=0,policy=Policy(acquire_seconds=5),
                                 clock=lambda:current[0],wait_key=wait,capture_factory=lambda:capture,guard=guard)
                self.assertEqual(task.run(),'acquisition_expired')
            self.assertGreaterEqual(current[0],8)
            evidence=json.loads((Path(directory)/'acquisition-latest.json').read_text())
            self.assertEqual(evidence['last_reason'],'missing_target')
            self.assertGreater(evidence['fresh_observations'],0)
