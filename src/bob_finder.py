import time, sys, os
import cv2 as cv
import numpy as np
from mss import exception as MSSException
try:
  from mss import MSS as mss
except ImportError:
  from mss import mss
from splash_detector import is_splash_whitepx
import pyautogui as pag
from loguru import logger
from humanize import move_to, sleep_range

METHOD = cv.TM_CCOEFF_NORMED

def get_updated_bobber_loc(settings, img):
  highest_val = -1
  target = None
  for template in settings.templates:
    h, w = template.shape
    res = cv.matchTemplate(img, template, METHOD)
    _, max_val, _, max_loc = cv.minMaxLoc(res)
    if max_val > highest_val:
      highest_val = max_val
      target = max_loc
  center = (int(target[0] + w / 2 + settings.get_left()), int(target[1] + h / 2 + settings.get_top()))
  return {
    "box": {
      "top": int(center[1] - h / 2),
      "left": int(center[0] - w / 2),
      "width": int(w),
      "height": int(h)
    },
    "center": center,
    "value": highest_val
  }

def search_and_destroy(settings):
  monitor = settings.get_monitor()
  start_time = time.time()

  with mss() as sct:
    best_target = None
    best_target_value = 0
    while "Screen capturing":
      if time.time() - start_time > settings.cast_timeout:
        return False
      if cv.waitKey(25) & 0xFF == ord("q"):
        break
      img = None
      try:
        img = cv.cvtColor(np.array(sct.grab(monitor)), cv.COLOR_BGRA2GRAY)
      except (MSSException.ScreenShotError):
        continue
      img = cv.Canny(img, settings.canny_thresholds[0], settings.canny_thresholds[1])

      updated_bobber = get_updated_bobber_loc(settings, img)
      if (updated_bobber["value"] > best_target_value):
        best_target_value = updated_bobber["value"]
        best_target = updated_bobber
        x, y = best_target["center"]
        move_to(settings, (x, y))
        logger.info(f"New bobber at ({x}, {y}) with value of {best_target_value}")

      try:
        img = cv.cvtColor(np.array(sct.grab(best_target["box"])), cv.COLOR_BGRA2GRAY)
      except (MSSException.ScreenShotError):
        continue
      is_splashed = is_splash_whitepx(settings.splash_threshold_whitepx, img)
      if is_splashed:
        delay = sleep_range(settings, settings.bobber_click_delay)
        logger.info(f"Splash! Clicking bobber after {delay:.2f}s")
        pag.rightClick()
        return True

  cv.destroyAllWindows()
  return False
