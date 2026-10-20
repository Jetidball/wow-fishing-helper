"""Offline sequence evaluation. Labels are never used as detector candidates."""
from pathlib import Path
import json
import math
import cv2 as cv
from visual_targeting.contracts import Frame, Box
from .sequence import CastTask, Policy, State


def evaluate_sequences(label_file, detector, policy=None):
    path=Path(label_file).resolve()
    sequences=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(sequences,list) or not sequences:raise ValueError("expected nonempty sequence list")
    reports={}
    def frame(row,sequence):
        name=(path.parent/row["image"]).resolve()
        if not name.is_relative_to(path.parent):raise ValueError("image outside replay root")
        image=cv.imread(str(name),cv.IMREAD_COLOR)
        if image is None:raise ValueError("unreadable replay image")
        return Frame(sequence,float(row["time"]),image,Box(0,0,image.shape[1],image.shape[0]),"bgr")
    for backend in ("baseline","temporal"):
        rows=[]; ids=set()
        for seq in sequences:
            if not isinstance(seq.get("id"),str) or seq["id"] in ids:raise ValueError("invalid or duplicate sequence ID")
            ids.add(seq["id"])
            if not seq.get("frames"):raise ValueError("empty sequence")
            pre=frame(seq["precast"],0)
            if pre.captured_at>float(seq["cast_time"]):raise ValueError("precast must precede cast")
            task=CastTask(float(seq["cast_time"]),detector.candidates(pre),policy,bite_backend=backend)
            clicks=[];wrong=0;events=set()
            last_time=seq["cast_time"]
            for i,row in enumerate(seq["frames"],1):
                current=frame(row,i)
                if type(row.get("catch_confirmed",False)) is not bool:raise ValueError("catch_confirmed must be boolean")
                own=row.get("own_box")
                if own is not None and (not isinstance(own,list) or len(own)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in own) or not 0<=own[0]<own[2]<=current.bounds.width or not 0<=own[1]<own[3]<=current.bounds.height):raise ValueError("invalid own_box")
                event=row.get("bite_event")
                if event is not None and (not isinstance(event,str) or not event):raise ValueError("invalid bite_event")
                if current.captured_at<last_time:raise ValueError("sequence time regressed")
                last_time=current.captured_at
                proposal=task.update(current,detector.candidates(current),current.captured_at,
                                     catch_confirmed=row.get("catch_confirmed",False))
                if proposal:
                    clicks.append(proposal)
                    own=row.get("own_box");event=row.get("bite_event")
                    point=proposal["point"]
                    correct=own is not None and own[0]<=point[0]<own[2] and own[1]<=point[1]<own[3]
                    if not correct or not event:wrong+=1
                    if correct and event:events.add(event)
                    task.acknowledge_click(True,current.captured_at)  # simulated only; no input adapter
            expected={r["bite_event"] for r in seq["frames"] if r.get("bite_event") and r.get("own_box")}
            if task.state!=State.DONE:
                last=frame(seq["frames"][-1],len(seq["frames"])+1)
                task.update(last,[],max(last_time,task.started+task.p.cast_seconds))
            rows.append({"id":seq["id"],"scenario":seq.get("scenario"),"outcome":task.outcome,
                         "click_proposals":len(clicks),"wrong_or_false_clicks":wrong,
                         "missed_bite_events":len(expected-events),"expected_bite_events":len(expected),
                         "catch_confirmed":task.outcome=="catch_confirmed"})
        reports[backend]={"sequences":rows,"click_proposals":sum(r["click_proposals"] for r in rows),
                          "wrong_or_false_clicks":sum(r["wrong_or_false_clicks"] for r in rows),
                          "missed_bite_events":sum(r["missed_bite_events"] for r in rows)}
    return {"kind":"labeled_sequence_replay","live_input_enabled":False,"clicks_are_simulated":True,"backends":reports}
