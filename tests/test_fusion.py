import pytest

from pothole_detection.fusion import accel_magnitude, calculate_severity, peak_jerk


def test_accel_magnitude():
    assert accel_magnitude(3.0, 4.0, 0.0) == pytest.approx(5.0)


def test_peak_jerk_needs_two_samples():
    assert peak_jerk([]) == 0.0
    assert peak_jerk([9.8]) == 0.0


def test_peak_jerk_picks_largest_change():
    # Changes of 0.1 and 1.0 m/s^2 over 0.05 s -> 2 and 20 m/s^3
    assert peak_jerk([9.8, 9.9, 10.9], dt=0.05) == pytest.approx(20.0)


def test_severity_below_threshold_is_zero():
    assert calculate_severity(0.2, 15.0, conf_threshold=0.25) == 0.0


def test_severity_vision_only():
    assert calculate_severity(0.9, 0.0) == pytest.approx(0.63)


def test_severity_jerk_is_clamped():
    # jerk_norm saturates at 1.0 for anything >= J_MAX
    assert calculate_severity(1.0, 100.0) == pytest.approx(1.0)
