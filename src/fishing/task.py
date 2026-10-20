import time
import random
import cv2 as cv
import numpy as np
from mss import exception as MSSException
try:
  from mss import MSS as mss
except ImportError:
  from mss import mss
from loguru import logger
from visual_targeting.contracts import Box, Frame
from visual_targeting.detector import TemplateDetector, get_updated_bobber_loc
from .splash import is_splash_whitepx

# search_and_destroy results
CAUGHT = "caught"      # clicked the bobber after a splash
MISSED = "missed"      # saw the splash but reacted too late on purpose
NO_BITE = "no_bite"    # no splash before the cast timed out
ABORTED = "aborted"    # paused or quit mid cast

def search_and_destroy(settings, *, capture_factory=None, mouse=None, move=None,
                       delay=None, guard=None, clock=time.monotonic, wait_key=None, matcher=None, splash=None, detector=None):
  matcher = matcher or get_updated_bobber_loc
  splash = splash or is_splash_whitepx
  # Lazy desktop imports permit offline replay and fake-mouse tests.
  if capture_factory is None:
    capture_factory = mss
  if mouse is None:
    from visual_targeting.input import desktop as mouse
  if move is None or delay is None:
    from humanize import move_to, sleep_range
    move = move or move_to
    delay = delay or sleep_range
  if guard is None:
    import safety as guard
  wait_key = wait_key or cv.waitKey
  detector = detector or TemplateDetector(settings.templates, getattr(settings, "match_threshold", .7), settings.canny_thresholds, clock)
  monitor = settings.get_monitor()
  started = clock()

  def aborted():
    return guard.paused.is_set() or guard.check_and_pause(settings)

  def capture(sct):
    captured_at = clock()
    gray = cv.cvtColor(np.array(sct.grab(monitor)), cv.COLOR_BGRA2GRAY)
    frame = Frame(capture.sequence, captured_at, gray, Box(**monitor))
    capture.latest = frame
    capture.sequence += 1
    if matcher is get_updated_bobber_loc:
      found = detector.detect(frame)
      target = found.legacy() if found else None
    else:  # compatibility injection used by existing detector tests
      target = matcher(settings, cv.Canny(gray, *settings.canny_thresholds))
    return gray, target
  capture.sequence = 0

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
        if not splash(settings.splash_threshold_whitepx, crop):
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
        from visual_targeting.input import DesktopFacade
        if isinstance(mouse, DesktopFacade):
          mouse.send("click", button="right", frame_sequence=capture.latest.sequence,
                     captured_at=capture.latest.captured_at)
        else:
          mouse.rightClick()
        logger.info("Clicked current bobber at {}", target["center"])
        return CAUGHT
    return NO_BITE
  finally:
    cv.destroyAllWindows()


class FishingTask:
  """One cancellable cast observation, with replaceable detector and injected IO.

  Configuration remains owned by the existing Settings/GUI application. Capture,
  movement, reaction timing and safety can be injected for deterministic replay.
  """
  def __init__(self, settings, detector=None, **io):
    self.settings, self.detector, self.io = settings, detector, io

  def run(self):
    return search_and_destroy(self.settings, detector=self.detector, **self.io)
