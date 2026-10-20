import time, sys, os
from visual_targeting.input import desktop as pag, Cancelled, DryRunInput
from bob_finder import NO_BITE, ABORTED
from fishing.task import FishingTask
from visual_targeting.detector import TemplateDetector
from visual_targeting.contracts import Frame, Box
from setup import initialize, get_single_loc
from clicker import bait
from settings import Settings
from session import Session
from humanize import move_to, sleep_range, maybe_idle_actions, set_bot_pos
import safety
from stats import Stats
from loot import LootTracker
from overlay import start_overlay
from loguru import logger

config = Settings()
session = Session(config)
stats = None
loot = None
ui_is_hidden = True
time_attached = 0
cast_time = 0
precast = None
live_input_enabled = False
loot_visible_precast = False

def init():
  logger.info("Initializing")
  initialize(config)
  loot.start()
  session.start()
  move_state(attach_bait)

state_func = init

def hide_ui():
  global ui_is_hidden
  if not ui_is_hidden:
    logger.info("Hidding UI")
    ui_is_hidden = True
    pag.typewrite('b')
    pag.typewrite('c')

def show_ui():
  global ui_is_hidden
  if ui_is_hidden:
    logger.info("Showing UI")
    ui_is_hidden = False
    pag.typewrite('b')
    pag.typewrite('c')

def move_state(state):
  global state_func
  state_func = state

def attach_bait():
  global time_attached
  if config.attach_bait and time.monotonic() - time_attached > config.bait_interval_mins * 60 and config.num_bait > 0:
    logger.info('Attaching bait...')
    show_ui()
    bait(config)
    config.num_bait = config.num_bait - 1
    time_attached = time.monotonic()
    hide_ui()
  move_state(pre_cast)

def pre_cast():
  global time_attached
  if session.expired():
    session.end()
    # bait wore off while logged out, and the mouse was free during the break
    time_attached = 0
    safety.reset()
    move_state(attach_bait)
    return
  if safety.check_and_pause(config, force=True):
    return
  maybe_idle_actions(config)
  move_state(cast)

def cast():
  global cast_time, precast, loot_visible_precast
  sleep_range(config, config.cast_delay)
  # Observe existing bobbers before casting, so another player's float is excluded.
  from mss import mss
  import numpy as np
  detector = TemplateDetector(config.templates, config.match_threshold, config.canny_thresholds)
  try:
    loot_visible_precast = bool(loot.enabled() and loot.occupied_slots(loot.grab()))
    with mss() as capture:
      frame = Frame(0, time.monotonic(), np.array(capture.grab(config.get_monitor())), Box(**config.get_monitor()), "bgra")
      precast = detector.candidates(frame)
  except Exception as exc:
    logger.warning("Cannot establish pre-cast ownership: {}", exc)
    precast = None
    move_state(attach_bait)
    return
  move_to(config, config.cast_location)
  pag.click()
  cast_time = time.monotonic()
  logger.info("Clicked fishing ability")
  move_state(find_hover_wait)

def find_hover_wait():
  sleep_range(config, config.splash_search_delay)
  def catch_check():
    # Independent visual loot evidence, never infer a catch from clicking/disappearance.
    return bool(not loot_visible_precast and loot.enabled() and loot.occupied_slots(loot.grab()))
  task = FishingTask(config, precast=precast, live_input=live_input_enabled,
                     bite_backend=getattr(config, "bite_backend", "temporal"), catch_check=catch_check, cancelled=pag.cancelled, cast_started=cast_time)
  result = task.run()
  logger.info("Fishing outcome: {}", result)
  if result == ABORTED:
    move_state(attach_bait)
    return
  stats.record_cast(result, time.monotonic() - cast_time)
  st = stats.snapshot()
  logger.info(f"Catch rate {100 * st['catch_rate']:.0f}% (n={st['casts']}), "
              f"last {st['recent_n']}: {100 * st['recent_catch_rate']:.0f}%")
  safety.record_cast(config, result in ("catch_confirmed", "click_unconfirmed"))
  move_state(loot_fish if result == "catch_confirmed" else attach_bait)

def click_loot(points):
  # bottom slot first, so it doesn't matter if the slots below shift up after one is taken
  for p in reversed(points):
    sleep_range(config, config.loot_delay)
    move_to(config, p)
    pag.rightClick()

def loot_fish():
  logger.info("Looting")
  if loot.on_catch(session.count, None if config.auto_loot else click_loot):
    move_state(attach_bait)
    return
  if not config.auto_loot:
    sleep_range(config, config.loot_delay)
    if config.loot_location:
      move_to(config, config.loot_location)
    else:
      config.loot_location = get_single_loc('loot')
      set_bot_pos(config.loot_location)
      logger.info(f"Location is {config.loot_location}, set it in the GUI to skip this next time")
    pag.rightClick()
  move_state(attach_bait)

if __name__ == "__main__":
  live_input_enabled = "--live-input" in sys.argv and "--dry-run" not in sys.argv
  if live_input_enabled:
    from visual_targeting.input import WindowsInput
    pag.configure(WindowsInput())
  else:
    pag.configure(DryRunInput())
  config.load()
  if "--no-gui" not in sys.argv:
    from gui import run_gui
    if not run_gui(config):
      logger.info("Closed without starting.")
      sys.exit(0)

  stats = Stats(config.running_avg_casts)
  loot = LootTracker(config, stats)
  if config.show_overlay:
    start_overlay(config, stats)

  try:
    while not pag.cancelled.is_set():
      safety.wait_if_paused(config)
      state_func()
  except (Cancelled, KeyboardInterrupt):
    logger.info("Fishing cancelled")
  finally:
    pag.release_all()
