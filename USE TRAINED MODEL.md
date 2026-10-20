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
