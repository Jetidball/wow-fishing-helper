"""Compatibility imports for existing callers; implementation lives in the packages."""
import cv2 as cv
from visual_targeting.detector import METHOD, get_updated_bobber_loc
from fishing.splash import is_splash_whitepx
from fishing.task import CAUGHT, MISSED, NO_BITE, ABORTED
from fishing.task import search_and_destroy as _run

def search_and_destroy(settings, **kwargs):
    return _run(settings, matcher=get_updated_bobber_loc, splash=is_splash_whitepx, **kwargs)
