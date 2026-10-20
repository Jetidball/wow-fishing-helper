import time
import cv2 as cv
import numpy as np
from .contracts import Box, Detection, Frame, Point

METHOD = cv.TM_CCOEFF_NORMED

def get_updated_bobber_loc(settings, img):
  """Return a fresh accepted match in screen coordinates, or None."""
  if (not isinstance(img, np.ndarray) or img.ndim != 2 or not img.size or
      img.dtype not in (np.uint8, np.float32) or not np.isfinite(img).all()):
    return None
  threshold = float(getattr(settings, "match_threshold", 0.7))
  if not np.isfinite(threshold) or not 0 <= threshold <= 1:
    raise ValueError("match_threshold must be between 0 and 1")
  best = None
  for template in settings.templates:
    if (not isinstance(template, np.ndarray) or template.ndim != 2 or not template.size or
        template.dtype != img.dtype or template.shape[0] > img.shape[0] or
        template.shape[1] > img.shape[1] or not np.isfinite(template).all() or np.ptp(template) == 0):
      continue
    res = cv.matchTemplate(img, template, METHOD)
    if not np.isfinite(res).all():
      continue
    _, score, _, loc = cv.minMaxLoc(res)
    if score < threshold or (best is not None and score <= best["value"]):
      continue
    h, w = template.shape
    left, top = loc[0] + settings.get_left(), loc[1] + settings.get_top()
    best = {"box": {"left": int(left), "top": int(top), "width": int(w), "height": int(h)},
            "center": (int(left + w / 2), int(top + h / 2)), "value": score}
  return best


class TemplateDetector:
    """Existing Canny + TM_CCOEFF_NORMED detector; no model or desktop dependencies."""
    def __init__(self, templates, threshold=.7, canny_thresholds=(100, 200), clock=time.monotonic):
        self.templates = templates
        self.match_threshold = threshold
        self.canny_thresholds = canny_thresholds
        self.clock = clock

    def detect(self, frame: Frame) -> Detection | None:
        gray = frame.pixels if frame.format == "gray" else cv.cvtColor(
            frame.pixels, cv.COLOR_BGRA2GRAY if frame.format == "bgra" else cv.COLOR_BGR2GRAY)
        edges = cv.Canny(gray, *self.canny_thresholds)
        from types import SimpleNamespace
        settings = SimpleNamespace(templates=self.templates, match_threshold=self.match_threshold,
                                  get_left=lambda: frame.bounds.left, get_top=lambda: frame.bounds.top)
        match = get_updated_bobber_loc(settings, edges)
        if match is None:
            return None
        return Detection(frame.sequence, frame.captured_at, self.clock(), Box(**match["box"]),
                         Point(*match["center"]), match["value"])
