import cv2 as cv
import os, json
from loguru import logger

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SRC_DIR, 'config', 'config.json')
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.bmp')

def resolve_path(path):
  # relative paths in the config are relative to the src folder
  return path if os.path.isabs(path) else os.path.normpath(os.path.join(SRC_DIR, path))

def _point(p):
  return None if p is None else (int(p["x"]), int(p["y"]))

def _to_point(p):
  return None if p is None else {"x": int(p[0]), "y": int(p[1])}

def _range(r):
  return (float(r[0]), float(r[1]))

class Settings():
  def __init__(self):
    self.is_testing = False
    self.area_of_interest = None
    self.top_left = None
    self.bot_right = None
    self.bait_location = None
    self.pole_location = None
    self.cast_location = None
    self.loot_location = None
    self.hearthstone_location = None
    self.auto_loot = False
    self.img_dir = "../images"
    self.splash_threshold_whitepx = 25
    self.canny_thresholds = [80, 180]
    self.attach_bait = False
    self.num_bait = 3
    self.bait_interval_mins = 10

    # timing, all ranges are (min, max) in seconds
    self.cast_delay = (0.25, 1.0)            # wait before casting again
    self.splash_search_delay = (1.5, 2.0)    # wait after casting before looking for the bobber
    self.bobber_click_delay = (0.5, 1.5)     # reaction time after a splash
    self.loot_delay = (0.3, 0.8)
    self.mouse_move_duration = (0.2, 0.6)
    self.click_jitter_px = 3
    self.cast_timeout = 30
    self.timing_distribution = "gaussian"    # "uniform" or "gaussian"

    # humanization, chances are 0..1 and rolled once per cast
    self.random_click_chance = 0.05
    self.random_move_chance = 0.03
    self.move_jump = True
    self.move_sidestep = False
    self.move_mouse_wander = True
    self.short_break_chance = 0.02
    self.short_break_secs = (10, 45)

    # session
    self.logout_mode = "fixed"               # "never", "fixed" or "random"
    self.logout_after_mins = 60
    self.logout_random_mins = (45, 90)
    self.logout_action = "logout"            # "logout", "hearth_logout" or "quit"
    self.relogin = False
    self.relogin_break_mins = (10, 30)
    self.relogin_load_secs = 30
    self.relogin_first_person = True
    self.max_sessions = 0                    # 0 = unlimited

    self.templates = []

  def apply(self, data):
    self.attach_bait = data.get("attachBait", self.attach_bait)
    self.num_bait = data.get("numBait", self.num_bait)
    self.bait_interval_mins = data.get("baitIntervalMins", self.bait_interval_mins)
    self.auto_loot = data.get("autoLoot", self.auto_loot)
    self.img_dir = data.get("imgDir") or data.get("imageDir") or self.img_dir
    self.splash_threshold_whitepx = data.get("splashThresholdWhitePx", self.splash_threshold_whitepx)
    self.bait_location = _point(data.get("baitLocation"))
    self.pole_location = _point(data.get("poleLocation"))
    self.cast_location = _point(data.get("castLocation"))
    self.loot_location = _point(data.get("lootLocation"))
    self.hearthstone_location = _point(data.get("hearthstoneLocation"))
    aoi = data.get("areaOfInterest") or []
    self.area_of_interest = [_point(p) for p in aoi] if len(aoi) > 2 else None

    t = data.get("timing", {})
    self.cast_delay = _range(t.get("castDelay", self.cast_delay))
    self.splash_search_delay = _range(t.get("splashSearchDelay", self.splash_search_delay))
    self.bobber_click_delay = _range(t.get("bobberClickDelay", self.bobber_click_delay))
    self.loot_delay = _range(t.get("lootDelay", self.loot_delay))
    self.mouse_move_duration = _range(t.get("mouseMoveDuration", self.mouse_move_duration))
    self.click_jitter_px = t.get("clickJitterPx", self.click_jitter_px)
    self.cast_timeout = t.get("castTimeout", self.cast_timeout)
    self.timing_distribution = t.get("distribution", self.timing_distribution)

    h = data.get("humanize", {})
    self.random_click_chance = h.get("randomClickChance", self.random_click_chance)
    self.random_move_chance = h.get("randomMoveChance", self.random_move_chance)
    self.move_jump = h.get("moveJump", self.move_jump)
    self.move_sidestep = h.get("moveSidestep", self.move_sidestep)
    self.move_mouse_wander = h.get("moveMouseWander", self.move_mouse_wander)
    self.short_break_chance = h.get("shortBreakChance", self.short_break_chance)
    self.short_break_secs = _range(h.get("shortBreakSecs", self.short_break_secs))

    s = data.get("session")
    if s is None and "timeInSecsBeforeLogout" in data:
      # migrate the old config format
      s = {
        "logoutMode": "fixed",
        "logoutAfterMins": data["timeInSecsBeforeLogout"] / 60,
        "logoutAction": "hearth_logout" if data.get("gracefulExit") else "quit",
      }
    s = s or {}
    self.logout_mode = s.get("logoutMode", self.logout_mode)
    self.logout_after_mins = s.get("logoutAfterMins", self.logout_after_mins)
    self.logout_random_mins = _range(s.get("logoutRandomMins", self.logout_random_mins))
    self.logout_action = s.get("logoutAction", self.logout_action)
    self.relogin = s.get("relogin", self.relogin)
    self.relogin_break_mins = _range(s.get("reloginBreakMins", self.relogin_break_mins))
    self.relogin_load_secs = s.get("reloginLoadSecs", self.relogin_load_secs)
    self.relogin_first_person = s.get("reloginFirstPerson", self.relogin_first_person)
    self.max_sessions = s.get("maxSessions", self.max_sessions)

  def to_dict(self):
    return {
      "attachBait": self.attach_bait,
      "numBait": self.num_bait,
      "baitIntervalMins": self.bait_interval_mins,
      "autoLoot": self.auto_loot,
      "imgDir": self.img_dir,
      "splashThresholdWhitePx": self.splash_threshold_whitepx,
      "castLocation": _to_point(self.cast_location),
      "poleLocation": _to_point(self.pole_location),
      "baitLocation": _to_point(self.bait_location),
      "lootLocation": _to_point(self.loot_location),
      "hearthstoneLocation": _to_point(self.hearthstone_location),
      "areaOfInterest": [_to_point(p) for p in (self.area_of_interest or [])],
      "timing": {
        "castDelay": list(self.cast_delay),
        "splashSearchDelay": list(self.splash_search_delay),
        "bobberClickDelay": list(self.bobber_click_delay),
        "lootDelay": list(self.loot_delay),
        "mouseMoveDuration": list(self.mouse_move_duration),
        "clickJitterPx": self.click_jitter_px,
        "castTimeout": self.cast_timeout,
        "distribution": self.timing_distribution,
      },
      "humanize": {
        "randomClickChance": self.random_click_chance,
        "randomMoveChance": self.random_move_chance,
        "moveJump": self.move_jump,
        "moveSidestep": self.move_sidestep,
        "moveMouseWander": self.move_mouse_wander,
        "shortBreakChance": self.short_break_chance,
        "shortBreakSecs": list(self.short_break_secs),
      },
      "session": {
        "logoutMode": self.logout_mode,
        "logoutAfterMins": self.logout_after_mins,
        "logoutRandomMins": list(self.logout_random_mins),
        "logoutAction": self.logout_action,
        "relogin": self.relogin,
        "reloginBreakMins": list(self.relogin_break_mins),
        "reloginLoadSecs": self.relogin_load_secs,
        "reloginFirstPerson": self.relogin_first_person,
        "maxSessions": self.max_sessions,
      },
    }

  def load(self, path=CONFIG_PATH):
    try:
      with open(path) as f:
        self.apply(json.load(f))
      logger.info(f"Loaded configuration from {path}")
    except IOError:
      logger.info("No configuration file found, using defaults.")

  def save(self, path=CONFIG_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
      json.dump(self.to_dict(), f, indent=2)
    logger.info(f"Saved configuration to {path}")

  def image_files(self):
    d = resolve_path(self.img_dir)
    if not os.path.isdir(d):
      return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(IMAGE_EXTS))

  def load_images(self):
    self.templates = []
    for f in self.image_files():
      img = cv.imread(f)
      if img is None:
        logger.warning(f"Could not read template {f}")
        continue
      self.templates.append(cv.Canny(cv.cvtColor(img, cv.COLOR_BGR2GRAY), self.canny_thresholds[0], self.canny_thresholds[1]))

    logger.info(f"Loaded {len(self.templates)} bobber images from {resolve_path(self.img_dir)}")

  def get_monitor(self):
    top = self.top_left[1]
    left = self.top_left[0]
    width = self.bot_right[0] - left
    height = self.bot_right[1] - top
    return {
      "top": int(top),
      "left": int(left),
      "width": int(width),
      "height": int(height)
    }

  def get_size(self):
    return (self.bot_right[0] - self.top_left[0], self.bot_right[1] - self.top_left[1])

  def get_left(self):
    return self.top_left[0]

  def get_right(self):
    return self.bot_right[0]

  def get_bot(self):
    return self.bot_right[1]

  def get_top(self):
    return self.top_left[1]
