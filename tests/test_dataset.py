import ast
import copy
import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock
import cv2 as cv
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from visual_targeting import dataset as ds

class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "dataset"

    def collect(self, session="visit1", cast="cast1", count=2, frames=None):
        image = np.zeros((20, 30, 4), np.uint8)
        image[:] = [11, 99, 220, 255]
        capture = MagicMock()
        capture.__enter__.return_value = capture
        capture.grab.side_effect = frames if frames is not None else lambda region: image
        ticks = itertools.count(10, .001)
        saved = ds.record(self.root, session, cast, (-100, 50, 30, 20), fps=30,
                          duration=10, max_frames=count, capture_factory=lambda: capture,
                          clock=lambda: next(ticks), sleep=lambda _: None)
        return saved

    def box(self, **change):
        return dict(class_id=0, space="frame_pixels", x=3, y=4, width=12, height=8, **change)

    def test_recording_keeps_color_timing_ids_and_transform(self):
        self.assertEqual(self.collect(), 2)
        data = ds.validate(self.root)
        first, second = data["frames"]
        self.assertEqual((first["session_id"], first["cast_id"]), ("visit1", "cast1"))
        self.assertEqual(first["sequence"], 0)
        self.assertGreater(second["captured_at"], first["captured_at"])
        self.assertGreaterEqual(first["capture_finished_at"], first["captured_at"])
        self.assertEqual(first["crop_transform"]["screen_to_frame"], [[1,0,100],[0,1,-50],[0,0,1]])
        image = cv.imread(str(ds.image_path(self.root, first["image"])))
        self.assertEqual(image[0,0].tolist(), [11, 99, 220])
        self.assertEqual(first["annotation"], dict(reviewed=False, boxes=[], bite=None))
        with self.assertRaises(ValueError): self.collect()

    def test_negative_is_explicit_and_bite_alone_does_not_mark_reviewed(self):
        self.collect()
        a, b = ds.load(self.root)["frames"]
        ds.annotate(self.root, [{"frame_id": a["id"], "boxes": [], "bite": "no_bite"},
                               {"frame_id": b["id"], "bite": "splash"}])
        data = ds.validate(self.root)
        self.assertTrue(data["frames"][0]["annotation"]["reviewed"])
        self.assertFalse(data["frames"][1]["annotation"]["reviewed"])
        output = self.base / "yolo"
        self.assertEqual(ds.export_yolo(self.root, output), dict(train=1, val=0, test=0))
        self.assertEqual((output / "labels/train" / (a["id"] + ".txt")).read_text(), "")
        self.assertEqual(ds.validate(output)["export"]["excluded_unreviewed"], 1)

    def test_invalid_box_rejects_whole_batch_without_clipping(self):
        self.collect()
        a, b = ds.load(self.root)["frames"]
        before = (self.root / "manifest.json").read_bytes()
        for change in ({"x": -1}, {"width": 0}, {"height": float("nan")}, {"width": 40}, {"space": "screen_pixels"}, {"class_id": 1}):
            box = self.box(); box.update(change)
            with self.assertRaises(ValueError):
                ds.annotate(self.root, [{"frame_id": a["id"], "boxes": []}, {"frame_id": b["id"], "boxes": [box]}])
            self.assertEqual((self.root / "manifest.json").read_bytes(), before)

    def test_yolo_values_and_session_splits_have_no_frame_leakage(self):
        for session in ("a", "b", "c"):
            for cast in ("one", "two"): self.collect(session, cast)
        data = ds.load(self.root)
        ds.annotate(self.root, [{"frame_id": r["id"], "boxes": [self.box()]} for r in data["frames"]])
        output = self.base / "export"
        counts = ds.export_yolo(self.root, output, val=.2, test=.1, seed=17)
        self.assertEqual(counts, dict(train=4, val=4, test=4))
        exported = ds.validate(output)
        sessions = {}
        for row in exported["frames"]:
            sessions.setdefault(row["session_id"], set()).add(row["split"])
            values = (output / "labels" / row["split"] / (row["id"] + ".txt")).read_text().split()
            self.assertEqual(values[0], "0")
            np.testing.assert_allclose([float(x) for x in values[1:]], [.3, .4, .4, .4])
        self.assertTrue(all(len(splits) == 1 for splits in sessions.values()))
        self.assertEqual(ds.session_splits(["a","b","c"], seed=17), exported["export"]["session_splits"])
        with self.assertRaises(ValueError): ds.export_yolo(self.root, output)

    def test_preview_outputs_overlay_without_modifying_recording(self):
        self.collect()
        row = ds.load(self.root)["frames"][0]
        original = ds.image_path(self.root, row["image"]).read_bytes()
        ds.annotate(self.root, [{"frame_id": row["id"], "boxes": [self.box()], "bite": "splash"}])
        output = self.base / "preview.png"
        ds.preview(self.root, row["id"], output)
        view = cv.imread(str(output))
        self.assertEqual(view.shape, (52, 30, 3))
        self.assertEqual(view[32+4,3].tolist(), [0,255,0])
        self.assertEqual(ds.image_path(self.root, row["image"]).read_bytes(), original)
        with self.assertRaises(ValueError): ds.preview(self.root, row["id"], ds.image_path(self.root, row["image"]))

    def test_corruption_order_and_path_escape_are_rejected(self):
        self.collect()
        original = ds.load(self.root)
        for mutate in (lambda d: d["frames"][0].update(image="../escape.png"),
                       lambda d: d["frames"][0].update(sha256="wrong"),
                       lambda d: d["frames"][1].update(captured_at=0),
                       lambda d: d["frames"][0]["crop_transform"].update(frame_to_screen=[])):
            data = copy.deepcopy(original); mutate(data)
            with self.assertRaises(ValueError): ds.validate(self.root, data)
        with self.assertRaises(ValueError): ds.validate(self.base / "missing")

    def test_interrupt_and_failure_preserve_already_saved_frames(self):
        image = np.zeros((20,30,4), np.uint8)
        self.assertEqual(self.collect(frames=[image, KeyboardInterrupt()]), 1)
        self.assertEqual(len(ds.validate(self.root)["frames"]), 1)
        with self.assertRaises(RuntimeError): self.collect("visit1", "cast2", frames=[image, RuntimeError("capture failed")])
        self.assertEqual(len(ds.validate(self.root)["frames"]), 2)
        self.assertFalse((self.root / ".dataset.lock").exists())

    def test_commands_run_without_loading_input_or_fishing_modules(self):
        self.collect()
        frame_id = ds.load(self.root)["frames"][0]["id"]
        tool = ROOT / "tools/dataset.py"
        commands = [["validate", "--dataset", str(self.root)],
                    ["annotate", "--dataset", str(self.root), "--frame", frame_id, "--negative"],
                    ["preview", "--dataset", str(self.root), "--frame", frame_id, "--output", str(self.base/"cli.png")],
                    ["export-yolo", "--dataset", str(self.root), "--output", str(self.base/"cli-export")]]
        for args in commands:
            script = "import runpy,sys; sys.argv=" + repr([str(tool), *args]) + "; runpy.run_path(" + repr(str(tool)) + ",run_name='__main__'); assert not any(n in sys.modules for n in ('pyautogui','visual_targeting.input','fishing.task','setup','mss'))"
            subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)

    def test_collection_has_no_click_capability_even_with_capture_loaded(self):
        self.collect()
        for path in (ROOT/"src/visual_targeting/dataset.py", ROOT/"tools/dataset.py"):
            source = path.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn(node.module, ("visual_targeting.input", "fishing.task", "humanize", "setup"))
                if isinstance(node, ast.Import):
                    self.assertFalse(any(n.name in ("pyautogui", "pynput", "ctypes") for n in node.names))

    def test_record_cli_with_fake_capture_never_imports_input(self):
        tool = ROOT / "tools/dataset.py"
        args = [str(tool), "record", "--dataset", str(self.root), "--session", "safe", "--cast", "one",
                "--region", "0", "0", "30", "20", "--max-frames", "1"]
        script = """import builtins, runpy, sys, types
import numpy as np
from unittest.mock import MagicMock
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name in ('pyautogui', 'pynput', 'visual_targeting.input', 'fishing.task', 'setup', 'humanize'):
        raise AssertionError('dataset loaded input capability: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
capture = MagicMock()
capture.__enter__.return_value = capture
capture.grab.return_value = np.zeros((20,30,4), np.uint8)
sys.modules['mss'] = types.SimpleNamespace(mss=lambda: capture)
"""
        script += "sys.argv=" + repr(args) + "; runpy.run_path(" + repr(str(tool)) + ",run_name='__main__')"
        result = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)["saved"], 1)
        self.assertEqual(len(ds.validate(self.root)["frames"]), 1)

    def test_record_limits_and_ids_are_validated_before_capture(self):
        for kwargs in ({"fps": 0}, {"duration": float("nan")}, {"max_frames": 10001}):
            with self.assertRaises(ValueError): ds.record(self.root, "s", "c", (0,0,10,10), **kwargs)
        with self.assertRaises(ValueError): ds.identifier("../escape")
        self.assertEqual(len(ds.session_splits(["s"])), 1)
        with self.assertRaises(ValueError): ds.session_splits(["s"], val=.8, test=.4)

if __name__ == "__main__": unittest.main()
