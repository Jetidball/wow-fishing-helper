import threading, ctypes
import tkinter as tk
from loguru import logger
import safety

REFRESH_MS = 500
MARGIN = 12
BG = "#111111"
FG = "#e8e8e8"
DIM = "#9a9a9a"
ACCENT = "#ffd100"

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
WS_EX_NOACTIVATE = 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x11


def pct(v):
  return "-" if v is None else f"{100 * v:.0f}%"

def num(v, fmt="{:.1f}"):
  return "-" if v is None else fmt.format(v)

def hms(secs):
  secs = int(secs)
  return f"{secs // 3600}:{secs // 60 % 60:02d}:{secs % 60:02d}"


def make_passive(root):
  # click-through, no taskbar button, never takes focus from the game, and left out of screenshots
  # so it can't confuse the bobber, splash or loot detection even if it overlaps them
  try:
    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(root.winfo_id())
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
      logger.warning("Overlay: could not hide it from screenshots (needs Windows 10 2004 or newer), keep it away from the water and loot window")
  except Exception as e:
    logger.warning(f"Overlay: could not make it click-through ({e})")


class Overlay():
  def __init__(self, settings, stats):
    self.s = settings
    self.stats = stats

  def run(self):
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.82)
    root.configure(bg=BG)

    self.title = tk.Label(root, text="Fishing", bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold"), anchor="w")
    self.title.pack(fill="x", padx=10, pady=(8, 0))
    self.body = tk.Label(root, bg=BG, fg=FG, font=("Consolas", 10), justify="left", anchor="w")
    self.body.pack(fill="x", padx=10)
    self.loot = tk.Label(root, bg=BG, fg=DIM, font=("Consolas", 9), justify="left", anchor="w")
    self.loot.pack(fill="x", padx=10, pady=(4, 8))

    self.root = root
    root.update_idletasks()
    make_passive(root)
    self.refresh()
    root.mainloop()

  def place(self):
    r = self.root
    r.update_idletasks()
    w, h = r.winfo_reqwidth(), r.winfo_reqheight()
    sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
    corner = self.s.overlay_corner
    x = MARGIN if corner.endswith("left") else sw - w - MARGIN
    y = MARGIN if corner.startswith("top") else sh - h - MARGIN - 40
    r.geometry(f"+{x}+{y}")

  def refresh(self):
    st = self.stats.snapshot()
    n = st["recent_n"]
    lines = [
      f"Time      {hms(st['elapsed'])}",
      f"Casts     {st['casts']}   bites {st['bites']}   caught {st['catches']}",
      f"Catch     {pct(st['catch_rate'])} all   {pct(st['recent_catch_rate'])} last {n}",
      f"Per hour  {num(st['per_hour'], '{:.0f}')} all   {num(st['recent_per_hour'], '{:.0f}')} recent",
      f"Cast->catch avg  {num(st['avg_catch_secs'])}s (last {n})",
    ]
    self.body.configure(text="\n".join(lines))

    loot = []
    if st["last_loot"]:
      loot.append("Last: " + ", ".join(st["last_loot"]))
    for name, count in st["top_items"]:
      loot.append(f"{count:>4}  {name}")
    self.loot.configure(text="\n".join(loot) if loot else "No loot logged yet")

    if safety.paused.is_set():
      self.title.configure(text=f"Fishing - PAUSED ({safety.pause_reason})", fg="#ff6b6b")
    else:
      self.title.configure(text="Fishing", fg=ACCENT)
    self.place()
    self.root.after(REFRESH_MS, self.refresh)


def start_overlay(settings, stats):
  # tkinter objects must stay on the thread that made them, so the overlay gets its own thread and Tk
  overlay = Overlay(settings, stats)
  threading.Thread(target=overlay.run, daemon=True, name="overlay").start()
  return overlay
