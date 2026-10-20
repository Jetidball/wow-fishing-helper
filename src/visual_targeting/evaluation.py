"""Single-class offline detection comparison and bounded-queue replay timing. No input IO."""
from collections import defaultdict
from pathlib import Path
import json
import math
import time
import cv2 as cv
import numpy as np
from .contracts import Box, Frame
from .detector import TemplateDetector
from .dataset import atomic_json, utc_now, image_path, identifier
from .experiments import exported_dataset, environment, fresh_output, sha

class TemplateBackend:
    def __init__(self, templates, threshold=.7, canny=(50,150)):
        self.detector=TemplateDetector(templates,threshold,canny)
    def sync(self): pass
    def predict(self,frame):
        detection=self.detector.detect(frame)
        if detection is None:return []
        b=detection.box; p=detection.center
        return [{"box":[b.left,b.top,b.left+b.width,b.top+b.height],"score":detection.score,"point":[p.x,p.y]}]

def iou(a,b):
    area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area
    return area/union if union else 0.

def match(predictions,truth,threshold=.5):
    available=set(range(len(truth))); pairs=[]; false=[]
    for pi,p in sorted(enumerate(predictions),key=lambda v:-v[1]["score"]):
        target=max(available,key=lambda j:iou(p["box"],truth[j]),default=None)
        if target is not None and iou(p["box"],truth[target]) >= threshold:
            available.remove(target); pairs.append((pi,target))
        else:false.append(pi)
    return pairs,false,sorted(available)

def percentile(values,p): return float(np.percentile(values,p)) if values else None

def average_precision(records,threshold):
    total=sum(len(r["truth"]) for r in records)
    if not total:return None
    candidates=[]
    for r in records:
        pairs,_,_=match(r["predictions"],r["truth"],threshold)
        hits={pi for pi,_ in pairs}
        candidates.extend((p["score"],int(i in hits)) for i,p in enumerate(r["predictions"]))
    candidates.sort(key=lambda p:-p[0])
    if not candidates:return 0.
    tp=np.cumsum([h for _,h in candidates]); fp=np.arange(1,len(tp)+1)-tp
    recall=tp/total; precision=tp/(tp+fp)
    return float(np.mean([max(precision[recall>=r],default=0.) for r in np.linspace(0,1,101)]))

def latest_queue_age(records):
    """Simulate one in-flight frame + one replaceable latest pending frame per cast.

    Accuracy uses ALL frames. This cadence simulation separately reports frame age/drops.
    Recorded acquisition latency + measured replay service time; not live-device latency.
    """
    casts=defaultdict(list)
    for row in records:casts[(row["session_id"],row["cast_id"])].append(row)
    ages=[]; dropped=0
    for rows in casts.values():
        rows=sorted(rows,key=lambda r:r["sequence"])
        ready=[r["elapsed_seconds"]+(r["capture_finished_at"]-r["captured_at"]) for r in rows]
        t=ready[0]; i=0
        while i<len(rows):
            if ready[i]>t:t=ready[i]
            j=i
            while j+1<len(rows) and ready[j+1]<=t:j+=1
            dropped+=j-i; i=j
            t+=rows[i]["service_ms"]/1000
            ages.append((t-rows[i]["elapsed_seconds"])*1000)
            i+=1
    return {"p95_frame_age_ms":percentile(ages,95),"processed_frames":len(ages),"dropped_frames":dropped,
            "mode":"simulated_recorded_cadence_latest_pending_1", "live_measurement":False}

def metrics(records,conf=.25,small_area=32**2):
    tp=fp=fn=small_total=small_missed=0; errors=[]; small_errors=[]; cast_fp=defaultdict(int)
    for r in records:
        pred=[p for p in r["predictions"] if p["score"]>=conf]
        pairs,false,missed=match(pred,r["truth"])
        tp+=len(pairs);fp+=len(false);fn+=len(missed)
        cast_fp[f"{r['session_id']}/{r['cast_id']}"]+=len(false)
        small={i for i,b in enumerate(r["truth"]) if (b[2]-b[0])*(b[3]-b[1])<small_area}
        small_total+=len(small);small_missed+=len(small.intersection(missed))
        # Prospective click: highest-confidence prediction, nearest annotated bobber center.
        if pred and r["truth"]:
            p=max(pred,key=lambda p:p["score"])["point"]
            distances=[math.dist(p,((b[0]+b[2])/2,(b[1]+b[3])/2)) for b in r["truth"]]
            j=int(np.argmin(distances));errors.append(distances[j])
            if j in small:small_errors.append(distances[j])
    ap=[average_precision(records,t) for t in np.linspace(.5,.95,10)]
    return {"frames":len(records),"operating_confidence":conf,"tp":tp,"fp":fp,"fn":fn,
        "precision":tp/(tp+fp) if tp+fp else None,"recall":tp/(tp+fn) if tp+fn else None,
        "ap50":ap[0],"map50_95":float(np.mean(ap)) if ap[0] is not None else None,
        "small_targets":{"area_lt_pixels2":small_area,"count":small_total,"missed":small_missed,
            "miss_rate":small_missed/small_total if small_total else None,"click_error_p95_px":percentile(small_errors,95)},
        "false_detections_per_cast":{"mean":fp/len(cast_fp) if cast_fp else None,"counts":dict(cast_fp), "cast_fraction_with_false_detections":sum(v>0 for v in cast_fp.values())/len(cast_fp) if cast_fp else None},
        "click_point_error":{"samples":len(errors),"mean_px":float(np.mean(errors)) if errors else None,
            "p95_px":percentile(errors,95),"definition":"top prediction to nearest ground-truth center; no predictions excluded, misses reported separately"},
        "inference_ms":{"mean":float(np.mean([r["inference_ms"] for r in records])),"p95":percentile([r["inference_ms"] for r in records],95)},
        "service_ms":{"mean":float(np.mean([r["service_ms"] for r in records])),"p95":percentile([r["service_ms"] for r in records],95)},
        "service_fps":1000/float(np.mean([r["service_ms"] for r in records])) if any(r["service_ms"] for r in records) else None,
        "frame_age":latest_queue_age(records)}

def overlay(image,record,path,conf):
    for b in record["truth"]:
        cv.rectangle(image,tuple(round(x) for x in b[:2]),tuple(round(x) for x in b[2:]),(0,255,0),1)
    for p in record["predictions"]:
        if p["score"]<conf:continue
        b=p["box"]
        cv.rectangle(image,tuple(round(x) for x in b[:2]),tuple(round(x) for x in b[2:]),(0,0,255),1)
        cv.drawMarker(image,tuple(p["point"]),(255,0,0),cv.MARKER_CROSS,7,1)
    image=cv.copyMakeBorder(image,30,0,0,0,cv.BORDER_CONSTANT,value=(20,20,20))
    cv.putText(image,"GT green | prediction red | prospective point blue",(3,20),cv.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
    if not cv.imwrite(str(path),image):raise ValueError("overlay write failed")

def evaluate(dataset,output,backends,*,split="test",conf=.25,small_area=1024,warmup=3,overlay_limit=50,provenance=None):
    if split not in ("val","test") or not 0<=conf<=1 or small_area<=0 or warmup<0 or overlay_limit<0:
        raise ValueError("invalid evaluation parameters; only held-out val/test allowed")
    dataset=Path(dataset).resolve();data=exported_dataset(dataset)
    rows=[r for r in data["frames"] if r["split"]==split]
    if not rows:raise ValueError("requested held-out split is empty")
    if provenance:
        overlap=set(provenance.get("train_sessions",[])) & {r["session_id"] for r in rows}
        if split=="test":overlap|=set(provenance.get("val_sessions",[])) & {r["session_id"] for r in rows}
        if overlap:raise ValueError("held-out sessions overlap training/tuning provenance")
    output=fresh_output(output,dataset)
    report={"kind":"offline_evaluation","status":"running","created_utc":utc_now(),"split":split,
        "sessions":sorted({r["session_id"] for r in rows}),"frame_ids":[r["id"] for r in rows],
        "manifest_sha256":sha(dataset/"manifest.json"),"environment":environment(),"backends":{},
        "provenance":provenance or {"training_provenance":"unverified"},"live_input_enabled":False,
        "timing_notes":"Batch 1; warmup excluded. Service includes image decode/preprocessing/inference/CPU postprocess and synchronization. Frame age is a bounded latest-pending replay simulation, not measured live capture age."}
    atomic_json(output/"report.json",report)
    for name,backend in backends.items():
        identifier(name)
        records=[];folder=output/name;folder.mkdir()
        # Warmup uses exactly the first held-out frame and never counts as a new observation.
        first=rows[0];pixels=cv.imread(str(image_path(dataset,first["image"])))
        frame=Frame(0,time.monotonic(),pixels,Box(0,0,first["width"],first["height"]),"bgr")
        for _ in range(warmup):backend.predict(frame);backend.sync()
        for row in rows:
            backend.sync();started=time.monotonic()
            image=cv.imread(str(image_path(dataset,row["image"])),cv.IMREAD_COLOR)
            frame=Frame(row["sequence"],started,image,Box(0,0,row["width"],row["height"]),"bgr")
            infer=time.monotonic();pred=backend.predict(frame);backend.sync();ended=time.monotonic()
            truth=[[b["x"],b["y"],b["x"]+b["width"],b["y"]+b["height"]] for b in row["annotation"]["boxes"]]
            record={k:row[k] for k in ("id","session_id","cast_id","sequence","elapsed_seconds","captured_at","capture_finished_at")}
            record.update(truth=truth,predictions=pred,inference_ms=(ended-infer)*1000,service_ms=(ended-started)*1000)
            records.append(record)
            if len(records)<=overlay_limit:overlay(image.copy(),record,folder/(row["id"]+".png"),conf)
        (folder/"predictions.jsonl").write_text("".join(json.dumps(r,allow_nan=False)+"\n" for r in records))
        report["backends"][name]=metrics(records,conf,small_area)
        report["backends"][name]["frame_ids"]=[r["id"] for r in records]
        atomic_json(output/"report.json",report)
    if sha(dataset/"manifest.json") != report["manifest_sha256"]:raise ValueError("dataset manifest changed during evaluation")
    report["status"]="completed"
    atomic_json(output/"report.json",report)
    return report
