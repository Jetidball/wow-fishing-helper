import time
import random
import cv2 as cv
import numpy as np
from mss import exception as MSSException
try:
  from mss import MSS as mss
except ImportError:
  from mss import mss
from splash_detector import is_splash_whitepx
from loguru import logger

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

# search_and_destroy results
CAUGHT = "caught"      # clicked the bobber after a splash
MISSED = "missed"      # saw the splash but reacted too late on purpose
NO_BITE = "no_bite"    # no splash before the cast timed out
ABORTED = "aborted"    # paused or quit mid cast

def search_and_destroy(settings, *, capture_factory=None, mouse=None, move=None,
                       delay=None, guard=None, clock=time.monotonic, wait_key=None):
  # Lazy desktop imports permit offline replay and fake-mouse tests.
  if capture_factory is None:
    capture_factory = mss
  if mouse is None:
    import pyautogui as mouse
  if move is None or delay is None:
    from humanize import move_to, sleep_range
    move = move or move_to
    delay = delay or sleep_range
  if guard is None:
    import safety as guard
  wait_key = wait_key or cv.waitKey
  monitor = settings.get_monitor()
  started = clock()

  def aborted():
    return guard.paused.is_set() or guard.check_and_pause(settings)

  def capture(sct):
    gray = cv.cvtColor(np.array(sct.grab(monitor)), cv.COLOR_BGRA2GRAY)
    edges = cv.Canny(gray, *settings.canny_thresholds)
    return gray, get_updated_bobber_loc(settings, edges)

  try:
    with capture_factory() as sct:
      while clock() - started <= settings.cast_timeout:
        if aborted() or wait_key(25) & 0xFF in (ord("q"), 27):
          return ABORTED
        try:
          gray, target = capture(sct)
        except MSSException.ScreenShotError:
          continue  # never retain a target from a failed capture
        if target is None:
          continue
        if aborted():
          return ABORTED
        move(settings, target["center"], use_jitter=False)
        box = target["box"]
        x, y = box["left"] - monitor["left"], box["top"] - monitor["top"]
        crop = gray[y:y + box["height"], x:x + box["width"]]
        if not is_splash_whitepx(settings.splash_threshold_whitepx, crop):
          continue
        if random.random() < settings.miss_chance:
          delay(settings, (3, 7))
          return ABORTED if aborted() else MISSED
        delay(settings, settings.bobber_click_delay)
        if aborted():
          return ABORTED
        if clock() - started > settings.cast_timeout:
          return NO_BITE
        # Reacquire after reaction time; the previous coordinates are no longer safe.
        try:
          _, target = capture(sct)
        except MSSException.ScreenShotError:
          continue
        if target is None:
          continue
        move(settings, target["center"], use_jitter=False)
        if aborted():
          return ABORTED
        mouse.rightClick()
        logger.info("Clicked current bobber at {}", target["center"])
        return CAUGHT
    return NO_BITE
  finally:
    cv.destroyAllWindows()
