import time, math, sys, os
import pyautogui as pag
from pynput.keyboard import Listener, Key
from pywinauto import Application
from loguru import logger



def distance(p1, p2):
  return math.sqrt( (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2 )

def countdown(secs, status=logger.info):
  while secs > 0:
    status(str(secs) + "...")
    time.sleep(1)
    secs = secs - 1

def get_single_loc(name, status=logger.info):
  status("Point to location of %s for 1 sec in..." % name)
  countdown(3, status)
  status("Hold the cursor still over the %s..." % name)
  last_point = (0,0)
  start_time = time.time()
  while True:
    x, y = pag.position()
    if last_point == (x,y):
      if time.time() - start_time > 1:
        status(f"Location of {name} at {x}, {y}")
        return (x, y)
    else:
      start_time = time.time()
    time.sleep(0.05)
    last_point = (x, y)

def get_pole_loc(status=logger.info):
  pag.typewrite('c')
  l = get_single_loc('fishing pole', status)
  pag.typewrite('c')
  return l

def get_area_of_interest(status=logger.info):
  status("Start drawing area of interest in...")
  countdown(3, status)
  status("Hold still 1s to place each point (at least 3), hold on the last point again to finish")
  points = []
  last_point = (0,0)
  last_time = time.time()
  while True:
    x, y = pag.position()
    if(last_point != (x, y)):
      last_time = time.time()
    last_point = (x, y)
    if time.time() - last_time > 1:
      if points != [] and points[-1] == (x, y):
        if len(points) > 2:
          status(f"Area of interest set with {len(points)} points")
          return [(int(px), int(py)) for px, py in points]
        else:
          status("Must draw at least 3 points")
          last_time = time.time()
      else:
        points.append((x, y))
        last_time = time.time()
        status(f"Points: {points}")
    time.sleep(0.05)

def focus_wow_window():
  try:
    wow = Application().connect(title_re="World of Warcraft.*", found_index=0)
    wow.top_window().set_focus()
  except Exception as e:
    logger.warning(f"Could not focus the World of Warcraft window ({e}), make sure it is in front")

def exit_bot(key):
  if key is Key.esc:
    logger.info("Manual override... Exiting bot!")
    os._exit(0)

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
    on_release=exit_bot)
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
  if not settings.templates:
    logger.error("No bobber images found. Add some in the GUI's Bobber Images tab.")
    os._exit(1)
