import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, MagicMock, patch
import numpy as np
import cv2 as cv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from visual_targeting import Action, Box, Detection, Frame, Point, Space, TemplateDetector
from visual_targeting.input import Cancelled, DesktopFacade, DryRunInput, WindowsInput
from visual_targeting.queues import LatestQueue
from visual_targeting.replay import frames
from visual_targeting.detector import get_updated_bobber_loc
from settings import Settings

class Contracts(unittest.TestCase):
    def test_frame_coordinates_and_owned_buffer(self):
        image = np.zeros((10, 20), np.uint8)
        frame = Frame(0, 10, image, Box(-80, 30, 20, 10))
        image[:] = 255
        self.assertFalse(frame.pixels.any())
        self.assertFalse(frame.pixels.flags.writeable)
        self.assertEqual(frame.to_screen(Point(4, 2, Space.FRAME)), Point(-76, 32))
        with self.assertRaises(ValueError): frame.to_screen(Point(4, 2))
        with self.assertRaises(ValueError): frame.to_screen(Point(20, 2, Space.FRAME))

    def test_bad_shapes_clocks_and_spaces(self):
        for clock in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError): Frame(0, clock, np.zeros((2, 2), np.uint8), Box(0, 0, 2, 2))
        with self.assertRaises(ValueError): Frame(0, 1, np.zeros((2, 2), np.uint8), Box(0, 0, 3, 2))
        with self.assertRaises(ValueError): Action("move", 2, Point(1, 2, Space.FRAME))
        with self.assertRaises(ValueError): Action("click", 1, frame_sequence=1, captured_at=2)
        with self.assertRaises(ValueError): Detection(0, 2, 1, Box(0, 0, 2, 2), Point(1, 1), .8)
        with self.assertRaises(ValueError): Detection(0, 1, 2, Box(0, 0, 2, 2), Point(8, 8), .8)

    def test_detector_preserves_exact_legacy_match_and_ties(self):
        rng = np.random.default_rng(42)
        gray = rng.integers(0, 255, (80, 100), dtype=np.uint8)
        settings = Settings()
        settings.top_left = (-50, 80)
        edges = cv.Canny(gray, *settings.canny_thresholds)
        template = edges[20:33, 30:45].copy()
        settings.templates = [template, template.copy()]
        detector = TemplateDetector(settings.templates, settings.match_threshold, settings.canny_thresholds, clock=lambda: 12)
        frame = Frame(7, 11, gray, Box(-50, 80, 100, 80))
        result = detector.detect(frame)
        self.assertEqual(result.legacy(), get_updated_bobber_loc(settings, edges))
        self.assertEqual((result.frame_sequence, result.captured_at, result.detected_at), (7, 11, 12))
        self.assertEqual(result.box.space, Space.SCREEN)

    def test_no_match_does_not_retain_a_detection(self):
        template = np.array([[0, 255], [255, 0]], np.uint8)
        detector = TemplateDetector([template], clock=lambda: 12)
        self.assertIsNone(detector.detect(Frame(8, 11, np.zeros((20, 20), np.uint8), Box(0, 0, 20, 20))))

    def test_fishing_task_accepts_an_injected_typed_detector_and_cancellation(self):
        from fishing.task import FishingTask, ABORTED
        from types import SimpleNamespace
        settings = Settings()
        settings.top_left = (0, 0)
        settings.bot_right = (20, 20)
        guard = SimpleNamespace(paused=threading.Event(), check_and_pause=lambda s: False)
        guard.paused.set()
        detector = Mock()
        mouse = Mock()
        task = FishingTask(settings, detector=detector, capture_factory=MagicMock(), mouse=mouse,
                           move=Mock(), delay=Mock(), guard=guard, wait_key=lambda _: -1)
        self.assertEqual(task.run(), ABORTED)
        detector.detect.assert_not_called()
        mouse.rightClick.assert_not_called()

    def test_queue_is_bounded_and_keeps_latest(self):
        q = LatestQueue(2)
        for n in range(100): q.put(n)
        self.assertEqual(q.qsize(), 2)
        self.assertEqual(q.dropped, 98)
        self.assertEqual([q.get_nowait(), q.get_nowait()], [98, 99])
        q.task_done(); q.task_done(); q.join()
        with self.assertRaises(ValueError): LatestQueue(0)

    def test_dry_run_is_bounded_and_cancellation_prevents_input(self):
        adapter = DryRunInput(capacity=2, clock=lambda: 5)
        for _ in range(10): adapter.execute(Action("press", 5, keys=("f",)))
        self.assertEqual(len(adapter.actions), 2)
        self.assertFalse(adapter.execute(Action("click", 5, frame_sequence=0, captured_at=1)))
        adapter.cancelled.set()
        self.assertFalse(adapter.execute(Action("click", 5)))
        adapter.release_all()
        self.assertEqual(adapter.actions[-1].kind, "release_all")

    def test_facade_cancel_interrupts_long_wait_and_releases(self):
        desktop = DesktopFacade()
        adapter = DryRunInput()
        desktop.configure(adapter)
        desktop.cancel()
        with self.assertRaises(Cancelled): desktop.sleep(100)
        with self.assertRaises(Cancelled): desktop.click()
        self.assertEqual(adapter.actions[-1].kind, "release_all")

    def test_windows_adapter_releases_held_keys_on_error_and_cancel(self):
        fake = Mock(FAILSAFE=True)
        with patch.dict(sys.modules, pyautogui=fake), patch("visual_targeting.input.os.name", "nt"):
            adapter = WindowsInput()
            adapter.execute(Action("key_down", 1, keys=("q",)))
            fake.click.side_effect = RuntimeError("desktop failure")
            with self.assertRaises(RuntimeError): adapter.execute(Action("click", 2))
            fake.keyUp.assert_called_with("q")
            self.assertFalse(adapter.held)
            self.assertTrue(fake.FAILSAFE)
            adapter.cancelled.set()
            self.assertFalse(adapter.execute(Action("press", 3, keys=("f",))))

    def test_runtime_input_imports_are_centralized(self):
        for path in (ROOT / "src").rglob("*.py"):
            if path == ROOT / "src/visual_targeting/input.py": continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse(any(n.name == "pyautogui" for n in node.names), path)

    def test_core_import_does_not_load_desktop_or_fishing_runtime(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        script = "import visual_targeting, sys; assert 'pyautogui' not in sys.modules; assert 'settings' not in sys.modules; assert 'fishing.task' not in sys.modules"
        subprocess.run([sys.executable, "-c", script], env=env, check=True)

    def test_replay_order_origin_and_monotonic_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"{i}.png" for i in range(2)]
            for path in paths: cv.imwrite(str(path), np.zeros((8, 9), np.uint8))
            times = iter((10, 11))
            replay = list(frames(paths, origin=(-100, 20), clock=lambda: next(times)))
            self.assertEqual([f.sequence for _, f in replay], [0, 1])
            self.assertEqual(replay[0][1].bounds, Box(-100, 20, 9, 8))
            times = iter((11, 10))
            with self.assertRaises(ValueError): list(frames(paths, clock=lambda: next(times)))

if __name__ == "__main__": unittest.main()
