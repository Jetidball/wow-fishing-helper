"""Task-scoped recording, explicit labels, training/evaluation and offline previews."""
from pathlib import Path
import hashlib
import json
import time
import cv2 as cv
import numpy as np
from . import dataset as ds
from .contracts import Box,Frame
from .geometry import Rect
from .profiles import make_detector,LabeledTemplate,WindowIdentity
from .experiments import train,exported_dataset,sha,environment,fresh_output
from .evaluation import metrics


def check_dataset(profile,root,*,human=False,exported=False,reviewed_only=False):
    data=exported_dataset(root) if exported else ds.validate(root)
    if data["classes"]!=profile.data["allowed_classes"]:raise ValueError("dataset class vocabulary differs from profile")
    reviews=[]
    for row in data["frames"]:
        metadata=data["sessions"][row["session_id"]]["casts"][row["cast_id"]].get("metadata",{})
        if metadata.get("task_id")!=profile.task_id:raise ValueError("dataset contains another task or lacks task provenance")
        a=row["annotation"]
        if reviewed_only and not a["reviewed"]:continue
        if human and (not a["reviewed"] or a.get("review_source")!="human" or not a.get("reviewer")):raise ValueError("explicit human-reviewed boxes/negatives required; self-labels are not training data")
        reviews.append({"id":row["id"],"annotation":a})
    digest=hashlib.sha256(json.dumps(reviews,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return data,digest

def label(profile,root,updates,reviewer):
    check_dataset(profile,root)
    return ds.annotate(root,updates,reviewer=reviewer)

def train_task(profile,dataset,output,config,*,allow_download=False,model_factory=None):
    data,review_sha=check_dataset(profile,dataset,human=True,exported=True)
    try:return train(dataset,output,config,allow_download=allow_download,model_factory=model_factory)
    finally:
        path=Path(output)/"run.json"
        if path.exists():
            run=json.loads(path.read_text())
            run.update(task_id=profile.task_id,profile_version=profile.data["profile_version"],profile_sha256=profile.digest,
                profile=profile.data,data_review_source="human",human_review_sha256=review_sha,live_input_enabled=False)
            ds.atomic_json(path,run)

def training_templates(profile,dataset,data):
    target=data["classes"].index(profile.data["target_class"]);templates=[];sources=[]
    for row in sorted(data["frames"],key=lambda r:r["id"]):
        if row["split"]!="train":continue
        image=cv.imread(str(ds.image_path(dataset,row["image"])),cv.IMREAD_GRAYSCALE)
        for b in row["annotation"]["boxes"]:
            if b["class_id"]!=target:continue
            x,y=int(b["x"]),int(b["y"]);right,bottom=int(np.ceil(b["x"]+b["width"])),int(np.ceil(b["y"]+b["height"]))
            template=cv.Canny(image[y:bottom,x:right],100,200)
            if template.size and np.ptp(template)>0:
                templates.append(template);sources.append({"frame_id":row["id"],"session_id":row["session_id"]})
            if len(templates)>=16:return templates,sources
    if not templates:raise ValueError("no usable training-only templates")
    return templates,sources

def evaluate_task(profile,dataset,output,*,weights=None,training_run=None,detector=None):
    data,review_sha=check_dataset(profile,dataset,human=True,exported=True)
    rows=[r for r in data["frames"] if r["split"]=="test"]
    if not rows:raise ValueError("held-out test sessions required")
    provenance=json.loads((Path(training_run)/"run.json").read_text()) if training_run else None
    checkpoint_sha=sha(weights) if weights else None
    if provenance:
        if not weights or provenance.get("status")!="completed" or provenance.get("checkpoint_sha256")!=checkpoint_sha or provenance.get("profile_sha256")!=profile.digest or provenance.get("dataset_manifest_sha256")!=sha(Path(dataset)/"manifest.json") or provenance.get("human_review_sha256")!=review_sha:raise ValueError("training/checkpoint/dataset/profile provenance mismatch")
        if {r["session_id"] for r in rows}&set(provenance["train_sessions"]+provenance["val_sessions"]):raise ValueError("held-out leakage")
    templates,sources=training_templates(profile,dataset,data)
    selected=detector or make_detector(profile,templates=templates,weights=weights,candidate=True)
    backends={"selected":selected,"template":LabeledTemplate(profile,templates)}
    output=fresh_output(output,dataset)
    report={"schema_version":1,"kind":"task_evaluation","status":"running","task_id":profile.task_id,
        "profile_sha256":profile.digest,"profile":profile.data,"selected_backend":"injected_test" if detector is not None else profile.data["model"]["backend"],"dataset_manifest_sha256":sha(Path(dataset)/"manifest.json"),
        "human_review_sha256":review_sha,"data_review_source":"human","checkpoint_sha256":checkpoint_sha,
        "split":"test","sessions":sorted({r["session_id"] for r in rows}),"frame_ids":[r["id"] for r in rows],
        "training_provenance_verified":provenance is not None,"template_sources":sources,"backends":{},
        "environment":environment(),"live_input_enabled":False,
        "notes":"Single task target class; one unambiguous detection per frame. AP truncated at profile confidence. No live frame-age claim."}
    ds.atomic_json(output/"report.json",report)
    try:
        target_class=data["classes"].index(profile.data["target_class"])
        for name,backend in backends.items():
            records=[];folder=output/name;folder.mkdir()
            for row in rows:
                started=time.monotonic();image=cv.imread(str(ds.image_path(dataset,row["image"])))
                frame=Frame(row["sequence"],started,image,Box(0,0,row["width"],row["height"]),"bgr")
                infer=time.monotonic();found=backend.detect(frame);ended=time.monotonic()
                predictions=[]
                if found is not None:
                    if found.label!=profile.data["target_class"]:raise ValueError("backend returned disallowed target class")
                    b=found.box;ax,ay=profile.data["click_anchor"]
                    predictions=[{"box":[b.left,b.top,b.left+b.width,b.top+b.height],"score":found.score,"point":[int(b.left+b.width*ax),int(b.top+b.height*ay)]}]
                    cv.rectangle(image,(b.left,b.top),(b.left+b.width,b.top+b.height),(0,0,255),1)
                    cv.drawMarker(image,tuple(predictions[0]["point"]),(255,0,0),cv.MARKER_CROSS,7)
                truth=[[b["x"],b["y"],b["x"]+b["width"],b["y"]+b["height"]] for b in row["annotation"]["boxes"] if b["class_id"]==target_class]
                for b in truth:cv.rectangle(image,tuple(int(v) for v in b[:2]),tuple(int(v) for v in b[2:]),(0,255,0),1)
                if not cv.imwrite(str(folder/(row["id"]+".png")),image):raise ValueError("overlay write failed")
                record={k:row[k] for k in ("id","session_id","cast_id","sequence","elapsed_seconds","captured_at","capture_finished_at")}
                record.update(truth=truth,predictions=predictions,inference_ms=(ended-infer)*1000,service_ms=(ended-started)*1000);records.append(record)
            (folder/"predictions.jsonl").write_text("".join(json.dumps(r,allow_nan=False)+"\n" for r in records),encoding="utf-8")
            report["backends"][name]=metrics(records,profile.data["confidence"])
            report["backends"][name]["frame_ids"]=[r["id"] for r in rows]
        if sha(Path(dataset)/"manifest.json")!=report["dataset_manifest_sha256"]:raise ValueError("dataset changed during evaluation")
        report["status"]="completed"
    except BaseException as exc:
        report.update(status="failed",error=str(exc));raise
    finally:ds.atomic_json(output/"report.json",report)
    return report

def preview_task(profile,dataset,frame_id,output,*,registry=None,weights=None,queue=None):
    data,_=check_dataset(profile,dataset)
    row=next((r for r in data["frames"] if r["id"]==frame_id),None)
    if row is None:raise ValueError("unknown frame")
    output=Path(output)
    if output.exists() or output.resolve().is_relative_to(Path(dataset).resolve()):raise ValueError("fresh preview output outside dataset required")
    image=cv.imread(str(ds.image_path(dataset,row["image"])));frame=Frame(row["sequence"],time.monotonic(),image,Box(0,0,row["width"],row["height"]),"bgr")
    detector=make_detector(profile,registry,weights=weights,candidate=weights is not None);found=detector.detect(frame)
    reason="missing_or_ambiguous" if found is None else "low_confidence" if found.score<profile.data["review_below"] else "preview_ready"
    suggestion=None
    if found is not None:
        b=found.box;ax,ay=profile.data["click_anchor"]
        point=(int(b.left+b.width*ax),int(b.top+b.height*ay))
        cv.rectangle(image,(b.left,b.top),(b.left+b.width,b.top+b.height),(0,255,0),1);cv.drawMarker(image,point,(255,0,0),cv.MARKER_CROSS,7)
        suggestion={"label":found.label,"score":found.score,"box":[b.left,b.top,b.width,b.height]}
    if queue and reason!="preview_ready":queue.add(profile,frame,reason,suggestion=suggestion,source={"session_id":row["session_id"],"cast_id":row["cast_id"],"frame_id":row["id"],"dataset_manifest_sha256":sha(Path(dataset)/"manifest.json"),"model_artifact_sha256":getattr(detector,"artifact_sha256",None)})
    output.parent.mkdir(parents=True,exist_ok=True)
    if not cv.imwrite(str(output),image):raise ValueError("preview write failed")
    return {"task_id":profile.task_id,"profile_sha256":profile.digest,"reason":reason,"suggestion":suggestion,"output":str(output),"candidate_weights":weights is not None,"live_input_enabled":False}


def record_task(profile,root,session,cast,hwnd,region,*,fps=5,duration=60,max_frames=600,probe=None,capture_factory=None):
    if probe is None:
        from .window_context import query_window
        probe=query_window
    identity,client,foreground=probe(hwnd)
    crop=Rect(*region)
    if not profile.allows(identity) or foreground!=hwnd or not client.encloses(crop):raise ValueError("recording window/region not allowed or not foreground")
    if capture_factory is None:
        from mss import mss
        capture_factory=mss
    class CheckedCapture:
        def __enter__(self):self.source=capture_factory();self.capture=self.source.__enter__();return self
        def __exit__(self,*args):return self.source.__exit__(*args)
        def grab(self,rect):
            current,current_client,fg=probe(hwnd)
            if current!=identity or current_client!=client or fg!=hwnd or not profile.allows(current):raise ValueError("window identity/geometry/focus changed during recording")
            return self.capture.grab(rect)
    return ds.record(root,session,cast,region,fps=fps,duration=duration,max_frames=max_frames,
        capture_factory=CheckedCapture,classes=profile.data["allowed_classes"],metadata={"task_id":profile.task_id,
        "profile_sha256":profile.digest,"profile_version":profile.data["profile_version"],"window":vars(identity)})
