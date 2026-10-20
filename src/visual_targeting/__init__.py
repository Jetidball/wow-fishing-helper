"""Desktop-independent visual targeting contracts and CPU detection."""
from .contracts import Action, Box, Detection, Frame, Point, Space
from .detector import TemplateDetector
__all__ = ["Action", "Box", "Detection", "Frame", "Point", "Space", "TemplateDetector"]
