"""Configurable detector for the original fishing loop. Neural weights load once."""
from pathlib import Path
from visual_targeting.detector import TemplateDetector

def make_fishing_detector(settings,*,live_input=False):
    backend=getattr(settings,'detector_backend','template')
    if backend=='template':
        return TemplateDetector(settings.templates,settings.match_threshold,settings.canny_thresholds)
    if backend!='neural':raise ValueError('Unknown fishing detector backend')
    from settings import resolve_path
    from visual_targeting.profiles import Profile,make_detector
    from visual_targeting.lifecycle import ModelRegistry
    profile=Profile.read(resolve_path(settings.neural_profile))
    if profile.data['model']['backend']!='neural' or profile.data['target_class']!='bobber':
        raise ValueError('Select a neural bobber profile')
    registry=ModelRegistry(resolve_path(settings.neural_registry))
    if live_input:
        # Requires matching immutable evidence, quality gates and explicit user promotion.
        return make_detector(profile,registry)
    weights=getattr(settings,'neural_weights','')
    if weights:return make_detector(profile,registry,weights=resolve_path(weights),candidate=True)
    return make_detector(profile,registry)
