import argparse
import cv2
import os
import signal
import sys
import threading
import glob
import csv
import urllib.request
import json
import time
import numpy as np
from typing import List, Tuple, Dict, Optional, Set

# --- Path Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

# --- Parse .env Manually ---
env_path = os.path.join(ROOT_DIR, '.env')
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip('"\'')

# Fix OpenCV FFmpeg timeout issue with ESP32 streams
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

from pothole_detection.detector import PotholeDetector
from pothole_detection.tracker import PotholeTracker
from pothole_detection.fusion import accel_magnitude, calculate_severity, peak_jerk

# --- CONFIGURATION ---
ASSETS_DIR = os.path.join(ROOT_DIR, 'assets')
OUTPUTS_DIR = os.path.join(ROOT_DIR, 'outputs')

VIDEO_DIR = os.path.join(ASSETS_DIR, 'videos')
MODEL_PATH = os.path.join(ASSETS_DIR, 'models', 'pothole_yolov8.pt')
MODEL_URL = "https://github.com/SanTiwari07/PotHoleDetection/releases/download/v1.0/pothole_yolov8.pt"

# Detection / Tracking Parameters
CONF_THRESHOLD = 0.25
TRACKER_MAX_AGE = 30
TRACKER_MIN_HITS = 3
TRACKER_IOU_THRESH = 0.3

# Visualization
REFERENCE_LINE_RATIO = 0.75
FONT = cv2.FONT_HERSHEY_SIMPLEX


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IPDS: real-time pothole detection, tracking and severity logging.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source", default=None,
                        help="Offline mode: video file path or webcam index (e.g. 0). "
                             "Defaults to the first .mp4 in assets/videos/.")
    parser.add_argument("--live", action="store_true",
                        help="Live mode: stream from the ESP32-CAM and query the ESP32 sensor node.")
    parser.add_argument("--cam-ip", default=None,
                        help="ESP32-CAM IP (live mode). Falls back to ESP32_CAM_IP in .env.")
    parser.add_argument("--sensor-ip", default=None,
                        help="ESP32 sensor node IP (live mode). Falls back to ESP32_SENSOR_IP in .env.")
    parser.add_argument("--model", default=MODEL_PATH,
                        help="Path to YOLOv8 weights. The default weights are downloaded on first run.")
    parser.add_argument("--conf", type=float, default=CONF_THRESHOLD, help="Detection confidence threshold.")
    parser.add_argument("--output-dir", default=OUTPUTS_DIR, help="Where annotated video and CSV log are written.")
    parser.add_argument("--no-display", action="store_true", help="Run headless (no preview window).")
    return parser.parse_args()


def ensure_model(model_path: str) -> None:
    """Downloads the default weights from GitHub Releases if they are missing."""
    if os.path.exists(model_path):
        return
    if os.path.abspath(model_path) != os.path.abspath(MODEL_PATH):
        sys.exit(f"Error: model not found at {model_path}")

    print(f"Model weights not found. Downloading from {MODEL_URL} ...")
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    tmp_path = model_path + ".part"

    def report(blocks: int, block_size: int, total: int) -> None:
        if total > 0:
            pct = min(100, blocks * block_size * 100 // total)
            print(f"\r  > {pct}%", end="", flush=True)

    urllib.request.urlretrieve(MODEL_URL, tmp_path, reporthook=report)
    os.replace(tmp_path, model_path)
    print("\n  > Download complete.")


def get_sensor_burst(url: str, pothole_id: int, burst_count: int = 5) -> Tuple[float, str, str, float, float]:
    """
    EVENT-DRIVEN sensor query for dual ESP32 architecture.
    Queries ESP32 Sensor Node multiple times to compute peak jerk.

    Args:
        url: ESP32 Sensor Node endpoint (http://<IP>/query)
        pothole_id: Unique pothole ID from SORT tracker
        burst_count: Number of sensor reads for jerk calculation

    Returns: (peak_jerk, date_str, time_str, lat, lon)
    """
    accel_magnitudes = []

    # Defaults
    last_date = time.strftime("%Y-%m-%d")
    last_time = time.strftime("%H:%M:%S")
    last_lat = 0.0
    last_lon = 0.0

    print(f"  > Querying ESP32 Sensor Node (Pothole ID: {pothole_id}, Burst: {burst_count})...")

    for _ in range(burst_count):
        try:
            # Query ESP32 Sensor Node with pothole_id parameter
            query_url = f"{url}?pothole_id={pothole_id}"
            with urllib.request.urlopen(query_url, timeout=0.5) as response:
                data = json.loads(response.read().decode())

                # New JSON format from ESP32 Sensor Node:
                # {"pothole_id":42,"timestamp":"2026-02-10T14:23:45","latitude":28.704060,
                #  "longitude":77.102493,"ax":0.12,"ay":-0.05,"az":9.81,
                #  "mpu_ok":true,"gps_ok":true,"rtc_ok":true}

                # Check sensor health
                if not data.get('mpu_ok', False):
                    print(f"    Warning: MPU6050 not responding")

                accel_magnitudes.append(accel_magnitude(data.get('ax', 0.0), data.get('ay', 0.0), data.get('az', 0.0)))

                # Parse ISO8601 timestamp
                timestamp_str = data.get('timestamp', "2000-01-01T00:00:00")
                if "T" in timestamp_str:
                    if timestamp_str.startswith("2000"):
                         # Fallback to local PC time if RTC is unconfigured or battery died
                         last_date = time.strftime("%Y-%m-%d")
                         last_time = time.strftime("%H:%M:%S")
                    else:
                         last_date, last_time = timestamp_str.split("T")

                last_lat = data.get('latitude', 0.0)
                last_lon = data.get('longitude', 0.0)

                # Log GPS status
                if not data.get('gps_ok', False):
                    print(f"    Warning: GPS fix not available")

        except Exception as e:
            print(f"    Sensor read error: {e}")

    jerk = peak_jerk(accel_magnitudes)
    print(f"  > Peak Jerk: {jerk:.2f} m/s³")
    return jerk, last_date, last_time, last_lat, last_lon


def draw_visuals(frame: np.ndarray,
                 tracks: List[List[float]],
                 detections: List[List[float]],
                 logged_ids: Set[int],
                 final_severities: Dict[int, float],
                 ref_y: int,
                 width: int,
                 height: int,
                 track_id_colors: Dict[int, Tuple[int, int, int]]) -> None:
    """
    Draws bounding boxes, labels, and reference line on the frame.
    """
    cv2.line(frame, (0, ref_y), (width, ref_y), (0, 255, 0), 2)

    for track in tracks:
        x1, y1, x2, y2, track_id_float = track
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        track_id = int(track_id_float)

        if track_id not in track_id_colors:
             track_id_colors[track_id] = ((track_id * 123) % 255, (track_id * 53) % 255, (track_id * 211) % 255)
        color = track_id_colors[track_id]

        # Match detection for confidence display
        best_conf = 0.0
        max_iou = 0
        for det in detections:
            dx1, dy1, dx2, dy2, dconf = det
            xx1 = max(x1, dx1); yy1 = max(y1, dy1)
            xx2 = min(x2, dx2); yy2 = min(y2, dy2)
            w = max(0, xx2 - xx1); h = max(0, yy2 - yy1)
            inter = w * h
            union = ((x2-x1)*(y2-y1)) + ((dx2-dx1)*(dy2-dy1)) - inter
            if union > 0 and (inter/union) > max_iou:
                max_iou = inter/union
                best_conf = dconf

        conf_str = f"{best_conf:.2f}" if max_iou > 0.5 else "Trk"

        severity_display = "N/A"
        if track_id in final_severities:
            severity_display = f"{final_severities[track_id]:.2f}"

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"ID:{track_id} Conf:{conf_str} Sev:{severity_display}"
        cv2.putText(frame, label, (x1, y1 - 10), FONT, 0.5, color, 2)


class ThreadedMJPEGStreamReader:
    def __init__(self, url):
        self.url = url
        self.frame = None
        self.frame_seq = 0  # increments per decoded frame so callers can skip duplicates
        self.stopped = False
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True

    def start(self):
        self.thread.start()
        return self

    def update(self):
        print(f"Stream thread started for: {self.url}")
        while not self.stopped:
            try:
                req = urllib.request.Request(self.url)
                req.add_header("Connection", "close")
                with urllib.request.urlopen(req, timeout=5) as stream:
                    bytes_data = bytes()
                    while not self.stopped:
                        bytes_data += stream.read(4096)
                        start = bytes_data.find(b'\xff\xd8')
                        end = bytes_data.find(b'\xff\xd9', start)
                        if start != -1 and end != -1:
                            jpg = bytes_data[start:end + 2]
                            bytes_data = bytes_data[end + 2:]
                            img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if img is not None:
                                with self.lock:
                                    self.frame = img
                                    self.frame_seq += 1
                            # Clear old data if buffer is too large
                            if len(bytes_data) > 1024 * 1024:
                                bytes_data = bytes()
            except Exception as e:
                print(f"Stream thread error: {e}. Reconnecting...")
                time.sleep(1)

    def read(self):
        with self.lock:
            return self.frame

    def read_new(self, last_seq: int):
        """Returns (seq, frame) if a frame newer than last_seq is available, else (last_seq, None)."""
        with self.lock:
            if self.frame is None or self.frame_seq == last_seq:
                return last_seq, None
            return self.frame_seq, self.frame.copy()

    def stop(self):
        self.stopped = True
        self.thread.join(timeout=1)


def resolve_offline_source(source: Optional[str]):
    """Returns a cv2.VideoCapture source: a webcam index, an explicit path, or the first bundled video."""
    if source is not None:
        return int(source) if source.isdigit() else source

    print(f"Searching for videos in: {VIDEO_DIR}")
    video_files = sorted(glob.glob(os.path.join(VIDEO_DIR, '*.mp4')))
    if not video_files:
        sys.exit(f"Error: no video found in '{VIDEO_DIR}'. Pass one with --source path/to/video.mp4")
    return video_files[0]


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt


def main():
    args = parse_args()

    # Treat service stops (SIGTERM) and Ctrl+Break like Ctrl+C so the MP4 and CSV are finalised
    signal.signal(signal.SIGTERM, _raise_interrupt)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _raise_interrupt)
    live = args.live

    # 1. Setup Source
    sensor_url = None
    if live:
        args.cam_ip = args.cam_ip or os.getenv("ESP32_CAM_IP")
        args.sensor_ip = args.sensor_ip or os.getenv("ESP32_SENSOR_IP")
        if not args.cam_ip or not args.sensor_ip:
            sys.exit("Error: live mode needs both device IPs. Set ESP32_CAM_IP / ESP32_SENSOR_IP in .env "
                     "(see .env.example) or pass --cam-ip / --sensor-ip.")
        video_source = f"http://{args.cam_ip}:81/stream"    # Vision Node (port 81)
        sensor_url = f"http://{args.sensor_ip}/query"       # Sensor Node (port 80)
        print(f"--- LIVE MODE ---")
        print(f"Connecting to ESP32-CAM at: {video_source}")
        print(f"Ensure both ESP32 boards are powered on and on the same WiFi as this computer.")
    else:
        video_source = resolve_offline_source(args.source)
        print(f"--- OFFLINE MODE (vision only, no sensor node) ---")
        print(f"Loading video: {video_source}")

    print(f"Loading model from: {args.model}")
    ensure_model(args.model)

    # 2. Initialize Components
    try:
        detector = PotholeDetector(args.model, conf_thres=args.conf)
        tracker = PotholeTracker(max_age=TRACKER_MAX_AGE, min_hits=TRACKER_MIN_HITS, iou_threshold=TRACKER_IOU_THRESH)
    except Exception as e:
        print(f"Failed to initialize components: {e}")
        return

    # 3. Stream Setup
    if live:
        print("Starting threaded stream reader...")
        stream_reader = ThreadedMJPEGStreamReader(video_source).start()

        # Wait for first frame
        timeout = time.time() + 10
        while stream_reader.read() is None:
            if time.time() > timeout:
                print("Error: Timeout waiting for first frame from stream.")
                stream_reader.stop()
                return
            time.sleep(0.1)

        print("  > Stream connected!")
        height, width = stream_reader.read().shape[:2]
        fps = 10.0
    else:
        cap = cv2.VideoCapture(video_source)
        if not cap.isOpened():
            print(f"Error: Could not open source {video_source}")
            return
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0: fps = 10.0

    # 4. Output Setup
    output_video_path = os.path.join(args.output_dir, 'videos', 'output_pothole_detection.mp4')
    log_path = os.path.join(args.output_dir, 'logs', 'pothole_log.csv')
    os.makedirs(os.path.dirname(output_video_path), exist_ok=True)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

    csv_file = open(log_path, 'w', newline='')
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(['date', 'time', 'frame_id', 'pothole_id', 'confidence',
                         'bounding_box_area', 'aspect_ratio', 'peak_jerk', 'severity',
                         'latitude', 'longitude'])

    # State variables
    logged_ids = set()
    track_history = {}
    final_severities = {}
    track_id_colors = {}
    ref_y = int(REFERENCE_LINE_RATIO * height)
    display = not args.no_display

    print(f"Processing started...")
    print("Press 'q' in the video window (or Ctrl+C here) to stop." if display else "Press Ctrl+C to stop.")

    frame_idx = 0
    last_seq = 0
    try:
        while True:
            if live:
                # Only process frames we haven't seen; re-running YOLO on a repeated
                # frame would inflate track_history and trip the "too static" filter.
                last_seq, frame = stream_reader.read_new(last_seq)
                if frame is None:
                    time.sleep(0.005)
                    continue
            else:
                ret, frame = cap.read()
                if not ret:
                    break

            frame_idx += 1

            # 1. Detect
            detections = detector.detect(frame)

            # 2. Track
            tracks = tracker.update(detections)

            # 3. Logic & Logging
            for track in tracks:
                x1, y1, x2, y2, track_id_float = track
                track_id = int(track_id_float)

                # --- DUMPER / SPEED BREAKER REJECTION ---
                if track_id not in track_history: track_history[track_id] = 0
                track_history[track_id] += 1

                bbox_w = x2 - x1
                bbox_h = y2 - y1
                frame_area = width * height
                if frame_area == 0: frame_area = 1 # Safety
                bbox_area = int(bbox_w * bbox_h)

                area_ratio = bbox_area / frame_area
                aspect_ratio = bbox_w / bbox_h if bbox_h > 0 else 0

                if area_ratio > 0.25: continue # Too big
                if aspect_ratio > 3.0: continue # Too wide
                if track_history[track_id] > 10: continue # Too static

                # --- LOGGING CHECK ---
                cy = (y1 + y2) / 2

                if cy >= ref_y and track_id not in logged_ids:
                    # Find best confidence
                    best_conf_log = 0.0
                    max_iou_log = 0
                    for det in detections:
                        dx1, dy1, dx2, dy2, dconf = det
                        xx1 = max(x1, dx1); yy1 = max(y1, dy1); xx2 = min(x2, dx2); yy2 = min(y2, dy2)
                        inter = max(0, xx2 - xx1) * max(0, yy2 - yy1)
                        union = ((x2-x1)*(y2-y1)) + ((dx2-dx1)*(dy2-dy1)) - inter
                        if union > 0 and (inter/union) > max_iou_log:
                            max_iou_log = inter/union
                            best_conf_log = dconf

                    if best_conf_log < args.conf:
                        continue

                    if live:
                        # --- QUERY SENSOR NODE (EVENT-DRIVEN) ---
                        # Only called after SORT + Validity Filter approval
                        jerk, rtc_date, rtc_time, lat, lon = get_sensor_burst(sensor_url, track_id)
                        jerk_str = f"{jerk:.2f}"
                    else:
                        # No sensor node offline: severity is vision-only and sensor columns stay empty
                        jerk, rtc_date, rtc_time, lat, lon = 0.0, time.strftime("%Y-%m-%d"), time.strftime("%H:%M:%S"), "", ""
                        jerk_str = ""

                    severity_val = calculate_severity(best_conf_log, jerk, conf_threshold=args.conf)

                    csv_writer.writerow([
                        rtc_date, rtc_time, frame_idx, track_id, f"{best_conf_log:.2f}",
                        bbox_area, f"{aspect_ratio:.2f}", jerk_str, f"{severity_val:.2f}",
                        lat, lon
                    ])
                    csv_file.flush()

                    logged_ids.add(track_id)
                    final_severities[track_id] = severity_val

            # 4. Visualize
            draw_visuals(frame, tracks, detections, logged_ids, final_severities, ref_y, width, height, track_id_colors)

            total_potholes = tracker.get_total_count()
            cv2.putText(frame, f"Total Unique Potholes: {total_potholes}", (10, 20), FONT, 0.5, (0, 0, 255), 1)

            out.write(frame)

            # 5. Display (Try-Except to avoid crash during data collection on headless builds)
            if display:
                try:
                    display_frame = cv2.resize(frame, (width * 2, height * 2)) if live else frame
                    cv2.imshow('Pothole Detection', display_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                except cv2.error as e:
                    print(f"Display unavailable ({e}). Continuing headless; use --no-display to silence this.")
                    display = False
    except KeyboardInterrupt:
        print("\nInterrupted, saving outputs...")

    if not live:
        cap.release()
    else:
        stream_reader.stop()

    out.release()
    csv_file.close()
    if not args.no_display:
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass  # opencv-python-headless has no GUI
    print(f"Processing complete. {len(logged_ids)} potholes logged.")
    print(f"  > Annotated video: {output_video_path}")
    print(f"  > CSV log:         {log_path}")


if __name__ == "__main__":
    main()
