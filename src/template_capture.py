import os, time
import cv2 as cv
import numpy as np
import pyautogui as pag
try:
  from mss import MSS as mss
except ImportError:
  from mss import mss

def capture_at_cursor(directory, size=50):
  # grabs a size x size square centered on the cursor and saves it as a template
  os.makedirs(directory, exist_ok=True)
  x, y = pag.position()
  area = {
    "top": int(y - size / 2),
    "left": int(x - size / 2),
    "width": int(size),
    "height": int(size)
  }
  with mss() as sct:
    img = cv.cvtColor(np.array(sct.grab(area)), cv.COLOR_BGRA2BGR)
  path = os.path.join(directory, f"bobber_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000:03d}.png")
  cv.imwrite(path, img)
  return path
