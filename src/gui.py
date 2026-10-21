import os, shutil, threading, queue, base64, time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2 as cv
from pynput.keyboard import Key, Listener
from settings import resolve_path, IMAGE_EXTS, Settings
from setup import get_single_loc, get_pole_loc, get_area_of_interest, get_box, focus_wow_window
from template_capture import capture_at_cursor

THUMB_SIZE = 72
THUMB_COLUMNS = 6
SELECTED_BG = "#3b82f6"

DISTRIBUTIONS = [("skewed", "Skewed (mostly quick, sometimes slow)"), ("gaussian", "Gaussian (clusters around the middle)"),
                 ("uniform", "Uniform (anywhere in the range)")]
BOX_ATTRS = ("chat_area", "health_area", "loot_icon_area")
LOGOUT_ACTIONS = [("logout", "/logout"), ("hearth_logout", "Hearthstone, then /logout"), ("quit", "Quit game (Alt+F4)")]
CORNERS = [("top_left", "Top left"), ("top_right", "Top right"), ("bottom_left", "Bottom left"), ("bottom_right", "Bottom right")]


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
    self.events = queue.Queue(maxsize=128)
    self.closed = threading.Event()
    self.fields = []
    self.capture_listener = None
    self.selected_images = set()
    self.thumbs = []
    self.loc_labels = {}

    self.root = tk.Tk()
    self.root.title("WoW Fishing Bot")
    from visual_targeting.errors import track_tk_errors
    track_tk_errors(self.root,lambda text:self.status.set(text) if hasattr(self,"status") else None)
    self.root.minsize(640, 560)
    self.root.protocol("WM_DELETE_WINDOW", self.cancel)

    self.defaults = Settings()
    self.field_help = tk.StringVar(value="Click or hover over any input to see what it does and its default.")
    self.pages = ttk.Notebook(self.root)
    self.pages.pack(fill="both", expand=True, padx=8, pady=(8, 0))
    nb = ttk.Notebook(self.pages)
    self.pages.add(nb, text="Normal fishing")
    self.home = ttk.Frame(nb, padding=22)
    nb.add(self.home, text="Start")
    nb.add(self.timing_tab(nb), text="Timing")
    nb.add(self.humanize_tab(nb), text="Humanize")
    nb.add(self.safety_tab(nb), text="Safety")
    nb.add(self.session_tab(nb), text="Log out / Log in")
    nb.add(self.images_tab(nb), text="Bobber Images")
    nb.add(self.setup_tab(nb), text="Locations & Fishing")
    nb.add(self.loot_tab(nb), text="Loot & Overlay")
    visual = ttk.Frame(self.pages)
    training = ttk.Frame(self.pages, padding=8)
    self.pages.add(visual, text="Visual targeting")
    self.pages.add(training, text="Neural training")
    from visual_targeting.app_gui import TargetingPanel
    self.targeting_panel = TargetingPanel(visual,training_parent=training,settings_provider=self.current_fishing_settings)
    self.targeting_panel.pack(fill="both",expand=True)
    from visual_targeting.model_results_gui import ModelResultsPanel
    self.model_results = ModelResultsPanel(self.pages,on_preview=lambda row: self.preview_model(row))
    self.targeting_panel.use_fishing_callback=self.use_selected_fishing
    self.model_results.connect(self.targeting_panel)
    self.pages.add(self.model_results,text="Model results")
    self.pages.bind('<<NotebookTabChanged>>',lambda event: self.model_results.refresh() if self.pages.select()==str(self.model_results) else None)
    self.build_home()
    self.describe_remaining_inputs(self.root)
    ttk.Label(self.root,textvariable=self.field_help,wraplength=850,justify="left").pack(fill="x",padx=12,pady=5)

    bottom = ttk.Frame(self.root)
    bottom.pack(fill="x", padx=8, pady=8)
    self.status = tk.StringVar(value="Use Guided setup once, then Start fishing. F9 pauses/resumes; Esc stops.")
    ttk.Label(bottom, textvariable=self.status, wraplength=380).pack(side="left", fill="x", expand=True)
    ttk.Button(bottom, text="Cancel", command=self.cancel).pack(side="right")
    ttk.Button(bottom, text="Start fishing", command=self.start).pack(side="right", padx=4)
    ttk.Button(bottom, text="Save", command=self.save).pack(side="right")

    from visual_targeting.input_help import install_button_help
    install_button_help(self.root)
    self.update_states()
    self.poll_timer = self.root.after(100, self.poll)

  def use_selected_fishing(self,info):
    if not self.collect():raise ValueError('Correct the invalid normal setting before auto-fill.')
    from visual_targeting.live_setup import fishing_setup
    report=fishing_setup(self.s,info,self.targeting_panel.get('registry'),self.targeting_panel.get('hwnd'))
    fields=report['fields']
    self.neural_weights_var.set(fields['weights'])
    self.neural_profile_var.set(fields['profile'])
    self.neural_registry_var.set(fields['registry'])
    self.backend_choice.set('Neural network (approved model for live)')
    self.s.neural_window_hwnd=report['hwnd']
    # Update the settings object as well as visible inputs; later Start reads the same values.
    self.s.detector_backend='neural';self.s.neural_weights=fields['weights']
    self.s.neural_profile=fields['profile'];self.s.neural_registry=fields['registry']
    self.pages.select(0)
    self.pages.nametowidget(self.pages.tabs()[0]).select(0)
    self.status.set(report['message']);self.ready_text.set(report['message'])
    if not report['ready']:
      from visual_targeting.errors import record_error
      record_error('live_auto_fill_blocked',ValueError(report['message']),{'profile':fields['profile'],'weights':fields['weights'],'hwnd':report['hwnd']})
    return report

  def preview_model(self,row):
    self.pages.select(1)
    self.targeting_panel.guard(lambda:self.targeting_panel.preview_model(row))

  def describe_input(self,widget,attr):
    from visual_targeting.input_help import describe
    describe(widget,attr,getattr(self.defaults,attr,None),self.field_help.set)

  def describe_remaining_inputs(self,parent):
    from visual_targeting.input_help import InputHint
    variables={}
    for name in ('img_dir','capture_size','loot_dir','tesseract','neural_weights_var','neural_profile_var','neural_registry_var'):
      value=getattr(self,name,None)
      if value is not None:variables[str(value)]={'tesseract':'tesseract_cmd'}.get(name,name.removesuffix('_var'))
    for widget in parent.winfo_children():
      if isinstance(widget,(ttk.Entry,ttk.Combobox,ttk.Checkbutton,ttk.Radiobutton)) and not hasattr(widget,'input_description'):
        attr=variables.get(str(widget.cget('textvariable'))) if isinstance(widget,(ttk.Entry,ttk.Combobox)) else None
        if attr:self.describe_input(widget,attr)
        elif isinstance(widget,ttk.Radiobutton):self.describe_input(widget,'logout_action')
        elif isinstance(widget,ttk.Checkbutton):self.describe_input(widget,'live_controls')
        else:InputHint(widget,'Enter the value shown by the adjacent label. Keep the prefilled value unless changing this setting.',self.field_help.set)
      self.describe_remaining_inputs(widget)

  def current_fishing_settings(self):
    return self.s if self.collect() else None

  def build_home(self):
    ttk.Label(self.home, text="Fishing", font=("Segoe UI", 24, "bold")).pack(anchor="w")
    ttk.Label(self.home, text="One setup. Saved for next time.", font=("Segoe UI", 12)).pack(anchor="w", pady=(0,18))
    ttk.Label(self.home, text="1. Open WoW at your fishing spot with the Fishing ability visible on your action bar.\n"
              "2. Enable Auto Loot in WoW. Click Guided setup, switch to WoW and cast.\n"
              "3. On the frozen picture, mark the water, bobber and Fishing ability. Save, then start.",
              wraplength=680, justify="left").pack(anchor="w", pady=8)
    ttk.Button(self.home, text="Guided setup (10-second countdown)", command=self.guided_setup).pack(anchor="w", pady=12)
    self.ready_text=tk.StringVar()
    ttk.Label(self.home, textvariable=self.ready_text, wraplength=680).pack(anchor="w", pady=10)
    self.live_controls=tk.BooleanVar(value=False)
    ttk.Checkbutton(self.home,text="Enable live game controls when I press Start fishing",
                    variable=self.live_controls).pack(anchor="w",pady=10)
    ttk.Label(self.home,text="Unchecked = dry-run, no game input. While fishing: F9 pauses/resumes; Esc stops.\n"
              "Redo setup if you move/resize the game or change its UI scale. Your original settings are in the Normal fishing tabs.",
              wraplength=680,justify="left").pack(anchor="w",pady=10)
    self.check(self.home_teaching_frame(),0,"Ask me to box missed bobbers while fishing (neural teaching)","teach_on_miss")
    self.refresh_ready()

  def home_teaching_frame(self):
    frame=ttk.Frame(self.home);frame.pack(fill="x",pady=4);return frame

  def refresh_ready(self):
    missing=[]
    if self.s.area_of_interest is None:missing.append("fishing area")
    if self.s.cast_location is None:missing.append("Fishing ability")
    if self.s.detector_backend=="template" and not self.s.image_files():missing.append("bobber picture")
    self.ready_text.set("Needs setup: "+", ".join(missing) if missing else "Setup saved. Ready to start fishing.")

  def guided_setup(self):
    if self.busy:return
    if not self.collect():return
    self.busy=True
    self.targeting_panel.stop()
    self.root.iconify()
    def complete(result):
      self.busy=False;self.root.deiconify()
      if result is not None:
        self.s.area_of_interest=result["area_of_interest"]
        self.s.cast_location=result["cast_location"]
        # Simple setup uses in-game Auto Loot and no automatic bait/equipment setup.
        for attr,value in (("auto_loot",True),("attach_bait",False)):
          getattr(self,"simple_"+attr).set(value)
          setattr(self.s,attr,value)
        self.s.save()
        self.show_loc("area_of_interest");self.show_loc("cast_location")
        self.refresh_images();self.status.set("Setup saved. Choose dry-run or enable live controls, then Start fishing.")
      else:self.status.set("Setup cancelled. Previous settings kept.")
      self.refresh_ready()
    def tick(seconds):
      if self.closed.is_set():return
      if seconds:
        self.status.set(f"Setup screenshot in {seconds}s. Switch to WoW and cast.")
        self.setup_timer=self.root.after(1000,lambda:tick(seconds-1))
      else:
        try:
          from visual_targeting.fishing_setup import open_fishing_setup
          open_fishing_setup(self.root,self.image_dir(),complete)
        except Exception as exc:
          complete(None);self.status.set(f"Could not capture setup picture: {exc}")
    tick(10)

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
    self.describe_input(entry,attr)
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
    self.describe_input(ea,attr)
    ea.grid(row=row, column=1, sticky="w", padx=(8, 0))
    eb = ttk.Entry(parent, textvariable=vb, width=8)
    self.describe_input(eb,attr)
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
    self.describe_input(cb,attr)
    cb.grid(row=row, column=0, columnspan=4, sticky="w", pady=3)
    self.fields.append((attr, var.get))
    return var

  def choice(self, parent, row, label, attr, options, command=None):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
    labels = [l for _, l in options]
    current = dict(options).get(getattr(self.s, attr), labels[0])
    var = tk.StringVar(value=current)
    box = ttk.Combobox(parent, textvariable=var, values=labels, state="readonly", width=34)
    self.describe_input(box,attr)
    if attr=="detector_backend":self.backend_choice=var
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
    self.num(p, 11, "Time to find a new bobber", "acquire_timeout", "seconds of searching, still bounded by cast timeout", lo=1, hi=30)
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
                     "Select a rectangle on a frozen screenshot. Keep the camera level in first person so the view matches after a relog.")
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
    scroll = ScrollFrame(nb,height=550)
    p = self.page(scroll.inner)
    p.pack(fill="both",expand=True)
    self.section(p, 0, "Screen locations")
    self.note(p, 1, "Pick takes a screenshot after 5 seconds. Click a location or drag an area on the frozen picture. "
                    "For bait or pole, open the bags or character panel during the countdown. Save after selecting.")
    rows = [("cast_location", "Fishing ability (action bar)"), ("loot_location", "Loot window item"),
            ("bait_location", "Bait in bags"), ("pole_location", "Fishing pole (character panel)"),
            ("hearthstone_location", "Hearthstone (action bar)"), ("area_of_interest", "Area of interest (water)")]
    for i, (attr, label) in enumerate(rows):
      self.loc_row(p, 2 + i, attr, label)

    self.section(p, 8, "Fishing")
    self.simple_auto_loot = self.check(p, 9, "Auto loot is on in game", "auto_loot")
    self.simple_attach_bait = self.check(p, 10, "Attach bait", "attach_bait")
    self.num(p, 11, "Number of baits", "num_bait", cast=int)
    self.num(p, 12, "Re-bait every", "bait_interval_mins", "minutes", lo=1)
    self.num(p, 14, "Template match confidence", "match_threshold", "0 to 1", lo=0, hi=1)
    self.num(p, 13, "Splash sensitivity", "splash_threshold_whitepx", "white pixels needed, lower = more sensitive", cast=int, lo=1)
    self.section(p, 15, "Detector and mouse placement")
    self.choice(p, 16, "Find bobbers using", "detector_backend",
                [("template","Template matching (original)"),("neural","Neural network (approved model for live)")])
    for row,attr,label in [(17,"neural_weights","Candidate .pt (dry-run only)"),(18,"neural_profile","Neural task profile"),(19,"neural_registry","Approved model registry")]:
      ttk.Label(p,text=label).grid(row=row,column=0,sticky="w")
      value=tk.StringVar(value=getattr(self.s,attr))
      setattr(self,attr+"_var",value)
      ttk.Entry(p,textvariable=value,width=40).grid(row=row,column=1,columnspan=3,sticky="ew")
      self.fields.append((attr,value.get))
    ttk.Button(p,text="Use latest trained model paths",command=self.use_latest_neural).grid(row=20,column=0,columnspan=4,sticky="w")
    self.check(p,21,"Move onto a uniquely tracked bobber while waiting for the bite","hover_on_acquire")
    self.check(p,22,"Require the calibrated gear cursor before a bite click","require_gear_cursor")
    ttk.Button(p,text="1. Capture normal cursor (5s)",command=lambda:self.calibrate_cursor(False)).grid(row=23,column=0,columnspan=2,sticky="w")
    ttk.Button(p,text="2. Capture gear cursor (5s)",command=lambda:self.calibrate_cursor(True)).grid(row=23,column=2,columnspan=2,sticky="w")
    self.cursor_status=tk.StringVar(value="Gear calibration is optional and lasts for this helper session.")
    ttk.Label(p,textvariable=self.cursor_status,wraplength=680).grid(row=24,column=0,columnspan=4,sticky="w")
    self.note(p,25,"Neural dry-run can inspect candidate weights. Automatic input requires an explicitly approved matching model. "
                      "A gear cursor confirms an interactable hover, not a bite; splash evidence is still required. "
                      "For a safe movement-only test use Visual targeting. Keep WoW visible on one monitor.")
    return scroll

  def use_latest_neural(self):
    try:
      from visual_targeting.deployment import latest_candidate
      info=latest_candidate()
      self.use_selected_fishing(info)
    except Exception as exc:
      from visual_targeting.errors import record_error
      record_error('latest_live_auto_fill',exc)
      self.status.set(f'Cannot configure live fishing: {exc}')

  def calibrate_cursor(self,gear):
    if self.busy:return
    self.targeting_panel.stop()
    self.busy=True;self.root.iconify()
    self.cursor_status.set("Hover YOUR bobber until the gear appears." if gear else "Hover empty water so the normal cursor appears.")
    def capture():
      self.cursor_timer=None
      try:
        from visual_targeting.cursor_feedback import cursor_identity
        from visual_targeting.window_context import query_window
        from visual_targeting.profiles import Profile
        handle,hwnd=cursor_identity()
        identity,_,_=query_window(hwnd)
        profile=Profile.read(resolve_path(self.neural_profile_var.get()))
        if not profile.allows(identity):raise ValueError("WoW must be foreground during calibration")
        other=self.s.normal_cursor_handle if gear else self.s.gear_cursor_handle
        if other and handle==other:raise ValueError("The two cursor shapes are identical. Hover empty water for normal, and the bobber for gear.")
        if gear:
          self.s.gear_cursor_handle=handle;self.s.gear_window_hwnd=hwnd
        else:self.s.normal_cursor_handle=handle
        self.cursor_status.set("Captured gear cursor." if gear else "Captured normal cursor. Now capture the gear while hovering your bobber.")
      except Exception as exc:self.cursor_status.set(f"Cursor calibration failed: {exc}")
      finally:
        self.busy=False
        if not self.closed.is_set():self.root.deiconify()
    self.cursor_timer=self.root.after(5000,capture)

  def loot_tab(self, nb):
    p = self.page(nb)
    self.section(p, 0, "Loot tracking")
    self.check(p, 1, "Screenshot the loot window, identify the items and log them", "loot_tracking")
    self.loc_row(p, 2, "loot_icon_area", "First loot icon")
    self.num(p, 3, "Slot spacing", "loot_slot_pitch_px", "pixels from one icon's top to the next (0 = guess)", cast=int, hi=300)
    self.num(p, 4, "Slots to check", "loot_max_slots", "", cast=int, lo=1, hi=8)
    self.check(p, 5, "Loot every item (off = only the first slot, like before)", "loot_all_slots")
    ttk.Label(p, text="Loot folder").grid(row=6, column=0, sticky="w", pady=3)
    folder = ttk.Frame(p)
    folder.grid(row=6, column=1, columnspan=3, sticky="we", padx=(8, 0))
    self.loot_dir = tk.StringVar(value=self.s.loot_dir)
    self.fields.append(("loot_dir", self.loot_dir.get))
    ttk.Entry(folder, textvariable=self.loot_dir, width=30).pack(side="left", fill="x", expand=True)
    ttk.Button(folder, text="Open", command=self.open_loot_dir).pack(side="left", padx=(4, 0))
    ttk.Label(p, text="Tesseract path").grid(row=7, column=0, sticky="w", pady=3)
    self.tesseract = tk.StringVar(value=self.s.tesseract_cmd)
    self.fields.append(("tesseract_cmd", self.tesseract.get))
    ttk.Entry(p, textvariable=self.tesseract, width=40).grid(row=7, column=1, columnspan=3, sticky="w", padx=(8, 0))
    self.note(p, 8, "Pick the box by pointing at the top left then bottom right corner of the first item's icon while a loot "
                    "window is open. Turn off \"Open loot window at mouse\" in game so it always opens in the same place. "
                    "Item names are read with Tesseract OCR if it's installed (blank path = default install folder); icons are "
                    "learned automatically and used when OCR can't read a name. Icons it can't name go to icons/unknown, rename "
                    "one to the item's name and move it up a folder to teach it. Screenshots and loot_log.csv go in the loot folder.")

    self.section(p, 9, "Overlay")
    self.check(p, 10, "Show stats and running averages on screen while fishing", "show_overlay")
    self.choice(p, 11, "Corner", "overlay_corner", CORNERS)
    self.num(p, 12, "Running average over", "running_avg_casts", "casts", cast=int, lo=1, hi=1000)
    self.note(p, 13, "The overlay is click-through and hidden from the bot's own screenshots. "
                     "WoW needs to run in windowed or windowed fullscreen mode for it to show on top.")
    return p

  def open_loot_dir(self):
    d = resolve_path(self.loot_dir.get() or ".")
    os.makedirs(d, exist_ok=True)
    os.startfile(d)

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
      from visual_targeting.errors import record_error
      record_error("invalid_setting",e)
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
    if self.busy:
      self.status.set("Finish or cancel setup first.")
      return
    if not self.collect():return
    if self.s.area_of_interest is None or self.s.cast_location is None or (self.s.detector_backend=="template" and not self.s.image_files()):
      self.guided_setup()
      return
    if self.s.attach_bait and (self.s.bait_location is None or self.s.pole_location is None):
      messagebox.showerror("Bait setup incomplete","Pick bait and pole in Normal fishing, or turn Attach bait off.",parent=self.root)
      return
    if not self.s.auto_loot and self.s.loot_location is None:
      messagebox.showerror("Loot setup incomplete","Use Guided setup with Auto Loot enabled, or pick the loot location in Normal fishing.",parent=self.root)
      return
    if self.s.logout_mode != "never" and self.s.logout_action == "hearth_logout" and self.s.hearthstone_location is None:
      messagebox.showerror("Hearthstone setup incomplete","Choose ordinary logout or pick the Hearthstone in Normal fishing.",parent=self.root)
      return
    self.s.load_images()
    if self.s.detector_backend=="template" and not self.s.templates:
      messagebox.showerror("Bobber picture unusable","Run Guided setup to select a clear bobber picture.",parent=self.root)
      return
    if self.s.require_gear_cursor and self.live_controls.get() and (not self.s.gear_cursor_handle or not self.s.normal_cursor_handle):
      messagebox.showerror("Calibrate the gear cursor","Capture both normal and gear cursor shapes above, or turn off Require calibrated gear.",parent=self.root)
      return
    if self.s.teach_on_miss and self.s.detector_backend!="neural":
      messagebox.showinfo("Neural teaching","Select Neural network in Locations & Fishing before enabling teaching. Original template fishing remains available without teaching.",parent=self.root)
      return
    if self.s.detector_backend=="neural":
      try:
        from fishing.backend import make_fishing_detector
        self.status.set("Checking neural model approval and loading detector...")
        self.root.update_idletasks()
        self.s._prepared_detector=make_fishing_detector(self.s,live_input=self.live_controls.get())
      except Exception as exc:
        from visual_targeting.errors import record_error
        record_error("live_start_model",exc,{"profile":self.s.neural_profile,"weights":self.s.neural_weights})
        self.model_results.refresh();self.pages.select(self.model_results)
        self.status.set("Live fishing blocked: "+str(exc)+". Select your model in Model results and review its evaluation.")
        messagebox.showerror("Neural model not ready",str(exc)+"\n\nModel results is now open. Select the model, Evaluate selected, then Review / approve selected if its results pass. Teaching preview remains available while improving it.",parent=self.root)
        return
    from visual_targeting.input import desktop, WindowsInput, DryRunInput
    desktop.configure(WindowsInput() if self.live_controls.get() else DryRunInput())
    self.s.save()
    self.started = True
    self.close()

  def cancel(self):
    self.close()

  def post_event(self, item):
    while not self.closed.is_set():
      try:
        self.events.put(item, timeout=0.1)
        return
      except queue.Full:
        continue

  def close(self):
    for timer in (getattr(self, "poll_timer", None), getattr(self, "setup_timer", None), getattr(self, "pick_timer", None), getattr(self, "cursor_timer", None)):
      if timer:
        try: self.root.after_cancel(timer)
        except tk.TclError: pass
    self.targeting_panel.shutdown()
    self.closed.set()
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
    self.poll_timer = self.root.after(100, self.poll)

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
    if self.busy:return
    self.busy = True
    self.targeting_panel.stop()
    point = attr != "area_of_interest" and attr not in BOX_ATTRS
    self.root.iconify()
    instruction = "click the location" if point else "drag a rectangle"
    self.status.set(f"Screenshot in 5 seconds. Show the game, then {instruction} on the frozen picture.")
    def finish(value):
      if self.closed.is_set():return
      self.busy = False
      self.root.deiconify()
      if value is not None:
        setattr(self.s, attr, value)
        self.show_loc(attr)
        self.refresh_ready()
        self.status.set("Selection accepted. Click Save to keep it. Redo after moving/resizing the game.")
      else:
        self.status.set("Selection cancelled; previous setting kept.")
    def select():
      self.pick_timer = None
      if self.closed.is_set():return
      try:
        from visual_targeting.area_picker import pick_desktop_area
        pick_desktop_area(self.root, label, finish, polygon=attr == "area_of_interest", point=point)
      except Exception as exc:
        finish(None)
        self.status.set(f"Screen selection failed: {exc}")
    self.pick_timer = self.root.after(5000, select)

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
        self.post_event(("captured", capture_at_cursor(directory, size)))
      elif key == Key.esc:
        self.post_event(("capture_done", None))
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
