"""Resolve trained/evaluated files without activating weights."""
import json
from pathlib import Path
from .profiles import Profile
from .experiments import sha
from .lifecycle import ModelRegistry

def latest_candidate(root=Path('.')):
    root=Path(root)
    latest=json.loads((root/'data/training-latest.json').read_text())
    weights=Path(latest['checkpoint']);run_dir=Path(latest['run'])
    run=json.loads((run_dir/'run.json').read_text())
    if run.get('status')!='completed' or not weights.is_file() or sha(weights)!=run['checkpoint_sha256']:
        raise ValueError('Completed, unchanged trained weights required')
    profile=root/'configs/tasks/fishing-neural-v2.json'
    if not profile.exists() or Profile.read(profile).digest!=run['profile_sha256']:
        profile=root/'data/profiles'/('trained-'+run['profile_sha256'][:16]+'.json')
        profile.parent.mkdir(parents=True,exist_ok=True)
        if not profile.exists():profile.write_text(json.dumps(run['profile'],indent=2))
    result={'weights':weights.resolve(),'run':run_dir.resolve(),'profile':profile.resolve(),'evaluation':None}
    active=root/'data/evaluation-active.json'
    if active.exists():
        info=json.loads(active.read_text());report_path=Path(info['output'])/'report.json'
        if report_path.exists():
            report=json.loads(report_path.read_text())
            try:ModelRegistry._validate_evidence(Profile.read(profile),sha(weights),run,report)
            except ValueError:pass
            else:result['evaluation']=report_path.resolve()
    return result
