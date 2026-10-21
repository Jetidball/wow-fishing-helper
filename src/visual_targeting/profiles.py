"""Versioned task policy and detector adapters; existing detect(Frame) contract unchanged."""
from dataclasses import replace,dataclass
from pathlib import Path,PureWindowsPath
import fnmatch
import hashlib
import json
import math
import time
import cv2 as cv
from .contracts import Box,Point,Detection
from .detector import TemplateDetector


def exact_keys(data,keys):
    if not isinstance(data,dict) or set(data)!=set(keys):raise ValueError("unknown or missing profile fields")

@dataclass(frozen=True)
class WindowIdentity:
    hwnd: int
    title: str
    executable: str

class Profile:
    def __init__(self,data,path=None):
        self.path=Path(path).resolve() if path else None
        self.data=json.loads(json.dumps(data,allow_nan=False))
        d=self.data
        exact_keys(d,("schema_version","task_id","profile_version","model","allowed_classes","target_class","allowed_windows","click_anchor","confidence","review_below","max_frame_age","outcome","promotion"))
        from .dataset import identifier,classes_valid
        if type(d["schema_version"]) is not int or d["schema_version"]!=1 or type(d["profile_version"]) is not int or d["profile_version"]<1:raise ValueError("unsupported profile version")
        identifier(d["task_id"]);classes_valid(d["allowed_classes"])
        if d["target_class"] not in d["allowed_classes"]:raise ValueError("target class not allowed")
        if not isinstance(d["allowed_windows"],list) or not d["allowed_windows"]:raise ValueError("window allowlist required")
        for window in d["allowed_windows"]:
            exact_keys(window,("title","executables"))
            if not isinstance(window["title"],str) or not window["title"] or window["title"]=="*" or not isinstance(window["executables"],list) or not window["executables"] or not all(isinstance(e,str) and e and not any(c in e for c in "*?/") for e in window["executables"]):raise ValueError("explicit title and executable allowlist required")
        if not isinstance(d["click_anchor"],list) or len(d["click_anchor"])!=2 or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<1 for v in d["click_anchor"]):raise ValueError("anchor must be normalized x/y in [0,1)")
        for key in ("confidence","review_below","max_frame_age"):
            if type(d[key]) not in (int,float) or not math.isfinite(d[key]):raise ValueError(key)
        if not 0<=d["confidence"]<=d["review_below"]<=1 or not 0<d["max_frame_age"]<=2:raise ValueError("invalid confidence/freshness policy")
        if not isinstance(d["model"],dict):raise ValueError("invalid model selection")
        model_keys=("backend","templates","release","device","imgsz")
        exact_keys(d["model"],model_keys+(("canny_thresholds",) if "canny_thresholds" in d["model"] else ()))
        thresholds=d["model"].get("canny_thresholds",[100,200])
        if not isinstance(thresholds,list) or len(thresholds)!=2 or not all(type(v) is int for v in thresholds) or not 0<=thresholds[0]<thresholds[1]<=255:raise ValueError("invalid Canny thresholds")
        m=d["model"]
        if m["backend"] not in ("template","neural") or not isinstance(m["templates"],str) or m["release"]!="active" or not isinstance(m["device"],str) or type(m["imgsz"]) is not int or m["imgsz"]<32:raise ValueError("invalid model selection")
        exact_keys(d["outcome"],("kind","value","timeout_seconds"))
        o=d["outcome"]
        if o["kind"] not in ("visible_class","local_event") or not isinstance(o["value"],str) or not o["value"] or type(o["timeout_seconds"]) not in (int,float) or not math.isfinite(o["timeout_seconds"]) or not 0<o["timeout_seconds"]<=60:raise ValueError("invalid outcome check")
        if o["kind"]=="visible_class" and o["value"] not in d["allowed_classes"]:raise ValueError("outcome class not allowed")
        exact_keys(d["promotion"],("min_precision","min_recall","max_false_per_cast"))
        p=d["promotion"]
        if not all(type(v) in (int,float) and math.isfinite(v) for v in p.values()) or not 0<=p["min_precision"]<=1 or not 0<=p["min_recall"]<=1 or p["max_false_per_cast"]<0:raise ValueError("invalid promotion thresholds")
    @classmethod
    def read(cls,path):return cls(json.loads(Path(path).read_text(encoding="utf-8")),path)
    @property
    def digest(self):return hashlib.sha256(json.dumps(self.data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    @property
    def task_id(self):return self.data["task_id"]
    def allows(self,window):
        exe=PureWindowsPath(window.executable).name.lower()
        return any(fnmatch.fnmatchcase(window.title,w["title"]) and exe in [e.lower() for e in w["executables"]] for w in self.data["allowed_windows"])
    def template_path(self):
        path=Path(self.data["model"]["templates"])
        return path.resolve() if path.is_absolute() else ((self.path.parent if self.path else Path.cwd())/path).resolve()

class LabeledTemplate:
    def __init__(self,profile,templates):
        self.profile=profile
        self.inner=TemplateDetector(templates,profile.data["confidence"],profile.data["model"].get("canny_thresholds",(100,200)))
        self.artifact_sha256=hashlib.sha256(b"".join(t.tobytes()+str(t.shape).encode() for t in templates)).hexdigest()
    def detections(self,frame):
        return [replace(found,label=self.profile.data["target_class"]) for found in self.inner.detections(frame)]
    def detect(self,frame):
        # The candidate API retains the old detector interface while allowing abstention.
        boxes=self.inner.candidates(frame)
        if len(boxes)!=1:return None
        found=self.inner.detect(frame)
        return replace(found,label=self.profile.data["target_class"]) if found else None

class TaskNeuralDetector:
    def __init__(self,profile,weights,model_factory=None):
        self.profile=profile
        self.offline_only=True
        if not Path(weights).is_file():raise ValueError("local weights required")
        self.gpu_required=model_factory is None
        self.device=profile.data["model"]["device"]
        if model_factory is None:
            from .gpu import require_gpu
            self.device=require_gpu("0" if self.device=="cpu" else self.device)
            from ultralytics import YOLO as model_factory
        self.model=model_factory(str(Path(weights).resolve()))
        names=self.model.names
        self.names=dict(enumerate(names)) if isinstance(names,list) else names
        if set(self.names.values())!=set(profile.data["allowed_classes"]):raise ValueError("model classes disagree with task profile")
        self.artifact_sha256=hashlib.sha256(Path(weights).read_bytes()).hexdigest()
    def detections(self,frame):
        import time
        import numpy as np
        m=self.profile.data["model"]
        image=frame.pixels
        if frame.format=="gray":image=cv.cvtColor(image,cv.COLOR_GRAY2BGR)
        elif frame.format=="bgra":image=cv.cvtColor(image,cv.COLOR_BGRA2BGR)
        # API already returns crop-local boxes; do not invert model letterboxing twice.
        result=self.model.predict(source=image,device=self.device,imgsz=m["imgsz"],conf=self.profile.data["confidence"],save=False,show=False,verbose=False)[0]
        if self.gpu_required and not str(self.model.predictor.device).startswith("cuda:"):raise RuntimeError("Neural inference left CUDA; CPU fallback is disabled")
        boxes=result.boxes.xyxy.detach().cpu().numpy();scores=result.boxes.conf.detach().cpu().numpy();classes=result.boxes.cls.detach().cpu().numpy()
        selected=[]
        for box,score,kind in zip(boxes,scores,classes):
            if self.names.get(int(kind))!=self.profile.data["target_class"]:continue
            x1,y1,x2,y2=(float(v) for v in box)
            if not all(math.isfinite(v) for v in (x1,y1,x2,y2,float(score))) or not 0<=x1<x2<=frame.bounds.width or not 0<=y1<y2<=frame.bounds.height:raise ValueError("invalid model box")
            left,top=math.floor(x1)+frame.bounds.left,math.floor(y1)+frame.bounds.top
            width,height=math.ceil(x2)-math.floor(x1),math.ceil(y2)-math.floor(y1)
            selected.append(Detection(frame.sequence,frame.captured_at,time.monotonic(),Box(left,top,width,height),Point(left+width//2,top+height//2),float(score),self.names[int(kind)]))
        return selected
    def detect(self,frame):
        selected=self.detections(frame)
        return selected[0] if len(selected)==1 else None
    def candidates(self,frame):
        # Preserve every candidate so the existing ownership tracker can abstain.
        return [[d.box.left,d.box.top,d.box.left+d.box.width,d.box.top+d.box.height] for d in self.detections(frame)]


def make_detector(profile,registry=None,*,templates=None,weights=None,candidate=False):
    if profile.data["model"]["backend"]=="template":
        if templates is None:
            templates=[]
            for path in sorted(p for p in profile.template_path().iterdir() if p.suffix.lower() in (".png",".jpg",".jpeg",".bmp")) if profile.template_path().is_dir() else []:
                image=cv.imread(str(path),cv.IMREAD_GRAYSCALE)
                if image is not None:
                    edge=cv.Canny(image,*profile.data["model"].get("canny_thresholds",(100,200)))
                    if edge.size and edge.max()!=edge.min():templates.append(edge)
        if not templates:raise ValueError(f"No valid bobber PNG templates in {profile.template_path()}. Use Open screenshot / select bobber to create one, then restart preview.")
        return LabeledTemplate(profile,templates)
    offline_weights=weights is not None
    if weights is not None and not candidate:raise ValueError("explicit offline candidate evaluation/preview required for unpromoted weights")
    if weights is None:
        if registry is None:raise ValueError("approved model registry required")
        weights=registry.active(profile)["weights_path"]
    detector=TaskNeuralDetector(profile,weights)
    detector.offline_only=offline_weights
    return detector

def evaluated_movement_candidate(profile,weights,training_run,evaluation):
    """Explicit one-shot movement testing only; does not promote or permit clicking."""
    import json
    from .lifecycle import ModelRegistry
    from .experiments import sha
    run=json.loads((Path(training_run)/"run.json").read_text())
    report=json.loads(Path(evaluation).read_text())
    ModelRegistry._validate_evidence(profile,sha(weights),run,report)
    detector=TaskNeuralDetector(profile,weights)
    detector.movement_test_approved=True
    return detector

class TaskSession:
    def __init__(self,profile,detector,queue=None):
        self.profile=profile;self.detector=detector;self.queue=queue;self.reason="idle";self.clicked_at=None;self.outcome=None;self.last_target=None;self.preview_window=None;self.bound_profile_sha=profile.digest
    def preview(self,frame,window,transform,now,source=None):
        p=self.profile.data
        if self.outcome is not None:self.reason="terminal";return None
        if self.clicked_at is not None:self.reason="awaiting_outcome";return None
        self.last_target=None;self.preview_window=None
        if not self.profile.allows(window):self.reason="window_not_allowed";return None
        if window.hwnd!=transform.window.hwnd:self.reason="window_transform_mismatch";return None
        if not 0<=now-frame.captured_at<=p["max_frame_age"]:self.reason="stale_frame";return None
        source=dict(source or {})
        artifact=getattr(self.detector,"artifact_sha256",None)
        source["model_artifact_sha256"]=artifact if isinstance(artifact,str) else "unavailable"
        began=time.monotonic();detection=self.detector.detect(frame)
        if now+max(0,time.monotonic()-began)-frame.captured_at>p["max_frame_age"]:self.reason="processing_stale";return None
        if detection is None:
            self.reason="missing_or_ambiguous"
            if self.queue:self.queue.add(self.profile,frame,self.reason,source=source)
            return None
        b=detection.box
        if b.space.value!="screen_pixels":self.reason="coordinate_space_rejected";return None
        if detection.frame_sequence!=frame.sequence or detection.captured_at!=frame.captured_at or detection.label not in p["allowed_classes"] or detection.label!=p["target_class"]:self.reason="class_or_provenance_rejected";return None
        if not (frame.bounds.left<=b.left and frame.bounds.top<=b.top and b.left+b.width<=frame.bounds.left+frame.bounds.width and b.top+b.height<=frame.bounds.top+frame.bounds.height):raise ValueError("detection outside frame")
        crop=transform.desktop_crop
        actual=(crop.left,crop.top,crop.width,crop.height);expected=(frame.bounds.left,frame.bounds.top,frame.bounds.width,frame.bounds.height)
        if not all(math.isclose(a,b,rel_tol=0,abs_tol=1e-6) for a,b in zip(actual,expected)) or (transform.letterbox.crop_width,transform.letterbox.crop_height)!=(frame.bounds.width,frame.bounds.height):raise ValueError("frame/transform crop mismatch")
        if detection.score<p["review_below"] and self.queue:
            self.queue.add(self.profile,frame,"low_confidence",suggestion={"label":detection.label,"score":detection.score,"box":[b.left-frame.bounds.left,b.top-frame.bounds.top,b.width,b.height]},source=source)
        if detection.score<p["confidence"]:self.reason="below_confidence";return None
        ax,ay=p["click_anchor"]
        target=transform.target(b.left-frame.bounds.left+b.width*ax,b.top-frame.bounds.top+b.height*ay,frame.sequence,frame.captured_at,space="crop")
        self.reason="preview_ready";self.last_target=target;self.preview_window=window.hwnd;return target
    def execute(self,mouse,target,kind,window,now):
        # Policy composition only: the detector and mouse interfaces stay unchanged.
        if self.outcome is not None or self.clicked_at is not None:return False
        if getattr(self.detector,"offline_only",False) is True and mouse.mode!="dry-run":
            if not (mouse.mode=="move" and kind=="move" and getattr(self.detector,"movement_test_approved",False) is True):return False
        if self.profile.digest!=self.bound_profile_sha or target!=self.last_target or not self.profile.allows(window) or window.hwnd!=self.preview_window:return False
        if not 0<=now-target.captured_at<=self.profile.data["max_frame_age"] or mouse.max_age>self.profile.data["max_frame_age"]:return False
        accepted=mouse.execute(target,kind)
        if kind=="click" and mouse.mode!="dry-run":self.mark_click(accepted,now)
        return accepted
    def mark_click(self,accepted,now):
        if self.clicked_at is not None or self.outcome is not None:return
        if accepted and self.last_target is None:self.outcome="click_without_preview";return
        if accepted:self.clicked_at=now
        else:self.outcome="click_rejected"
    def check_outcome(self,window,kind,value,observed_at,now):
        if self.outcome:return self.outcome
        if self.clicked_at is None:return None
        o=self.profile.data["outcome"]
        if now-self.clicked_at>o["timeout_seconds"]:self.outcome="unconfirmed";return self.outcome
        if self.profile.allows(window) and window.hwnd==self.preview_window and self.clicked_at<=observed_at<=now and now-observed_at<=self.profile.data["max_frame_age"] and (kind,value)==(o["kind"],o["value"]):self.outcome="confirmed"
        return self.outcome
