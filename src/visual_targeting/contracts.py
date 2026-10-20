from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol
import math
import numpy as np
from numpy.typing import NDArray

class Space(str, Enum):
    SCREEN = "screen_pixels"
    FRAME = "frame_pixels"

@dataclass(frozen=True)
class Point:
    x: int
    y: int
    space: Space = Space.SCREEN

@dataclass(frozen=True)
class Box:
    left: int
    top: int
    width: int
    height: int
    space: Space = Space.SCREEN

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError("box dimensions must be positive")

@dataclass(frozen=True)
class Frame:
    sequence: int
    captured_at: float  # time.monotonic(), seconds in this process's clock domain
    pixels: NDArray[np.uint8]
    bounds: Box  # screen rectangle corresponding exactly to pixels
    format: Literal["gray", "bgr", "bgra"] = "gray"

    def __post_init__(self):
        if self.sequence < 0 or not math.isfinite(self.captured_at) or self.captured_at < 0:
            raise ValueError("invalid frame identity or monotonic timestamp")
        if self.bounds.space != Space.SCREEN:
            raise ValueError("frame bounds must be screen pixels")
        shape = (self.bounds.height, self.bounds.width)
        channels = {"gray": (), "bgr": (3,), "bgra": (4,)}
        if self.format not in channels or self.pixels.shape != shape + channels[self.format]:
            raise ValueError("pixel shape does not match bounds/format")
        if self.pixels.dtype != np.uint8:
            raise ValueError("frames must contain uint8 pixels")
        # Own the buffer: a capture backend may reuse its storage next tick.
        pixels = self.pixels.copy()
        pixels.flags.writeable = False
        object.__setattr__(self, "pixels", pixels)

    def to_screen(self, point: Point) -> Point:
        if point.space != Space.FRAME:
            raise ValueError("expected a frame-local point")
        if not 0 <= point.x < self.bounds.width or not 0 <= point.y < self.bounds.height:
            raise ValueError("point lies outside frame")
        return Point(point.x + self.bounds.left, point.y + self.bounds.top)

@dataclass(frozen=True)
class Detection:
    frame_sequence: int
    captured_at: float
    detected_at: float
    box: Box
    center: Point
    score: float
    label: str = "bobber"

    def __post_init__(self):
        if self.frame_sequence < 0 or not all(math.isfinite(t) for t in (self.captured_at, self.detected_at)) or not 0 <= self.captured_at <= self.detected_at:
            raise ValueError("invalid detection timestamps")
        if self.box.space != self.center.space or not math.isfinite(self.score) or not 0 <= self.score <= 1:
            raise ValueError("inconsistent detection coordinates/score")
        if not (self.box.left <= self.center.x < self.box.left + self.box.width and self.box.top <= self.center.y < self.box.top + self.box.height):
            raise ValueError("center outside detection box")

    def legacy(self):
        return {"box": {k: getattr(self.box, k) for k in ("left", "top", "width", "height")},
                "center": (self.center.x, self.center.y), "value": self.score}

@dataclass(frozen=True)
class Action:
    kind: Literal["move", "click", "press", "key_down", "key_up", "hotkey", "text", "scroll", "release_all"]
    issued_at: float
    point: Point | None = None
    keys: tuple[str, ...] = ()
    button: str = "left"
    amount: int = 0
    duration: float = 0.0
    interval: float = 0.0
    frame_sequence: int | None = None
    captured_at: float | None = None

    def __post_init__(self):
        if self.kind not in ("move", "click", "press", "key_down", "key_up", "hotkey", "text", "scroll", "release_all"):
            raise ValueError("unknown action")
        if not all(math.isfinite(v) and v >= 0 for v in (self.issued_at, self.duration, self.interval)):
            raise ValueError("invalid action timing")
        if self.point is not None and self.point.space != Space.SCREEN:
            raise ValueError("input accepts screen pixels only")
        if self.kind == "move" and self.point is None:
            raise ValueError("move requires a point")
        if (self.frame_sequence is None) != (self.captured_at is None):
            raise ValueError("frame reference requires sequence and capture time")
        if self.frame_sequence is not None and self.frame_sequence < 0:
            raise ValueError("invalid source frame sequence")
        if self.captured_at is not None and (not math.isfinite(self.captured_at) or not 0 <= self.captured_at <= self.issued_at):
            raise ValueError("invalid source frame timestamp")

class FrameSource(Protocol):
    def capture(self) -> Frame: ...

class Detector(Protocol):
    def detect(self, frame: Frame) -> Detection | None: ...

class InputAdapter(Protocol):
    def execute(self, action: Action) -> bool: ...
    def release_all(self) -> None: ...
