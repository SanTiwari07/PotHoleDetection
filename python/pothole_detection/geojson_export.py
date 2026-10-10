"""Convert an IPDS pothole log (CSV) into a GeoJSON FeatureCollection for GIS tools."""
import csv
import json
from typing import Any, Dict, List, Optional, Tuple

# Log columns copied into each feature's `properties` when they have a value.
PROPERTY_COLUMNS = ("date", "time", "frame_id", "pothole_id", "confidence", "bounding_box_area",
                    "aspect_ratio", "peak_jerk", "severity")


def _to_number(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_value(column: str, value: str) -> Any:
    """Numbers stay numbers; text such as 'Medium' or 'pothole_001' is kept as-is."""
    value = value.strip()
    if column in ("date", "time", "pothole_id"):
        return value
    number = _to_number(value)
    return value if number is None else number


def row_to_feature(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Return a GeoJSON Point feature for one log row, or None if it has no usable position."""
    lat, lon = _to_number(row.get("latitude", "")), _to_number(row.get("longitude", ""))
    if lat is None or lon is None:
        return None                      # offline mode leaves the GPS columns empty
    if lat == 0 and lon == 0:
        return None                      # the sensor node writes 0,0 when there is no GPS fix
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    properties = {}
    for column in PROPERTY_COLUMNS:
        value = (row.get(column) or "").strip()
        if value:
            properties[column] = _parse_value(column, value)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},   # GeoJSON order is lon, lat
        "properties": properties,
    }


def csv_to_geojson(csv_path: str) -> Tuple[Dict[str, Any], int]:
    """Read a pothole log and return (FeatureCollection, number of rows skipped)."""
    features: List[Dict[str, Any]] = []
    skipped = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            feature = row_to_feature(row)
            if feature is None:
                skipped += 1
            else:
                features.append(feature)
    return {"type": "FeatureCollection", "features": features}, skipped


def write_geojson(collection: Dict[str, Any], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2)
        f.write("\n")
