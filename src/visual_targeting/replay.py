"""Ordered replay source: shares the frame/detector contract, never opens a desktop adapter."""
import time
import cv2 as cv
from .contracts import Box, Frame

def frames(paths, origin=(0, 0), clock=time.monotonic):
    previous = -1.0
    for sequence, path in enumerate(paths):
        image = cv.imread(str(path), cv.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"unreadable frame: {path}")
        timestamp = clock()
        if timestamp < previous:
            raise ValueError("replay clock moved backwards")
        previous = timestamp
        yield path, Frame(sequence, timestamp, image, Box(*origin, image.shape[1], image.shape[0]))
