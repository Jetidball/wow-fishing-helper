"""Headless preview of the local target-app task; no desktop IO."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from visual_targeting.profiles import Profile
from visual_targeting.local_demo import run_demo
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--profile",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    print(json.dumps(run_demo(Profile.read(a.profile),a.output)))
