"""Recording/labeling/export only. No input, task, GUI, hotkey or window-focus imports."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import os
import random
import re
import shutil
import time
import uuid

import cv2 as cv
import numpy as np

VERSION = 1
CLASS_NAMES = ["bobber"]

def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise ValueError("IDs must be 1-80 ASCII letters, digits, underscores or hyphens")
    return value

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def atomic_json(path, data):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

@contextmanager
def locked(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".dataset.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("dataset is in use; after a crash verify no writer remains before removing .dataset.lock") from None
    try:
        os.close(fd)
        yield root
    finally:
        path.unlink(missing_ok=True)

def image_path(root, name):
    relative = Path(name)
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root) or path == root:
        raise ValueError("image path must stay within dataset")
    return path

def load(root):
    path = Path(root) / "manifest.json"
    if not path.exists():
        return {"version": VERSION, "classes": CLASS_NAMES, "sessions": {}, "frames": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != VERSION or data.get("classes") != CLASS_NAMES:
        raise ValueError("unsupported manifest version/classes")
    if not isinstance(data.get("sessions"), dict) or not isinstance(data.get("frames"), list):
        raise ValueError("invalid manifest collections")
    return data

def number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)

def boxes_valid(boxes, width, height):
    if not isinstance(boxes, list):
        raise ValueError("boxes must be a list")
    for box in boxes:
        if not isinstance(box, dict) or (type(box.get("class_id")) is not int or box["class_id"] != 0) or box.get("space") != "frame_pixels":
            raise ValueError("boxes must identify class 0 in frame_pixels")
        values = [box.get(k) for k in ("x", "y", "width", "height")]
        if not all(number(v) for v in values):
            raise ValueError("box coordinates must be finite")
        x, y, w, h = values
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise ValueError("box must have positive area entirely inside the saved image")

def validate(root, data=None):
    if data is None and not (Path(root) / "manifest.json").is_file():
        raise ValueError("dataset manifest does not exist")
    data = load(root) if data is None else data
    ids, paths, previous = set(), set(), {}
    for row in data["frames"]:
        frame_id = identifier(row["id"])
        session, cast = identifier(row["session_id"]), identifier(row["cast_id"])
        if frame_id in ids or row["image"] in paths:
            raise ValueError("duplicate frame ID or image path")
        ids.add(frame_id); paths.add(row["image"])
        cast_info = data["sessions"][session]["casts"][cast]
        if row["clock_domain"] != cast_info["clock_domain"]:
            raise ValueError("inconsistent monotonic clock domain")
        w, h = row["width"], row["height"]
        if type(w) is not int or type(h) is not int or w <= 0 or h <= 0:
            raise ValueError("invalid image dimensions")
        start, end, elapsed = row["captured_at"], row["capture_finished_at"], row["elapsed_seconds"]
        if not all(number(t) and t >= 0 for t in (start, end, elapsed)) or end < start:
            raise ValueError("invalid frame timing")
        group = (session, cast)
        seq = row["sequence"]
        if type(seq) is not int or seq < 0:
            raise ValueError("invalid sequence")
        if group in previous and (seq <= previous[group][0] or start < previous[group][1] or elapsed < previous[group][2]):
            raise ValueError("frame order/timestamps regressed within cast")
        previous[group] = (seq, start, elapsed)
        transform = row["crop_transform"]
        screen = transform["screen_rect"]
        if (transform["source_space"], transform["destination_space"]) != ("screen_pixels", "frame_pixels"):
            raise ValueError("invalid transform spaces")
        left, top, sw, sh = screen
        if not all(type(v) is int for v in screen) or (sw, sh) != (w, h):
            raise ValueError("only unscaled screen crops are supported")
        if transform["screen_to_frame"] != [[1, 0, -left], [0, 1, -top], [0, 0, 1]] or transform["frame_to_screen"] != [[1, 0, left], [0, 1, top], [0, 0, 1]]:
            raise ValueError("inconsistent crop transform")
        if row["color_format"] != "bgr8" or row["annotation"]["bite"] not in (None, "splash", "no_bite"):
            raise ValueError("invalid color format/bite annotation")
        annotation = row["annotation"]
        if type(annotation["reviewed"]) is not bool:
            raise ValueError("reviewed must be boolean")
        boxes_valid(annotation["boxes"], w, h)
        if not annotation["reviewed"] and annotation["boxes"]:
            raise ValueError("unreviewed frames cannot contain boxes")
        path = image_path(root, row["image"])
        payload = path.read_bytes()
        if not payload.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10))):
            raise ValueError("recorded image must be PNG")
        if hashlib.sha256(payload).hexdigest() != row["sha256"]:
            raise ValueError(f"image checksum changed: {row['image']}")
        image = cv.imdecode(np.frombuffer(payload, np.uint8), cv.IMREAD_UNCHANGED)
        if image is None or image.shape != (h, w, 3) or image.dtype != np.uint8:
            raise ValueError("image must be a color uint8 PNG matching manifest dimensions")
    return data

def record(root, session_id, cast_id, region, *, fps=5, duration=60, max_frames=600,
           capture_factory=None, clock=time.monotonic, sleep=time.sleep, stop=None):
    """Synchronous color capture, no producer backlog. Ctrl+C/stop finalizes saved frames.

    Capture factory is injectable for tests. This function never imports an input adapter.
    A session should represent one continuous recording visit, including all its casts.
    """
    session_id, cast_id = identifier(session_id), identifier(cast_id)
    if len(region) != 4 or any(type(v) is not int for v in region) or min(region[2:]) <= 0:
        raise ValueError("region must be integer left, top, positive width, positive height")
    if not number(fps) or not 0 < fps <= 120 or not number(duration) or not 0 < duration <= 86400:
        raise ValueError("fps must be in (0,120], duration in (0,86400] seconds")
    if type(max_frames) is not int or not 0 < max_frames <= 10000:
        raise ValueError("max_frames must be in [1,10000]")
    if capture_factory is None:
        from mss import mss
        capture_factory = mss
    monitor = dict(zip(("left", "top", "width", "height"), region))
    left, top, width, height = region
    with locked(root) as root:
        data = validate(root) if (root / "manifest.json").exists() else load(root)
        info = data["sessions"].setdefault(session_id, {"created_utc": utc_now(), "casts": {}})
        if cast_id in info["casts"]:
            raise ValueError("cast ID already recorded in this session; choose a new cast ID")
        domain = uuid.uuid4().hex
        info["casts"][cast_id] = {"started_utc": utc_now(), "clock_domain": domain, "fps_requested": fps}
        begun = clock()
        count = 0
        try:
            with capture_factory() as capture:
                while count < max_frames:
                    if stop is not None and stop.is_set(): break
                    acquired = clock()
                    if acquired - begun >= duration: break
                    image = np.array(capture.grab(monitor))
                    finished = clock()
                    if finished < acquired: raise ValueError("capture clock regressed")
                    if image.dtype != np.uint8 or image.shape != (height, width, 4):
                        raise ValueError("capture must supply BGRA uint8 pixels matching region")
                    image = cv.cvtColor(image, cv.COLOR_BGRA2BGR)
                    ok, png = cv.imencode(".png", image)
                    if not ok: raise ValueError("PNG encoding failed")
                    frame_id = uuid.uuid4().hex
                    name = f"images/{session_id}/{cast_id}/{frame_id}.png"
                    path = image_path(root, name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    payload = png.tobytes()
                    path.write_bytes(payload)
                    data["frames"].append({"id": frame_id, "image": name, "sha256": hashlib.sha256(payload).hexdigest(),
                        "session_id": session_id, "cast_id": cast_id, "sequence": count, "clock_domain": domain,
                        "captured_at": acquired, "capture_finished_at": finished, "elapsed_seconds": acquired - begun,
                        "width": width, "height": height, "color_format": "bgr8",
                        "crop_transform": {"source_space": "screen_pixels", "destination_space": "frame_pixels",
                            "screen_rect": list(region), "screen_to_frame": [[1,0,-left],[0,1,-top],[0,0,1]],
                            "frame_to_screen": [[1,0,left],[0,1,top],[0,0,1]]},
                        "annotation": {"reviewed": False, "boxes": [], "bite": None}})
                    # Each saved frame is committed; a later failed capture cannot erase its metadata.
                    atomic_json(root / "manifest.json", data)
                    count += 1
                    remaining = min(begun + duration, acquired + 1/fps) - clock()
                    if remaining > 0:
                        if stop is None: sleep(remaining)
                        elif stop.wait(remaining): break
        except KeyboardInterrupt:
            pass
        finally:
            atomic_json(root / "manifest.json", data)
        return count

def annotate(root, updates):
    """Batch reviewed boxes/explicit negatives and optional frame-local bite events.

    Updates are validated completely before replacing the manifest (all or nothing).
    """
    with locked(root) as root:
        data = validate(root)
        rows = {r["id"]: r for r in data["frames"]}
        seen = set()
        for update in updates:
            frame_id = update["frame_id"]
            if frame_id in seen or frame_id not in rows: raise ValueError("duplicate or unknown annotation frame ID")
            seen.add(frame_id)
            row = rows[frame_id]
            annotation = row["annotation"]
            if "boxes" in update:
                boxes_valid(update["boxes"], row["width"], row["height"])
                annotation["boxes"] = update["boxes"]
                annotation["reviewed"] = True
            if "bite" in update:
                if update["bite"] not in (None, "splash", "no_bite"): raise ValueError("invalid bite annotation")
                annotation["bite"] = update["bite"]
            if "boxes" not in update and "bite" not in update: raise ValueError("annotation update is empty")
            annotation["updated_utc"] = utc_now()
        atomic_json(root / "manifest.json", data)
        return len(seen)

def session_splits(sessions, val=.2, test=.1, seed=42):
    if not all(number(v) and 0 <= v < 1 for v in (val, test)) or val + test >= 1:
        raise ValueError("validation/test fractions must be nonnegative and sum to less than one")
    sessions = sorted(set(sessions))
    random.Random(seed).shuffle(sessions)
    n = len(sessions)
    nv, nt = int(n * val), int(n * test)
    # Keep a training session; allocate requested holdouts when enough sessions exist.
    if val and n >= 2: nv = max(1, nv)
    if test and n >= 3: nt = max(1, nt)
    nt = min(nt, max(0, n - nv - 1))
    return {s: "val" if i < nv else "test" if i < nv + nt else "train" for i, s in enumerate(sessions)}

def export_yolo(root, output, *, val=.2, test=.1, seed=42):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists(): raise ValueError("export directory already exists; use a fresh output directory")
    if output == root or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("export must be outside the recording dataset")
    with locked(root):
        data = validate(root)
        rows = [r for r in data["frames"] if r["annotation"]["reviewed"]]
        if not rows: raise ValueError("no reviewed frames; label positives or explicit negatives first")
        split = session_splits((r["session_id"] for r in rows), val, test, seed)
        staging = output.with_name(output.name + ".tmp-" + uuid.uuid4().hex)
        try:
            for part in ("train", "val", "test"):
                (staging / "images" / part).mkdir(parents=True)
                (staging / "labels" / part).mkdir(parents=True)
            exported = []
            for row in rows:
                part, frame_id = split[row["session_id"]], row["id"]
                shutil.copyfile(image_path(root, row["image"]), staging / "images" / part / (frame_id + ".png"))
                lines = []
                for b in row["annotation"]["boxes"]:
                    x = (b["x"] + b["width"] / 2) / row["width"]
                    y = (b["y"] + b["height"] / 2) / row["height"]
                    w, h = b["width"] / row["width"], b["height"] / row["height"]
                    lines.append(f"0 {x:.12g} {y:.12g} {w:.12g} {h:.12g}")
                (staging / "labels" / part / (frame_id + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
                exported.append(dict(row, image=f"images/{part}/{frame_id}.png", source_image=row["image"], split=part))
            # JSON strings are also valid YAML scalar strings, including Windows paths.
            (staging / "data.yaml").write_text(f"path: {json.dumps(str(output))}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: bobber\n", encoding="utf-8")
            atomic_json(staging / "manifest.json", dict(data, frames=exported, export={"seed": seed,
                "val_fraction": val, "test_fraction": test, "session_splits": split,
                "excluded_unreviewed": len(data["frames"]) - len(rows), "created_utc": utc_now()}))
            os.rename(staging, output)
        finally:
            if staging.exists(): shutil.rmtree(staging)
        return {part: sum(r["split"] == part for r in exported) for part in ("train", "val", "test")}

def preview(root, frame_id, output):
    data = validate(root)
    row = next((r for r in data["frames"] if r["id"] == frame_id), None)
    if row is None: raise ValueError("unknown frame ID")
    output = Path(output).resolve()
    dataset = Path(root).resolve()
    if output == dataset or output.is_relative_to(dataset): raise ValueError("preview must be outside dataset")
    if output.exists(): raise ValueError("preview output already exists")
    image = cv.imread(str(image_path(root, row["image"])), cv.IMREAD_COLOR)
    for box in row["annotation"]["boxes"]:
        x, y, w, h = (box[k] for k in ("x", "y", "width", "height"))
        cv.rectangle(image, (round(x), round(y)), (min(row["width"]-1, round(x+w)), min(row["height"]-1, round(y+h))), (0, 255, 0), 1)
    a = row["annotation"]
    label = "unreviewed" if not a["reviewed"] else f"bobbers={len(a['boxes'])}"
    label += f" bite={a['bite']} session={row['session_id']} cast={row['cast_id']}"
    # Header is outside the source frame: overlay text cannot obscure the bobber.
    image = cv.copyMakeBorder(image, 32, 0, 0, 0, cv.BORDER_CONSTANT, value=(20,20,20))
    cv.putText(image, label, (4, 21), cv.FONT_HERSHEY_SIMPLEX, .45, (255,255,255), 1)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv.imwrite(str(output), image): raise ValueError("failed to write preview")
    return output
