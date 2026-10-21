"""Plain-language input explanations shared by normal and neural tools."""
import tkinter as tk
HELP={
'profile':'Rules for the detector: permitted game, classes, confidence and model identity. The latest-model buttons fill this.',
'registry':'Folder holding explicitly approved model releases. Leave the default unless moving your model library.',
'hwnd':'Windows ID of the game window. Use Select game window; you do not need to type or guess it.',
'dataset':'Folder containing recorded pictures and their manifest. Automatic training prepares reviewed data for you.',
'session':'One independent visit/recording session. Keep casts from the same visit together to prevent train/test leakage.',
'cast':'ID for this individual cast within the session. Recording buttons generate safe IDs.',
'region':'Physical screen capture rectangle: left, top, width, height. Use the game-area buttons instead of typing coordinates.',
'config':'Saved training configuration. Load config fills the manual controls; automatic first training uses its stated preset.',
'output':'New folder for the next manual training/evaluation run. Existing results are never overwritten.',
'release':'An already approved release ID, used only for rollback. Leave empty unless restoring a previous model.',
'reviewer':'Account/name of the person who explicitly reviews labels or approves a model. Prefilled with your Windows account.',
'weights':'Candidate trained .pt file. Latest-model buttons fill this. Selecting it does not approve or activate it.',
'training_run':'Folder containing run.json for these exact weights. Filled by latest-model buttons for provenance checking.',
'python':'Python executable used by the cancellable training process. Default is this app’s Python.',
'export_output':'New folder for a reviewed, session-split dataset. Automatic training fills this; raw pictures stay unchanged.',
'model':'Pretrained .pt weights to fine-tune. The starter is yolo11n.pt; download requires explicit confirmation.',
'epochs':'Maximum training passes through the data. More passes take longer and do not guarantee better test results.',
'imgsz':'Model input resolution in pixels. Larger values can preserve small bobbers but use more memory and time.',
'batch':'Training images processed together. Lower this if memory runs out.',
'device':'cpu, or a CUDA GPU index such as 0 when available. Automatic training detects usable CUDA support.',
'mode':'dry-run shows targets only; move permits an armed move; single-click needs an approved model and explicit arming.',
'allow_download':'Allow downloading official starter weights when training begins. Does not train or activate a model by itself.',
'cast_delay':'Wait before another cast. The two numbers are minimum and maximum seconds.',
'splash_search_delay':'Wait after casting before searching, allowing the bobber to land. Min/max seconds.',
'bobber_click_delay':'Reaction-delay range used by the legacy splash loop. The tracked loop uses its bounded temporal bite policy.',
'loot_delay':'Delay before manually collecting each loot item. In-game Auto Loot can make manual looting unnecessary.',
'mouse_move_duration':'Duration of legacy/random mouse movements. Guarded target moves go directly to the verified point.',
'click_jitter_px':'Random offset for legacy/random actions. Confirmed bobber targeting uses the exact point without jitter.',
'cast_timeout':'Maximum total seconds for a cast before giving up or recasting; includes landing/search time.',
'acquire_timeout':'Seconds of searching after the landing wait to confirm a unique new bobber. Total cast timeout still applies.',
'timing_distribution':'How legacy/random delays are sampled between min and max; equal endpoints give a fixed delay.',
'random_click_chance':'Chance per cast of an optional random water click. Set to 0 to disable this extra action.',
'random_move_chance':'Chance per cast of an optional movement action. Set to 0 to disable extra movement.',
'move_jump':'Allow jumping when an optional random movement is chosen. This can change the fishing view.',
'move_sidestep':'Allow brief sideways movement during random actions. It can slowly change your position.',
'move_mouse_wander':'Allow random mouse wandering between casts when an optional movement is selected.',
'short_break_chance':'Chance per cast of an optional pause. Set to 0 to disable these short breaks.',
'short_break_secs':'Minimum/maximum duration of an optional short break, in seconds.',
'miss_chance':'Intentional-miss probability in the legacy splash loop. The tracked bite loop does not use this setting.',
'fatigue_pct_per_hour':'How much legacy/random delays grow per hour. Does not relax target freshness or input guards.',
'pause_on_whisper':'Pause when a new pink whisper is detected in a configured chat area. No area means this check is skipped.',
'pause_on_health_drop':'Pause when the configured health-bar area shows a sufficient drop. No area means the check is skipped.',
'health_drop_pct':'Health-bar drop that triggers a pause; requires a valid health area.',
'pause_after_no_bites':'Consecutive unsuccessful casts before a troubleshooting pause. 0 disables this counter.',
'pause_on_mouse_takeover':'Treat your manual mouse movement as takeover and stop/pause automated input.',
'alert_sound':'Play an audible alert when a safety pause needs attention.',
'logout_mode':'Never log out, use a fixed session length, or randomly choose a session length.',
'logout_after_mins':'Session length in minutes when fixed logout is selected.',
'logout_random_mins':'Minimum/maximum session length in minutes when random logout is selected.',
'logout_action':'What happens at session end: logout, Hearthstone then logout, or quit. Hearthstone needs its location.',
'relogin':'Attempt to resume from the character-selection screen after a break. Never types your password.',
'relogin_break_mins':'Minimum/maximum break length in minutes before attempting another session.',
'relogin_load_secs':'Wait for the game to finish loading after relogging, in seconds.',
'max_sessions':'Maximum sessions before stopping. 0 means no session-count limit.',
'relogin_first_person':'Restore first-person zoom after relogging so the view resembles your captured templates.',
'auto_loot':'Confirm Auto Loot is enabled inside WoW. This checkbox does not change the game setting.',
'attach_bait':'Apply bait automatically. Requires valid bait and equipped-pole screen locations.',
'num_bait':'How many bait applications remain; decremented as bait is applied.',
'bait_interval_mins':'Minutes between automatic bait applications.',
'match_threshold':'Template matching cutoff from 0 to 1. Higher can reduce false matches but miss bobbers. Neural confidence comes from its evaluated profile.',
'splash_threshold_whitepx':'Number of bright pixels used in splash evidence. Lower values are more sensitive to reflections.',
'detector_backend':'Choose original template matching or neural detection. Live neural input requires an approved model.',
'hover_on_acquire':'Move to your uniquely confirmed new bobber while waiting for a bite. Does not click just because it is hovered.',
'require_gear_cursor':'Require the calibrated gear shape before a bite click. Calibrate both shapes each helper/game session.',
'loot_tracking':'Record loot images/items and statistics. This does not prove a catch when only a click was issued.',
'loot_slot_pitch_px':'Vertical spacing between loot slots in pixels. 0 lets the tracker estimate spacing.',
'loot_max_slots':'Maximum loot slots to inspect per loot window.',
'loot_all_slots':'Attempt all visible loot slots rather than only the first.',
'show_overlay':'Show fishing statistics over the game window.',
'overlay_corner':'Screen corner used for the statistics overlay.',
'running_avg_casts':'Number of recent casts used for the running average; larger values smooth short-term changes.',
'img_dir':'Your saved bobber reference-image folder for original template matching. Your existing path is preserved.',
'capture_size':'Square reference-image crop size in screen pixels for the F8 capture tool.',
'loot_dir':'Folder for loot icons, screenshots and item logs. Existing files are kept.',
'tesseract_cmd':'Optional Tesseract OCR executable path. Blank uses the default installation if available.',
'neural_weights':'Candidate .pt path for neural dry-run. Use latest trained model paths fills it; live input uses an approved registry artifact.',
'neural_profile':'Exact evaluated neural policy. Changing it can invalidate model approval; use latest trained paths.',
'neural_registry':'Folder of approved neural releases and their evidence. Leave the normal default.',
'live_controls':'Explicitly allow the normal fishing loop to send game input when Start fishing is pressed. Default is off.',
'class':'Object type for the box you draw. Choose bobber for a float; loot only for visible loot objects.',
}
for name,label in {
'cast_location':'Fishing ability icon on the action bar','loot_location':'Item location in the loot window',
'bait_location':'Bait item in your bags','pole_location':'Equipped fishing pole in the character panel',
'hearthstone_location':'Hearthstone action-bar icon','area_of_interest':'Water region where your bobber can land',
'chat_area':'Chat region used for whisper checks','health_area':'Health-bar region used for health-drop checks',
'loot_icon_area':'First loot-slot icon region'}.items():
    HELP[name]=label+'. Use Pick to select it on a frozen screenshot; do not type coordinates.'

def explanation(name,label=None):
    if name not in HELP:raise KeyError('Missing input description: '+name)
    return HELP[name]

def default_text(value):
    if value is None or value=='':return 'Not set; fill with the relevant selection button when needed.'
    if value is True:return 'On'
    if value is False:return 'Off'
    return str(value)

class InputHint:
    def __init__(self,widget,text,on_focus=None):
        self.widget=widget;self.text=text;self.window=None;self.timer=None
        widget.input_description=text
        widget.bind('<Enter>',self.enter,add='+');widget.bind('<FocusIn>',self.focus,add='+')
        widget.bind('<Leave>',self.hide,add='+');widget.bind('<FocusOut>',self.hide,add='+')
        widget.bind('<Destroy>',self.hide,add='+')
        self.on_focus=on_focus
        widget.input_hint=self
    def focus(self,event=None):
        if self.on_focus:self.on_focus(self.text)
    def enter(self,event=None):
        self.focus()
        self.timer=self.widget.after(350,self.show)
    def show(self):
        self.timer=None
        try:
            self.window=tk.Toplevel(self.widget);self.window.wm_overrideredirect(True)
            self.window.geometry(f'+{self.widget.winfo_rootx()+10}+{self.widget.winfo_rooty()+self.widget.winfo_height()+8}')
            tk.Label(self.window,text=self.text,wraplength=420,justify='left',background='#fff7d6',foreground='#172033',
                     relief='solid',borderwidth=1,padx=10,pady=7).pack()
        except tk.TclError:self.window=None
    def hide(self,event=None):
        if self.timer:
            try:self.widget.after_cancel(self.timer)
            except tk.TclError:pass
            self.timer=None
        if self.window:
            try:self.window.destroy()
            except tk.TclError:pass
            self.window=None

def describe(widget,name,default=None,on_focus=None):
    return InputHint(widget,explanation(name)+'\nDefault: '+default_text(default),on_focus)
