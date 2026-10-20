"""Explicit record-label-train-evaluate-preview and reviewed model lifecycle. No input."""
import argparse
import json
from pathlib import Path
import sys

from visual_targeting import dataset as ds
from visual_targeting.profiles import Profile
from visual_targeting.lifecycle import ReviewQueue,ModelRegistry
from visual_targeting.task_workflow import record_task,label,train_task,evaluate_task,preview_task,check_dataset
from visual_targeting.experiments import TrainConfig


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile",type=Path,required=True)
    parser.add_argument("--registry",type=Path,default=Path("data/model-registry"))
    subs=parser.add_subparsers(dest="command",required=True)
    subs.add_parser("describe")
    subs.add_parser("windows")
    rec=subs.add_parser("record")
    rec.add_argument("--dataset",type=Path,required=True);rec.add_argument("--session",required=True);rec.add_argument("--cast",required=True)
    rec.add_argument("--hwnd",type=int,required=True);rec.add_argument("--region",type=int,nargs=4,required=True)
    rec.add_argument("--fps",type=float,default=5);rec.add_argument("--duration",type=float,default=30);rec.add_argument("--max-frames",type=int,default=150)
    ann=subs.add_parser("label");ann.add_argument("--dataset",type=Path,required=True);ann.add_argument("--annotations",type=Path,required=True);ann.add_argument("--reviewer",required=True)
    exp=subs.add_parser("export");exp.add_argument("--dataset",type=Path,required=True);exp.add_argument("--output",type=Path,required=True)
    exp.add_argument("--val",type=float,default=.2);exp.add_argument("--test",type=float,default=.1);exp.add_argument("--seed",type=int,default=42)
    fit=subs.add_parser("train");fit.add_argument("--dataset",type=Path,required=True);fit.add_argument("--config",type=Path,required=True);fit.add_argument("--output",type=Path,required=True);fit.add_argument("--allow-download",action="store_true")
    test=subs.add_parser("evaluate");test.add_argument("--dataset",type=Path,required=True);test.add_argument("--weights",type=Path);test.add_argument("--training-run",type=Path);test.add_argument("--output",type=Path,required=True)
    view=subs.add_parser("preview");view.add_argument("--dataset",type=Path,required=True);view.add_argument("--frame",required=True);view.add_argument("--weights",type=Path);view.add_argument("--queue",type=Path);view.add_argument("--output",type=Path,required=True)
    for name in ("review-list","review","review-export","review-preview"):
        cmd=subs.add_parser(name);cmd.add_argument("--queue",type=Path,required=True)
        if name=="review":
            cmd.add_argument("--item",required=True);cmd.add_argument("--decision",choices=("accept","reject"),required=True);cmd.add_argument("--reviewer",required=True);cmd.add_argument("--boxes",type=Path,help="human-written JSON box list, [] for explicit negative")
        if name=="review-preview":cmd.add_argument("--item",required=True);cmd.add_argument("--output",type=Path,required=True)
        if name=="review-export":cmd.add_argument("--output",type=Path,required=True)
    reg=subs.add_parser("register");reg.add_argument("--weights",type=Path,required=True);reg.add_argument("--training-run",type=Path,required=True);reg.add_argument("--evaluation",type=Path,required=True)
    for name in ("promote","rollback"):
        cmd=subs.add_parser(name);cmd.add_argument("--release",required=True);cmd.add_argument("--reviewer",required=True)
    subs.add_parser("active")
    subs.add_parser("models")
    args=parser.parse_args(argv)
    try:
        profile=Profile.read(args.profile);registry=ModelRegistry(args.registry);c=args.command
        if c=="windows":
            from visual_targeting.window_context import allowed_windows
            result={"windows":allowed_windows(profile)}
        elif c=="describe":result={"profile":profile.data,"sha256":profile.digest}
        elif c=="record":result={"saved":record_task(profile,args.dataset,args.session,args.cast,args.hwnd,args.region,fps=args.fps,duration=args.duration,max_frames=args.max_frames)}
        elif c=="label":result={"updated":label(profile,args.dataset,json.loads(args.annotations.read_text()),args.reviewer)}
        elif c=="export":
            check_dataset(profile,args.dataset,human=True,reviewed_only=True)
            result=ds.export_yolo(args.dataset,args.output,val=args.val,test=args.test,seed=args.seed)
        elif c=="train":result={"checkpoint":str(train_task(profile,args.dataset,args.output,TrainConfig.read(args.config),allow_download=args.allow_download))}
        elif c=="evaluate":result=evaluate_task(profile,args.dataset,args.output,weights=args.weights,training_run=args.training_run)
        elif c=="preview":result=preview_task(profile,args.dataset,args.frame,args.output,registry=registry,weights=args.weights,queue=ReviewQueue(args.queue) if args.queue else None)
        elif c=="models":result=registry.load()["tasks"].get(profile.task_id,{"active":None,"candidates":[]})
        elif c=="review-preview":result={"preview":ReviewQueue(args.queue).preview(args.item,args.output)}
        elif c=="review-list":result=ReviewQueue(args.queue).load()
        elif c=="review":
            ReviewQueue(args.queue).decide(profile,args.item,args.decision,args.reviewer,json.loads(args.boxes.read_text()) if args.boxes else None);result={"decision":args.decision}
        elif c=="review-export":result={"saved":ReviewQueue(args.queue).export(profile,args.output)}
        elif c=="register":result={"candidate":registry.register(profile,args.weights,args.training_run/"run.json",args.evaluation)}
        elif c=="promote":registry.promote(profile,args.release,args.reviewer);result={"promoted":args.release}
        elif c=="rollback":registry.rollback(profile,args.release,args.reviewer);result={"rolled_back":args.release}
        else:
            result=registry.active(profile);result["weights_path"]=str(result["weights_path"])
        result["live_input_enabled"]=False
        print(json.dumps(result,allow_nan=False))
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,ImportError) as exc:parser.error(str(exc))

if __name__=="__main__":main()
