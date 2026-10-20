# Recording-only bobber dataset

These commands read screen pixels or saved files. They never import the fishing
task, GUI/setup, PyAutoGUI, pynput or the input adapters; they cannot cast, move the
mouse, click, focus windows, or send keys. Cast manually while collecting. No ML
model is loaded. Recording needs the existing `mss` dependency; labeling/export
need only NumPy/OpenCV. Run commands from the repository root with the venv Python.

## Collect color frames

```powershell
.\.venv\Scripts\python.exe tools\dataset.py record --dataset data\bobbers --session visit_001 --cast cast_001 --region 100 150 800 500 --fps 5 --duration 30 --max-frames 150
```

Region is **screen-pixel left top width height**, with negative monitor origins
allowed. PNGs retain color (BGR uint8 internally, ordinary color PNG on disk), not
the detector's grayscale/Canny representation. No scaling/letterboxing is applied.
Recording is synchronous: no frame queue or growing producer backlog. Caps: 120
FPS, 24 hours per command, 10,000 frames; defaults 5 FPS, 60 seconds, 600 frames.
Requested FPS is a ceiling; inspect actual timing in the manifest. Ctrl+C finalizes
saved frames; a later capture failure preserves frames already committed.

Reuse **one session ID for an entire continuous visit/video**, across every cast,
crop/zoom setting and restarted recording command. Choose a fresh cast ID within
that session. Do not give adjacent chunks of one video different session IDs.
No automatic cast recognition is attempted. Keep similar scenes/overlapping video
in the same session when in doubt; splitting cannot repair incorrect session IDs.

## Label in saved-image pixels

Find frame IDs and image paths in `manifest.json`. Open the PNG in an image viewer
or labeling tool; record boxes in **frame_pixels**, with origin at the saved crop's
top-left. CLI labeling does not open an interactive mouse interface.

```powershell
.\.venv\Scripts\python.exe tools\dataset.py annotate --dataset data\bobbers --frame FRAME_ID --box 120 85 24 30 --bite splash
.\.venv\Scripts\python.exe tools\dataset.py annotate --dataset data\bobbers --frame ANOTHER_ID --negative
.\.venv\Scripts\python.exe tools\dataset.py annotate --dataset data\bobbers --frame FRAME_ID --bite unknown
.\.venv\Scripts\python.exe tools\dataset.py preview --dataset data\bobbers --frame FRAME_ID --output previews\FRAME_ID.png
```

`--box X Y WIDTH HEIGHT` may repeat for multiple bobbers. All boxes must have finite
coordinates, positive area and lie completely within the saved image. Coordinates
are not clipped silently. One class: **0 = bobber**. Use a tight rectangle around
the visible bobber body/float, consistently including its visible stem/feather if
part of the bobber, excluding splash spray, ripples, fishing line, cursor and UI.
Label all recognizable bobbers, not only the one the player cast. For crop-edge or
partially obscured bobbers, box the visible identifiable portion; leave ambiguous
frames unreviewed rather than inventing hidden extents or marking them negative.
Never call a visible bobber a negative just because there is no bite.

`--negative` explicitly reviews a frame as containing **zero bobbers** (water,
UI distractions, no bobber after a catch, etc.). Unreviewed is distinct from
negative and never exported for training. Bite annotations are optional: `splash`
means a visible bite/splash event in that exact frame; `no_bite` means reviewed
absence of that event in the frame, not failure of the whole cast; `unknown`
clears the annotation. Bite-only updates do not review detection boxes. Bite
events are metadata and do not become another YOLO class or trigger any input.

For batch import, `annotate --dataset data\bobbers --annotations labels.json`:

```json
[
  {"frame_id": "FRAME_ID", "boxes": [{"class_id": 0, "space": "frame_pixels", "x": 120, "y": 85, "width": 24, "height": 30}], "bite": "splash"},
  {"frame_id": "NEGATIVE_ID", "boxes": [], "bite": "no_bite"}
]
```

An update containing `boxes` replaces all boxes and marks the frame reviewed.
Omit `boxes` to change only bite metadata. The whole batch validates before any
manifest replacement. Unknown/duplicate IDs and invalid boxes reject the batch.
Previews show boxes plus a separate status header and never modify source images.
Preview/export destinations must be fresh and outside the recording dataset.

## Validate and export YOLO

```powershell
.\.venv\Scripts\python.exe tools\dataset.py validate --dataset data\bobbers
.\.venv\Scripts\python.exe tools\dataset.py export-yolo --dataset data\bobbers --output datasets\bobbers-v1 --val 0.2 --test 0.1 --seed 42
```

Export validates every recorded PNG, SHA-256 checksum, color shape, dimensions,
crop transform, timestamps, IDs and annotation boxes. Only reviewed frames are
copied. YOLO labels are `0 x_center y_center width height`, normalized to [0,1]
relative to the saved crop. Negatives have an intentionally empty `.txt` label.
Output contains `images/{train,val,test}`, `labels/{train,val,test}`, `data.yaml`
and an enriched `manifest.json` retaining frame metadata, boxes and bite events.
`source_image` preserves the original path; `image` points to the exported copy.

Sessions are shuffled deterministically from sorted IDs with `--seed`; **every
cast/frame of a session goes to one split**. Fractions apply to session counts,
not image counts, so frame ratios may differ. When possible, requested validation
gets at least one session with two sessions, and requested test gets one with
three; training retains at least one. Small collections can have empty holdouts;
collect more independent sessions before evaluating a model. Adding sessions can
change assignments: treat exported manifests as frozen dataset versions. There is
no frame-random split option. Exports refuse existing output directories.

## Manifest schema (version 1)

`manifest.json` contains `version`, `classes: ["bobber"]`, `sessions` and `frames`.
Each session has creation UTC and a `casts` mapping. Each cast records UTC start,
requested FPS and a fresh `clock_domain` UUID identifying this command's monotonic
clock. Each frame contains:

* `id` (unique UUID), `image` (relative PNG path), `sha256`, `session_id`, `cast_id`,
  and zero-based per-cast `sequence`.
* `captured_at` and `capture_finished_at`: acquisition start/end from
  `time.monotonic()` in seconds; `elapsed_seconds` is relative to command start.
  Compare absolute monotonic values only within a cast/clock domain; UTC fields
  provide external correlation and are not used for elapsed time.
* `width`, `height`, `color_format: "bgr8"`.
* `crop_transform`: `source_space: "screen_pixels"`,
  `destination_space: "frame_pixels"`, `screen_rect: [left,top,width,height]`,
  and 3x3 homogeneous `screen_to_frame` / `frame_to_screen` matrices. No resizing
  means `frame_x = screen_x - left`, `frame_y = screen_y - top`.
* `annotation`: `reviewed` boolean, `boxes` list in frame pixels,
  `bite` (null/splash/no_bite), and optional `updated_utc`.

Export adds `split` per frame, `source_image`, and `export` metadata containing
seed/fractions, the complete session assignment and count of excluded unreviewed
frames. PNGs and annotations remain linked by IDs, including negative images.

Writers use an exclusive `.dataset.lock` and atomic manifest replacement. Do not
record and label the same dataset simultaneously. After a crash, verify no writer
is running before removing a stale lock. Manifest writes happen after every PNG;
an abrupt process kill between PNG and manifest writes can leave an unreferenced
PNG, which is never exported automatically. Keep source recordings immutable after
labeling; collect/review representative sessions before training anything.
