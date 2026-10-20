# Offline pretrained bobber experiments

`tools/model.py` offers explicit **train**, **evaluate**, and **benchmark** commands.
None imports input adapters, capture, the GUI, or the fishing task. No command
launches the bot, edits GUI settings, or promotes a checkpoint to live use. Training
only saves artifacts; the existing template backend remains the live default.

## Environment and configuration

Use a separate Python 3.12 environment for ML so GPU packages cannot disturb the
desktop helper's locked runtime:

```powershell
py -3.12 -m venv .venv-ml
.\.venv-ml\Scripts\python.exe -m pip install -e ".[ml]"
```

For GPU work, select the appropriate Windows/CUDA PyTorch installation from
[PyTorch's official installer](https://pytorch.org/get-started/locally/), then verify
`torch.cuda.is_available()`. The optional extra installs Ultralytics; CUDA support
depends on the installed PyTorch build. Existing non-ML tests and template-only
evaluation do not require torch/Ultralytics. Nothing is downloaded by tests.

Edit `configs/bobber-training.json`. Choose local pretrained `.pt` weights, epochs,
image size, batch, device (`cpu` or a CUDA index), workers, seed, deterministic
algorithms, AMP, optimizer, learning rate and patience. Defaults favor repeatability:
seed 42, deterministic true, workers 0, AMP false. Model paths are relative to the
working directory. Unknown config keys are rejected. Select a larger image size
on validation sessions if small bobbers disappear under downscaling; record the
choice and never tune it on test sessions.

Local pretrained weights are required by default. To intentionally download an
official checkpoint, set `model` to a simple filename such as `yolo11n.pt`, and pass
`--allow-download`. No URL/arbitrary download path is accepted. The checkpoint's
actual SHA-256 is saved after loading. This follows the public Ultralytics
[training API](https://docs.ultralytics.com/modes/train/) and
[prediction API](https://docs.ultralytics.com/modes/predict/).

## Train without exposing test sessions

First collect, review and export at least three independent sessions as described
in [DATASET.md](DATASET.md). Training requires nonempty train and validation splits,
with positive training boxes. A final comparison requires a nonempty test split.

```powershell
.\.venv-ml\Scripts\python.exe tools\model.py train --dataset datasets\bobbers-v1 --config configs\bobber-training.json --output runs\bobber-v1
```

The runner validates image checksums, session isolation, boxes and YOLO labels
against the manifest. It generates its own **train/val-only** YAML and image lists,
rather than trusting arbitrary paths in the export's `data.yaml`. Test images are
not given to the trainer. The trained checkpoint is `runs/bobber-v1/fit/weights/best.pt`.
The trainer's standard metrics/plots and resolved `args.yaml` remain under `fit/`.

Each `run.json` records requested/resolved settings, dataset-manifest hash, train/val
session IDs, pretrained and final checkpoint hashes, timestamps, Python/platform,
installed package versions, source hashes/Git HEAD, completion/failure status and
available Torch/CUDA/GPU metadata. `requirements-run.txt` snapshots installed
versions. Preserve the export, source, pretrained weights and environment alongside
the run. Seed/deterministic flags improve repeatability; they do not guarantee
bit-identical results across GPU hardware, drivers or library versions. Package
versions alone do not specify a CUDA wheel index: retain your install command.

## Evaluation only: neural versus template

```powershell
.\.venv-ml\Scripts\python.exe tools\model.py evaluate --dataset datasets\bobbers-v1 --weights runs\bobber-v1\fit\weights\best.pt --training-run runs\bobber-v1 --output runs\bobber-v1-test --devices cpu --split test --backend both --overlays 50
```

This command never calls training. Neural evaluation requires a local fine-tuned
checkpoint with exactly `0 = bobber`; a generic COCO class 0 is not a bobber model.
`--training-run` checks the final checkpoint hash and rejects test-session overlap
with training/validation provenance. If omitted, the report explicitly marks
training provenance unverified; session isolation within the dataset still checks.
`--split val` is available for tuning, never `train`; only a frozen test comparison
should support a final accuracy claim.

Both backends process **identical held-out frame IDs**, including negatives. Template
crops come only from positive **training** annotations (up to `--template-count 16`),
not held-out images. They use the original Canny/correlation implementation and
single-best-match policy. Neural inference can return multiple boxes. Those are
different candidate-generation policies, recorded with template source IDs and
configuration; do not interpret score values as comparable calibrated probabilities.

Tune `--template-threshold`, `--confidence`, `--imgsz`, `--canny` and template count
using validation sessions only. Defaults: correlation .7, operational confidence
.25, neural candidate floor .001, Canny 50/150, image size 960. AP uses all candidates
returned at each backend's configured floor; operational errors use `--confidence`.
Template AP is limited by its correlation threshold and one-box output, matching
the current detector's behavior. Run `--backend template` without ML dependencies
for a CPU baseline. Training/evaluation choices and checkpoint hash are recorded.

`report.json` contains:

* TP/FP/FN, precision/recall at IoU .5, AP50 and mean AP over IoU .50:.05:.95.
  AP uses 101-point interpolated precision for this single class. These are the
  harness's explicit metrics, not a claim of full COCO evaluation parity. Images
  with no annotated positives have undefined AP/recall, represented by null.
* **Small-target errors**: GT area below `--small-area 1024` original saved-image
  pixels squared, missed count/miss rate, and small-target point-error p95.
* **False detections per cast**: total unmatched predictions per session/cast,
  mean, and fraction of casts with any false detections. Repeated false predictions
  on adjacent frames count repeatedly; this is not unique-object tracking, and it
  depends on recording FPS. Both backends use the same observations/denominator.
* **Prospective click-point error**: highest-confidence accepted prediction's center
  versus the nearest annotated bobber center, mean/p95 pixels and sample count.
  No actual clicks occur. Frames without predictions are excluded from this distance
  statistic and penalized through FN; wrong predictions on negative images count as
  FP. Centers are a reproducible proxy, not a guarantee of the game's hit region.
* Mean/p95 inference and complete service latency, service FPS, and **p95 frame age**
  from the replay simulation below.

Per-backend `predictions.jsonl` retains frame/session/cast IDs, truth/predicted boxes,
scores, prospective points and timings for every evaluated image. Overlays show
green GT, red predictions and blue prospective points, with a separate legend.
`--overlays N` saves the first N held-out frames per backend; zero disables overlays.
Use raw JSONL to select failure cases; never overwrite source images with previews.

## CPU/GPU inference benchmark

```powershell
.\.venv-ml\Scripts\python.exe tools\model.py benchmark --dataset datasets\bobbers-v1 --weights runs\bobber-v1\fit\weights\best.pt --training-run runs\bobber-v1 --output runs\bobber-v1-benchmark --devices cpu cuda:0 cuda:1 --warmup 5 --overlays 10
```

This repeats the same held-out comparison for each requested neural device, plus
the CPU template baseline. Batch size is one; warmup calls are excluded. CUDA is
synchronized around timed work; measurements include transfer and CPU box/point
postprocessing. Service time also includes image decoding, frame ownership copy
and preprocessing. One timed sample is taken per held-out frame/backend; collect
enough frames and rerun fresh outputs for stable estimates. Concurrent desktop/GPU
work affects timings. Checkpoints and backend initialization are excluded.

Unavailable CUDA devices/dependencies are reported explicitly under
`unavailable_backends` in benchmark mode; there is no silent CPU fallback. Evaluation
mode fails on a requested unavailable backend. Comparisons may differ because CPU
and GPU execution have small numerical differences; compare detections as well as
speed. Hardware/runtime details and the device list are saved in the report.

Frame-age reporting is **offline, simulated**, not a claim about live capture:
recorded frame cadence/acquisition duration plus measured service times feed a
one-in-flight/one-replaceable-pending queue simulation independently for each cast.
It reports p95 time from recorded capture start to simulated detection completion,
processed count and dropped count. Accuracy uses all frames regardless of simulated
drops. No recorded wall-clock timestamp is subtracted from today's clock. The model
assumes zero source interprocess transport delay and excludes rendering/input; a
future live read-only replay/telemetry measurement is required for deployment age.

All output directories must be fresh and outside the dataset. No real training,
GPU result or accuracy improvement is implied by passing the synthetic tests.
Live input remains disabled; model promotion requires a separate explicit change.

## Task-scoped workflows

The legacy model CLI is bobber-only. For other task vocabularies and explicit model promotion/rollback, use [TASK_PROFILES.md](TASK_PROFILES.md). Training, evaluation and preview never activate weights.
