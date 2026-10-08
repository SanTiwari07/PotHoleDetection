"""Geometric false-positive filters, as described in the paper, Section 5.4."""
import math
from dataclasses import dataclass
from typing import Dict, Tuple

MAX_AREA_RATIO = 0.25        # Eq. 2: box area / frame area
MAX_ASPECT_RATIO = 3.0       # Eq. 3: box width / height
MAX_STATIONARY_FRAMES = 10   # persistence filter

# How far (as a fraction of frame height) a track centre may move between frames and still
# count as "stationary". The paper does not give a value; 1% of the frame height is ~2.4 px
# at 320x240, above SORT's frame-to-frame jitter but below a pothole's apparent motion.
STATIONARY_TOLERANCE = 0.01


@dataclass
class FilterResult:
    passed: bool
    reason: str               # "" if passed, otherwise which filter rejected the track
    bbox_area: int
    aspect_ratio: float


class GeometricFilter:
    """
    Area, aspect-ratio and persistence filters applied to every tracked box
    before the sensor node is queried.
    """

    def __init__(self, frame_width: int, frame_height: int,
                 max_area_ratio: float = MAX_AREA_RATIO,
                 max_aspect_ratio: float = MAX_ASPECT_RATIO,
                 max_stationary_frames: int = MAX_STATIONARY_FRAMES,
                 stationary_tolerance: float = STATIONARY_TOLERANCE):
        self.frame_area = max(frame_width * frame_height, 1)
        self.max_area_ratio = max_area_ratio
        self.max_aspect_ratio = max_aspect_ratio
        self.max_stationary_frames = max_stationary_frames
        self.stationary_px = stationary_tolerance * frame_height
        self._last_centre: Dict[int, Tuple[float, float]] = {}
        self._stationary_frames: Dict[int, int] = {}

    def update(self, track_id: int, x1: float, y1: float, x2: float, y2: float) -> FilterResult:
        """Call once per frame for each track; returns whether it may trigger a sensor query."""
        w, h = x2 - x1, y2 - y1
        bbox_area = int(w * h)
        aspect_ratio = w / h if h > 0 else 0.0

        # Persistence: count consecutive frames in which the centre barely moved
        centre = ((x1 + x2) / 2, (y1 + y2) / 2)
        prev = self._last_centre.get(track_id)
        if prev is not None and math.dist(prev, centre) < self.stationary_px:
            self._stationary_frames[track_id] = self._stationary_frames.get(track_id, 0) + 1
        else:
            self._stationary_frames[track_id] = 0
        self._last_centre[track_id] = centre

        if bbox_area / self.frame_area > self.max_area_ratio:
            return FilterResult(False, "area", bbox_area, aspect_ratio)
        if aspect_ratio > self.max_aspect_ratio:
            return FilterResult(False, "aspect_ratio", bbox_area, aspect_ratio)
        if self._stationary_frames[track_id] > self.max_stationary_frames:
            return FilterResult(False, "stationary", bbox_area, aspect_ratio)
        return FilterResult(True, "", bbox_area, aspect_ratio)
