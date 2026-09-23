import os, shutil, threading, queue, base64, time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2 as cv
from pynput.keyboard import Key, Listener
from settings import resolve_path, IMAGE_EXTS
from setup import get_single_loc, get_pole_loc, get_area_of_interest, get_box, focus_wow_window
from template_capture import capture_at_cursor

THUMB_SIZE = 72
THUMB_COLUMNS = 6
SELECTED_BG = "#3b82f6"

DISTRIBUTIONS = [("skewed", "Skewed (mostly quick, sometimes slow)"), ("gaussian", "Gaussian (clusters around the middle)"),
                 ("uniform", "Uniform (anywhere in the range)")]
BOX_ATTRS = ("chat_area", "health_area")
LOGOUT_ACTIONS = [("logout", "/logout"), ("hearth_logout", "Hearthstone, then /logout"), ("quit", "Quit game (Alt+F4)")]


def fmt(v):
  return f"{v:g}" if isinstance(v, float) else str(v)

def thumbnail(path, size=THUMB_SIZE):
  img = cv.imread(path)
  if img is None:
    return None
  h, w = img.shape[:2]
  scale = size / max(h, w)
  interp = cv.INTER_NEAREST if scale > 1 else cv.INTER_AREA
  img = cv.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=interp)
  _, buf = cv.imencode('.png', img)
  return tk.PhotoImage(data=base64.b64encode(buf.tobytes()))


class ScrollFrame(ttk.Frame):
  def __init__(self, parent, height=280):
    super().__init__(parent)
    self.canvas = tk.Canvas(self, highlightthickness=0, height=height)
    bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
    self.inner = ttk.Frame(self.canvas)
    self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
    self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
    self.canvas.configure(yscrollcommand=bar.set)
    self.canvas.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_wheel))
    self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

  def _on_wheel(self, event):
    self.canvas.yview_scroll(int(-event.delta / 120), "units")


class App():
  def __init__(self, settings):
    self.s = settings
    self.started = False
    self.busy = False
    self.events = queue.Queue()
    self.fields = []
    self.capture_listener = None
    self.selected_images = set()
    self.thumbs = []
    self.loc_labels = {}

    self.root = tk.Tk()
    self.root.title("WoW Fishing Bot")
    self.root.minsize(640, 560)
    self.root.protocol("WM_DELETE_WINDOW", self.cancel)

    nb = ttk.Notebook(self.root)
    nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
    nb.add(self.timing_tab(nb), text="Timing")
    nb.add(self.humanize_tab(nb), text="Humanize")
    nb.add(self.safety_tab(nb), text="Safety")
    nb.add(self.session_tab(nb), text="Log out / Log in")
    nb.add(self.images_tab(nb), text="Bobber Images")
    nb.add(self.setup_tab(nb), text="Locations & Fishing")

    bottom = ttk.Frame(self.root)
    bottom.pack(fill="x", padx=8, pady=8)
    self.status = tk.StringVar(value="Configure the bot, then press Start fishing. While it runs, F9 pauses/resumes and Esc quits.")
    ttk.Label(bottom, textvariable=self.status, wraplength=380).pack(side="left", fill="x", expand=True)
    ttk.Button(bottom, text="Cancel", command=self.cancel).pack(side="right")
    ttk.Button(bottom, text="Start fishing", command=self.start).pack(side="right", padx=4)
    ttk.Button(bottom, text="Save", command=self.save).pack(side="right")

    self.update_states()
    self.root.after(100, self.poll)

  # ---------- field helpers ----------

  def page(self, parent):
    f = ttk.Frame(parent, padding=12)
    f.columnconfigure(3, weight=1)
    return f

  def note(self, parent, row, text):
    ttk.Label(parent, text=text, foreground="gray", wraplength=580, justify="left").grid(row=row, column=0, columnspan=4, sticky="w", pady=(2, 8))

  def section(self, parent, row, text):
    ttk.Label(parent, text=text, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, columnspan=4, sticky="w", pady=(10, 2))

  def num(self, parent, row, label, attr, unit="", cast=float, lo=0, hi=None, scale=1):
    # scale lets a 0..1 chance be shown as a percentage
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
    var = tk.StringVar(value=fmt(cast(getattr(self.s, attr) * scale)))
    entry = ttk.Entry(parent, textvariable=var, width=8)
    entry.grid(row=row, column=1, sticky="w", padx=(8, 0))
    ttk.Label(parent, text=unit, foreground="gray").grid(row=row, column=3, sticky="w", padx=8)

    def read():
      v = self.parse(var.get(), cast, label)
      self.check_bounds(v, lo, hi, label)
      return v if scale == 1 else v / scale
    self.fields.append((attr, read))
    return [entry]

  def rng(self, parent, row, label, attr, unit="", lo=0, hi=None):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
    a, b = getattr(self.s, attr)
    va, vb = tk.StringVar(value=fmt(float(a))), tk.StringVar(value=fmt(float(b)))
    ea = ttk.Entry(parent, textvariable=va, width=8)
    ea.grid(row=row, column=1, sticky="w", padx=(8, 0))
    eb = ttk.Entry(parent, textvariable=vb, width=8)
    eb.grid(row=row, column=2, sticky="w", padx=(4, 0))
    ttk.Label(parent, text=unit, foreground="gray").grid(row=row, column=3, sticky="w", padx=8)

    def read():
      x, y = self.parse(va.get(), float, label), self.parse(vb.get(), float, label)
      self.check_bounds(x, lo, hi, label)
      self.check_bounds(y, lo, hi, label)
      if x > y:
        raise ValueError(f"{label}: min is bigger than max")
      return (x, y)
    self.fields.append((attr, read))
    return [ea, eb]

  def check(self, parent, row, label, attr, command=None):
    var = tk.BooleanVar(value=bool(getattr(self.s, attr)))
    cb = ttk.Checkbutton(parent, text=label, variable=var, command=command)
    cb.grid(row=row, column=0, columnspan=4, sticky="w", pady=3)
    self.fields.append((attr, var.get))
    return var

  def choice(self, parent, row, label, attr, options, command=None):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
    labels = [l for _, l in options]
    current = dict(options).get(getattr(self.s, attr), labels[0])
    var = tk.StringVar(value=current)
    box = ttk.Combobox(parent, textvariable=var, values=labels, state="readonly", width=34)
    box.grid(row=row, column=1, columnspan=3, sticky="w", padx=(8, 0))
    if command:
      box.bind("<<ComboboxSelected>>", lambda e: command())
    lookup = {l: v for v, l in options}
    self.fields.append((attr, lambda: lookup[var.get()]))
    return lambda: lookup[var.get()]

  def parse(self, text, cast, label):
    try:
      return cast(float(text)) if cast is int else cast(text)
    except ValueError:
      raise ValueError(f"{label}: '{text}' is not a number")

  def check_bounds(self, v, lo, hi, label):
    if lo is not None and v < lo:
      raise ValueError(f"{label}: must be at least {lo}")
    if hi is not None and v > hi:
      raise ValueError(f"{label}: must be at most {hi}")

  def set_state(self, widgets, enabled):
    for w in widgets:
      w.configure(state="normal" if enabled else "disabled")

  # ---------- tabs ----------

  def timing_tab(self, nb):
    p = self.page(nb)
    ttk.Label(p, text="min").grid(row=0, column=1, sticky="w", padx=(8, 0))
    ttk.Label(p, text="max").grid(row=0, column=2, sticky="w", padx=(4, 0))
    self.rng(p, 1, "Time before casting again", "cast_delay", "seconds")
    self.rng(p, 2, "Wait after cast before searching", "splash_search_delay", "seconds, lets the bobber land")
    self.rng(p, 3, "Delay on bobber click", "bobber_click_delay", "seconds, reaction time after a splash")
    self.rng(p, 4, "Delay before looting", "loot_delay", "seconds, ignored with auto loot")
    self.rng(p, 5, "Mouse move duration", "mouse_move_duration", "seconds per movement")
    self.num(p, 6, "Click position jitter", "click_jitter_px", "pixels, random offset on every click", cast=int, hi=25)
    self.num(p, 7, "Recast if no splash after", "cast_timeout", "seconds", lo=5, hi=60)
    self.section(p, 8, "Randomization")
    self.choice(p, 9, "Timing distribution", "timing_distribution", DISTRIBUTIONS)
    self.note(p, 10, "Every delay is picked at random between its min and max each time it is used. "
                     "Set min and max to the same value to turn randomization off for that delay. "
                     "Gaussian makes values near the middle more common, which looks more natural than uniform.")
    return p

  def humanize_tab(self, nb):
    p = self.page(nb)
    self.note(p, 0, "Chances are rolled once before every cast.")
    self.num(p, 1, "Random click chance", "random_click_chance", "% per cast, clicks a random spot on the water", hi=100, scale=100)
    self.num(p, 2, "Random movement chance", "random_move_chance", "% per cast, does one of the movements below", hi=100, scale=100)
    self.section(p, 3, "Movements")
    self.check(p, 4, "Jump", "move_jump")
    self.check(p, 5, "Sidestep left/right and back (Q/E, can slowly drift your position)", "move_sidestep")
    self.check(p, 6, "Wander the mouse around the screen", "move_mouse_wander")
    self.section(p, 7, "Short breaks")
    self.num(p, 8, "Short break chance", "short_break_chance", "% per cast", hi=100, scale=100)
    ttk.Label(p, text="min").grid(row=9, column=1, sticky="w", padx=(8, 0))
    ttk.Label(p, text="max").grid(row=9, column=2, sticky="w", padx=(4, 0))
    self.rng(p, 10, "Short break length", "short_break_secs", "seconds")
    self.section(p, 11, "Mistakes and fatigue")
    self.num(p, 12, "Miss a bite chance", "miss_chance", "% of bites, notices the splash too late and recasts", hi=100, scale=100)
    self.num(p, 13, "Slow down over a session", "fatigue_pct_per_hour", "% longer delays per hour, resets after a log out", hi=100)
    return p

  def safety_tab(self, nb):
    p = self.page(nb)
    self.note(p, 0, "When one of these triggers, the bot stops where it is and beeps. Deal with it yourself, then press F9 to resume. "
                    "F9 also pauses at any time, and Esc quits.")
    self.check(p, 1, "Pause when a new whisper shows up in chat (default pink whisper color)", "pause_on_whisper")
    self.loc_row(p, 2, "chat_area", "Chat box")
    self.check(p, 3, "Pause when my health drops", "pause_on_health_drop")
    self.loc_row(p, 4, "health_area", "Health bar")
    self.num(p, 5, "Health drop that pauses", "health_drop_pct", "% of the bar", lo=1, hi=100)
    self.num(p, 6, "Pause after casts with no bite", "pause_after_no_bites", "in a row (0 = off), catches being moved or a GM teleport", cast=int)
    self.check(p, 7, "Pause when I move the mouse myself (take over)", "pause_on_mouse_takeover")
    self.check(p, 8, "Beep when paused", "alert_sound")
    self.note(p, 9, "Pick the chat box and health bar by pointing at their top left then bottom right corner. "
                    "Checks that have no box picked are skipped.")
    return p

  def session_tab(self, nb):
    p = self.page(nb)
    self.section(p, 0, "Log out")
    self.logout_mode = tk.StringVar(value=self.s.logout_mode)
    self.fields.append(("logout_mode", self.logout_mode.get))
    modes = [("never", "Never log out"), ("fixed", "Log out after a set time"), ("random", "Log out after a random time")]
    for i, (value, label) in enumerate(modes):
      ttk.Radiobutton(p, text=label, value=value, variable=self.logout_mode, command=self.update_states).grid(row=1 + i, column=0, columnspan=4, sticky="w")
    self.w_fixed = self.num(p, 4, "Log out after", "logout_after_mins", "minutes", lo=1)
    self.w_random = self.rng(p, 5, "Log out after (random)", "logout_random_mins", "minutes, min / max", lo=1)
    self.logout_action = self.choice(p, 6, "When logging out", "logout_action", LOGOUT_ACTIONS, command=self.update_states)

    self.section(p, 7, "Log back in")
    self.relogin = self.check(p, 8, "Log back in after a break (repeats until the session limit)", "relogin", command=self.update_states)
    self.w_relogin = []
    self.w_relogin += self.rng(p, 9, "Break length", "relogin_break_mins", "minutes, min / max")
    self.w_relogin += self.num(p, 10, "Loading screen wait", "relogin_load_secs", "seconds", lo=5)
    self.w_relogin += self.num(p, 11, "Stop after", "max_sessions", "sessions (0 = never stop)", cast=int)
    self.check(p, 12, "Zoom to first person after logging in", "relogin_first_person")
    self.note(p, 13, "Logging back in presses Enter on the character select screen that /logout leaves you on. "
                     "The bot never types your password, so it can't log in if the game fully disconnects or you choose Quit. "
                     "Draw the area of interest with the camera level in first person, so the view matches after a relog.")
    return p

  def images_tab(self, nb):
    p = ttk.Frame(nb, padding=12)
    top = ttk.Frame(p)
    top.pack(fill="x")
    ttk.Label(top, text="Folder").pack(side="left")
    self.img_dir = tk.StringVar(value=self.s.img_dir)
    self.fields.append(("img_dir", self.img_dir.get))
    ttk.Entry(top, textvariable=self.img_dir).pack(side="left", fill="x", expand=True, padx=6)
    ttk.Button(top, text="Browse...", command=self.browse_img_dir).pack(side="left")
    ttk.Button(top, text="Open", command=lambda: os.startfile(self.image_dir()) if os.path.isdir(self.image_dir()) else None).pack(side="left", padx=(4, 0))

    self.image_count = tk.StringVar()
    ttk.Label(p, textvariable=self.image_count, foreground="gray").pack(fill="x", pady=(8, 4))
    self.grid = ScrollFrame(p)
    self.grid.pack(fill="both", expand=True)

    buttons = ttk.Frame(p)
    buttons.pack(fill="x", pady=(8, 0))
    ttk.Button(buttons, text="Add images...", command=self.add_images).pack(side="left")
    self.capture_button = ttk.Button(buttons, text="Capture from screen", command=self.toggle_capture)
    self.capture_button.pack(side="left", padx=4)
    ttk.Label(buttons, text="size").pack(side="left", padx=(4, 2))
    self.capture_size = tk.StringVar(value="50")
    ttk.Entry(buttons, textvariable=self.capture_size, width=5).pack(side="left")
    ttk.Button(buttons, text="Remove selected", command=self.remove_images).pack(side="right")
    ttk.Button(buttons, text="Refresh", command=self.refresh_images).pack(side="right", padx=4)
    ttk.Label(p, text="Capture: the window minimizes, hover over your bobber in game and press F8 for each picture, Esc to finish. "
                      "Grab several sizes and angles, captured with the same window size you fish at.",
              foreground="gray", wraplength=600, justify="left").pack(fill="x", pady=(6, 0))
    self.img_dir.trace_add("write", lambda *a: self.refresh_images())
    self.refresh_images()
    return p

  def setup_tab(self, nb):
    p = self.page(nb)
    self.section(p, 0, "Screen locations")
    self.note(p, 1, "Pick minimizes this window. Hold the cursor still over the spot for 1 second after the 3 second countdown. "
                    "Anything left unset is asked for when the bot starts.")
    rows = [("cast_location", "Fishing ability (action bar)"), ("loot_location", "Loot window item"),
            ("bait_location", "Bait in bags"), ("pole_location", "Fishing pole (character panel)"),
            ("hearthstone_location", "Hearthstone (action bar)"), ("area_of_interest", "Area of interest (water)")]
    for i, (attr, label) in enumerate(rows):
      self.loc_row(p, 2 + i, attr, label)

    self.section(p, 8, "Fishing")
    self.check(p, 9, "Auto loot is on in game", "auto_loot")
    self.check(p, 10, "Attach bait", "attach_bait")
    self.num(p, 11, "Number of baits", "num_bait", cast=int)
    self.num(p, 12, "Re-bait every", "bait_interval_mins", "minutes", lo=1)
    self.num(p, 13, "Splash sensitivity", "splash_threshold_whitepx", "white pixels needed, lower = more sensitive", cast=int, lo=1)
    return p

  def loc_row(self, p, r, attr, label):
    ttk.Label(p, text=label).grid(row=r, column=0, sticky="w", pady=2)
    value = tk.StringVar()
    self.loc_labels[attr] = value
    ttk.Label(p, textvariable=value, width=16).grid(row=r, column=1, columnspan=2, sticky="w", padx=(8, 0))
    btns = ttk.Frame(p)
    btns.grid(row=r, column=3, sticky="w")
    ttk.Button(btns, text="Pick", width=6, command=lambda: self.pick(attr, label)).pack(side="left")
    ttk.Button(btns, text="Clear", width=6, command=lambda: self.clear_loc(attr)).pack(side="left", padx=4)
    self.show_loc(attr)

  # ---------- state ----------

  def update_states(self):
    mode = self.logout_mode.get()
    self.set_state(self.w_fixed, mode == "fixed")
    self.set_state(self.w_random, mode == "random")
    can_relogin = mode != "never" and self.logout_action() != "quit"
    self.set_state(self.w_relogin, can_relogin and self.relogin.get())

  def collect(self):
    values = {}
    try:
      for attr, read in self.fields:
        values[attr] = read()
    except ValueError as e:
      messagebox.showerror("Invalid setting", str(e), parent=self.root)
      return False
    for attr, v in values.items():
      setattr(self.s, attr, v)
    return True

  def save(self):
    if self.collect():
      self.s.save()
      self.status.set("Saved to config/config.json")
      return True
    return False

  def start(self):
    if not self.collect():
      return
    if not self.s.image_files():
      messagebox.showerror("No bobber images", "Add at least one bobber image in the Bobber Images tab.", parent=self.root)
      return
    self.s.save()
    self.started = True
    self.close()

  def cancel(self):
    self.close()

  def close(self):
    self.stop_capture()
    self.root.destroy()

  def poll(self):
    # background threads talk to the GUI through this queue, tkinter isn't thread safe
    try:
      while True:
        kind, data = self.events.get_nowait()
        if kind == "status":
          self.status.set(data)
        elif kind == "picked":
          attr, value = data
          setattr(self.s, attr, value)
          self.show_loc(attr)
          self.busy = False
          self.root.deiconify()
        elif kind == "captured":
          self.status.set(f"Saved {os.path.basename(data)}")
          self.refresh_images()
        elif kind == "capture_done":
          self.stop_capture()
          self.root.deiconify()
    except queue.Empty:
      pass
    self.root.after(100, self.poll)

  # ---------- locations ----------

  def show_loc(self, attr):
    v = getattr(self.s, attr)
    if v is None:
      text = "not set"
    elif attr == "area_of_interest":
      text = f"{len(v)} points"
    elif attr in BOX_ATTRS:
      text = f"{abs(v[1][0] - v[0][0])} x {abs(v[1][1] - v[0][1])} box"
    else:
      text = f"({v[0]}, {v[1]})"
    self.loc_labels[attr].set(text)

  def clear_loc(self, attr):
    setattr(self.s, attr, None)
    self.show_loc(attr)

  def pick(self, attr, label):
    if self.busy:
      return
    self.busy = True
    self.root.iconify()
    status = lambda msg: self.events.put(("status", msg))

    def work():
      focus_wow_window()
      time.sleep(0.3)
      if attr == "area_of_interest":
        value = get_area_of_interest(status)
      elif attr in BOX_ATTRS:
        value = get_box(label.lower(), status)
      elif attr == "pole_location":
        value = get_pole_loc(status)
      else:
        value = get_single_loc(label.lower(), status)
      self.events.put(("picked", (attr, value)))
    threading.Thread(target=work, daemon=True).start()

  # ---------- images ----------

  def image_dir(self):
    return resolve_path(self.img_dir.get() or ".")

  def image_paths(self):
    d = self.image_dir()
    if not os.path.isdir(d):
      return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(IMAGE_EXTS))

  def browse_img_dir(self):
    d = filedialog.askdirectory(initialdir=self.image_dir() if os.path.isdir(self.image_dir()) else None, parent=self.root)
    if d:
      self.img_dir.set(d)

  def refresh_images(self):
    for w in self.grid.inner.winfo_children():
      w.destroy()
    self.thumbs = []
    paths = self.image_paths()
    self.selected_images &= set(paths)
    for i, path in enumerate(paths):
      img = thumbnail(path)
      if img is None:
        continue
      self.thumbs.append(img)
      cell = tk.Label(self.grid.inner, image=img, width=THUMB_SIZE + 12, height=THUMB_SIZE + 12, bd=2, relief="groove",
                      bg=SELECTED_BG if path in self.selected_images else None)
      cell.grid(row=i // THUMB_COLUMNS, column=i % THUMB_COLUMNS, padx=3, pady=3)
      cell.bind("<Button-1>", lambda e, p=path, c=cell: self.toggle_image(p, c))
    n = len(paths)
    self.image_count.set(f"{n} bobber image{'s' if n != 1 else ''} in {self.image_dir()}"
                         + ("" if n else "  (you need at least one to start)"))

  def toggle_image(self, path, cell):
    self.status.set(os.path.basename(path))
    if path in self.selected_images:
      self.selected_images.discard(path)
      cell.configure(bg=self.root.cget("bg"))
    else:
      self.selected_images.add(path)
      cell.configure(bg=SELECTED_BG)

  def add_images(self):
    files = filedialog.askopenfilenames(parent=self.root, title="Add bobber images",
                                        filetypes=[("Images", " ".join("*" + e for e in IMAGE_EXTS))])
    if not files:
      return
    d = self.image_dir()
    os.makedirs(d, exist_ok=True)
    for f in files:
      if os.path.dirname(os.path.abspath(f)) != os.path.abspath(d):
        shutil.copy2(f, d)
    self.refresh_images()

  def remove_images(self):
    if not self.selected_images:
      self.status.set("Click images to select them first")
      return
    n = len(self.selected_images)
    if not messagebox.askyesno("Remove images", f"Delete {n} selected image{'s' if n != 1 else ''} from the folder?", parent=self.root):
      return
    for path in self.selected_images:
      os.remove(path)
    self.selected_images = set()
    self.refresh_images()

  def toggle_capture(self):
    if self.capture_listener:
      self.stop_capture()
      return
    try:
      size = int(self.capture_size.get())
      if not 10 <= size <= 300:
        raise ValueError
    except ValueError:
      messagebox.showerror("Invalid size", "Capture size must be a number between 10 and 300.", parent=self.root)
      return
    directory = self.image_dir()

    def on_release(key):
      if key == Key.f8:
        self.events.put(("captured", capture_at_cursor(directory, size)))
      elif key == Key.esc:
        self.events.put(("capture_done", None))
        return False

    self.capture_listener = Listener(on_release=on_release)
    self.capture_listener.start()
    self.capture_button.configure(text="Stop capturing")
    self.status.set("Capturing: hover the bobber and press F8, Esc to finish")
    self.root.iconify()

  def stop_capture(self):
    if self.capture_listener:
      self.capture_listener.stop()
      self.capture_listener = None
      self.capture_button.configure(text="Capture from screen")


def run_gui(settings):
  # returns True if the user pressed Start
  app = App(settings)
  app.root.mainloop()
  return app.started
