from pothole_detection.filters import GeometricFilter


def make():
    return GeometricFilter(frame_width=320, frame_height=240)


def test_normal_pothole_passes():
    r = make().update(1, 100, 100, 160, 140)
    assert r.passed and r.bbox_area == 2400 and r.aspect_ratio == 1.5


def test_area_filter_rejects_large_boxes():
    # 200 x 120 = 24000 px > 25% of 76800
    r = make().update(1, 0, 0, 200, 120)
    assert not r.passed and r.reason == "area"


def test_aspect_ratio_filter_rejects_wide_boxes():
    r = make().update(1, 10, 100, 110, 120)   # 100 x 20 -> 5.0
    assert not r.passed and r.reason == "aspect_ratio"


def test_persistence_filter_rejects_stationary_track():
    f = make()
    results = [f.update(7, 100, 100, 140, 130) for _ in range(12)]
    assert all(r.passed for r in results[:11])          # stationary for up to 10 frames is fine
    assert not results[11].passed and results[11].reason == "stationary"


def test_moving_track_is_never_stationary():
    f = make()
    for step in range(30):
        y = 60 + step * 3                               # pothole moving down the frame
        assert f.update(3, 100, y, 140, y + 30).passed
