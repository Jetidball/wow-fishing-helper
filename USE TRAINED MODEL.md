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
