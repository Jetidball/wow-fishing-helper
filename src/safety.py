import time, threading
import numpy as np
from loguru import logger
try:
  from mss import MSS as mss
except ImportError:
  from mss import mss
import humanize

# default whisper color in chat, BGR
WHISPER_BGR = np.array([255, 128, 255])
WHISPER_TOLERANCE = 40
NEW_WHISPER_PX = 15
CHECK_INTERVAL = 1.0

paused = threading.Event()
pause_reason = None
alert = False
whisper_baseline = None
health_baseline = None
no_bite_count = 0
last_check = 0

def box_monitor(box):
  (x1, y1), (x2, y2) = box
  return {"left": int(min(x1, x2)), "top": int(min(y1, y2)),
          "width": max(1, int(abs(x2 - x1))), "height": max(1, int(abs(y2 - y1)))}

def count_whisper_pixels(img):
  # img is BGR(A) from mss
  diff = np.abs(img[:, :, :3].astype(int) - WHISPER_BGR).max(axis=2)
  return int((diff <= WHISPER_TOLERANCE).sum())

def health_fraction(img):
  # share of the health bar box that is green
  b, g, r = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
  green = (g > 120) & (g > r + 50) & (g > b + 50)
  return float(green.mean())

def request_pause(reason, with_alert=True):
  global pause_reason, alert
  pause_reason = reason
  alert = with_alert
  paused.set()

def toggle_pause():
  # F9
  if paused.is_set():
    paused.clear()
  else:
    request_pause("F9 pressed", with_alert=False)

def reset():
  global whisper_baseline, health_baseline, no_bite_count
  whisper_baseline = None
  health_baseline = None
  no_bite_count = 0
  humanize.set_bot_pos(None)

def beep():
  try:
    import winsound
    for _ in range(3):
      winsound.Beep(880, 200)
      time.sleep(0.1)
  except Exception:
    print("\a", end="", flush=True)

def wait_if_paused(settings):
  # called by the main loop between states
  if not paused.is_set():
    return
  logger.warning(f"PAUSED ({pause_reason}) Press F9 to resume, Esc to quit.")
  last_beep = 0
  while paused.is_set():
    if alert and settings.alert_sound and time.time() - last_beep > 15:
      beep()
      last_beep = time.time()
    time.sleep(0.2)
  logger.info("Resumed")
  reset()

def check_screen(settings, force=False):
  # returns a reason to pause, or None. Throttled so it can run inside the bobber loop.
  global whisper_baseline, health_baseline, last_check
  if settings.pause_on_mouse_takeover and humanize.user_moved_mouse():
    return "You moved the mouse"
  if not force and time.time() - last_check < CHECK_INTERVAL:
    return None
  last_check = time.time()
  with mss() as sct:
    if settings.pause_on_whisper and settings.chat_area:
      n = count_whisper_pixels(np.array(sct.grab(box_monitor(settings.chat_area))))
      if whisper_baseline is not None and n > whisper_baseline + NEW_WHISPER_PX:
        whisper_baseline = n
        return "New whisper in chat"
      # also follows old whispers scrolling out of the chat box
      whisper_baseline = n
    if settings.pause_on_health_drop and settings.health_area:
      f = health_fraction(np.array(sct.grab(box_monitor(settings.health_area))))
      if health_baseline is None or f > health_baseline:
        health_baseline = f
      elif health_baseline - f >= settings.health_drop_pct / 100 * max(health_baseline, 1e-6):
        return f"Health dropped by {100 * (health_baseline - f) / health_baseline:.0f}%"
  return None

def check_and_pause(settings, force=False):
  reason = check_screen(settings, force)
  if reason:
    request_pause(reason)
  return reason is not None

def record_cast(settings, got_bite):
  global no_bite_count
  no_bite_count = 0 if got_bite else no_bite_count + 1
  limit = settings.pause_after_no_bites
  if limit > 0 and no_bite_count >= limit:
    request_pause(f"No bite for {no_bite_count} casts in a row, did something move you?")
