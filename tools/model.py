"""Offline pretrained training, evaluation-only comparisons, and CPU/CUDA benchmarks. No live input."""
import argparse
import json
import math
from pathlib import Path
import sys
import cv2 as cv
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from visual_targeting.dataset import atomic_json, image_path
from visual_targeting.experiments import TrainConfig, train, exported_dataset, sha
from visual_targeting.evaluation import TemplateBackend, evaluate

def training_templates(dataset,data,count,canny):
    templates=[];sources=[]
    for row in sorted(data["frames"],key=lambda r:r["id"]):
        if row["split"]!="train":continue
        image=cv.imread(str(image_path(dataset,row["image"])),cv.IMREAD_GRAYSCALE)
        for b in row["annotation"]["boxes"]:
            x,y=math.floor(b["x"]),math.floor(b["y"])
            right,bottom=math.ceil(b["x"]+b["width"]),math.ceil(b["y"]+b["height"])
            edges=cv.Canny(image[y:bottom,x:right],*canny)
            if not edges.size or np.ptp(edges)==0:continue
            templates.append(edges);sources.append({"frame_id":row["id"],"session_id":row["session_id"],"crop":[x,y,right,bottom]})
            if len(templates)>=count:return templates,sources
    if not templates:raise ValueError("no nonconstant templates in training boxes")
    return templates,sources

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    fit=sub.add_parser("train")
    fit.add_argument("--dataset",type=Path,required=True)
    fit.add_argument("--output",type=Path,required=True)
    fit.add_argument("--config",type=Path,required=True)
    fit.add_argument("--allow-download",action="store_true")
    for name in ("evaluate","benchmark"):
        p=sub.add_parser(name)
        p.add_argument("--dataset",type=Path,required=True)
        p.add_argument("--output",type=Path,required=True)
        p.add_argument("--weights",type=Path)
        p.add_argument("--training-run",type=Path)
        p.add_argument("--split",choices=("val","test"),default="test")
        p.add_argument("--backend",choices=("both","template","neural"),default="both")
        p.add_argument("--devices",nargs="+",default=["cpu"])
        p.add_argument("--imgsz",type=int,default=960)
        p.add_argument("--confidence",type=float,default=.25)
        p.add_argument("--score-floor",type=float,default=.001)
        p.add_argument("--template-threshold",type=float,default=.7)
        p.add_argument("--template-count",type=int,default=16)
        p.add_argument("--canny",nargs=2,type=int,default=[50,150])
        p.add_argument("--small-area",type=float,default=1024)
        p.add_argument("--warmup",type=int,default=3)
        p.add_argument("--overlays",type=int,default=50)
    args=parser.parse_args(argv)
    try:
        if args.command=="train":
            if exported_dataset(args.dataset)["classes"]!=["bobber"]:raise ValueError("legacy model CLI is bobber-only; use tools/task.py for task profiles")
            best=train(args.dataset,args.output,TrainConfig.read(args.config),allow_download=args.allow_download)
            print(json.dumps({"checkpoint":str(best),"live_input_enabled":False}));return
        if args.template_count<=0 or not 0<=args.template_threshold<=1 or args.imgsz<=0:
            raise ValueError("invalid template count/threshold or image size")
        if not 0<=args.score_floor<=args.confidence<=1:raise ValueError("require 0 <= score-floor <= confidence <= 1")
        data=exported_dataset(args.dataset)
        if data["classes"]!=["bobber"]:raise ValueError("legacy model CLI is bobber-only; use tools/task.py for task profiles")
        backends={};sources=[];errors={};provenance=None
        if args.training_run:
            provenance=json.loads((args.training_run/"run.json").read_text())
            if args.weights is None or provenance.get("status")!="completed" or provenance.get("checkpoint_sha256")!=sha(args.weights):
                raise ValueError("training provenance does not match completed checkpoint")
        if args.backend in ("both","template"):
            templates,sources=training_templates(args.dataset,data,args.template_count,args.canny)
            backends["template_cpu"]=TemplateBackend(templates,args.template_threshold,args.canny)
        if args.backend in ("both","neural"):
            if args.weights is None or not args.weights.is_file():raise ValueError("neural evaluation needs local --weights")
            from visual_targeting.neural import NeuralDetector
            for device in args.devices:
                if device!="cpu" and not (device.removeprefix("cuda:").isdigit()):raise ValueError("devices must be cpu, CUDA index, or cuda:INDEX")
                key="neural_"+device.replace(":","_")
                try:backends[key]=NeuralDetector(args.weights,device=device,imgsz=args.imgsz,score_floor=args.score_floor)
                except (ValueError,RuntimeError) as exc:
                    if args.command!="benchmark":raise
                    errors[key]=str(exc)
        if not backends:raise ValueError("none of the requested inference backends is available")
        report=evaluate(args.dataset,args.output,backends,split=args.split,conf=args.confidence,
                        small_area=args.small_area,warmup=args.warmup,overlay_limit=args.overlays,provenance=provenance)
        report["command"]=args.command
        report["configuration"]={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}
        report["template_sources"]=sources
        report["checkpoint_sha256"]=sha(args.weights) if args.weights else None
        report["unavailable_backends"]=errors
        report["hardware"]={}
        for name,backend in backends.items():
            torch=getattr(backend,"torch",None)
            if torch is not None:
                report["hardware"][name]={"device":backend.device,"torch":torch.__version__,"cuda_runtime":torch.version.cuda,
                    "gpu_names":[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}
        atomic_json(args.output/"report.json",report)
        print(json.dumps({"report":str(args.output/"report.json"),"backends":list(report["backends"]),"unavailable":errors}))
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as exc:parser.error(str(exc))

if __name__=="__main__":main()
