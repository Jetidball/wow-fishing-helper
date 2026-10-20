"""Input-free fishing state-machine comparison on labeled image sequences."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from settings import Settings
from visual_targeting.detector import TemplateDetector
from fishing.replay import evaluate_sequences

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequences",type=Path,required=True)
    parser.add_argument("--templates",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error("output already exists")
    settings=Settings();settings.img_dir=str(args.templates.resolve());settings.load_images()
    if not settings.templates:parser.error("no valid templates")
    detector=TemplateDetector(settings.templates,settings.match_threshold,settings.canny_thresholds)
    try:report=evaluate_sequences(args.sequences,detector)
    except (ValueError,OSError,KeyError,TypeError) as exc:parser.error(str(exc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as file:json.dump(report,file,indent=2,allow_nan=False)
    print(json.dumps(report))
if __name__=="__main__":main()
