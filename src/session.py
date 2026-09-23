import time, os
import pyautogui as pag
from loguru import logger
from humanize import rand_between, move_to, type_text, session_length_secs
from setup import focus_wow_window

class Session():
  def __init__(self, settings):
    self.settings = settings
    self.count = 0
    self.start_time = None
    self.length = None

  def start(self):
    self.count = self.count + 1
    self.start_time = time.time()
    self.length = session_length_secs(self.settings)
    if self.length is None:
      logger.info(f"Session {self.count} started (no logout timer)")
    else:
      logger.info(f"Session {self.count} started, logging out in {self.length / 60:.1f} min")

  def expired(self):
    return self.length is not None and time.time() - self.start_time >= self.length

  def elapsed(self):
    return time.time() - self.start_time

  def can_relogin(self):
    s = self.settings
    if not s.relogin or s.logout_action == "quit":
      return False
    return s.max_sessions <= 0 or self.count < s.max_sessions

  def chat_command(self, cmd):
    pag.press('enter')
    time.sleep(0.3)
    type_text(cmd)
    time.sleep(0.2)
    pag.press('enter')

  def logout(self):
    s = self.settings
    logger.info(f"Session over after {self.elapsed() / 60:.1f} min, action: {s.logout_action}")
    if s.logout_action == "quit":
      pag.hotkey('alt', 'f4')
      return
    if s.logout_action == "hearth_logout" and s.hearthstone_location:
      move_to(s, s.hearthstone_location)
      pag.click()
      # 10s cast plus loading screen
      time.sleep(25)
    self.chat_command('/logout')
    # logging out outside of an inn/city takes 20s
    time.sleep(25)

  def take_break(self):
    secs = rand_between(self.settings.relogin_break_mins, self.settings.timing_distribution) * 60
    logger.info(f"Taking a break for {secs / 60:.1f} min before logging back in")
    end = time.time() + secs
    while time.time() < end:
      remaining = end - time.time()
      logger.info(f"{remaining / 60:.1f} min until log in")
      time.sleep(min(60, remaining))

  def login(self):
    # the client sits at character select after /logout, so Enter logs the last character back in
    s = self.settings
    logger.info("Logging back in")
    focus_wow_window()
    time.sleep(1)
    pag.press('enter')
    time.sleep(s.relogin_load_secs)
    if s.relogin_first_person:
      # zoom all the way in with the cursor over the water
      move_to(s, ((s.get_left() + s.get_right()) // 2, (s.get_top() + s.get_bot()) // 2), use_jitter=False)
      for _ in range(15):
        pag.scroll(5)
        time.sleep(0.05)
      time.sleep(1)

  def end(self):
    self.logout()
    if not self.can_relogin():
      logger.info("Done fishing. Exiting bot.")
      os._exit(0)
    self.take_break()
    self.login()
    self.start()
