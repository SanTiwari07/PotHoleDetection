import json
import os

from pothole_detection.geojson_export import csv_to_geojson, row_to_feature, write_geojson

SAMPLE_LOG = os.path.join(os.path.dirname(__file__), "..", "outputs", "sample_logs", "output.csv")

HEADER = ("date,time,frame_id,pothole_id,confidence,bounding_box_area,aspect_ratio,"
          "peak_jerk,severity,latitude,longitude\n")


def _write_csv(tmp_path, *rows):
    path = tmp_path / "log.csv"
    path.write_text(HEADER + "".join(r + "\n" for r in rows))
    return str(path)


def test_coordinates_are_lon_lat():
    feature = row_to_feature({"latitude": "18.4575", "longitude": "73.8513"})
    assert feature["geometry"] == {"type": "Point", "coordinates": [73.8513, 18.4575]}


def test_numeric_severity_stays_a_number():
    row = {"latitude": "18.4", "longitude": "73.8", "severity": "0.63", "peak_jerk": "4.20",
           "pothole_id": "7"}
    props = row_to_feature(row)["properties"]
    assert props["severity"] == 0.63
    assert props["peak_jerk"] == 4.2
    assert props["pothole_id"] == "7"        # IDs are labels, not quantities


def test_text_severity_band_is_kept():
    row = {"latitude": "18.4", "longitude": "73.8", "severity": "Medium", "pothole_id": "pothole_001"}
    props = row_to_feature(row)["properties"]
    assert props["severity"] == "Medium"
    assert props["pothole_id"] == "pothole_001"


def test_empty_columns_are_omitted():
    props = row_to_feature({"latitude": "18.4", "longitude": "73.8", "peak_jerk": ""})["properties"]
    assert "peak_jerk" not in props


def test_rows_without_a_position_are_skipped():
    assert row_to_feature({"latitude": "", "longitude": ""}) is None          # offline mode
    assert row_to_feature({"latitude": "0", "longitude": "0"}) is None        # no GPS fix
    assert row_to_feature({"latitude": "abc", "longitude": "73.8"}) is None
    assert row_to_feature({"latitude": "95", "longitude": "73.8"}) is None    # out of range


def test_csv_to_geojson_counts_skipped_rows(tmp_path):
    path = _write_csv(
        tmp_path,
        "2026-03-20,13:56:00,15,1,0.88,2955,0.80,3.00,0.65,18.457497,73.851289",
        "2026-03-20,13:57:00,30,2,0.85,5828,1.42,7.80,0.80,0,0",
        "2026-03-20,13:58:00,45,3,0.70,1200,1.10,,0.49,,",
    )
    collection, skipped = csv_to_geojson(path)
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 1
    assert skipped == 2


def test_sample_log_converts():
    collection, skipped = csv_to_geojson(SAMPLE_LOG)
    assert len(collection["features"]) + skipped == 50
    assert collection["features"]
    lon, lat = collection["features"][0]["geometry"]["coordinates"]
    assert 73 < lon < 74 and 18 < lat < 19      # Pune, per the README


def test_write_geojson_round_trips(tmp_path):
    collection, _ = csv_to_geojson(SAMPLE_LOG)
    out = tmp_path / "out.geojson"
    write_geojson(collection, str(out))
    assert json.loads(out.read_text()) == collection
