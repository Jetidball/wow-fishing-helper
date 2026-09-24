import os, re, csv, time, difflib
import cv2 as cv
import numpy as np
try:
  from mss import MSS as mss
except ImportError:
  from mss import mss
from loguru import logger
from settings import resolve_path, IMAGE_EXTS

ICON_SIZE = 32
ICON_INNER = 4              # px trimmed off each side of a resized icon, skips the border and stack count
ICON_MATCH = 0.88           # similarity needed to call two icons the same
SAME_ICON_AFTER = 0.80      # looser, used to see if an item is still in the window after looting
SLOT_PITCH_RATIO = 1.11     # default loot frame: slot spacing / icon height
NAME_WIDTH_RATIO = 4.0      # name text area width / icon width
ICON_MIN_STD = 18           # flat backgrounds are below this, icons are well above
TEXT_MIN_FRACTION = 0.01
UNKNOWN_DIR = "unknown"
TESSERACT_PATHS = [r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]

# item name colors, BGR
QUALITIES = [
  ("poor", (157, 157, 157)),
  ("common", (255, 255, 255)),
  ("uncommon", (0, 255, 30)),
  ("rare", (221, 112, 0)),
  ("epic", (238, 53, 163)),
  ("legendary", (0, 128, 255)),
]
LOG_FIELDS = ["time", "session", "catch", "slot", "item", "quality", "identified_by", "icon_score", "pulled", "screenshot"]


def normalize_icon(img):
  img = cv.resize(img, (ICON_SIZE, ICON_SIZE), interpolation=cv.INTER_AREA)
  return img[ICON_INNER:-ICON_INNER, ICON_INNER:-ICON_INNER]

def icon_similarity(a, b):
  # both already normalized, BGR
  return float(cv.matchTemplate(a, b, cv.TM_CCOEFF_NORMED)[0][0])

def safe_filename(name):
  return re.sub(r'[<>:"/\\|?*]', "", name).strip() or "item"

def clean_ocr(text):
  lines = []
  for line in text.splitlines():
    line = re.sub(r"[^A-Za-z0-9' ,:.\-]", "", line)
    line = re.sub(r"\s+", " ", line).strip(" .,-")
    if len(re.sub(r"[^A-Za-z]", "", line)) >= 2:
      lines.append(line)
  # long names wrap onto a second line
  return " ".join(lines)

def text_mask(img):
  return img.max(axis=2) > 130

def quality_of(name_img):
  mask = text_mask(name_img)
  if mask.sum() < 5:
    return None
  color = np.median(name_img[mask].astype(int), axis=0)
  return min(QUALITIES, key=lambda q: np.sum((color - np.array(q[1])) ** 2))[0]


class LootTracker():
  def __init__(self, settings, stats):
    self.s = settings
    self.stats = stats
    self.library = []        # (name, normalized icon)
    self.unknowns = []
    self.ocr = None
    self.catch_count = 0

  # ---------- setup ----------

  def enabled(self):
    return self.s.loot_tracking and self.s.loot_icon_area is not None

  def base_dir(self):
    return resolve_path(self.s.loot_dir)

  def icon_dir(self):
    return os.path.join(self.base_dir(), "icons")

  def start(self):
    if not self.enabled():
      if self.s.loot_tracking:
        logger.info("Loot tracking is on but the first loot icon box isn't picked, skipping it")
      return
    os.makedirs(os.path.join(self.icon_dir(), UNKNOWN_DIR), exist_ok=True)
    self.load_library()
    self.ocr = self.find_ocr()
    logger.info(f"Loot tracking: {len(self.library)} known icons, item names "
                + ("read with OCR" if self.ocr else "from icons only (install Tesseract to read names)"))

  def load_icons(self, d):
    icons = []
    for f in sorted(os.listdir(d)):
      if not f.lower().endswith(IMAGE_EXTS):
        continue
      img = cv.imread(os.path.join(d, f))
      if img is None:
        continue
      # "Name.png", "Name (2).png" etc. are all the same item
      name = re.sub(r"\s*\(\d+\)$", "", os.path.splitext(f)[0])
      icons.append((name, normalize_icon(img)))
    return icons

  def load_library(self):
    self.library = self.load_icons(self.icon_dir())
    # icons nobody has named yet, so the same unknown item isn't saved again every catch
    self.unknowns = self.load_icons(os.path.join(self.icon_dir(), UNKNOWN_DIR))

  def find_ocr(self):
    try:
      import pytesseract
    except ImportError:
      return None
    cmd = self.s.tesseract_cmd or next((p for p in TESSERACT_PATHS if os.path.isfile(p)), None)
    if cmd:
      pytesseract.pytesseract.tesseract_cmd = cmd
    try:
      pytesseract.get_tesseract_version()
    except Exception:
      logger.warning("pytesseract is installed but Tesseract itself wasn't found, set its path in the Loot tab")
      return None
    return pytesseract

  # ---------- geometry ----------

  def icon_box(self):
    (x1, y1), (x2, y2) = self.s.loot_icon_area
    return min(x1, x2), min(y1, y2), max(1, abs(x2 - x1)), max(1, abs(y2 - y1))

  def pitch(self):
    _, _, _, h = self.icon_box()
    return self.s.loot_slot_pitch_px or round(h * SLOT_PITCH_RATIO)

  def window_monitor(self):
    # screen area covering every slot's icon and name, with a little padding
    x, y, w, h = self.icon_box()
    pad = 8
    return {"left": int(x - pad), "top": int(y - pad),
            "width": int(w * (1 + NAME_WIDTH_RATIO) + 2 * pad + 4),
            "height": int(self.pitch() * (self.s.loot_max_slots - 1) + h + 2 * pad)}

  def slot_crops(self, img, i):
    # returns (icon, name) crops of slot i from a window_monitor() image
    x, y, w, h = self.icon_box()
    mon = self.window_monitor()
    top = y + i * self.pitch() - mon["top"]
    left = x - mon["left"]
    icon = img[top:top + h, left:left + w]
    name_left = left + w + 4
    name = img[top:top + h, name_left:name_left + int(w * NAME_WIDTH_RATIO)]
    return icon, name

  def slot_point(self, i):
    x, y, w, h = self.icon_box()
    return (x + w // 2, y + h // 2 + i * self.pitch())

  # ---------- capture ----------

  def grab(self):
    with mss() as sct:
      return cv.cvtColor(np.array(sct.grab(self.window_monitor())), cv.COLOR_BGRA2BGR)

  def occupied(self, img, i):
    icon, name = self.slot_crops(img, i)
    if icon.size == 0 or name.size == 0:
      return False
    return cv.cvtColor(icon, cv.COLOR_BGR2GRAY).std() > ICON_MIN_STD and text_mask(name).mean() > TEXT_MIN_FRACTION

  def occupied_slots(self, img):
    return [i for i in range(self.s.loot_max_slots) if self.occupied(img, i)]

  def wait_for_window(self, timeout):
    end = time.time() + timeout
    while True:
      img = self.grab()
      slots = self.occupied_slots(img)
      if slots:
        # let the frame finish drawing (fade in) before reading it
        time.sleep(0.15)
        img = self.grab()
        return img, self.occupied_slots(img) or slots
      if time.time() > end:
        return None, []
      time.sleep(0.05)

  # ---------- identify ----------

  def match_icon(self, icon, library=None):
    best_name, best_score = None, -1
    for name, lib_icon in self.library if library is None else library:
      score = icon_similarity(icon, lib_icon)
      if score > best_score:
        best_name, best_score = name, score
    return best_name, best_score

  def read_name(self, name_img):
    if not self.ocr:
      return ""
    # item names are colored, so take the brightest channel, then dark text on white for Tesseract
    gray = name_img.max(axis=2)
    gray = cv.resize(gray, None, fx=3, fy=3, interpolation=cv.INTER_CUBIC)
    _, bw = cv.threshold(gray, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
    bw = cv.copyMakeBorder(255 - bw, 10, 10, 10, 10, cv.BORDER_CONSTANT, value=255)
    try:
      text = clean_ocr(self.ocr.image_to_string(bw, config="--psm 6"))
    except Exception as e:
      logger.warning(f"OCR failed: {e}")
      return ""
    # snap small OCR mistakes to a name we already know
    known = sorted({n for n, _ in self.library})
    close = difflib.get_close_matches(text, known, n=1, cutoff=0.85) if text else []
    return close[0] if close else text

  def learn_icon(self, name, icon_img, folder=None):
    d = os.path.join(self.icon_dir(), folder) if folder else self.icon_dir()
    base = safe_filename(name)
    path = os.path.join(d, base + ".png")
    n = 2
    while os.path.exists(path):
      path = os.path.join(d, f"{base} ({n}).png")
      n += 1
    cv.imwrite(path, icon_img)
    (self.unknowns if folder else self.library).append((name, normalize_icon(icon_img)))
    return path

  def identify(self, img, i):
    icon_img, name_img = self.slot_crops(img, i)
    icon = normalize_icon(icon_img)
    icon_name, score = self.match_icon(icon)
    icon_hit = icon_name is not None and score >= ICON_MATCH
    ocr_name = self.read_name(name_img)

    if ocr_name:
      name, by = ocr_name, "ocr"
      if icon_hit and icon_name == ocr_name:
        by = "ocr+icon"
      elif not any(n == ocr_name and icon_similarity(icon, li) >= ICON_MATCH for n, li in self.library):
        path = self.learn_icon(ocr_name, icon_img)
        logger.info(f"Loot: learned icon for '{ocr_name}' ({os.path.basename(path)})")
    elif icon_hit:
      name, by = icon_name, "icon"
    else:
      seen, seen_score = self.match_icon(icon, self.unknowns)
      if seen is not None and seen_score >= ICON_MATCH:
        label = seen
      else:
        label = time.strftime("item_%Y%m%d_%H%M%S") + f"_{i}"
        path = self.learn_icon(label, icon_img, UNKNOWN_DIR)
        logger.info(f"Loot: unknown icon saved to {path}, rename it to the item's name and move it up to "
                    f"{self.icon_dir()} so it's recognized next time")
      name, by = f"Unknown ({label})", "unknown"
    return {"slot": i + 1, "item": name, "quality": quality_of(name_img) or "",
            "identified_by": by, "icon_score": round(score, 3) if icon_name else "", "icon": icon}

  def still_there(self, item, after):
    if after is None:
      return False
    for i in self.occupied_slots(after):
      icon_img, _ = self.slot_crops(after, i)
      if icon_similarity(item["icon"], normalize_icon(icon_img)) >= SAME_ICON_AFTER:
        return True
    return False

  # ---------- log ----------

  def save_screenshot(self, img):
    d = os.path.join(self.base_dir(), "screens", time.strftime("%Y-%m-%d"))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, time.strftime("%H%M%S") + f"_{self.catch_count:04d}.png")
    cv.imwrite(path, img)
    return path

  def write_log(self, session, items, screenshot):
    path = os.path.join(self.base_dir(), "loot_log.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
      w = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
      if new:
        w.writeheader()
      now = time.strftime("%Y-%m-%d %H:%M:%S")
      shot = os.path.relpath(screenshot, self.base_dir())
      for it in items:
        w.writerow({**it, "time": now, "session": session, "catch": self.catch_count,
                    "pulled": "yes" if it["pulled"] else "no", "screenshot": shot})

  # ---------- main entry ----------

  def on_catch(self, session, loot_fn=None, timeout=2.5):
    # Call right after clicking the bobber. loot_fn(points) clicks the given slots; leave it None with auto loot.
    # Returns False if the loot window never showed up, so the caller can fall back to the old looting.
    if not self.enabled():
      return False
    img, slots = self.wait_for_window(timeout if loot_fn else 1.5)
    if img is None:
      logger.warning("Loot: no loot window seen" + ("" if loot_fn else " (auto loot can close it before it's captured)"))
      return False
    self.catch_count += 1
    shot = self.save_screenshot(img)
    items = [self.identify(img, i) for i in slots]

    if loot_fn:
      targets = slots if self.s.loot_all_slots else slots[:1]
      loot_fn([self.slot_point(i) for i in targets])
      time.sleep(0.4)
      after = self.grab()
      if not self.occupied_slots(after):
        after = None    # window closed, everything was taken
      for it in items:
        it["pulled"] = not self.still_there(it, after)
    else:
      for it in items:
        it["pulled"] = True

    self.write_log(session, items, shot)
    pulled = [it["item"] for it in items if it["pulled"]]
    left = [it["item"] for it in items if not it["pulled"]]
    self.stats.record_loot(pulled)
    logger.info("Loot: " + ", ".join(f"{it['item']} ({it['quality'] or '?'}, {it['identified_by']})" for it in items)
                + (f" | left behind: {', '.join(left)}" if left else ""))
    return True
