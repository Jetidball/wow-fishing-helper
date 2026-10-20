# Coordinate and mouse verification, before continuous fishing

The new `geometry`, `guarded_mouse` and `windows_mouse` layers are isolated from
continuous fishing. The old application adapter is not silently replaced. No
training/evaluation output arms this adapter. All modes default to dry-run.

## Explicit spaces and transforms

1. **Model pixels** are coordinates in the actual preprocessed tensor image.
2. `Letterbox` records saved-crop dimensions, actual resized dimensions, model
   dimensions and integer left/top padding. Its inverse rejects padding points and
   boxes crossing padding; it never clamps an invalid prediction onto a target.
   `Letterbox.fit` describes the matching `apply` preprocessor. When using another
   preprocessor, construct Letterbox with its recorded sizes/padding instead of
   assuming a 640x640 canvas. Odd resize rounding uses distinct actual x/y ratios.
3. **Crop pixels** refer to the saved image, with top-left (0,0). Crop/model point
   conversion is separate from box conversion. Boxes use half-open xywh rectangles.
4. `Transform.crop_logical` describes the crop relative to the window **client**,
   in 96-DPI logical units. Window client and monitor/desktop rectangles are physical
   pixels. Logical units scale by window DPI / 96; crop pixels can be an explicitly
   resized recording. Physical capture callers derive this logical rectangle from
   their actual capture rectangle, as the local lab does. Do not multiply an already
   physical pixel origin by DPI a second time.
5. **Desktop pixels** include the window's physical client origin, which may be
   negative on a monitor left/above the primary. Input never uses outer window
   borders/title bars as a client origin. Point outputs floor to integer pixels;
   boxes retain continuous edge coordinates. Bounds are checked again after mapping.

`target(..., space="model")` produces a desktop Target with frame sequence,
monotonic capture time and transform UUID. Use `space="crop"` if a detector (such
as Ultralytics) already returned coordinates in the original crop. Applying inverse
letterboxing again would be incorrect. `box_to_desktop` maps rectangle edges with
the same chain. Preprocessing and window geometry must describe the same observation.

`Transforms.bind` creates a new identity. Movement, resize, DPI, monitor bounds,
virtual-desktop bounds or a revision mismatch invalidate it on the next check.
`invalidate(reason)` handles explicit window/display/capture changes, even when a
window returns to its old location. The lab invalidates on root/canvas Configure.
A future capture integration must invalidate on window/display/DPI notifications
and ROI/preprocessor changes, not merely poll coordinates. Handles can be reused;
never retain a transform across window destruction or process restart.

## Per-action gates

`GuardedMouse` accepts only move/click actions and requires explicit arming:

* A valid transform and visible, non-minimized window snapshot.
* Capture age in [0,0.5] seconds (configurable); future timestamps rejected.
* Matching current foreground HWND and unchanged window/display geometry.
* Desktop target inside the crop, client, virtual desktop and recorded monitor.
* WindowFromPoint resolves to that same top-level HWND (occlusion rejection).
* Cancellation unset and no mouse button already held.
* Cursor within the expected position tolerance and unchanged last-input token.
  Unexpected pointer or keyboard activity latches cancellation; rearming does not
  clear it. Restart or explicitly reset cancellation only after user intervention.

A rejection disarms the controller. `move` mode cannot click. `single-click` mode
first requires a verified movement to the same transformed point, then permits
one attempted click per explicit arm. The budget is consumed before native input;
failed/partial sends are never retried. Native errors fail closed. Each verification
cycle is initiated explicitly, with no continuous action queue.

The backend uses ordinary User32 SetCursorPos and SendInput, not a custom driver.
It uses per-monitor-v2 thread DPI contexts around physical-coordinate queries and
movement. A down/up pair is sent in one SendInput call; a partial pair triggers only
a release attempt. UIPI/integrity restrictions may block delivery and are reported,
not bypassed. Sources: [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput),
[ClientToScreen](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-clienttoscreen),
[thread DPI awareness](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddpiawarenesscontext).

These checks are best-effort snapshots, not an atomic OS transaction: foreground or
human input can change between the final gate and injection. GetLastInputInfo and
cursor deltas cannot identify every concurrent physical event, especially events
within a single timer tick. The lab does not force focus or hide this limitation.
Keep continuous fishing disconnected until manual checks on each monitor/DPI layout
and a stronger physical-event audit are acceptable for the intended use.

## Local known-target window

Run from the repository root. Press Esc to cancel or close the window. Only the
orange canvas targets count as verification clicks; clicking Run does not count.
The window shows crop coordinates; the report records model/crop/desktop points,
DPI, HWND, transform ID, movement status and actual received canvas click positions.

```powershell
# No input: inspect transforms and gates.
.\.venv\Scripts\python.exe tools\mouse_lab.py --mode dry-run

# First: focus the lab, press Run, and keep the pointer still briefly.
.\.venv\Scripts\python.exe tools\mouse_lab.py --verify --manual --mode move --timeout 60 --output data\mouse-verification\movement.json

# Only after movement passes: separate one-click test against target 1.
.\.venv\Scripts\python.exe tools\mouse_lab.py --verify --manual --mode single-click --timeout 60 --output data\mouse-verification\single-click.json
```

Outputs must be fresh. In verification mode the window exits after one cycle or
its bounded timeout. An automatic `--verify` cycle without `--manual` is available
for controlled desktops; it still refuses input if not foreground. It never brings
itself forward or retries a blocked click.

Repeat movement verification after moving/resizing the window or moving it between
100%, 125%, 150% and 200% monitors, including negative-origin monitors. Arm, then move
the window or take over the mouse before delivery to check rejection. Cover/defocus
it, cancel with Esc, and use a stale transform in the unit harness. Changes invalidate
old targets; rerun with a fresh transform rather than applying an old offset.

## Automated checks and limits

`python -m unittest discover -s tests -p test_mouse_geometry.py -v` uses pure geometry
and fake mouse/native APIs. It covers fractional DPI, letterbox rounding/padding,
negative origins, moved/resized windows, monitor changes, explicit invalidation,
stale/future observations, foreground loss, occlusion, held buttons, takeover,
cancellation, movement failure, one-click limits and partial SendInput cleanup.
These tests do not claim native multi-monitor mouse delivery. Local-window reports
must separately pass movement and one-click verification on the actual desktop.
No driver, kernel component, neural model, or game input is installed by this tool.

## Verified local result (2026-10-19)

The user-armed native lab passed movement-only verification at 120 DPI (125%) with
canvas position (120,100) and zero canvas clicks. The subsequent single-click test
received exactly one left-click at (120,100), on target 1. The model point was
(132.413793...,248.303030...) on a 640x640 letterbox; the physical desktop point
was (219,289). [Saved native reports](verification/mouse-native-125dpi.json) retain
both checks. Other DPI scales, moved windows and negative origins were checked
in automated geometry/guard tests, not by native mouse delivery in this run.
Continuous fishing remains disconnected from this adapter.
