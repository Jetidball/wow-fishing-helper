"""Heuristic review hints only. Never edits labels or asserts a reflection is ground truth."""
import json,math
from pathlib import Path
from . import dataset as ds

def audit_labels(root):
    data=ds.load(root);findings=[]
    target=data['classes'].index('bobber') if 'bobber' in data['classes'] else 0
    for row in data['frames']:
        boxes=[b for b in row['annotation']['boxes'] if b['class_id']==target]
        reasons=[]
        for i,a in enumerate(boxes):
            for b in boxes[i+1:]:
                ax=a['x']+a['width']/2;bx=b['x']+b['width']/2
                ay=a['y']+a['height']/2;by=b['y']+b['height']/2
                if abs(ax-bx)<=max(a['width'],b['width'])*.4 and abs(ay-by)>min(a['height'],b['height'])*.6:
                    reasons.append('Vertically aligned bobber labels: check whether the lower box is a water reflection. Keep both if they are truly separate bobbers.')
        if reasons:findings.append({'frame_id':row['id'],'session_id':row['session_id'],'image':row['image'],'reasons':list(set(reasons))})
    return {'dataset':str(Path(root).resolve()),'frames':len(data['frames']),'flagged':len(findings),'findings':findings,'labels_changed':False,'human_review_required':True}

def raw_sources(frame_ids):
    wanted=set(frame_ids);found=[]
    for manifest in Path('data').glob('*/manifest.json'):
        try:
            data=ds.load(manifest.parent)
            if data.get('export'):continue
            matching=wanted.intersection(r['id'] for r in data['frames'])
            if matching:found.append((manifest.parent,matching))
        except (OSError,ValueError,KeyError,TypeError):continue
    return sorted(found,key=lambda item:len(item[1]),reverse=True)
