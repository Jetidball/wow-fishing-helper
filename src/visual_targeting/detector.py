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

    def candidates(self, frame, limit=32):
        """Multiple distinct screen boxes for ambiguity-aware tracking (NMS across templates)."""
        gray=frame.pixels if frame.format=="gray" else cv.cvtColor(frame.pixels,cv.COLOR_BGRA2GRAY if frame.format=="bgra" else cv.COLOR_BGR2GRAY)
        edges=cv.Canny(gray,*self.canny_thresholds)
        proposals=[]
        for template in self.templates:
            if not isinstance(template,np.ndarray) or template.ndim!=2 or not template.size or template.dtype!=np.uint8 or np.ptp(template)==0 or template.shape[0]>edges.shape[0] or template.shape[1]>edges.shape[1]:continue
            scores=cv.matchTemplate(edges,template,METHOD)
            h,w=template.shape
            for _ in range(128):
                _,score,_,(x,y)=cv.minMaxLoc(scores)
                if not np.isfinite(score) or score<self.match_threshold:break
                proposals.append((score,[x,y,x+w,y+h]))
                scores[max(0,y-h//2):y+h//2+1,max(0,x-w//2):x+w//2+1]=-1
        kept=[]
        for score,b in sorted(proposals,key=lambda p:-p[0]):
            duplicate=False
            for a in kept:
                overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-overlap
                if overlap/union>.3:duplicate=True;break
            if not duplicate:kept.append(b)
            if len(kept)>=limit:break
        return [[x1+frame.bounds.left,y1+frame.bounds.top,x2+frame.bounds.left,y2+frame.bounds.top] for x1,y1,x2,y2 in kept]
