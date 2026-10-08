import numpy as np

from pothole_detection.tracker import PotholeTracker


def test_tracker_keeps_id_for_moving_box():
    tracker = PotholeTracker(max_age=5, min_hits=1, iou_threshold=0.3)
    ids = set()
    for step in range(5):
        y = 100 + step * 5  # pothole moving down the frame as the vehicle advances
        tracks = tracker.update(np.array([[100, y, 160, y + 40, 0.9]]))
        ids.update(int(t[4]) for t in tracks)
    assert len(ids) == 1
    assert tracker.get_total_count() == 1


def test_tracker_handles_empty_frames():
    tracker = PotholeTracker()
    tracks = tracker.update(np.empty((0, 5)))
    assert len(tracks) == 0
