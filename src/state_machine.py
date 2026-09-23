import time, sys, os
import pyautogui as pag
from bob_finder import search_and_destroy, CAUGHT, NO_BITE, ABORTED
from setup import initialize, get_single_loc
from clicker import bait
from settings import Settings
from session import Session
from humanize import move_to, sleep_range, maybe_idle_actions, set_bot_pos
import safety
from loguru import logger

config = Settings()
session = Session(config)
ui_is_hidden = True
time_attached = 0
round_count = 0
successes = 0

def init():
  logger.info("Initializing")
  initialize(config)
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
  if config.attach_bait and time.time() - time_attached > config.bait_interval_mins * 60 and config.num_bait > 0:
    logger.info('Attaching bait...')
    show_ui()
    bait(config)
    config.num_bait = config.num_bait - 1
    time_attached = time.time()
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
  sleep_range(config, config.cast_delay)
  move_to(config, config.cast_location)
  pag.click()
  logger.info("Clicked fishing ability")
  move_state(find_hover_wait)

def find_hover_wait():
  global round_count, successes
  sleep_range(config, config.splash_search_delay)
  result = search_and_destroy(config)
  if result == ABORTED:
    move_state(attach_bait)
    return
  round_count = round_count + 1
  successes = successes + (0 if result == NO_BITE else 1)
  logger.info("Accuracy is %f%% (n=%d)" % (round(100 * successes/round_count), round_count) )
  safety.record_cast(config, result != NO_BITE)
  move_state(loot_fish if result == CAUGHT else attach_bait)

def loot_fish():
  logger.info("Looting")
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
  config.load()
  if "--no-gui" not in sys.argv:
    from gui import run_gui
    if not run_gui(config):
      logger.info("Closed without starting.")
      sys.exit(0)

  while True:
    safety.wait_if_paused(config)
    state_func()
