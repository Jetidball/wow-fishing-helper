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
CLICK_ISSUED = "click_issued"
CAUGHT = CLICK_ISSUED  # deprecated compatibility name; never means catch-confirmed
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
  """Bounded tracker runner. No movement/input imports unless explicitly enabled.

  Pre-cast candidates are required. catch_check must provide independent loot/game
  evidence; disappearance alone never confirms a catch.
  """
  def __init__(self, settings, detector=None, *, precast=None, live_input=False, policy=None,
               bite_backend="temporal", catch_check=None, **io):
    self.settings,self.detector,self.io=settings,detector,io
    self.precast,self.live_input,self.policy=precast,live_input,policy
    self.bite_backend,self.catch_check=bite_backend,catch_check
    self.machine=None

  def run(self):
    from .sequence import CastTask, Policy, State
    settings=self.settings
    clock=self.io.get("clock",time.monotonic)
    guard=self.io.get("guard")
    if guard is None:
      import safety as guard
    stop=self.io.get("cancelled")
    def stopped():
      return bool((stop is not None and stop.is_set()) or guard.paused.is_set() or guard.check_and_pause(settings))
    if stopped():return ABORTED
    started=self.io.get("cast_started")
    searching=clock()
    self.machine=CastTask(searching if started is None else started,self.precast,self.policy or Policy(
                          acquire_seconds=getattr(settings,"acquire_timeout",8.0),cast_seconds=settings.cast_timeout,
                          white_threshold=settings.splash_threshold_whitepx),self.bite_backend,acquisition_started=searching)
    if self.machine.outcome:return self.machine.outcome
    factory=self.io.get("capture_factory",mss)
    detector=self.detector or TemplateDetector(settings.templates,getattr(settings,"match_threshold",.7),settings.canny_thresholds,clock)
    if not hasattr(detector,"candidates"):raise ValueError("tracked task requires a multi-candidate detector")
    wait=self.io.get("wait_key",cv.waitKey)
    monitor=settings.get_monitor();sequence=0;last_frame=None;capture_errors=0;last_progress=searching
    logger.info("Finding bobber: search budget={}s, total cast timeout={}s, threshold={}, templates={}, pre-cast matches={}, area={}",
                self.machine.p.acquire_seconds,self.machine.p.cast_seconds,getattr(settings,"match_threshold",.7),
                len(settings.templates),len(self.precast or []),monitor)
    try:
      with factory() as capture:
        while self.machine.state!=State.DONE:
          cancelled=stopped() or wait(25)&0xff in (27,ord("q"))
          now=clock()
          if cancelled:self.machine.finish("aborted");break
          try:
            frame=Frame(sequence,now,np.array(capture.grab(monitor)),Box(**monitor),"bgra")
          except MSSException.ScreenShotError:
            capture_errors+=1
            self.machine.update(None,[],now)  # deadlines advance without old pixels
            continue
          sequence+=1;last_frame=frame
          confirmed=False
          if self.machine.click_issued and self.catch_check:
            try: confirmed=bool(self.catch_check())
            except MSSException.ScreenShotError: pass
          prior=self.machine.state
          candidates=detector.candidates(frame)
          observed=clock()
          action=self.machine.update(frame,candidates,observed,catch_confirmed=confirmed)
          if self.machine.state==State.ACQUIRE and observed-last_progress>=1:
            logger.info("Bobber search: {} | matches={} new={} excluded={} confirmed_frames={}/{} frame_age={:.3f}s remaining={:.1f}s",
                        self.machine.reason,self.machine.candidate_count,self.machine.eligible_count,self.machine.excluded_count,
                        self.machine.hits,self.machine.p.acquire_frames,observed-frame.captured_at,
                        max(0,self.machine.p.acquire_seconds-(observed-self.machine.acquire_started)))
            last_progress=observed
          if self.machine.state!=prior:
            logger.info("Fishing state {} -> {}: {}",prior.value,self.machine.state.value,self.machine.reason)
          if action:
            if not self.live_input:
              self.machine.finish("click_proposed")
              break
            # Explicit opt-in only; recheck cancellation and frame age immediately before input.
            if stopped() or clock()-frame.captured_at>self.machine.p.max_frame_age:
              self.machine.finish("aborted");break
            mouse=self.io.get("mouse")
            move=self.io.get("move")
            if mouse is None:
              from visual_targeting.input import desktop as mouse
            if move is None:
              from humanize import move_to as move
            move(settings,action["point"],use_jitter=False)
            if stopped() or clock()-frame.captured_at>self.machine.p.max_frame_age:
              self.machine.finish("aborted");break
            accepted=mouse.rightClick()
            self.machine.acknowledge_click(accepted is not False,clock())
    finally:
      cv.destroyAllWindows()
    if self.machine.outcome=="acquisition_expired":
      from .diagnostics import save_acquisition_report
      try:
        report=save_acquisition_report(settings,self.machine,last_frame,capture_errors=capture_errors)
        logger.warning("Bobber not acquired: {}. Best match={} vs threshold={}; matches={} new={} stale_frames={}. Report: {}",
                       report["last_reason"],report["best_match_score"],report["match_threshold"],
                       report["candidate_count"],report["eligible_count"],report["stale_frames"],report["report_path"])
      except Exception as exc:
        logger.warning("Could not save acquisition diagnostics: {}",exc)
    return self.machine.outcome
