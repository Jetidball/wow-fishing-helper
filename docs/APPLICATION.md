# Local Windows application

Install CPython 3.12 x64 including Tcl/Tk. In a fresh checkout:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-inference.txt ".[inference]"
.\.venv\Scripts\visual-targeting.exe
```

After installation, double-click `Start Targeting.cmd` in the repository root, or use the installed `visual-targeting` command.

Template inference installs without torch or Ultralytics. Neural inference requires `pip install ".[ml,inference]"`; Ultralytics bundles its training API in that runtime, but training is never started automatically. A separate training environment can use `targeting-task`. Profiles and weights are external files selected by explicit paths; keep the checkout configs alongside the installation. No model download or promotion occurs on launch.

The existing settings GUI has a Visual targeting tab; its original settings migration and controls remain intact. Closing settings or starting legacy fishing stops targeting. Do not run both input loops concurrently.

Choose a profile, enter registry path, then use Allowed windows / metadata to see permitted HWNDs, profile hash and model history. Enter HWND and Start preview, then focus the target. The cross shows the click anchor. Focus loss pauses capture; geometry changes rebuild transforms and disarm. Missing templates/dependencies, unapproved weights and rejected detections produce visible reasons.

Dry-run is default. For a one-shot verification select move, or single-click after verifying movement with the existing local mouse lab. Arm ONE attempt starts a three-second delay: focus the allowed target and release your input. Existing freshness, foreground, bounds, cancellation, takeover and occlusion guards apply. Each arm permits one attempt. Click-issued is explicitly outcome UNCONFIRMED, never catch success. This application does not enable continuous fishing.

Pause / Stop disarms preview and cancels delayed capture. Escape also stops preview in the standalone window. Cancel job terminates the owned capture/training/evaluation process tree; closing the app cancels its job. It never kills unrelated processes. No global hotkey is registered; foreground and takeover guards apply while the target has focus.

Capture uses physical desktop `left top width height`, session and cast IDs, and starts after three seconds. Focus the permitted target. Recording is bounded to 30 seconds / 150 frames, validates geometry/focus on every grab and cannot click. Cancel job stops early. Inspect partial artifacts before reuse.

Train uses dataset, config and a NEW output directory; Evaluate uses dataset/output plus optional weights and training_run. Jobs run in separate processes without input adapters. Exit status and trailing output appear in the panel; full logs are in `%USERPROFILE%\wow-fishing-helper\logs`. Cancelled jobs may leave partial output, which is never approved automatically. Rollback requires a previously approved release and explicit reviewer, stops/disarms preview and requires preview restart. Registration, promotion, human labeling and uncertainty review remain explicit CLI commands: see [TASK_PROFILES.md](TASK_PROFILES.md). Suggestions and unevaluated weights never auto-promote.

Run `tools/test_windows_install.ps1` to create a fresh temporary environment, install the inference-only package, exercise installed CLI/imports and open/close the real Tk panel in dry-run. Evidence and dependency freeze are saved in `data/install-verification`. Network/index access is needed on an empty cache. This test does not capture, train or move/click. The isolated environment is retained for inspection. Native input verification remains a separate manual local mouse-lab step.

## Clickable setup

Prefer the root Setup Fishing Helper.cmd and START HERE.html visual guide. Setup uses a separate .venv-app, installs the pinned inference dependencies, verifies the installed GUI and worker, and saves data/setup.log and data/setup-verification.json. Python 3.12 x64 with Launcher and Tcl/Tk is a prerequisite; setup opens the official download page when it is missing. Start Targeting.cmd runs setup if needed. Re-running setup repairs the installation without deleting datasets. The manual .venv installation above remains an alternative; the clickable launcher uses .venv-app.

Legacy settings area selection now captures the desktop after three seconds, then lets you drag a rectangle on the frozen screenshot. Use this area confirms; Cancel/Escape preserves the existing setting. Area of interest is saved as four polygon corners for compatibility. Other box settings use two corners. Reselect after moving/resizing the game or changing display scaling. It does not use timed hover points or click in the game.

## Simple fishing home

Double-click Start Fishing.cmd for the existing continuous fishing loop with a Fishing home screen. The separate Start Targeting.cmd remains the developer preview tool. Missing fishing runtime dependencies are installed with setup_app.ps1 -Fishing using requirements.lock. The home opens without technical model fields. Guided setup captures one desktop screenshot after a visible ten-second countdown, then asks for the water rectangle, bobber rectangle and Fishing action-bar icon on that frozen picture. It saves legacy-compatible locations and a validated bobber template together, requires confirmation of in-game Auto Loot, and disables automatic bait application for the simple setup. It preserves timing/safety/session settings. Cancel preserves earlier settings. Start validates required settings instead of falling into hover setup. Live input remains unchecked on each launch; the checkbox explicitly selects the native or dry-run input adapter when Start is pressed. F9/Escape remain the original runtime pause/stop controls. Redo setup after moving/resizing the game, changing the view or changing UI scale.
