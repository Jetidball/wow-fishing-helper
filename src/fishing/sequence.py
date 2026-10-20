"""Bounded per-cast policy. Pure observations/actions; no capture or desktop imports."""
from dataclasses import dataclass
from enum import Enum
import math
import numpy as np

class State(str, Enum):
    ACQUIRE = "post_cast_acquire"
    TRACK = "tracking"
    BITE = "bite_pending"
    CONFIRM = "await_catch"
    DONE = "done"

@dataclass(frozen=True)
class Policy:
    acquire_seconds: float = 5
    cast_seconds: float = 30
    lost_seconds: float = .8
    confirm_seconds: float = 3
    max_frame_age: float = .5
    association_px: float = 24
    acquire_frames: int = 2
    baseline_frames: int = 2
    bite_frames: int = 2
    white_threshold: int = 25
    white_rise: int = 12
    reaction_seconds: float = .2
    def __post_init__(self):
        for k in ("acquire_seconds", "cast_seconds", "lost_seconds", "confirm_seconds", "max_frame_age", "association_px"):
            if not math.isfinite(getattr(self,k)) or getattr(self,k)<=0: raise ValueError(k)
        for k in ("acquire_frames", "baseline_frames", "bite_frames"):
            if type(getattr(self,k)) is not int or getattr(self,k)<1: raise ValueError(k)
        for k in ("white_threshold", "white_rise", "reaction_seconds"):
            if not math.isfinite(getattr(self,k)) or getattr(self,k)<0: raise ValueError(k)

class BaselineSplash:
    """Original absolute white-pixel method, retained as a comparison backend."""
    def __init__(self, policy): self.policy=policy
    def reset(self): pass
    def observe(self, crop): return int(np.count_nonzero(crop>=245))>self.policy.white_threshold

class TemporalSplash(BaselineSplash):
    def __init__(self, policy):
        super().__init__(policy); self.reset()
    def reset(self): self.baseline=[]; self.streak=0
    def observe(self, crop):
        white=int(np.count_nonzero(crop>=245))
        if len(self.baseline)<self.policy.baseline_frames:
            self.baseline.append(white); return False
        base=float(np.median(self.baseline))
        rising=white>self.policy.white_threshold and white-base>=self.policy.white_rise
        self.streak=self.streak+1 if rising else 0
        return self.streak>=self.policy.bite_frames

class CastTask:
    """One update per fresh frame; at most one click proposal in the entire cast.

    Candidates are screen-pixel xyxy boxes. A pre-cast snapshot is mandatory for
    ownership inference. Persistence/appearance is evidence, not proof of ownership.
    """
    def __init__(self, started, precast, policy=None, bite_backend="temporal", *, acquisition_started=None):
        self.p=policy or Policy()
        if not math.isfinite(started) or started<0: raise ValueError("started")
        if bite_backend not in ("temporal","baseline"): raise ValueError("bite_backend")
        self.acquire_started=started if acquisition_started is None else acquisition_started
        if not math.isfinite(self.acquire_started) or self.acquire_started<started:raise ValueError("acquisition_started")
        self.last_reason="waiting for post-cast evidence";self.observations=0;self.stale_frames=0
        self.candidate_count=0;self.eligible_count=0;self.excluded_count=0
        self.started=started; self.precast=precast; self.state=State.ACQUIRE
        self.track=None; self.last_seen=started; self.sequence=-1; self.last_capture=-1
        self.hits=0; self.proposed=False; self.click_issued=False; self.outcome=None
        self.bite=TemporalSplash(self.p) if bite_backend=="temporal" else BaselineSplash(self.p)
        self.bite_at=None; self.confirm_at=None; self.reason="waiting for post-cast evidence"
        if precast is None: self.finish("ownership_unknown")
    def finish(self, outcome):
        self.last_reason=self.reason
        self.state=State.DONE; self.outcome=outcome; self.reason=outcome
    @staticmethod
    def center(box): return ((box[0]+box[2])/2,(box[1]+box[3])/2)
    def nearby(self,a,b): return math.dist(self.center(a),self.center(b))<=self.p.association_px
    def acknowledge_click(self, accepted, now):
        if self.proposed and self.state==State.CONFIRM and not self.click_issued:
            if accepted: self.click_issued=True; self.confirm_at=now
            else: self.finish("click_rejected")
    def update(self, frame, candidates, now, *, cancelled=False, catch_confirmed=False):
        if self.state==State.DONE:return None
        if cancelled:self.finish("aborted");return None
        if now-self.started>=self.p.cast_seconds:self.finish("click_unconfirmed" if self.click_issued else "no_bite");return None
        if self.state==State.CONFIRM:
            if self.click_issued and catch_confirmed:self.finish("catch_confirmed")
            elif now-self.confirm_at>=self.p.confirm_seconds:self.finish("click_unconfirmed" if self.click_issued else "click_not_issued")
            return None
        if self.state==State.ACQUIRE and now-self.acquire_started>=self.p.acquire_seconds:
            self.finish("acquisition_expired");return None
        if self.track is not None and now-self.last_seen>=self.p.lost_seconds:
            self.finish("lost_track");return None
        if frame is None:return None
        if frame.sequence<=self.sequence or frame.captured_at<=self.last_capture or not 0<=now-frame.captured_at<=self.p.max_frame_age:
            self.stale_frames+=1;self.reason="stale_frame";return None
        self.sequence=frame.sequence;self.last_capture=frame.captured_at
        self.observations+=1
        candidates=[list(b) for b in candidates]
        self.candidate_count=len(candidates)
        for b in candidates:
            if len(b)!=4 or not all(math.isfinite(v) for v in b) or not (frame.bounds.left<=b[0]<b[2]<=frame.bounds.left+frame.bounds.width and frame.bounds.top<=b[1]<b[3]<=frame.bounds.top+frame.bounds.height):
                raise ValueError("candidate outside screen crop")
        if self.state==State.ACQUIRE:
            options=[b for b in candidates if not any(self.nearby(b,old) for old in self.precast)]
        else:options=[b for b in candidates if self.nearby(b,self.track)]
        self.eligible_count=len(options)
        self.excluded_count=len(candidates)-len(options)
        if len(options)!=1:
            self.reason="ambiguous_target" if options else "only_precast_targets" if candidates and self.state==State.ACQUIRE else "missing_target"
            self.bite.reset();self.bite_at=None
            if self.state==State.BITE:self.state=State.TRACK
            if self.state==State.ACQUIRE:self.hits=0;self.track=None
            return None
        selected=options[0]
        if self.state==State.ACQUIRE:
            self.hits=self.hits+1 if self.track is not None and self.nearby(selected,self.track) else 1
        self.track=selected;self.last_seen=now
        if self.state==State.ACQUIRE and self.hits<self.p.acquire_frames:
            self.reason=f"confirming_new_bobber {self.hits}/{self.p.acquire_frames}";return None
        if self.state==State.ACQUIRE:self.state=State.TRACK
        x1,y1,x2,y2=selected
        x1,y1=math.floor(x1-frame.bounds.left),math.floor(y1-frame.bounds.top)
        x2,y2=math.ceil(x2-frame.bounds.left),math.ceil(y2-frame.bounds.top)
        crop=frame.pixels[y1:y2,x1:x2]
        if crop.ndim==3:
            import cv2 as cv
            crop=cv.cvtColor(crop,cv.COLOR_BGRA2GRAY if crop.shape[2]==4 else cv.COLOR_BGR2GRAY)
        evidence=self.bite.observe(crop)
        if not evidence:
            self.bite_at=None;self.state=State.TRACK;self.reason="waiting for temporal bite";return None
        if self.state!=State.BITE:self.state=State.BITE;self.bite_at=now
        if now-self.bite_at<self.p.reaction_seconds:return None
        if not self.proposed:
            self.proposed=True;self.state=State.CONFIRM;self.confirm_at=now;self.reason="bite event; click proposed"
            return {"kind":"click", "point":self.center(selected), "event_id":1,
                    "frame_sequence":frame.sequence,"captured_at":frame.captured_at}
        return None
