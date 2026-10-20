"""Prepare reviewed data and train a candidate. No input adapters or model promotion."""
import argparse,json,time,os
from pathlib import Path
from . import dataset as ds
from .profiles import Profile
from .experiments import TrainConfig
from .task_workflow import check_dataset,train_task

def run(args):
    profile=Profile.read(args.profile)
    if profile.data['model']['backend']!='neural':raise ValueError('Neural profile required')
    output=Path(args.output).resolve()
    if output.exists():raise ValueError('Use a fresh run folder')
    data,_=check_dataset(profile,args.dataset,human=True,reviewed_only=True)
    reviewed=[r for r in data['frames'] if r['annotation']['reviewed']]
    sessions={r['session_id'] for r in reviewed}
    if len(sessions)<2:raise ValueError('Review examples from at least 2 independent sessions for training/validation')
    if not any(r['annotation']['boxes'] for r in reviewed):raise ValueError('At least one reviewed positive box is required')
    export=Path('datasets')/(output.name+'-reviewed')
    print(f'Preparing {len(reviewed)} human-reviewed frames from {len(sessions)} sessions. Unreviewed frames are excluded.',flush=True)
    splits=ds.export_yolo(args.dataset,export)
    print('Session-split export: '+json.dumps(splits),flush=True)
    if splits['test']==0:
        print('INITIAL CANDIDATE ONLY: no reviewed third session is available for independent held-out testing. No promotion will occur.',flush=True)
    import torch
    torch.set_num_threads(min(8,os.cpu_count() or 1))
    device='0' if torch.cuda.is_available() else 'cpu'
    print(f'Training device: {device}; epochs={args.epochs}, image size={args.imgsz}, batch={args.batch}. No game input.',flush=True)
    config=TrainConfig(model=args.model,epochs=args.epochs,imgsz=args.imgsz,batch=args.batch,device=device,workers=0)
    checkpoint=train_task(profile,export,output,config,allow_download=args.allow_download)
    result={'status':'completed','checkpoint':str(checkpoint),'run':str(output),'dataset':str(export.resolve()),
            'splits':splits,'independent_test_available':splits['test']>0,'promoted':False,'live_input_enabled':False}
    status=Path('data/training-latest.json');status.parent.mkdir(parents=True,exist_ok=True);ds.atomic_json(status,result)
    print(json.dumps(result),flush=True)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True,type=Path)
    parser.add_argument('--dataset',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--model',default='yolo11n.pt')
    parser.add_argument('--epochs',type=int,default=5)
    parser.add_argument('--imgsz',type=int,default=640)
    parser.add_argument('--batch',type=int,default=4)
    parser.add_argument('--allow-download',action='store_true')
    run(parser.parse_args())

if __name__=='__main__':main()
