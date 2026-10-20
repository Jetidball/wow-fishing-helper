"""Offline CPU baseline: ordered screenshot files, JSON lines, no mouse input."""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2 as cv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from settings import Settings
from visual_targeting.detector import TemplateDetector
from visual_targeting.replay import frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--templates", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=.7)
    args = parser.parse_args()
    settings = Settings()
    settings.img_dir = str(args.templates.resolve())
    settings.match_threshold = args.threshold
    settings.top_left = (0, 0)
    settings.load_images()
    if not settings.templates:
        parser.error("no valid templates")
    files = sorted(p for p in args.frames.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp"))
    if not files:
        parser.error("no replay frames")
    detector = TemplateDetector(settings.templates, settings.match_threshold, settings.canny_thresholds)
    for path, frame in frames(files):
        started = time.perf_counter()
        detection = detector.detect(frame)
        match = detection.legacy() if detection else None
        print(json.dumps(dict(frame=path.name, target=match, sequence=frame.sequence,
                              captured_at=frame.captured_at, coordinate_space="screen_pixels",
                              milliseconds=round((time.perf_counter() - started) * 1000, 3))))



if __name__ == "__main__":
    main()
