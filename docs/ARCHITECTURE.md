# Visual targeting and fishing boundaries

`visual_targeting` contains reusable CPU perception, typed contracts, replay, bounded
queues and input adapters. It imports no GUI, game settings, capture device or mouse
driver at package import time. `fishing.task` owns splash/reaction/reacquisition policy.
`bob_finder` and `splash_detector` retain the old import/API surface. The unchanged
GUI/Settings schema feeds the fishing runner through `src/state_machine.py`.

## Contracts

* `Frame`: owned, read-only uint8 gray/BGR/BGRA buffer, sequence, screen bounds and
  acquisition-start `time.monotonic()` timestamp (seconds).
* `Detection`: source sequence/capture time, completion time, box, center and score.
  The detector emits screen pixels, including negative multi-monitor origins.
* `Point`/`Box`: explicit `Space.SCREEN` or `Space.FRAME`. Conversion is explicit
  through `frame.to_screen()`. Input rejects frame-local coordinates.
* `Action`: monotonic issue time, typed operation, optional screen point, keys and
  source frame identity. Frame-derived final fishing clicks carry source provenance;
  adapters reject observations older than one second. Fixed GUI positions have no
  frame reference. These timestamps cannot be compared across process/reboot domains.

The correlation implementation is extracted intact, including validation, threshold,
first-wins ties, template dimensions and integer-center rounding. Canny and splash
logic remain unchanged. Each capture replaces the detection, and clicks still
reacquire after the configured reaction delay. No learning or ML dependencies added.

## Input and shutdown

Only `visual_targeting/input.py` imports PyAutoGUI. `WindowsInput` loads it lazily;
`DryRunInput` records at most 256 typed actions and never sends desktop input.
The compatibility facade preserves configured humanized timings and GUI setup calls.
Esc cancels interruptible waits, rejects further actions, and releases held keys.
F9 retains pause/resume; requesting a pause also releases held keys. The runner
releases keys in `finally`, including exception paths. PyAutoGUI's failsafe remains
enabled during normal actions. Window focusing remains setup functionality.

Run `python src/state_machine.py --dry-run` (or set `FISHING_DRY_RUN=1`) to exercise
the existing GUI/runtime without sending keys/clicks. It still reads the screen and
can focus the game. For fully desktop-free use, run replay instead.

## Backpressure

The live capture/detection/task loop stays synchronous: it holds one frame, no worker
backlog. `LatestQueue(capacity)` supports future capture workers with drop-oldest
semantics and a dropped counter. Do not use it for ordered input or control messages.
The GUI event queue has capacity 128 and bounded-time producer waits that check GUI
closure; completion events retain FIFO order. Dry-run input history is a bounded deque.

## Replay and verification

From the root: `python -m unittest discover -s tests -v`.
`python tools/replay.py --frames replay/frames --templates images --threshold .7`
uses the same typed frame/detector path, ordered files and no desktop adapter. JSONL
retains legacy target fields and adds sequence, monotonic capture time and coordinate
space. Replay origin is (0,0), so screen coordinates equal the saved crop's pixels;
library callers can supply another origin. Timings vary; detection outputs should not.

Install reusable packages with `python -m pip install -e .`; the fishing desktop
application still uses `requirements.lock` and the existing launcher. Fishing's task
requires `mss` and `loguru`; reusable perception needs only NumPy/OpenCV. The GUI,
loot/OCR, session and safety shell remain application modules, not reusable core.
GUI close/pause, real screen capture and Windows key delivery require manual smoke
testing; unit tests never send actual input. No labeled game dataset is bundled.
