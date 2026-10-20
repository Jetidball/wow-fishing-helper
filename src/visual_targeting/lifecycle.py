"""Human review queue and explicit evaluated model promotion/rollback. No desktop IO."""
from pathlib import Path
import hashlib
import math
import re
import json
import shutil
import uuid
import cv2 as cv
from . import dataset as ds
from .experiments import sha

class ReviewQueue:
    def __init__(self,root,capacity=1000):
        self.root=Path(root);self.capacity=capacity
        if type(capacity) is not int or capacity<1:raise ValueError("invalid queue capacity")
    def load(self):
        p=self.root/"queue.json"
        data=json.loads(p.read_text()) if p.exists() else {"schema_version":1,"items":[]}
        if data.get("schema_version")!=1 or not isinstance(data.get("items"),list):raise ValueError("unsupported review queue schema")
        return data
    def add(self,profile,frame,reason,*,suggestion=None,source=None):
        source=source or {}
        image=frame.pixels
        if frame.format=="gray":image=cv.cvtColor(image,cv.COLOR_GRAY2BGR)
        elif frame.format=="bgra":image=cv.cvtColor(image,cv.COLOR_BGRA2BGR)
        ok,png=cv.imencode(".png",image)
        if not ok:raise ValueError("cannot encode review image")
        payload=png.tobytes();digest=hashlib.sha256(payload).hexdigest()
        key=hashlib.sha256((profile.digest+digest+json.dumps(source,sort_keys=True)).encode()).hexdigest()
        with ds.locked(self.root):
            data=self.load()
            if any(r["key"]==key for r in data["items"]):return None
            if len(data["items"])>=self.capacity:return None
            item=uuid.uuid4().hex
            folder=self.root/"images";folder.mkdir(exist_ok=True)
            (folder/(item+".png")).write_bytes(payload)
            data["items"].append({"id":item,"key":key,"image":"images/"+item+".png","sha256":digest,
                "profile_sha256":profile.digest,"task_id":profile.task_id,"classes":profile.data["allowed_classes"],
                "reason":reason,"suggestion":suggestion,"source":source,"captured_at":frame.captured_at,
                "sequence":frame.sequence,"bounds":vars(frame.bounds)|{"space":frame.bounds.space.value},
                "status":"pending","created_utc":ds.utc_now()})
            ds.atomic_json(self.root/"queue.json",data)
            return item
    def decide(self,profile,item_id,decision,reviewer,boxes=None):
        if decision not in ("accept","reject") or not isinstance(reviewer,str) or not reviewer.strip():raise ValueError("explicit human decision/reviewer required")
        with ds.locked(self.root):
            data=self.load();row=next((r for r in data["items"] if r["id"]==item_id),None)
            if row is None or row["status"]!="pending" or row["profile_sha256"]!=profile.digest:raise ValueError("unknown, already reviewed, or wrong-profile queue item")
            if decision=="accept":
                if boxes is None:raise ValueError("human boxes or explicit [] negative required; suggestions are never accepted automatically")
                ds.boxes_valid(boxes,row["bounds"]["width"],row["bounds"]["height"],row["classes"])
            row.update(status=decision,reviewer=reviewer.strip(),human_boxes=boxes if decision=="accept" else None,reviewed_utc=ds.utc_now())
            ds.atomic_json(self.root/"queue.json",data)
    def export(self,profile,output):
        import numpy as np
        output=Path(output)
        if output.exists() or output.resolve().is_relative_to(self.root.resolve()):raise ValueError("use fresh reviewed-data output outside queue")
        with ds.locked(self.root):
            rows=[r for r in self.load()["items"] if r["status"]=="accept" and r["profile_sha256"]==profile.digest]
            if not rows:raise ValueError("no explicitly accepted human reviews")
            prepared=[]
            for row in rows:
                session=ds.identifier(row["source"].get("session_id"))
                payload=ds.image_path(self.root,row["image"]).read_bytes()
                if hashlib.sha256(payload).hexdigest()!=row["sha256"]:raise ValueError("review image changed")
                image=cv.imdecode(np.frombuffer(payload,np.uint8),cv.IMREAD_COLOR)
                if image is None:raise ValueError("invalid review image")
                prepared.append((row,session,image))
            for row,session,image in prepared:
                class Capture:
                    def __enter__(self):return self
                    def __exit__(self,*args):pass
                    def grab(self,region):return cv.cvtColor(image,cv.COLOR_BGR2BGRA)
                ds.record(output,session,"review_"+row["id"],(0,0,image.shape[1],image.shape[0]),max_frames=1,
                    capture_factory=Capture,classes=profile.data["allowed_classes"],metadata={"task_id":profile.task_id,
                    "profile_sha256":profile.digest,"review_queue_item":row["id"],"original_source":row["source"],"original_captured_at":row["captured_at"]})
                frame=ds.load(output)["frames"][-1]
                ds.annotate(output,[{"frame_id":frame["id"],"boxes":row["human_boxes"]}],reviewer=row["reviewer"])
            return len(rows)

    def preview(self,item_id,output):
        data=self.load();row=next((r for r in data["items"] if r["id"]==item_id),None)
        if row is None:raise ValueError("unknown queue item")
        output=Path(output)
        if output.exists() or output.resolve().is_relative_to(self.root.resolve()):raise ValueError("fresh preview outside queue required")
        source=ds.image_path(self.root,row["image"])
        if sha(source)!=row["sha256"]:raise ValueError("review image changed")
        image=cv.imread(str(source))
        suggestion=row.get("suggestion")
        if suggestion and suggestion.get("box"):
            x,y,w,h=(round(v) for v in suggestion["box"])
            cv.rectangle(image,(x,y),(x+w,y+h),(0,0,255),1)
        for box in row.get("human_boxes") or []:
            x,y,w,h=(round(box[k]) for k in ("x","y","width","height"))
            cv.rectangle(image,(x,y),(x+w,y+h),(0,255,0),1)
        image=cv.copyMakeBorder(image,28,0,0,0,cv.BORDER_CONSTANT,value=(20,20,20))
        cv.putText(image,"Red=suggestion only; green=human; "+row["status"],(3,18),cv.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
        output.parent.mkdir(parents=True,exist_ok=True)
        if not cv.imwrite(str(output),image):raise ValueError("preview write failed")
        return str(output)

class ModelRegistry:
    def __init__(self,root):self.root=Path(root).resolve()
    def load(self):
        path=self.root/"registry.json"
        data=json.loads(path.read_text()) if path.exists() else {"schema_version":1,"tasks":{}}
        if data.get("schema_version")!=1 or not isinstance(data.get("tasks"),dict):raise ValueError("unsupported registry schema")
        return data
    def _evidence(self,profile,release):
        path=ds.image_path(self.root,"releases/"+release)
        info=json.loads((path/"release.json").read_text())
        if info["profile_sha256"]!=profile.digest or info["task_id"]!=profile.task_id:raise ValueError("release belongs to a different task/profile version")
        for filename,key in (("weights.pt","weights_sha256"),("run.json","run_sha256"),("evaluation.json","evaluation_sha256")):
            if sha(path/filename)!=info[key]:raise ValueError("release artifact or evidence changed")
        report=json.loads((path/"evaluation.json").read_text());run=json.loads((path/"run.json").read_text())
        self._validate_evidence(profile,info["weights_sha256"],run,report)
        return info,report,path
    @staticmethod
    def _validate_evidence(profile,weights_sha,run,report):
        for evidence in (run,report):
            for key in ("profile_sha256","checkpoint_sha256","human_review_sha256","dataset_manifest_sha256"):
                if not isinstance(evidence.get(key),str) or not re.fullmatch(r"[a-f0-9]{64}",evidence[key]):raise ValueError("invalid evidence hash")
        if profile.data["model"]["backend"]!="neural" or report.get("selected_backend")!="neural":raise ValueError("a neural checkpoint must be evaluated by the selected neural backend")
        if run.get("task_id")!=profile.task_id or report.get("task_id")!=profile.task_id or not run.get("train_sessions") or not run.get("val_sessions"):raise ValueError("task/training sessions missing")
        if run.get("status")!="completed" or report.get("status")!="completed" or report.get("split")!="test" or not report.get("frame_ids") or not report.get("sessions"):raise ValueError("completed held-out test evaluation required")
        if run.get("profile_sha256")!=profile.digest or report.get("profile_sha256")!=profile.digest:raise ValueError("profile evidence mismatch")
        if run.get("checkpoint_sha256")!=weights_sha or report.get("checkpoint_sha256")!=weights_sha:raise ValueError("unevaluated checkpoint")
        if run.get("data_review_source")!="human" or report.get("data_review_source")!="human" or not run.get("human_review_sha256") or run.get("human_review_sha256")!=report.get("human_review_sha256"):raise ValueError("human-reviewed training data required")
        if run.get("dataset_manifest_sha256")!=report.get("dataset_manifest_sha256") or not report.get("training_provenance_verified"):raise ValueError("dataset/training provenance mismatch")
        if set(report["sessions"]) & set(run.get("train_sessions",[])+run.get("val_sessions",[])):raise ValueError("held-out session leakage")
    def register(self,profile,weights,run_file,evaluation_file):
        weights=Path(weights);run_file=Path(run_file);evaluation_file=Path(evaluation_file)
        run=json.loads(run_file.read_text());report=json.loads(evaluation_file.read_text());digest=sha(weights)
        self._validate_evidence(profile,digest,run,report)
        with ds.locked(self.root):
            data=self.load()
            task=data["tasks"].setdefault(profile.task_id,{"active":None,"candidates":[],"approved":[],"history":[],"profile_versions":{}})
            versions=task.setdefault("profile_versions",{})
            key=str(profile.data["profile_version"])
            if key in versions and versions[key]!=profile.digest:raise ValueError("profile version already registered with different content; increment the version")
            versions[key]=profile.digest
            release=uuid.uuid4().hex
            folder=self.root/"releases"/release;folder.mkdir(parents=True)
            for source,name in ((weights,"weights.pt"),(run_file,"run.json"),(evaluation_file,"evaluation.json")):shutil.copyfile(source,folder/name)
            info={"task_id":profile.task_id,"profile_sha256":profile.digest,"weights_sha256":digest,
                "run_sha256":sha(folder/"run.json"),"evaluation_sha256":sha(folder/"evaluation.json"),"created_utc":ds.utc_now()}
            ds.atomic_json(folder/"release.json",info)
            task["candidates"].append(release);ds.atomic_json(self.root/"registry.json",data)
            return release
    def _quality(self,profile,report):
        m=report["backends"]["selected"]
        gates=profile.data["promotion"]
        values=[m.get("precision"),m.get("recall"),m.get("false_detections_per_cast",{}).get("mean")]
        if not all(type(v) in (int,float) and math.isfinite(v) for v in values) or not 0<=values[0]<=1 or not 0<=values[1]<=1 or values[2]<0:raise ValueError("invalid evaluated quality metrics")
        if m["precision"] is None or m["recall"] is None or m["false_detections_per_cast"]["mean"] is None or m["precision"]<gates["min_precision"] or m["recall"]<gates["min_recall"] or m["false_detections_per_cast"]["mean"]>gates["max_false_per_cast"]:raise ValueError("held-out quality gates not met")
    def promote(self,profile,release,reviewer):
        if not isinstance(reviewer,str) or not reviewer.strip():raise ValueError("explicit promotion reviewer required")
        ds.identifier(release)
        with ds.locked(self.root):
            data=self.load();task=data["tasks"].get(profile.task_id)
            if task is None or release not in task["candidates"]:raise ValueError("unknown candidate")
            info,report,path=self._evidence(profile,release);self._quality(profile,report)
            previous=task["active"];task["active"]=release
            if release not in task["approved"]:task["approved"].append(release)
            task["history"].append({"action":"promote","from":previous,"to":release,"reviewer":reviewer,"at":ds.utc_now()})
            ds.atomic_json(self.root/"registry.json",data)
    def rollback(self,profile,release,reviewer):
        if not isinstance(reviewer,str) or not reviewer.strip():raise ValueError("rollback reviewer required")
        ds.identifier(release)
        with ds.locked(self.root):
            data=self.load();task=data["tasks"].get(profile.task_id)
            if task is None or release not in task["approved"] or release==task["active"]:raise ValueError("rollback must select a previously approved inactive release")
            info,report,path=self._evidence(profile,release);self._quality(profile,report)
            previous=task["active"];task["active"]=release
            task["history"].append({"action":"rollback","from":previous,"to":release,"reviewer":reviewer,"at":ds.utc_now()})
            ds.atomic_json(self.root/"registry.json",data)
    def active(self,profile):
        task=self.load()["tasks"].get(profile.task_id)
        if not task or task["active"] not in task["approved"]:raise ValueError("no explicitly promoted task model")
        info,report,path=self._evidence(profile,task["active"]);self._quality(profile,report)
        return dict(info,release=task["active"],weights_path=path/"weights.pt")
