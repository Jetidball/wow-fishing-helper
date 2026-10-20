# Bounded fishing task and sequence replay

The application uses `FishingTask` and its pure `CastTask` policy. Default input is
**dry-run**: neither startup nor training enables live input. To explicitly opt in,
use `python src/state_machine.py --live-input`. `--dry-run` overrides that flag.
The input facade itself also defaults to DryRunInput; programmatic users must
explicitly configure a live adapter (or set FISHING_LIVE_INPUT=1). F9 pause and Esc
stop are unchanged. Never use a replay accuracy result as permission to enable input.

## States and bounds

| State | Behavior | Default bound |
|---|---|---|
| post_cast_acquire | exclude pre-cast bobbers, require one persistent new candidate | 5 seconds, 2 fresh frames |
| tracking | associate within 24 screen pixels; abstain if two candidates qualify | cast limit 30 seconds |
| bite_pending | maintain temporal bite evidence during reaction delay | 0.2 seconds, within cast limit |
| await_catch | never issue another click; wait for independent catch evidence | 3 seconds |
| done | immutable outcome; subsequent updates cannot propose actions | terminal |

A track missing or ambiguous for 0.8 seconds expires. It cannot transfer to a distant
float. Frames older than 0.5 seconds, duplicate sequence IDs and nonincreasing capture
timestamps cannot add evidence. Capture failures advance deadlines without reusing
old pixels. Each update handles one observation and returns; the runner polls pause
and stop between captures and rechecks frame freshness/cancellation before input.
The detector is synchronous and scans a bounded number of peaks per template; it
has no unbounded capture queue. This is cooperative scheduling, not a hard real-time
guarantee for an individual OpenCV or screen-capture call.

A pre-cast candidate snapshot is mandatory. The application takes it immediately
before the cast action. An absent snapshot yields ownership_unknown. This is a
conservative appearance heuristic, not a game-provided ownership ID. Two newly
appearing bobbers cause abstention even if one scores higher. Another player casting
at exactly the same time, camera motion, very close crossings or missed pre-cast
objects can still confuse it. Keep those sequences in the labeled test set.

## Bite evidence and outcomes

The temporal backend learns two initial brightness counts inside the tracked box.
It requires two consecutive fresh observations above 25 pixels >=245 gray value,
and at least 12 pixels brighter than the initial median, then maintains evidence
during the reaction delay. Missing/ambiguous observations reset bite evidence.
Static bright regions and a single bright frame do not constitute a temporal bite.
A real reflection that changes like a splash can still fool this simple method.

The baseline backend uses the original absolute white-pixel count, without temporal
filtering, under the same ownership/tracking/action limits. Set `biteBackend` in
settings JSON to `baseline` or `temporal` (default). Programmatic callers can supply
`Policy(...)` to configure all state limits and evidence thresholds. The old
`bob_finder.search_and_destroy` remains a legacy baseline API; its deprecated CAUGHT
constant now aliases **click_issued**, never a confirmed catch.

The policy proposes at most one bite action per cast. An adapter acceptance sets
`click_issued`; an adapter rejection produces click_rejected without retry. Dry-run
returns click_proposed without moving/clicking. A real issued click without independent
evidence ends click_unconfirmed. Only an explicit post-click catch signal produces
catch_confirmed. Disappearance, timing out, and issuing a click never prove a catch.

The application uses a newly visible occupied loot region as independent visual
evidence, refuses a loot region already occupied before casting, and only counts
catch_confirmed in catch-rate statistics. It tracks clicks_issued separately.
Configure the loot icon region to obtain this evidence. Auto-loot that closes the
window before it can be seen, missing loot configuration, or capture failures may
leave a real catch unconfirmed; no success is invented. Visual loot detection is
itself a heuristic and needs in-game validation. An injected catch_check can provide
another read-only confirmation source.

## Labeled image-sequence evaluation (no live input)

```powershell
.\.venv\Scripts\python.exe tools\fishing_replay.py --sequences replay\sequences.json --templates images --output reports\fishing-sequences.json
```

The command never imports input adapters or the fishing runner. It feeds the same
saved images through the multi-candidate template detector for both baseline and
temporal policies. It simulates click acknowledgements; no desktop actions occur.
The existing single-best template detector remains unchanged for detector baselines.
All output paths must be fresh. Image paths are relative to the sequence JSON's
folder and may not escape that folder. Use a fixed crop without scaling or camera
motion; boxes below are **frame-pixel xyxy**, not dataset x/y/width/height boxes.

Example labels (supply every observed frame in timestamp order):

```json
[
  {
    "id": "visit1-cast1",
    "scenario": "other_players_and_bright_reflections",
    "cast_time": 1.0,
    "precast": {"image": "pre.png", "time": 0.9},
    "frames": [
      {"image": "0001.png", "time": 1.1, "own_box": [20,30,40,50]},
      {"image": "0002.png", "time": 1.2, "own_box": [20,30,40,50]},
      {"image": "0003.png", "time": 1.3, "own_box": [20,30,40,50], "bite_event": "bite1"},
      {"image": "0004.png", "time": 1.4, "own_box": null, "catch_confirmed": true}
    ]
  }
]
```

Times are seconds in one recording clock domain. A bite_event ID labels every
frame belonging to that visible event on the player's own bobber; omit it for
reflections and other players' bites. own_box identifies the player's float, not
other visible bobbers. Omit it when absent/ambiguous. catch_confirmed marks actual
independent outcome evidence in that frame. These labels score policy results;
they are **never detector inputs**. Include enough normal frames to establish the
baseline before each bite. Include negatives, persistent reflections, momentary
reflections, close crossings, multiple newly appearing floats, disappearance,
late arrivals, and unsuccessful clicks.

Reports contain per-sequence outcomes, click-proposal counts, wrong-target/false
bite actions, missed labeled bite events and independently confirmed outcomes,
for both evidence backends. Every click is simulated, and frames after a terminal
outcome cannot generate another action. Final unfinished tasks are advanced to
their deadline. This replay measures policy accuracy, not actual mouse delivery
or live frame latency; use the separate model benchmark for inference timings.

## Synthetic regression baseline

`python -m unittest discover -s tests -p test_fishing_sequence.py -v` covers ownership,
ambiguity, track loss, stale/duplicate frames, cancellation, one-click enforcement,
click rejection, catch confirmation and dry-run input. Its three image-driven
labeled sequences include an existing other player's bobber, a persistent bright
reflection, and two newly appearing ambiguous floats. A fixture segmentation
detector isolates policy behavior; a separate test checks multi-peak Canny template
matching on two synthetic bobbers.

| Synthetic sequence comparison | Absolute baseline | Temporal |
|---|---:|---:|
| Valid own bite actions | 1 | 1 |
| False reflection actions | 1 | 0 |
| Actions on ambiguous new bobbers | 0 | 0 |

These are regression fixtures, not a real-game performance claim. No real labeled
fishing recordings were available for this change. Collect and label independent
visits before deciding whether this policy works well enough to enable live input.
