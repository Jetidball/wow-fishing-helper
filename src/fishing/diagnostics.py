"""Bounded local evidence for the latest failed acquisition. Never sends input."""
import json
from pathlib import Path
import cv2 as cv
import numpy as np

def save_acquisition_report(settings,machine,frame,*,capture_errors=0,directory=None):
    directory=Path(directory) if directory else Path(__file__).resolve().parents[2]/'data/fishing-debug'
    directory.mkdir(parents=True,exist_ok=True)
    report={
        'outcome':machine.outcome,'last_reason':machine.last_reason,
        'candidate_count':machine.candidate_count,'eligible_count':machine.eligible_count,
        'excluded_count':machine.excluded_count,'precast_count':len(machine.precast or []),
        'fresh_observations':machine.observations,'stale_frames':machine.stale_frames,
        'capture_errors':capture_errors,'acquire_seconds':machine.p.acquire_seconds,
        'cast_seconds':machine.p.cast_seconds,'match_threshold':float(settings.match_threshold),
        'template_count':len(settings.templates),'canny_thresholds':list(settings.canny_thresholds),
        'monitor':settings.get_monitor(),'best_match_score':None,'image_path':None,
        'explanation':{
            'missing_target':'No template matched. Check the screenshot contains the bobber and templates match its current size/view.',
            'ambiguous_target':'More than one new candidate matched. The tracker abstained rather than guessing which is yours.',
            'only_precast_targets':'All matches were near objects already present before casting. The tracker did not establish ownership.',
            'stale_frame':'Processing took longer than the freshness limit; old frames are rejected.',
        }.get(machine.last_reason,'A unique new bobber did not persist for enough fresh frames.')
    }
    if frame is not None:
        gray=frame.pixels if frame.format=='gray' else cv.cvtColor(frame.pixels,cv.COLOR_BGRA2GRAY if frame.format=='bgra' else cv.COLOR_BGR2GRAY)
        edges=cv.Canny(gray,*settings.canny_thresholds)
        scores=[]
        for template in settings.templates:
            if template.ndim!=2 or not template.size or np.ptp(template)==0 or template.shape[0]>edges.shape[0] or template.shape[1]>edges.shape[1]:continue
            values=cv.matchTemplate(edges,template,cv.TM_CCOEFF_NORMED)
            if np.isfinite(values).all():scores.append(float(cv.minMaxLoc(values)[1]))
        report['best_match_score']=max(scores) if scores else None
        image=directory/'acquisition-latest.png'
        ok,encoded=cv.imencode('.png',frame.pixels)
        if ok:
            image.write_bytes(encoded.tobytes());report['image_path']=str(image)
    path=directory/'acquisition-latest.json';report['report_path']=str(path)
    path.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return report
