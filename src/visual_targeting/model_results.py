"""Lightweight model history: read metadata/CSV only, never load weights or images."""
import csv,json,math,hashlib
from pathlib import Path
from .profiles import Profile
from .lifecycle import ModelRegistry

def fraction(value):
    try:value=float(value)
    except (TypeError,ValueError):return None
    return value if math.isfinite(value) and 0<=value<=1 else None

def percent(value):
    value=fraction(value)
    return '—' if value is None else f'{value*100:.1f}%'

def f1(precision,recall):
    if precision is None or recall is None:return None
    return 2*precision*recall/(precision+recall) if precision+recall else 0.0

def validation_metrics(path):
    if not path.is_file():return {}
    with path.open(newline='',encoding='utf-8-sig') as stream:
        rows=[{k.strip():v.strip() for k,v in row.items() if k is not None and v is not None} for row in csv.DictReader(stream)]
    if not rows:return {}
    row=rows[-1]
    p=fraction(row.get('metrics/precision(B)'));r=fraction(row.get('metrics/recall(B)'))
    return {'precision':p,'recall':r,'ap50':fraction(row.get('metrics/mAP50(B)')),
            'map50_95':fraction(row.get('metrics/mAP50-95(B)')),'f1':f1(p,r),
            'epoch':row.get('epoch'),'scope':'Validation — last epoch'}

def model_results(root):
    root=Path(root);runs=root/'runs';reports=[];errors=[]
    if not runs.is_dir():return [],errors
    for path in runs.glob('*/report.json'):
        try:
            report=json.loads(path.read_text(encoding='utf-8'))
            if report.get('status')=='completed' and report.get('kind')=='task_evaluation':
                reports.append((path.stat().st_mtime_ns,path,report))
        except (OSError,ValueError,TypeError) as exc:errors.append(f'{path.name}: {exc}')
    reports.sort(reverse=True,key=lambda item:item[0])
    approved={};active=set()
    registry=root/'data/model-registry'
    try:
        registered=ModelRegistry(registry).load()
        for task in registered['tasks'].values():
            for release in task.get('approved',[]):
                info=json.loads((registry/'releases'/release/'release.json').read_text())
                key=(info['profile_sha256'],info['weights_sha256'])
                approved[key]=release
                if task.get('active')==release:active.add(key)
    except (OSError,ValueError,KeyError,TypeError) as exc:errors.append(f'Registry: {exc}')
    rows=[]
    for path in sorted(runs.glob('*/run.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True):
        try:
            run=json.loads(path.read_text(encoding='utf-8'))
            if run.get('kind')!='training':continue
            config=run.get('config',{})
            val=validation_metrics(path.parent/'fit/results.csv')
            match=None;report_file=None
            if run.get('profile') and run.get('checkpoint_sha256'):
                profile=Profile(run['profile'])
                for _,report_path,report in reports:
                    try:ModelRegistry._validate_evidence(profile,run['checkpoint_sha256'],run,report)
                    except (ValueError,KeyError,TypeError):continue
                    match=report;report_file=report_path;break
            metrics=match['backends']['selected'] if match else val
            p=fraction(metrics.get('precision'));r=fraction(metrics.get('recall'))
            key=(run.get('profile_sha256'),run.get('checkpoint_sha256'))
            verdict='Needs held-out test'
            if run.get('status')!='completed':verdict='Training '+str(run.get('status','unknown'))
            elif match:
                try:ModelRegistry(registry)._quality(Profile(run['profile']),match)
                except (ValueError,KeyError,TypeError):verdict='Needs improvement'
                else:verdict='Meets thresholds; not approved'
                if key in approved:verdict='Approved' if key not in active else 'Active — approved'
            comparison=None
            if match:
                comparison=hashlib.sha256(json.dumps([sorted(match['frame_ids']),match.get('test_truth_sha256',match['human_review_sha256']),match.get('detection_metrics_version',1)]).encode()).hexdigest()[:12]
            weights=Path(run.get('checkpoint',path.parent/'fit/weights/best.pt'))
            rows.append({
                'name':path.parent.name,'run_dir':path.parent,'run':run,
                'status':run.get('status','unknown'),'scope':'Independent test' if match else val.get('scope','Not evaluated'),
                'precision':p,'recall':r,'f1':f1(p,r),
                'ap50':fraction(metrics.get('ap50')),'map50_95':fraction(metrics.get('map50_95')),
                'validation':val,'evaluation':match,'evaluation_file':report_file,
                'metrics':metrics,'verdict':verdict,'weights':weights,'config':config,'comparison':comparison})
        except (OSError,ValueError,KeyError,TypeError) as exc:errors.append(f'{path.parent.name}: {exc}')
    return rows,errors
