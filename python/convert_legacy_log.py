"""Convert an older IPDS pothole log to the schema python/main.py writes today.

    python python/convert_legacy_log.py outputs/sample_logs/output_legacy.csv -o outputs/sample_logs/output.csv

Per-row rules (rows that are already in the current format are copied unchanged):

* time        '01:56 pm'     -> '13:56:00'  (the old log has no seconds, so they are set to 00)
* pothole_id  'pothole_001'  -> '1'
* severity    'Low'/'Medium'/'High' -> the 0-1 score main.py computes from the row's own
              confidence and peak_jerk (Eqs. 6-7, see pothole_detection/fusion.py)
* confidence, aspect_ratio, peak_jerk -> two decimals, as main.py writes them
"""
import argparse
import csv
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pothole_detection.fusion import calculate_severity

COLUMNS = ["date", "time", "frame_id", "pothole_id", "confidence", "bounding_box_area",
           "aspect_ratio", "peak_jerk", "severity", "latitude", "longitude"]

_LEGACY_ID = re.compile(r"^pothole_0*(\d+)$")


def _two_decimals(value: str) -> str:
    value = value.strip()
    return f"{float(value):.2f}" if value else ""


def convert_time(value: str) -> str:
    """'01:56 pm' -> '13:56:00'; a value that is already HH:MM:SS is returned as is."""
    value = value.strip()
    for fmt in ("%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(value.upper(), fmt).strftime("%H:%M:%S")
        except ValueError:
            pass
    return value


def convert_id(value: str) -> str:
    """'pothole_001' -> '1'; numeric IDs are returned as is."""
    match = _LEGACY_ID.match(value.strip())
    return match.group(1) if match else value.strip()


def convert_row(row: Dict[str, str], conf_threshold: float = 0.25) -> Dict[str, str]:
    """Return one log row in the current schema."""
    out = {col: (row.get(col) or "").strip() for col in COLUMNS}
    out["time"] = convert_time(out["time"])
    out["pothole_id"] = convert_id(out["pothole_id"])
    for col in ("confidence", "aspect_ratio", "peak_jerk"):
        out[col] = _two_decimals(out[col])
    if not _is_number(out["severity"]):     # a text band; numeric scores are kept
        jerk = float(out["peak_jerk"]) if out["peak_jerk"] else 0.0
        out["severity"] = f"{calculate_severity(float(out['confidence']), jerk, conf_threshold):.2f}"
    return out


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def convert_file(src: str, dst: str) -> int:
    """Convert the CSV at `src` into `dst`; returns the number of rows written."""
    with open(src, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{src} is missing columns: {', '.join(missing)}")
        rows: List[Dict[str, str]] = [convert_row(r) for r in reader]
    with open(dst, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", help="Old-format pothole log (Low/Medium/High severity, pothole_001 IDs).")
    parser.add_argument("-o", "--output", required=True, help="Where to write the converted log.")
    args = parser.parse_args(argv)
    count = convert_file(args.csv, args.output)
    print(f"Wrote {count} rows to {args.output}")


if __name__ == "__main__":
    main()
