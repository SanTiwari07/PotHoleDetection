"""Sensor fusion as described in the paper, Section 6 (Eqs. 4-7)."""
import math
from typing import Sequence

# Jerk saturation threshold J_max (m/s^3), Eq. 7
J_MAX = 20.0

# Minimum peak jerk that counts as a physical impact for the fusion gate (Section 6.1).
# The paper does not give a value; 1.5 m/s^3 sits just below the smallest peak jerk (1.6)
# in outputs/sample_logs/output.csv. Calibrate per vehicle (see docs/DETAIL.md).
JERK_GATE = 1.5

# Fusion weights w1 (vision) and w2 (inertial), Eq. 6
W_VISION = 0.7
W_INERTIAL = 0.3


def accel_magnitude(ax: float, ay: float, az: float) -> float:
    """Returns the magnitude of a 3-axis acceleration sample (m/s^2)."""
    return math.sqrt(ax ** 2 + ay ** 2 + az ** 2)


def peak_jerk(accel_magnitudes: Sequence[float], dt: float = 0.05) -> float:
    """
    Computes peak jerk J_peak = max(|delta a / delta t|) from a burst of samples (Eq. 5).

    Args:
        accel_magnitudes: Acceleration magnitudes (m/s^2) read back-to-back.
        dt: Approximate time between reads (s).

    Returns:
        Peak absolute jerk (m/s^3), or 0.0 if fewer than two samples.
    """
    if len(accel_magnitudes) < 2:
        return 0.0
    return max(abs(accel_magnitudes[i] - accel_magnitudes[i - 1]) / dt
               for i in range(1, len(accel_magnitudes)))


def jerk_confirms_impact(jerk: float, threshold: float = JERK_GATE) -> bool:
    """
    Fusion gate (Section 6.1): a visual detection is only logged if the accelerometer
    also registered an impact. Shadows and manhole covers fail here.
    """
    return jerk >= threshold


def calculate_severity(confidence: float, jerk: float, conf_threshold: float = 0.25) -> float:
    """
    Normalized severity index (Eqs. 6-7):
        J_norm = min(J_peak / J_max, 1.0)
        S      = 0.7 * C_yolo + 0.3 * J_norm
    """
    if confidence < conf_threshold:
        return 0.0

    jerk_norm = min(max(jerk, 0.0) / J_MAX, 1.0)
    severity = W_VISION * confidence + W_INERTIAL * jerk_norm
    return round(severity, 2)
