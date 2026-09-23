import time, random, math
import pyautogui as pag
from loguru import logger

MAX_FATIGUE = 2.0
TAKEOVER_PX = 25

fatigue_start = time.time()
last_bot_pos = None

def rand_between(rng, distribution="uniform"):
  lo, hi = rng
  if hi <= lo:
    return lo
  if distribution == "gaussian":
    # centered in the range, ~99.7% of values fall inside it; clamp the rest
    return min(hi, max(lo, random.gauss((lo + hi) / 2, (hi - lo) / 6)))
  if distribution == "skewed":
    # like human reaction times: usually about a third of the way into the range, with a long slow tail
    return lo + (hi - lo) * min(1.0, random.lognormvariate(0, 0.5) / 3)
  return random.uniform(lo, hi)

def start_fatigue():
  global fatigue_start
  fatigue_start = time.time()

def fatigue_factor(settings):
  hours = (time.time() - fatigue_start) / 3600
  return min(MAX_FATIGUE, 1 + settings.fatigue_pct_per_hour / 100 * hours)

def sleep_range(settings, rng):
  secs = rand_between(rng, settings.timing_distribution) * fatigue_factor(settings)
  time.sleep(secs)
  return secs

def _move(x, y, duration):
  global last_bot_pos
  pag.moveTo(x, y, duration=duration, tween=pag.easeInOutQuad)
  last_bot_pos = pag.position()

def set_bot_pos(pos):
  global last_bot_pos
  last_bot_pos = pos

def user_moved_mouse():
  if last_bot_pos is None:
    return False
  x, y = pag.position()
  return math.hypot(x - last_bot_pos[0], y - last_bot_pos[1]) > TAKEOVER_PX

def jitter(settings, point):
  j = int(settings.click_jitter_px)
  if j <= 0:
    return point
  return (point[0] + random.randint(-j, j), point[1] + random.randint(-j, j))

def move_to(settings, point, use_jitter=True):
  if use_jitter:
    point = jitter(settings, point)
  duration = rand_between(settings.mouse_move_duration, settings.timing_distribution) * fatigue_factor(settings)
  _move(point[0], point[1], duration)

def random_point_in_area(settings):
  return (random.randint(settings.get_left(), settings.get_right()),
          random.randint(settings.get_top(), settings.get_bot()))

def random_click(settings):
  logger.info("Humanize: random click")
  move_to(settings, random_point_in_area(settings), use_jitter=False)
  time.sleep(random.uniform(0.1, 0.4))
  pag.click()

def jump():
  logger.info("Humanize: jump")
  pag.press('space')
  time.sleep(random.uniform(0.9, 1.4))

def sidestep():
  # step one way then the same amount back so the camera ends up (roughly) where it was
  keys = ['q', 'e'] if random.random() < 0.5 else ['e', 'q']
  hold = random.uniform(0.08, 0.2)
  logger.info(f"Humanize: sidestep {keys[0]}/{keys[1]} for {hold:.2f}s")
  for key in keys:
    pag.keyDown(key)
    time.sleep(hold)
    pag.keyUp(key)
    time.sleep(random.uniform(0.2, 0.5))

def mouse_wander(settings):
  logger.info("Humanize: mouse wander")
  w, h = pag.size()
  for _ in range(random.randint(1, 3)):
    x = random.randint(int(w * 0.15), int(w * 0.85))
    y = random.randint(int(h * 0.15), int(h * 0.85))
    _move(x, y, random.uniform(0.3, 1.0))
    time.sleep(random.uniform(0.1, 0.6))

def random_movement(settings):
  actions = []
  if settings.move_jump:
    actions.append(jump)
  if settings.move_sidestep:
    actions.append(sidestep)
  if settings.move_mouse_wander:
    actions.append(lambda: mouse_wander(settings))
  if actions:
    random.choice(actions)()

def maybe_idle_actions(settings):
  # rolled once per cast, before casting
  if random.random() < settings.short_break_chance:
    secs = rand_between(settings.short_break_secs, settings.timing_distribution)
    logger.info(f"Humanize: taking a short break for {secs:.0f}s")
    time.sleep(secs)
  if random.random() < settings.random_move_chance:
    random_movement(settings)
  if random.random() < settings.random_click_chance:
    random_click(settings)

def type_text(text):
  pag.typewrite(text, interval=random.uniform(0.04, 0.12))

def session_length_secs(settings):
  if settings.logout_mode == "fixed":
    return settings.logout_after_mins * 60
  if settings.logout_mode == "random":
    return random.uniform(*settings.logout_random_mins) * 60
  return None
