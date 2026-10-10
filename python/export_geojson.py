"""Export an IPDS pothole log to GeoJSON (QGIS, geojson.io, uMap, Google My Maps).

    python python/export_geojson.py outputs/logs/pothole_log.csv -o potholes.geojson
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pothole_detection.geojson_export import csv_to_geojson, write_geojson


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", help="Pothole log written by main.py (or the sample log).")
    parser.add_argument("-o", "--output", default=None,
                        help="Output file (default: the CSV path with a .geojson extension).")
    args = parser.parse_args()

    out_path = args.output or os.path.splitext(args.csv)[0] + ".geojson"
    collection, skipped = csv_to_geojson(args.csv)
    write_geojson(collection, out_path)
    print(f"Wrote {len(collection['features'])} potholes to {out_path}")
    if skipped:
        print(f"Skipped {skipped} rows with no GPS position (offline run, or no GPS fix)")


if __name__ == "__main__":
    main()
