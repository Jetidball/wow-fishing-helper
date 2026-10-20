"""Explicit snapshots of existing Settings into task tools; never writes normal settings."""
import hashlib
import json
from pathlib import Path
from .profiles import Profile

def import_fishing_settings(settings,base_profile,output_directory):
    data=json.loads(json.dumps(base_profile.data))
    from settings import resolve_path
    data['model']['templates']=str(Path(resolve_path(settings.img_dir)).resolve())
    data['model']['canny_thresholds']=list(settings.canny_thresholds)
    data['confidence']=float(settings.match_threshold)
    data['review_below']=max(data['review_below'],data['confidence'])
    # A new profile file prevents silently changing an evaluated profile's identity.
    profile=Profile(data)
    folder=Path(output_directory);folder.mkdir(parents=True,exist_ok=True)
    path=folder/('fishing-'+profile.digest[:16]+'.json')
    if not path.exists():path.write_text(json.dumps(data,indent=2),encoding='utf-8')
    region=None
    if settings.area_of_interest:
        xs=[p[0] for p in settings.area_of_interest];ys=[p[1] for p in settings.area_of_interest]
        if max(xs)<=min(xs) or max(ys)<=min(ys):raise ValueError('Normal fishing area is empty')
        region=f'{min(xs)} {min(ys)} {max(xs)-min(xs)} {max(ys)-min(ys)}'
    return path,region,{
        'img_dir → model.templates':data['model']['templates'],
        'match_threshold → confidence':data['confidence'],
        'canny_thresholds → model.canny_thresholds':data['model']['canny_thresholds'],
        'area_of_interest → recording region':region or 'unset; select a game area',
        'unchanged normal-only variables':'cast_location, loot_location, bait, splash/bite, timing, safety and session settings',
        'why separate model fields':'Training labels, weights, epochs, device and evaluation evidence have no original Settings equivalent.',
        'profile_sha256':profile.digest,
        'note':'Explicit snapshot. Import again after changing normal settings; a changed profile needs new evaluation before model promotion.'
    }
