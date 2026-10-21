# Use your trained model

Open **Start Fishing.cmd**. Your original fishing settings remain under **Normal fishing**.

## Try it now, without clicks

1. Open **Visual targeting**.
2. Click **Preview latest trained model (no input)**.
3. Focus WoW and cast manually. Inspect the cross on the bobber.
4. Click **Set up movement-only test**, wait for the preview, then **Arm ONE attempt (3s)**.
5. Focus WoW within three seconds and leave the mouse still briefly. One move is allowed; no click is allowed.
6. Check whether the cursor becomes a gear. Use **Pause / Stop** afterward.

A gear is useful hover confirmation, not a bite. The program must still identify your new bobber and see bite evidence.

## Optional gear check

Under **Normal fishing → Locations & Fishing → Detector and mouse placement**:
- Capture normal cursor over empty water.
- Capture gear cursor over your bobber.
- Optionally enable **Require the calibrated gear cursor before a bite click**.
- Both captures have five-second countdowns. Recalibrate each helper/game session.

## Full neural fishing

After a matching independent evaluation passes the configured thresholds:
1. **Visual targeting → Review evaluation / approve model**; explicitly approve.
2. **Normal fishing → Locations & Fishing → Find bobbers using → Neural network**.
3. **Use latest trained model paths**.
4. Enable **Move onto a uniquely tracked bobber while waiting for the bite** if desired.
5. Save, enable live game controls on the Start page, and Start fishing.
6. F9 pauses/resumes; Esc stops.

Your current evaluated model has 97.1% precision and 68.4% recall. It does not meet the configured automatic-use thresholds. Candidate preview and armed movement-only testing are available; automatic neural fishing remains blocked until a model passes and you approve it.

For the complete illustrated step-by-step guide and troubleshooting, open **docs/USING-TRAINED-MODEL.html**.


## Compare your models

Open **Model results** in either launcher. Each row shows correct detections (precision), bobbers found (recall), F1 and mAP50 as percentages. Select a row for more metrics, training settings and file locations. Independent test and last-epoch validation scores are labeled separately; compare identical test comparison groups. Missing scores show a dash. Refresh after training or evaluation finishes. Preview selected never activates a model.

Click or hover over settings inputs to see what each does and its default. Keep prefilled values unless changing a specific setting. Existing normal fishing settings are preserved; candidate model paths fill from the latest completed run. Select game window and Pick still provide values that cannot safely be guessed.


## Easy improvement loop (GPU only)

Restart using **Start Fishing.cmd**, then open **Model results** and select a row.

1. **Auto-fill everything** finds the model files, original dataset and game window.
2. **Run & collect improvements** shows live detections and saves uncertain/periodic pictures. Focus WoW; recording does not click. Collection stops saving after 360 pictures or 30 minutes. Each start is a visit: do not restart within the same visit to manufacture independent test sessions.
3. **STOP / cancel**, then **Review new pictures**. Draw correct boxes or explicitly mark negatives. Skip uncertain frames. Model suggestions are never accepted automatically.
4. **Refine + test on GPU** fine-tunes the selected weights for 10 passes. Only reviewed new visits enter training; all old train/validation/test assignments and old labels stay frozen. It evaluates the new candidate automatically. A model with no independent test set needs a baseline with three reviewed visits first.
5. **Refresh results**, select the new row, compare it with its parent and use **Review / approve selected** if the quality gates pass. Refinement never changes your active model automatically; improvement is not guaranteed.
6. **Use selected for fishing** fills Normal fishing with the approved model. Enable live controls yourself, then Start fishing. This existing bite-aware loop moves to the bobber and right-clicks on bite evidence. F9 pauses and Esc stops.

**Move mouse test** configures a one-shot evaluated movement test. **Single-click test** requires an approved active selected model and performs one move plus LEFT click, not a bite/loot action. Press **Arm ONE attempt (3s)** each time and focus the game. Freshness, foreground, geometry, bounds and user-takeover guards still apply.

**Check GPUs** writes device names/indices to the job log. This machine has an RTX 3090 and RTX 3070. Neural fitting, preview and evaluation require a CUDA GPU; no CPU fallback. Historical CPU profiles run inference on GPU 0 without changing their stored evidence. Capture, UI, image decoding, template baseline comparison and file work still use the CPU. Models run on one selected GPU; both are available, but a tiny detector does not need multi-GPU training.

**Setup GPU.cmd** creates a separate `.venv-gpu` and installs CUDA PyTorch from the official PyTorch wheel index. Both launchers prefer that runtime. Close/reopen the application after installation. **Install / repair GPU support** is also available on Model results. If CUDA is unavailable the job stops with an error. It never starts training on the CPU.

Collected examples live in `data/improvement-examples`; training/evaluation artifacts remain under `runs` and `datasets`. Suggestions, source model hashes, original capture times and crop transforms are saved. Observation IDs are not real game cast IDs; do not interpret their count as measured catch success. Catch confirmation remains separate from click issuance.


Model results now shows a recommended next step and **Do recommended next step** button. It never approves or arms input automatically. **Open job log** opens the full worker log; failures also show the final error line. Newly reviewed frames from an existing training visit can be used on the next refinement; old validation/test visits remain frozen.


## Teach missed bobbers while using the model

On **Model results**, select your model and press **Teach missed bobbers while running**. This runs neural preview without game input. After a sustained failed search, a frozen picture opens. Draw a tight square/rectangle around every visible bobber and press **Save correction & continue**. The preview resumes on a fresh frame. Use **No bobber here & continue** only if no listed objects are visible; **Skip** saves nothing. **Stop teaching** stops prompting. Input remains disarmed during correction.

For actual fishing, select an approved neural model and enable **Ask me to box missed bobbers while fishing (neural teaching)** on Normal fishing → Start. Each expired acquisition asks for a correction before the next cast. The fishing loop sends no input while the correction window is open. Focus WoW after saving; press F9 if the existing mouse-takeover protection paused fishing. Esc still stops the normal fishing loop.

Every five saved corrections request a background GPU refinement and held-out evaluation. **Train now in background** starts sooner using corrections already saved. Save the current box before requesting training if you want it included. The current model keeps running; a busy trainer does not discard later corrections. Those corrections can enter the next run. Background teaching uses the other GPU on this two-GPU machine. Errors never trigger CPU fallback.

Corrections are human-reviewed examples in `data/improvement-examples`, with the source model hash, visit ID, timing and crop transforms. Existing validation/test visits stay frozen. New candidates appear in Model results; compare and explicitly approve one before using it for live fishing. Accuracy improvement is measured, not guaranteed. The currently loaded weights do not change mid-cast. Normal fishing teaching logs are under `data/teaching-logs`.

All buttons, including screenshot selectors and labeling dialogs, now have hover/focus help. Teaching is opt-in and saved with normal settings; older settings files default to teaching off.


## Auto-fill for live fishing and error tracking

In the **Start Fishing.cmd** app, select the desired model on **Model results** and press **Auto-fill everything**. This now configures Normal fishing as well as preview: neural backend, the exact training profile, an absolute registry path and matching approved weights. It checks the selected WoW window, saved water rectangle and Fishing action-bar point. **LIVE SETUP READY** means you can enable live game controls and press Start fishing. **LIVE SETUP BLOCKED** lists what must be fixed. Auto-fill does not approve a failed model or enable input automatically. Missing original training data blocks retraining, but does not block inference from an otherwise valid approved model.

The standalone Start Targeting launcher remains a preview/teaching application; it tells you to use Start Fishing for live fishing. Reused output folders are replaced with unique new output names for GUI training/evaluation retries. Refine checks for eligible reviewed corrections before launching a job.

**Open error history** opens `data/logs/application-errors.jsonl`: timestamps, error IDs, action, relevant paths and traceback. GUI callback errors, failed previews, failed worker jobs, blocked live setup and fatal fishing errors are recorded. Logs rotate at 2 MB with three backups. **Open job log** still opens the detailed worker output. Normal fishing writes rotating logs under `data/logs/fishing-*.log`. Previously observed output-folder and missing-review errors have also been imported into the history.


## Repairing model accuracy and startup errors

New evaluations score ALL bobber detections. Older reports used the single-target click policy, so ambiguous frames were counted as misses. Reports and comparison groups now distinguish the corrected metric version. Live ambiguity/ownership guards remain unchanged.

Use **Review suspicious labels** on Model results to inspect likely bobber/reflection pairs in the original recordings. The audit is heuristic and never changes labels. **Clear boxes & redraw** makes correction quick: draw only actual bobbers, excluding reflections, and Save. A reflection label teaches the detector the wrong object. Correcting validation/test labels invalidates the old evidence; train a fresh baseline from corrected original recordings, evaluate, then explicitly approve only a passing candidate. The latest audit is `data/audits/latest-label-audit.json`.

Startup now opens Model results when the selected model is unapproved. A failed approval is different from a missing, still-training or changed checkpoint; those errors now give specific recovery instructions. Current model files were checked against their recorded hashes without altering their evidence.
