import sys
import threading
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2 as cv
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import bob_finder as bob
from settings import Settings


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        self.settings.top_left = (-50, 80)
        self.settings.bot_right = (50, 160)
        self.rng = np.random.default_rng(42)
        self.template = self.rng.integers(0, 230, (9, 13), dtype=np.uint8)
        self.settings.templates = [self.template]
        self.image = np.zeros((80, 100), np.uint8)
        self.image[20:29, 30:43] = self.template

    def test_winners_dimensions_not_last_template(self):
        self.settings.templates.append(self.rng.integers(0, 230, (4, 5), dtype=np.uint8))
        target = bob.get_updated_bobber_loc(self.settings, self.image)
        self.assertEqual(target["box"], dict(left=-20, top=100, width=13, height=9))
        self.assertEqual(target["center"], (-13, 104))

    def test_empty_and_invalid_templates_are_missing(self):
        self.settings.templates = [None, np.array([]), np.zeros((3, 3), np.uint8),
                                   np.zeros((90, 110), np.uint8), np.ones((2, 3, 4)),
                                   np.array([[np.nan, 1]], np.float32), "invalid"]
        self.assertIsNone(bob.get_updated_bobber_loc(self.settings, self.image))
        self.settings.templates = []
        self.assertIsNone(bob.get_updated_bobber_loc(self.settings, self.image))

    def test_bad_frames_are_missing(self):
        for image in (None, np.array([]), np.zeros((2, 3, 4)), np.array([[np.nan]], np.float32)):
            self.assertIsNone(bob.get_updated_bobber_loc(self.settings, image))

    def test_weak_match_is_missing(self):
        noise = self.rng.integers(0, 230, self.image.shape, dtype=np.uint8)
        self.assertIsNone(bob.get_updated_bobber_loc(self.settings, noise))

    def test_invalid_threshold_is_explicit(self):
        self.settings.match_threshold = float("nan")
        with self.assertRaises(ValueError):
            bob.get_updated_bobber_loc(self.settings, self.image)

    def run_frames(self, frames, *, splash=False, delay=None, paused=False, key=-1):
        frames = iter(frames)
        capture = Mock()
        capture.__enter__ = Mock(return_value=capture)
        capture.__exit__ = Mock(return_value=False)
        def grab(box):
            try:
                gray = next(frames)
            except StopIteration:
                raise RuntimeError("test ran out of frames")
            if isinstance(gray, Exception):
                raise gray
            return cv.cvtColor(gray, cv.COLOR_GRAY2BGRA)
        capture.grab.side_effect = grab
        guard = SimpleNamespace(paused=threading.Event(), check_and_pause=Mock(return_value=False))
        if paused:
            guard.paused.set()
        self.settings.cast_timeout = 10
        self.settings.miss_chance = 0
        mouse, move = Mock(), Mock()
        ticks = iter(range(100))
        with (patch.object(bob.cv, "Canny", side_effect=lambda im, *a: im),
              patch.object(bob.cv, "destroyAllWindows"),
              patch.object(bob, "is_splash_whitepx", return_value=splash)):
            result = bob.search_and_destroy(
                self.settings, capture_factory=lambda: capture, mouse=mouse, move=move,
                delay=lambda *a: delay(guard) if delay else None, guard=guard,
                clock=lambda: next(ticks), wait_key=lambda _: key)
        return result, mouse, move

    def test_missing_target_never_moves_or_clicks(self):
        result, mouse, move = self.run_frames([np.zeros_like(self.image)] * 12)
        self.assertEqual(result, bob.NO_BITE)
        move.assert_not_called()
        mouse.rightClick.assert_not_called()

    def test_lower_scoring_new_frame_replaces_old_location(self):
        moved = np.zeros_like(self.image)
        changed = self.template.copy()
        changed[0, 0] ^= 32
        moved[40:49, 50:63] = changed
        result, mouse, move = self.run_frames([self.image, moved], splash=True)
        self.assertEqual(result, bob.CAUGHT)
        self.assertEqual(move.call_args.args[1], (6, 124))
        mouse.rightClick.assert_called_once()

    def test_target_disappears_during_delay_no_click(self):
        result, mouse, _ = self.run_frames([self.image] + [np.zeros_like(self.image)] * 12, splash=True)
        self.assertEqual(result, bob.NO_BITE)
        mouse.rightClick.assert_not_called()

    def test_pause_during_reaction_delay_prevents_click(self):
        result, mouse, _ = self.run_frames([self.image], splash=True, delay=lambda guard: guard.paused.set())
        self.assertEqual(result, bob.ABORTED)
        mouse.rightClick.assert_not_called()

    def test_pause_and_quit_controls(self):
        for options in (dict(paused=True), dict(key=ord("q")), dict(key=27)):
            result, mouse, move = self.run_frames([], **options)
            self.assertEqual(result, bob.ABORTED)
            move.assert_not_called()
            mouse.rightClick.assert_not_called()

    def test_capture_failure_does_not_reuse_target(self):
        from mss.exception import ScreenShotError
        result, mouse, _ = self.run_frames(
            [self.image, ScreenShotError("lost capture")] + [np.zeros_like(self.image)] * 12, splash=True)
        self.assertEqual(result, bob.NO_BITE)
        mouse.rightClick.assert_not_called()

    def test_settings_migration_and_roundtrip(self):
        self.settings.apply(dict(imageDir="old-images", timeInSecsBeforeLogout=120, gracefulExit=True))
        self.assertEqual(self.settings.img_dir, "old-images")
        self.assertEqual(self.settings.logout_after_mins, 2)
        self.assertEqual(self.settings.logout_action, "hearth_logout")
        self.settings.match_threshold = .85
        other = Settings()
        other.apply(self.settings.to_dict())
        self.assertEqual(other.to_dict(), self.settings.to_dict())

    def test_template_loader_skips_corrupt_and_blank_images(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / "corrupt.png").write_bytes(b"not an image")
            cv.imwrite(str(directory / "blank.png"), np.zeros((20, 20), np.uint8))
            cv.imwrite(str(directory / "good.png"), self.template)
            self.settings.img_dir = str(directory)
            self.settings.load_images()
            self.assertEqual(len(self.settings.templates), 1)

    def test_replay_cli_real_canny_and_no_desktop_input(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            templates, frames = directory / "templates", directory / "frames"
            templates.mkdir()
            frames.mkdir()
            template = np.zeros((24, 24), np.uint8)
            template[5:19, 5:19] = self.rng.integers(0, 255, (14, 14), dtype=np.uint8)
            image = np.zeros((80, 100), np.uint8)
            image[20:44, 30:54] = template
            cv.imwrite(str(templates / "bob.png"), template)
            cv.imwrite(str(frames / "0001.png"), image)
            cv.imwrite(str(frames / "0002.png"), np.zeros_like(image))
            root = Path(__file__).resolve().parents[1]
            result = subprocess.run(
                [sys.executable, str(root / "tools" / "replay.py"),
                 "--frames", str(frames), "--templates", str(templates)],
                capture_output=True, text=True, check=True)
            rows = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(rows[0]["target"]["box"], dict(left=30, top=20, width=24, height=24))
            self.assertIsNone(rows[1]["target"])


if __name__ == "__main__":
    unittest.main()
