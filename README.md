# wow-fishing-bot
A fishing bot for World of Warcraft created with OpenCV. 

## How it Works
This program captures a portion of the screen and simulates mouse and
keyboard events. No GPU needed since this doesn't use object detection. 
It detects the fishing bobber using [template matching](https://docs.opencv.org/master/d4/dc6/tutorial_py_template_matching.html),
and then clicks on it once there are enough white pixels, which is perceived as a splash. This is possible with these simple 
methods because the fishing bobber has a predicable rotation and the image of the splash is always expected to have brighter 
pixels in grayscale. Fixed things like fishing bait, fishing pole, loot, and cast action are found by user setup.

## How to Use
Install the requirements (`pip install -r src/requirements.txt`), then run `python state_machine.py` from the `src` folder as administrator.
A settings window opens before the bot starts. Everything you set there is saved to `src/config/config.json`
and loaded the next time. Run `python state_machine.py --no-gui` to skip the window and use the saved config as is.

#### Settings window
- **Timing**: time before casting again, the wait before searching for the bobber, the delay on the bobber click
  (reaction time), the delay before looting, mouse move speed, click position jitter and the recast timeout. Every delay is a
  min/max range that is picked at random each time. "Skewed" (the default) works like human reaction times: usually quick,
  sometimes slow. Gaussian and uniform are also available.
- **Humanize**: chance per cast of a random click on the water, chance of a random movement (jump, sidestep and back,
  or mouse wander), chance of a short break, a chance to miss a bite (noticing the splash too late), and fatigue: delays get
  a bit longer each hour of a session and reset after logging out.
- **Safety**: pause and beep when a new whisper shows up in chat, your health drops, several casts in a row get no bite
  (for example if something moved you), or you move the mouse yourself. Deal with it, then press F9 to resume.
- **Log out / Log in**: never log out, log out after a set time, or log out after a random time. When logging out it can
  `/logout`, hearth first then `/logout`, or quit the game. It can log back in after a random break, and stop after a number of sessions.
- **Bobber Images**: see, add and remove your bobber template images, or capture new ones straight from the game
  (hover the bobber, press F8 for each picture, Esc to finish).
- **Locations & Fishing**: pick the screen locations (fishing ability, loot, bait, fishing pole, hearthstone, and the area of interest),
  bait and auto loot settings, and splash sensitivity. Anything left unset is asked for when the bot starts, the same way as before.

About logging back in: after `/logout` the game sits at character select, and the bot presses Enter to log the last character back in.
The bot never types your password, so it can't recover if the game fully disconnects to the login screen or you picked Quit.
Draw your area of interest with the camera level in first person, since that's the view the bot restores after logging in.

#### First-Time Setup
The first thing to do is to gather some template images. These are images of the fishing bobber casted independently.
Multiple images of different orientations and sizes of the fishing bobber is required to improve accuracy. 
Capture them with the **Capture from screen** button in the Bobber Images tab (or `gather-templates.py`), with the game
window at the size you plan to bot at. You can also add images you took with the Snipping Tool.

#### Steps
1. Turn liquid quality to ultra.
1. Find a body of water that is not reflecting the sun.
1. Run the program `state_machine.py` as administrator and set things up in the settings window.
1. If you haven't picked the area of interest yet: look in first person, and start drawing the border to the area of interest. This area is the body of water where the fishing bobber may appear.
 You will draw it by placing at least 3 points that define the shape, and these points are placed when the cursor hasn't 
 moved for 1 second. Leaving the cursor at the ending point will finish the shape.
1. If you haven't picked it yet, point to the casting ability for 1 second.
1. It will start fishing on its own. If there is no loot location and auto loot is off, hold the cursor over the loot on the first catch.
1. Press F9 at any time to pause or resume, and Esc to stop the bot.

Note: Once a splash is detected, there is a click delay (0.5 - 1.5 seconds by default, set in the Timing tab). This is
intended to show human-like reaction to any admin that may suspect you for botting. Also, I wouldn't fish for more
than a couple of hours.

#### If attach bait is on
Tick **Attach bait** in the Locations & Fishing tab and pick the bait and fishing pole locations (or point to them for 1 second when the bot starts).
Bait is reattached on the interval you set (10 minutes by default).

#### Demo Video (Includes Attaching of Fishing Bait to Pole)
<a href="http://www.youtube.com/watch?feature=player_embedded&v=6conRJqjcTE
" target="_blank"><img src="http://img.youtube.com/vi/6conRJqjcTE/0.jpg" 
alt="IMAGE ALT TEXT HERE" width="240" height="180" border="10" /></a>

## Why?
Because World of Warcraft fishing mechanism is pretty simple, this can easily be automated with a program. I decided 
to take this challenge on as an educational opportunity and to practice my skills with OpenCV. If you decide to use this 
program, use at your own risk because I believe it does not abide with their rules, so if you get banned it's not on me.
I think I had an encounter with an admin as I was working and testing this program, but since I was supervising it, I was able to 
take command and show human-like reactions.

**Also, this program is really accurate if you catch decent template images.**

## Todo:
- ~~Find best bob location, continually (not on first frame)~~
- ~~Create documentation: how to use, how it works, etc...~~
- ~~If splash wasn't detected for casting time length, then recast. This means it fails. <- Statistic opportunity here.~~
- ~~Create demo video~~
- Create *better* demo video
- ~~Create programmatic way to capture new templates~~
- ~~Settings GUI~~
