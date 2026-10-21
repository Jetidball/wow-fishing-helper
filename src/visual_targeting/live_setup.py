"""Read-only live-fishing preflight. Never sends input or loads a neural model."""
from pathlib import Path
from .profiles import Profile
from .lifecycle import ModelRegistry
from .experiments import sha
from .geometry import Rect

def fishing_setup(settings,info,registry,hwnd,probe=None):
    profile=Profile.read(info['profile']);registry=Path(registry).resolve()
    fields={'profile':str(Path(info['profile']).resolve()),'registry':str(registry),'weights':str(Path(info['weights']).resolve())}
    blockers=[];active=None
    if profile.data['model']['backend']!='neural' or profile.data['target_class']!='bobber':blockers.append('Select a neural bobber model.')
    try:
        active=ModelRegistry(registry).active(profile)
        if active['weights_sha256']!=sha(info['weights']):
            blockers.append('This selected model is not the active approved model. Use Review / approve selected after its test passes.')
        else:fields['weights']=str(Path(active['weights_path']).resolve())
    except (OSError,ValueError,KeyError) as exc:blockers.append('Model approval: '+str(exc)+'. Evaluate selected, then Review / approve selected.')
    if blockers and info.get('evaluation'):
        import json
        from .model_results import percent
        try:
            report=json.loads(Path(info['evaluation']).read_text(encoding='utf-8'));metrics=report['backends']['selected'];gates=profile.data['promotion']
            blockers.append(f"Selected test: precision {percent(metrics.get('precision'))} (needs {percent(gates['min_precision'])}), recall {percent(metrics.get('recall'))} (needs {percent(gates['min_recall'])}), false detections/cast {metrics.get('false_detections_per_cast',{}).get('mean','unknown')} (maximum {gates['max_false_per_cast']}).")
        except (OSError,ValueError,KeyError,TypeError):pass
    if not settings.area_of_interest:blockers.append('Pick the fishing water area in Locations & Fishing.')
    if not settings.cast_location:blockers.append('Pick the Fishing ability icon in Locations & Fishing.')
    if not hwnd:blockers.append('Select the WoW game window.')
    else:
        try:
            if probe is None:
                from .window_context import query_window
                probe=query_window
            identity,client,_=probe(int(hwnd))
            if not profile.allows(identity):raise ValueError('Selected window is not allowed by this model profile.')
            if settings.area_of_interest:
                xs=[p[0] for p in settings.area_of_interest];ys=[p[1] for p in settings.area_of_interest]
                water=Rect(min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys))
                if water.width<=0 or water.height<=0 or not client.encloses(water):blockers.append('Saved water area is outside the selected game or empty. Pick it again after moving or resizing WoW.')
            if settings.cast_location:
                x,y=settings.cast_location
                if not (client.left<=x<client.left+client.width and client.top<=y<client.top+client.height):blockers.append('Saved Fishing ability is outside the selected game. Pick its action-bar icon again.')
        except (OSError,ValueError,RuntimeError) as exc:blockers.append('Game window: '+str(exc))
    if settings.attach_bait and (settings.bait_location is None or settings.pole_location is None):blockers.append('Pick bait and pole, or turn Attach bait off.')
    if not settings.auto_loot and settings.loot_location is None:blockers.append('Enable Auto Loot or pick the loot location.')
    if settings.require_gear_cursor and (not settings.gear_cursor_handle or not settings.normal_cursor_handle):blockers.append('Calibrate both cursor shapes or turn Require gear cursor off.')
    ready=not blockers
    return {'ready':ready,'fields':fields,'blockers':blockers,'hwnd':int(hwnd) if str(hwnd).isdigit() else 0,
            'message':'LIVE SETUP READY: enable live game controls, then Start fishing.' if ready else 'LIVE SETUP BLOCKED: '+' | '.join(blockers)}
