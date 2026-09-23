import pyautogui as pag
import time
from humanize import move_to

def bait(settings):
  move_to(settings, settings.bait_location)
  pag.rightClick()
  move_to(settings, settings.pole_location)
  pag.click()
  time.sleep(8)
