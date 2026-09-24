# Config file

`config.json` is written by the settings window when you press Save or Start fishing, so you normally don't need to edit it by hand.
Old config files (with `timeInSecsBeforeLogout` / `gracefulExit`) are still read and converted.
Locations set to `null` are asked for when the bot starts. Chances are 0 to 1, ranges are `[min, max]` in seconds unless the name says minutes.

```json
{
  "attachBait": false,
  "numBait": 3,
  "baitIntervalMins": 10,
  "autoLoot": false,
  "imgDir": "../images",
  "splashThresholdWhitePx": 25,
  "castLocation": {"x": 0, "y": 0},
  "poleLocation": null,
  "baitLocation": null,
  "lootLocation": {"x": 0, "y": 0},
  "hearthstoneLocation": null,
  "areaOfInterest": [{"x": 0, "y": 0}, {"x": 0, "y": 0}, {"x": 0, "y": 0}],
  "chatArea": [{"x": 0, "y": 0}, {"x": 0, "y": 0}],
  "healthArea": null,
  "timing": {
    "castDelay": [0.25, 1.0],
    "splashSearchDelay": [1.5, 2.0],
    "bobberClickDelay": [0.5, 1.5],
    "lootDelay": [0.3, 0.8],
    "mouseMoveDuration": [0.2, 0.6],
    "clickJitterPx": 3,
    "castTimeout": 30,
    "distribution": "skewed"
  },
  "humanize": {
    "randomClickChance": 0.05,
    "randomMoveChance": 0.03,
    "moveJump": true,
    "moveSidestep": false,
    "moveMouseWander": true,
    "shortBreakChance": 0.02,
    "shortBreakSecs": [10, 45],
    "missChance": 0.03,
    "fatiguePctPerHour": 15
  },
  "safety": {
    "pauseOnWhisper": true,
    "pauseOnHealthDrop": true,
    "healthDropPct": 10,
    "pauseAfterNoBites": 5,
    "pauseOnMouseTakeover": true,
    "alertSound": true
  },
  "session": {
    "logoutMode": "fixed",
    "logoutAfterMins": 60,
    "logoutRandomMins": [45, 90],
    "logoutAction": "logout",
    "relogin": false,
    "reloginBreakMins": [10, 30],
    "reloginLoadSecs": 30,
    "reloginFirstPerson": true,
    "maxSessions": 0
  },
  "loot": {
    "tracking": true,
    "iconArea": [{"x": 0, "y": 0}, {"x": 0, "y": 0}],
    "slotPitchPx": 0,
    "maxSlots": 4,
    "lootAllSlots": true,
    "dir": "../loot",
    "tesseractCmd": ""
  },
  "overlay": {
    "show": true,
    "corner": "top_right",
    "runningAvgCasts": 20
  }
}
```

`loot.iconArea` is the box around the first loot slot's icon; `slotPitchPx` 0 guesses the slot spacing from the icon size.
`overlay.corner` is `top_left`, `top_right`, `bottom_left` or `bottom_right`.

`chatArea` and `healthArea` are two corners of a box. `distribution` is `skewed`, `gaussian` or `uniform`.
`logoutMode` is `never`, `fixed` or `random`. `logoutAction` is `logout`, `hearth_logout` or `quit`.
