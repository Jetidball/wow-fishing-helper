# Versioned task profiles and explicit model lifecycle

Task profiles generalize the targeting engine without changing `detect(Frame)` or
`GuardedMouse.execute(Target, kind)`. The existing fishing runtime remains separate;
none of the workflow commands starts it, imports desktop-input adapters, or promotes
a model automatically. The local app offers a second task, `local_confirm`.

## Profiles and contracts

Examples under `configs/tasks/`:

* `fishing-v1.json`: template bobber selection; allowed bobber/loot classes and WoW windows.
* `fishing-neural-v2.json`: the same task with registry-selected neural inference.
* `local-confirm-v1.json`: template confirmation-button task in the local target app.
* `local-confirm-neural-v2.json`: optional neural version of that task.

Each profile requires schema_version 1, task_id and positive profile_version. Unknown
fields and unsupported schema versions fail validation. Its canonical SHA-256 is
recorded in queue entries, runs, evaluations and releases. Bump profile_version for
changes; the registry refuses different content under an already registered version.
Model weights can have multiple evaluated releases under one unchanged profile.

Fields:

| Field | Meaning |
|---|---|
| model.backend | template or neural; no neural dependency imported for templates |
| model.templates | raw PNG template directory, relative to the profile file |
| model.release | active: only an explicitly promoted registry release is used by default |
| model.device / imgsz | neural inference device and image size |
| allowed_classes | ordered dataset/model vocabulary; IDs are list indexes |
| target_class | the one class this task selects for action |
| allowed_windows | title glob plus explicit executable basenames, both must match |
| click_anchor | normalized x/y within the selected box, each in [0,1); e.g. [0.6,0.5] |
| confidence | minimum detection confidence for a preview/proposal |
| review_below | detections below this confidence are copied to review when a queue is supplied |
| max_frame_age | per-task freshness limit; dispatch rejects a mouse adapter with a wider limit |
| outcome | kind, value and timeout_seconds; independent post-click evidence required |
| promotion | minimum test precision/recall and maximum false detections per cast |

Template adapters use the existing multi-candidate implementation and abstain when
more than one candidate qualifies. Neural adapters expose the same detector method,
filter the target class, and also abstain on multiple eligible targets. Neural model
class names must match the complete profile vocabulary. Ultralytics outputs already
refer to the original crop; inverse letterboxing is not applied twice.

`TaskSession.preview` checks the allowed window, frame/detection provenance, class,
confidence, freshness and frame/crop transform agreement. A rejected new observation
invalidates any prior preview target. `TaskSession.execute` composes task policy with
the existing guarded mouse API; it rechecks the window, target identity and freshness.
It never widens mouse safety gates. The outcome check accepts `visible_class` from a
read-only observer or `local_event` from the local application. Evidence must be from
the same allowed HWND, after an accepted click, and within the freshness/deadline
limits. Issuing a click, prediction confidence and disappearance are not success.
A caller must supply an honest independent observer; a configured outcome string
alone does not implement OCR, loot recognition or another sensor.

## Record -> label -> export -> train -> evaluate -> preview

Use the existing Python environment for recording/labeling/templates. Neural training
uses the separate optional ML environment documented in [TRAINING.md](TRAINING.md).
No weights or neural dependencies are downloaded by these commands unless training
is explicitly given --allow-download. Pretrained initialization is selected in the
training JSON; deployment/inference selection belongs to the task profile/registry.

From the repository root in PowerShell:

```powershell
$taskProfile = 'configs/tasks/local-confirm-neural-v2.json'
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile describe
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile windows
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile record --dataset data\confirm-raw --session visit_001 --cast attempt_001 --hwnd 12345 --region 100 150 600 400 --fps 5 --duration 30 --max-frames 150
```

Replace HWND/region with the listed allowed window and a physical client crop.
Recording verifies executable/title, foreground HWND and client bounds, and stops if
identity, position/size or focus changes. It cannot focus, click, cast or send keys.
Window queries read process identity only, not application memory. As with normal
screen capture, overlays can appear in pixels; review before labeling. Use one
session ID per independent visit/video, across all attempts, to prevent split leakage.
Color, timing and crop transforms retain the dataset format in [DATASET.md](DATASET.md).
Per-cast metadata adds task/profile identity and the observed window identity.

Create `labels.json` after inspecting images. Boxes are saved-image xywh; a negative
has an explicit empty list. The same IDs/order apply to YOLO class numbers.

```json
[
  {"frame_id":"FRAME_ID","boxes":[{"class_id":0,"space":"frame_pixels","x":400,"y":219,"width":100,"height":42}]},
  {"frame_id":"NEGATIVE_ID","boxes":[]}
]
```

```powershell
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile label --dataset data\confirm-raw --annotations labels.json --reviewer USER_NAME
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile export --dataset data\confirm-raw --output datasets\confirm-v1 --val .2 --test .1 --seed 42
.\.venv-ml\Scripts\python.exe tools\task.py --profile $taskProfile train --dataset datasets\confirm-v1 --config configs\task-training.json --output runs\confirm-v1
.\.venv-ml\Scripts\python.exe tools\task.py --profile $taskProfile evaluate --dataset datasets\confirm-v1 --weights runs\confirm-v1\fit\weights\best.pt --training-run runs\confirm-v1 --output runs\confirm-v1-test
.\.venv-ml\Scripts\python.exe tools\task.py --profile $taskProfile preview --dataset datasets\confirm-v1 --frame FRAME_ID --weights runs\confirm-v1\fit\weights\best.pt --queue data\confirm-review --output previews\confirm.png
```

Unreviewed frames are excluded from export; reviewed frames must carry explicit
human provenance. Importing labels with the old programmatic annotate API without
an explicit reviewer removes prior human provenance, so an automated rewrite cannot
silently retain approval. Profile training requires human-reviewed exported data,
matching vocabulary/task IDs and independent train/validation sessions. Record
independent test sessions too. Raw legacy datasets lack task/reviewer provenance;
re-record or explicitly migrate/re-review them rather than inventing approval.
The legacy model CLI remains bobber-only; use the task CLI for other vocabularies.

Training records profile/hash, label-review hash, dataset manifest hash, settings,
checkpoint hashes, environment and train/val session IDs. Test images are not passed
to fitting. Evaluation never calls training; it compares the selected task backend
and training-only templates on identical held-out test frame IDs and saves overlays,
per-frame predictions and metrics. Metrics target the configured target_class;
other vocabulary classes are not treated as that target. The one-candidate policy
abstains on ambiguity, and AP is truncated at configured confidence. Prospective
point error uses nearest GT center as a proxy, so intentional off-center anchors
can have nonzero center error. Frame age remains the existing offline queue simulation,
not a live desktop measurement. Benchmark devices with the separate tools where
appropriate; this workflow does not claim GPU acceleration or accuracy improvements.

`--weights` on evaluate/preview is an explicit **offline candidate** override. It
cannot set the active model or send input. Candidate detector instances are also
marked offline-only and refused by task dispatch to non-dry-run mouse modes. A normal neural detector factory without
an override requires an approved registry release. Template previews use only the
profile's template library; evaluation constructs its template comparator from
training annotations. Preview files/directories must be fresh and outside datasets.

## Uncertain-example review queue

When supplied a queue, missing/ambiguous and low-confidence observations are saved
as color PNGs with task/profile hash, source session/cast/frame IDs, crop bounds,
reason and optional suggested box. Entries start **pending**. Suggestions never
become labels on their own. Duplicate source/image/profile observations are deduplicated.
The queue is bounded (default 1,000 total items); full queues stop accepting new items
without deleting review history. Start a new queue when archiving a completed batch.

```powershell
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile review-list --queue data\confirm-review
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile review-preview --queue data\confirm-review --item ITEM_ID --output previews\review-ITEM_ID.png
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile review --queue data\confirm-review --item ITEM_ID --decision accept --reviewer USER_NAME --boxes human-boxes.json
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile review --queue data\confirm-review --item OTHER_ID --decision reject --reviewer USER_NAME
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile review-export --queue data\confirm-review --output data\confirm-reviewed-batch
```

`human-boxes.json` is a human-written box list (same format as `boxes` above), or []
for a reviewed negative. There is no accept-the-suggestion flag. Review previews
show suggestions in red and explicit human boxes in green. Review export creates
a **new** recording dataset only from accepted items, verifies image hashes and
preserves original session IDs, so adjacent frames stay in the same split. It does
not merge into training data, launch a training job, or change any active model.
The source visit is required; do not invent different sessions for adjacent chunks.

Reviewer attribution is an explicit audit step, not cryptographic proof a person
inspected the image. Deliberately forged metadata or a script passing a false human
reviewer cannot be identified by these local files. The normal commands never add
human approval or promote a self-label automatically.

## Candidate registration, promotion and rollback

Use the neural profile under which the checkpoint was actually trained/evaluated:

```powershell
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile register --weights runs\confirm-v1\fit\weights\best.pt --training-run runs\confirm-v1 --evaluation runs\confirm-v1-test\report.json
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile models
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile promote --release RELEASE_ID --reviewer USER_NAME
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile active
.\.venv\Scripts\python.exe tools\task.py --profile $taskProfile rollback --release PREVIOUS_APPROVED_ID --reviewer USER_NAME
```

Registration copies local weights, run metadata and evaluation evidence into an
immutable-by-convention release directory and stores their hashes. It requires a
completed neural test evaluation of that exact checkpoint, profile and human-reviewed
dataset, with test sessions excluded from fitting/tuning. A template comparison or
an injected-test backend cannot approve neural weights. Poor-quality evaluated
candidates can be retained for audit, but promotion checks profile precision/recall
and false-detections-per-cast gates. Nonfinite/missing metrics fail closed.

Registration, training, evaluation and preview **never activate a model**. Promotion
requires an explicit command/reviewer and records the previous active pointer.
Rollback can select only a previously approved inactive release for the same exact
profile hash; an unevaluated candidate is not a rollback target. To use another
profile version, explicitly load that profile and approve compatible weights.
Every active-model resolution rechecks file hashes and evidence. No fallback to an
unapproved file occurs. Registry state changes use a writer lock and atomic index
replacement. Keep releases/evidence together; altering or deleting an artifact makes
it unusable. Local hashes detect accidental changes, not malicious edits to every
registry/evidence file. None of these commands enables continuous input.

## Second task in the local target-test app

```powershell
.\.venv\Scripts\python.exe tools\mouse_lab.py --profile configs\tasks\local-confirm-v1.json --verify --output data\task-demos\local-confirm-demo
# Same application scene and workflow without opening a window:
.\.venv\Scripts\python.exe tools\task_demo.py --profile configs\tasks\local-confirm-v1.json --output data\task-demos\local-confirm-headless
```

The app contains an orange float distractor and a blue CONFIRM button. The profile
selects confirm_button, applies anchor [0.6,0.5], and checks target_2_released as its
outcome. An author-defined synthetic fixture supplies the template. The unchanged
detector contract and guarded mouse API drive a **simulated local app backend**;
no OS input, registry mutation, learned weights or training labels are produced.
The displayed before/outcome images and JSON report make the result reviewable.
This demonstrates a second task and policy reuse, not native mouse qualification
or a trained model's accuracy. Native mouse verification remains a separate manual
procedure in [MOUSE_VERIFICATION.md](MOUSE_VERIFICATION.md).

The checked-in [demo report](verification/local-confirm-v1/report.json), [preview](verification/local-confirm-v1/preview.png) and [outcome](verification/local-confirm-v1/outcome.png) record the passing simulated demonstration and source hashes. No trained-model accuracy claim is implied.
