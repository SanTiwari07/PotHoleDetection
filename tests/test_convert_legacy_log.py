import csv
import os

import pytest

from convert_legacy_log import COLUMNS, convert_file, convert_id, convert_row, convert_time
from pothole_detection.fusion import calculate_severity

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs", "sample_logs")
LEGACY_LOG = os.path.join(SAMPLE_DIR, "output_legacy.csv")
SAMPLE_LOG = os.path.join(SAMPLE_DIR, "output.csv")

LEGACY_ROW = {"date": "2026-03-20", "time": "01:56 pm", "frame_id": "15", "pothole_id": "pothole_001",
              "confidence": "0.88", "bounding_box_area": "2955", "aspect_ratio": "0.8",
              "peak_jerk": "3.0", "severity": "Medium", "latitude": "18.457497", "longitude": "73.851289"}


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("old, new", [
    ("01:56 pm", "13:56:00"), ("12:05 am", "00:05:00"), ("12:30 pm", "12:30:00"),
    ("11:59 PM", "23:59:00"), ("13:56:00", "13:56:00"),
])
def test_convert_time(old, new):
    assert convert_time(old) == new


def test_convert_id():
    assert convert_id("pothole_001") == "1"
    assert convert_id("pothole_120") == "120"
    assert convert_id("7") == "7"


def test_convert_row_matches_current_writer_format():
    row = convert_row(LEGACY_ROW)
    assert row["time"] == "13:56:00"
    assert row["pothole_id"] == "1"
    assert (row["aspect_ratio"], row["peak_jerk"]) == ("0.80", "3.00")
    assert row["severity"] == f"{calculate_severity(0.88, 3.0):.2f}" == "0.66"
    assert row["latitude"] == "18.457497"


def test_numeric_severity_is_kept():
    row = convert_row({**LEGACY_ROW, "severity": "0.63"})
    assert row["severity"] == "0.63"


def test_conversion_is_idempotent():
    once = convert_row(LEGACY_ROW)
    assert convert_row(once) == once


def test_convert_file_keeps_every_row(tmp_path):
    out = tmp_path / "converted.csv"
    assert convert_file(LEGACY_LOG, str(out)) == 50
    assert _read(str(out)) == _read(SAMPLE_LOG)


def test_sample_log_uses_current_schema():
    rows = _read(SAMPLE_LOG)
    assert len(rows) == len(_read(LEGACY_LOG)) == 50
    with open(SAMPLE_LOG, encoding="utf-8") as f:
        assert f.readline().strip().split(",") == COLUMNS
    for row in rows:
        assert row["pothole_id"].isdigit()
        assert len(row["time"]) == 8 and row["time"].count(":") == 2
        assert 0.0 <= float(row["severity"]) <= 1.0
