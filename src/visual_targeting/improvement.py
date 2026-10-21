"""Bounded human-review collection and refinement with frozen held-out sessions."""
import argparse,copy,json,time,uuid,shutil
from pathlib import Path
from . import dataset as ds
from .experiments import exported_dataset,sha,TrainConfig

class ExampleCollector:
    def __init__(self,root,profile,model_sha,max_frames=360,interval=5):
        self.root=Path(root);self.profile=profile;self.model_sha=model_sha
        self.session='visit_'+uuid.uuid4().hex[:16];self.count=0;self.last=-float('inf')
        self.max_frames=max_frames;self.interval=interval;self.started=time.monotonic()
    def add(self,profile,frame,reason,*,suggestion=None,source=None):
        now=time.monotonic()
        if self.count>=self.max_frames or now-self.started>1800 or now-self.last<self.interval:return None
        self.last=now
        import cv2 as cv
        image=frame.pixels.copy()
        if frame.format=='gray':image=cv.cvtColor(image,cv.COLOR_GRAY2BGR)
        elif frame.format=='bgra':image=cv.cvtColor(image,cv.COLOR_BGRA2BGR)
        class Capture:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def grab(self,region):return cv.cvtColor(image,cv.COLOR_BGR2BGRA)
        ds.record(self.root,self.session,'observation_'+str(self.count),
            (frame.bounds.left,frame.bounds.top,frame.bounds.width,frame.bounds.height),
            max_frames=1,capture_factory=Capture,classes=profile.data['allowed_classes'],metadata={
            'task_id':profile.task_id,'profile_sha256':profile.digest,'model_artifact_sha256':self.model_sha,
            'reason':reason,'suggestion_only':suggestion,'source_frame_sequence':frame.sequence,
            'source_captured_at':frame.captured_at,'session_is_visit':True,
            'cast_id_is_observation_not_game_cast':True,'human_review_required':True})
        self.count+=1
        return self.count

def prepare_refinement(base_dataset,new_data,output):
    """Only new human-reviewed visits enter training. Every existing split stays frozen."""
    base=exported_dataset(base_dataset);new=ds.validate(new_data)
    if new['classes']!=base['classes']:raise ValueError('Review dataset classes differ from selected model')
    new_rows=[r for r in new['frames'] if r['annotation']['reviewed'] and r['annotation'].get('review_source')=='human' and r['session_id'] not in base['sessions']]
    if not new_rows:raise ValueError('No new human-reviewed visits yet. Run & collect, Stop, then Review new pictures. Existing test/validation visits cannot be added to training.')
    output=Path(output)
    if output.exists():raise ValueError('Fresh refinement dataset folder required')
    if not any(r['split']=='test' for r in base['frames']):raise ValueError('Selected model has no independent test visits. Record/label a third visit and train a baseline first.')
    raw=output.with_name(output.name+'-source');raw.mkdir(parents=True,exist_ok=False)
    combined=copy.deepcopy(base);combined.pop('export',None);combined['frames']=[]
    ids={r['id'] for r in base['frames']}
    if any(r['id'] in ids for r in new_rows):raise ValueError('New data reuses existing frame IDs')
    assignment=dict(base['export']['session_splits'])
    for source,rows in ((Path(base_dataset),base['frames']),(Path(new_data),new_rows)):
        for row in rows:
            row=copy.deepcopy(row);original=row['image'];row.pop('split',None)
            row['image']='images/'+row['id']+'.png'
            destination=ds.image_path(raw,row['image']);destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(ds.image_path(source,original),destination)
            combined['frames'].append(row)
            if source==Path(new_data):
                combined['sessions'][row['session_id']]=new['sessions'][row['session_id']]
                assignment[row['session_id']]='train'
    ds.atomic_json(raw/'manifest.json',combined)
    ds.export_yolo(raw,output,session_assignment={r['session_id']:assignment[r['session_id']] for r in combined['frames']})
    return output

def run(args):
    from .deployment import candidate_for_run
    from .profiles import Profile
    from .gpu import require_gpu
    from .task_workflow import train_task,evaluate_task
    device=require_gpu(args.device)
    info=candidate_for_run(args.run);profile=Profile.read(info['profile'])
    parent=json.loads((info['run']/'run.json').read_text())
    base=Path(args.dataset)
    if sha(base/'manifest.json')!=parent['dataset_manifest_sha256']:raise ValueError('Selected model training dataset changed')
    output=Path(args.output).resolve();dataset=prepare_refinement(base,args.new_data,Path('datasets')/(output.name+'-reviewed'))
    print('Refining on GPU '+device+'; existing validation/test sessions frozen. New labels enter training only.',flush=True)
    checkpoint=train_task(profile,dataset,output,TrainConfig(model=str(info['weights']),epochs=10,imgsz=960,batch=4,device=device))
    provenance=json.loads((output/'run.json').read_text())
    provenance.update(parent_run=str(info['run']),parent_checkpoint_sha256=parent['checkpoint_sha256'],frozen_session_splits=ds.load(base)['export']['session_splits'],refinement_data=str(Path(args.new_data).resolve()))
    ds.atomic_json(output/'run.json',provenance)
    report_dir=output.with_name(output.name+'-evaluation')
    evaluate_task(profile,dataset,report_dir,weights=checkpoint,training_run=output)
    Path('data').mkdir(exist_ok=True)
    record={'status':'completed','checkpoint':str(checkpoint),'run':str(output),'dataset':str(dataset.resolve()),'parent_run':str(info['run']),'promoted':False,'live_input_enabled':False}
    ds.atomic_json(Path('data/training-latest.json'),record)
    ds.atomic_json(Path('data/evaluation-active.json'),{'output':str(report_dir),'profile':str(info['profile'])})
    print('Refinement and independent evaluation complete. Review Model results. Working model unchanged.',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run','dataset','new-data','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--device',default='0');run(p.parse_args())
if __name__=='__main__':main()
