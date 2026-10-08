import math
from typing import Sequence

# Jerk normalisation range (m/s^3)
J_MIN = 0.0
J_MAX = 20.0


def accel_magnitude(ax: float, ay: float, az: float) -> float:
    """Returns the magnitude of a 3-axis acceleration sample (m/s^2)."""
    return math.sqrt(ax ** 2 + ay ** 2 + az ** 2)


def peak_jerk(accel_magnitudes: Sequence[float], dt: float = 0.05) -> float:
    """
    Computes peak jerk (rate of change of acceleration) from a burst of samples.

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


def calculate_severity(confidence: float, jerk: float, conf_threshold: float = 0.25) -> float:
    """
    Calculates severity based on ML confidence (Primary) and Jerk (Secondary).
    Formula: 0.7 * confidence + 0.3 * (jerk_norm ^ 2)
    """
    jerk_norm = (jerk - J_MIN) / (J_MAX - J_MIN)
    jerk_norm = max(0.0, min(1.0, jerk_norm))

    if confidence < conf_threshold:
        return 0.0

    severity = 0.7 * confidence + 0.3 * (jerk_norm ** 2)
    return round(severity, 2)
