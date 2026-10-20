import time, math, sys, os, warnings
from visual_targeting.input import desktop as pag, Cancelled
from pynput.keyboard import Listener, Key
# pywinauto puts the main thread in multithreaded COM mode by default, which makes
# Windows file dialogs (the GUI's Browse/Add images/Open) hang. Use single-threaded mode instead.
sys.coinit_flags = 2
with warnings.catch_warnings():
  warnings.simplefilter("ignore", UserWarning)
  from pywinauto import Application
from loguru import logger
import safety



def distance(p1, p2):
  return math.sqrt( (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2 )

def countdown(secs, status=logger.info):
  while secs > 0:
    status(str(secs) + "...")
    pag.sleep(1)
    secs = secs - 1

def get_single_loc(name, status=logger.info):
  from visual_targeting.area_picker import request_desktop_area
  status(f"Show {name} in the game. Screenshot in 5 seconds; click the location on the frozen picture.")
  countdown(5, status)
  value = request_desktop_area(name, cancelled=pag.cancelled, point=True)
  if value is None:
    raise Cancelled("Location selection cancelled")
  return value


def get_pole_loc(status=logger.info):
  status("Open the character panel manually so the fishing pole is visible.")
  return get_single_loc("fishing pole (character panel)", status)


def get_box(name, status=logger.info):
  from visual_targeting.area_picker import request_desktop_area
  status(f"Screenshot of {name} in 3 seconds. Show the game, then drag a rectangle on the frozen picture.")
  countdown(3, status)
  value = request_desktop_area(name, cancelled=pag.cancelled)
  if value is None:
    raise Cancelled("Area selection cancelled")
  return value


def get_area_of_interest(status=logger.info):
  from visual_targeting.area_picker import request_desktop_area
  status("Screenshot in 3 seconds. Show the game, then drag a rectangle around the fishing water.")
  countdown(3, status)
  value = request_desktop_area("fishing water", polygon=True, cancelled=pag.cancelled)
  if value is None:
    raise Cancelled("Area selection cancelled")
  status(f"Area of interest set with {len(value)} corners")
  return value


def focus_wow_window():
  try:
    wow = Application().connect(title_re="Wow*", found_index=0)
    wow.top_window().set_focus()
  except Exception as e:
    logger.warning(f"Could not focus the World of Warcraft window ({e}), make sure it is in front")

def on_key_release(key):
  if key is Key.esc:
    logger.info("Manual override... Exiting bot!")
    pag.cancel()
    return False
  if key is Key.f9:
    safety.toggle_pause()

def initialize(settings):
  def get_extreme(arr, i, cmp):
    ext = arr[0][i]
    for el in arr[1:]:
      if cmp(el[i], ext):
        ext = el[i]
    return ext
  def less(a, b):
    return a < b
  def greater(a, b):
    return a > b

  # listen for manual override
  listener = Listener(
    on_release=on_key_release)
  listener.start()

  focus_wow_window()

  # ask for anything that wasn't set in the config / GUI
  if settings.attach_bait:
    if settings.bait_location is None:
      settings.bait_location = get_single_loc('bait')
    if settings.pole_location is None:
      settings.pole_location = get_pole_loc()
  if settings.logout_action == "hearth_logout" and settings.hearthstone_location is None:
    settings.hearthstone_location = get_single_loc('hearthstone')
  if settings.area_of_interest is None:
    settings.area_of_interest = get_area_of_interest()
  if settings.cast_location is None:
    settings.cast_location = get_single_loc('cast action')

  min_x = get_extreme(settings.area_of_interest, 0, less)
  min_y = get_extreme(settings.area_of_interest, 1, less)
  max_x = get_extreme(settings.area_of_interest, 0, greater)
  max_y = get_extreme(settings.area_of_interest, 1, greater)
  settings.top_left = (min_x, min_y)
  settings.bot_right = (max_x, max_y)
  settings.load_images()
  if settings.detector_backend=="template" and not settings.templates:
    logger.error("No bobber images found. Add some in the GUI's Bobber Images tab.")
    raise RuntimeError("No valid bobber templates")
