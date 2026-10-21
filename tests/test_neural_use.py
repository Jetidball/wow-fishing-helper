import sys,tempfile,time,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from visual_targeting.profiles import Profile,TaskNeuralDetector,TaskSession,WindowIdentity
from visual_targeting.contracts import Frame,Box,Detection,Point
from visual_targeting.geometry import Rect,WindowGeometry,Transforms,Letterbox
from visual_targeting.cursor_feedback import gear_matches

class Tensor:
    def __init__(self,value):self.value=np.array(value)
    def detach(self):return self
    def cpu(self):return self
    def numpy(self):return self.value

class NeuralUseTests(unittest.TestCase):
    def profile(self):
        return Profile.read(Path(__file__).parents[1]/'configs/tasks/fishing-neural-v2.json')
    def test_neural_candidates_add_desktop_origin_once_and_abstain_on_multiple(self):
        boxes=SimpleNamespace(xyxy=Tensor([[10,10,30,40],[50,10,70,40]]),conf=Tensor([.9,.95]),cls=Tensor([0,0]))
        model=Mock();model.names={0:'bobber',1:'loot'};model.predict.return_value=[SimpleNamespace(boxes=boxes)]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'weights.pt';path.write_bytes(b'fake')
            detector=TaskNeuralDetector(self.profile(),path,model_factory=lambda path:model)
            frame=Frame(1,1,np.zeros((100,100,3),np.uint8),Box(-900,200,100,100),'bgr')
            self.assertEqual(detector.candidates(frame),[[-890,210,-870,240],[-850,210,-830,240]])
            self.assertIsNone(detector.detect(frame))
    def test_evaluated_candidate_may_only_execute_movement_not_click(self):
        profile=self.profile()
        frame=Frame(1,10,np.zeros((100,200,3),np.uint8),Box(-800,100,200,100),'bgr')
        window=WindowIdentity(42,'World of Warcraft','Wow.exe')
        geometry=WindowGeometry(42,Rect(-800,100,200,100),96,Rect(-1920,0,1920,1080),Rect(-1920,0,3840,1080))
        transform=Transforms().bind(geometry,Rect(0,0,200,100),Letterbox.fit(200,100,200,100))
        detector=Mock();detector.offline_only=True;detector.movement_test_approved=True
        detector.detect.return_value=Detection(1,10,10.1,Box(-750,120,20,20),Point(-740,130),.95,'bobber')
        session=TaskSession(profile,detector);target=session.preview(frame,window,transform,10.1)
        mouse=Mock();mouse.mode='move';mouse.max_age=.5;mouse.execute.return_value=True
        self.assertTrue(session.execute(mouse,target,'move',window,10.1))
        self.assertFalse(session.execute(mouse,target,'click',window,10.1))
        mouse.mode='single-click'
        self.assertFalse(session.execute(mouse,target,'click',window,10.1))
        self.assertEqual(mouse.execute.call_count,1)
    def test_gear_requires_distinct_shapes_and_same_window(self):
        settings=SimpleNamespace(gear_cursor_handle=20,normal_cursor_handle=10,gear_window_hwnd=42)
        self.assertTrue(gear_matches(settings,lambda:(20,42)))
        self.assertFalse(gear_matches(settings,lambda:(20,43)))
        self.assertFalse(gear_matches(settings,lambda:(10,42)))
        settings.normal_cursor_handle=20
        self.assertFalse(gear_matches(settings,lambda:(20,42)))
    def test_unevaluated_candidate_cannot_run_automatic_fishing(self):
        from fishing.task import FishingTask
        from settings import Settings
        detector=Mock();detector.offline_only=True
        guard=SimpleNamespace(paused=threading.Event(),check_and_pause=lambda settings:False)
        capture=Mock()
        with self.assertRaisesRegex(ValueError,'candidate model'):
            FishingTask(Settings(),detector,precast=[],live_input=True,guard=guard,capture_factory=capture).run()
        capture.assert_not_called()
    def test_guarded_hover_and_right_click_coordinates_and_gear_gate(self):
        from fishing.dispatch import FishingDispatch
        settings=SimpleNamespace(get_monitor=lambda:{'left':-780,'top':120,'width':100,'height':60},require_gear_cursor=True)
        geometry=WindowGeometry(42,Rect(-800,100,200,100),144,Rect(-1920,0,1920,1080),Rect(-1920,0,3840,1080))
        identity=WindowIdentity(42,'World of Warcraft','Wow.exe')
        api=Mock();api.geometry.return_value=geometry;api.foreground.return_value=42;api.cursor.return_value=(-750,130)
        api.buttons_down.return_value=False;api.last_input.return_value=1;api.window_at.return_value=42
        def move(x,y):api.cursor.return_value=(x,y);api.last_input.return_value+=1
        api.move.side_effect=move
        dispatcher=FishingDispatch(settings,threading.Event(),self.profile(),api=api,probe=lambda hwnd:(identity,geometry.client,42))
        frame=Frame(1,time.monotonic(),np.zeros((60,100,4),np.uint8),Box(-780,120,100,60),'bgra')
        with patch('humanize.set_bot_pos'):
            self.assertTrue(dispatcher.move(frame,(-730,150)))
            self.assertEqual(api.cursor.return_value,(-730,150))
            with patch('fishing.dispatch.gear_matches',return_value=False):
                self.assertFalse(dispatcher.click(frame,(-730,150)))
            api.click.assert_not_called()
            with patch('fishing.dispatch.gear_matches',return_value=True):
                self.assertTrue(dispatcher.click(frame,(-730,150)))
            api.click.assert_called_once()
            self.assertFalse(dispatcher.click(frame,(-730,150)))
    def test_windows_right_click_uses_right_button_pair(self):
        from visual_targeting.windows_mouse import WindowsMouse
        mouse=object.__new__(WindowsMouse);calls=[]
        def send(count,events,size):
            calls.append([events[i].u.mi.dwFlags for i in range(count)]);return count
        mouse.user=SimpleNamespace(SendInput=send)
        mouse.click(button='right')
        self.assertEqual(calls,[[8,16]])

    def test_backend_dry_run_candidate_and_live_registry_paths_are_separate(self):
        from fishing.backend import make_fishing_detector
        from settings import Settings
        settings=Settings();settings.detector_backend='neural';settings.neural_weights='candidate.pt'
        with patch('visual_targeting.profiles.make_detector',return_value=object()) as make:
            make_fishing_detector(settings,live_input=False)
            self.assertTrue(make.call_args.kwargs['candidate'])
            self.assertTrue(make.call_args.kwargs['weights'].endswith('candidate.pt'))
            make.reset_mock()
            with patch('visual_targeting.lifecycle.ModelRegistry.active',return_value={'weights_sha256':'approved'}),patch('visual_targeting.experiments.sha',return_value='approved'):
                make_fishing_detector(settings,live_input=True)
            self.assertNotIn('weights',make.call_args.kwargs)
            make.reset_mock()
            with patch('visual_targeting.lifecycle.ModelRegistry.active',return_value={'weights_sha256':'approved'}),patch('visual_targeting.experiments.sha',return_value='different'):
                with self.assertRaisesRegex(ValueError,'differs from the approved'):make_fishing_detector(settings,live_input=True)
            make.assert_not_called()
    def test_cursor_handles_are_not_persisted_as_calibration(self):
        from settings import Settings
        settings=Settings();settings.gear_cursor_handle=123;settings.normal_cursor_handle=456
        settings.detector_backend='neural';settings.hover_on_acquire=False;settings.require_gear_cursor=True
        data=settings.to_dict();restored=Settings();restored.apply(data)
        self.assertEqual(restored.detector_backend,'neural')
        self.assertFalse(restored.hover_on_acquire)
        self.assertTrue(restored.require_gear_cursor)
        self.assertEqual(restored.gear_cursor_handle,0)
        self.assertEqual(restored.normal_cursor_handle,0)

    def test_preview_reuses_fishing_crop_without_double_desktop_offset(self):
        from visual_targeting.application import Preview
        profile=self.profile()
        identity=WindowIdentity(42,'World of Warcraft','Wow.exe')
        client=Rect(-800,100,200,100)
        geometry=WindowGeometry(42,client,144,Rect(-1920,0,1920,1080),Rect(-1920,0,3840,1080))
        api=Mock();api.geometry.return_value=geometry
        capture=Mock();capture.__enter__=Mock(return_value=capture);capture.__exit__=Mock(return_value=False)
        capture.grab.return_value=np.zeros((60,100,4),np.uint8)
        preview=Preview();session=Mock();session.reason='preview_ready'
        def observe(frame,window,transform,now):
            self.assertEqual((frame.bounds.left,frame.bounds.top,frame.bounds.width,frame.bounds.height),(-780,120,100,60))
            self.assertEqual(transform.desktop_crop,Rect(-780,120,100,60))
            target=transform.target(30,20,frame.sequence,frame.captured_at,space='crop')
            self.assertEqual((target.x,target.y),(-750,140))
            preview.stop_event.set()
            return target
        session.preview.side_effect=observe
        with patch('mss.mss',return_value=capture),patch('visual_targeting.windows_mouse.WindowsMouse',return_value=api),patch('visual_targeting.window_context.query_window',return_value=(identity,client,42)),patch('visual_targeting.profiles.make_detector',return_value=Mock()),patch('visual_targeting.profiles.TaskSession',return_value=session):
            preview.start(profile,None,42,region=(-780,120,100,60))
            preview.thread.join(timeout=5)
        self.assertFalse(preview.thread.is_alive())
        image,reason=preview.frames.get_nowait()
        self.assertEqual(reason,'preview_ready')
        self.assertGreater(image[20,30,1],0)
        api.move.assert_not_called();api.click.assert_not_called()
