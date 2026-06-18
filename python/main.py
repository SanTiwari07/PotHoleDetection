import cv2
import os
import threading
import glob
import csv
import urllib.request
import json
import time
import math
import numpy as np
from typing import List, Tuple, Dict, Set

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

# --- CONFIGURATION ---
LIVE_MODE = True  # Set to True to use ESP32 devices, False for video file

# IMPORTANT: UPDATE THESE IP ADDRESSES TO MATCH YOUR ESP32 DEVICES
# After uploading firmware, check the Arduino Serial Monitor (115200 baud) 
# to get the correct IP addresses for both devices.
# Both ESP32 devices must be on the same WiFi network as this computer.

# DUAL ESP32 ARCHITECTURE CONFIGURATION
# Configure ESP32 IPs in the .env file in the project root
ESP32_CAM_IP = os.getenv("ESP32_CAM_IP", "10.83.168.54")
ESP32_SENSOR_IP = os.getenv("ESP32_SENSOR_IP", "10.83.168.215")

ESP32_STREAM_URL = f"http://{ESP32_CAM_IP}:81/stream"  # Vision Node (port 81)
ESP32_SENSOR_URL = f"http://{ESP32_SENSOR_IP}/query"    # Sensor Node (port 80)

ASSETS_DIR = os.path.join(ROOT_DIR, 'assets')
OUTPUTS_DIR = os.path.join(ROOT_DIR, 'outputs')

VIDEO_DIR = os.path.join(ASSETS_DIR, 'videos')
MODEL_PATH = os.path.join(ASSETS_DIR, 'models', 'pothole_yolov8.pt')
OUTPUT_VIDEO_PATH = os.path.join(OUTPUTS_DIR, 'videos', 'output_pothole_detection.mp4')
LOG_PATH = os.path.join(OUTPUTS_DIR, 'logs', 'pothole_log.csv')

# Detection / Tracking Parameters
CONF_THRESHOLD = 0.25
TRACKER_MAX_AGE = 30
TRACKER_MIN_HITS = 3
TRACKER_IOU_THRESH = 0.3

# Physics / Sensor Parameters
J_MIN = 0.0
J_MAX = 20.0

# Visualization
REFERENCE_LINE_RATIO = 0.75
FONT = cv2.FONT_HERSHEY_SIMPLEX


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
            if LIVE_MODE:
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
                    
                    ax = data.get('ax', 0.0)
                    ay = data.get('ay', 0.0)
                    az = data.get('az', 0.0)
                    accel_magnitudes.append(math.sqrt(ax**2 + ay**2 + az**2))
                    
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
                    
            else:
                # Simulated Data
                accel_magnitudes.append(9.8 + (0.5 * _))
                time.sleep(0.05)
            
        except Exception as e:
            print(f"    Sensor read error: {e}")
            pass

    # Compute Jerk (rate of change of acceleration)
    if len(accel_magnitudes) < 2:
        peak_jerk = 0.0
    else:
        jerks = []
        dt = 0.05  # Approximate dt between reads
        for i in range(1, len(accel_magnitudes)):
            j = abs(accel_magnitudes[i] - accel_magnitudes[i-1]) / dt
            jerks.append(j)
        peak_jerk = max(jerks) if jerks else 0.0

    print(f"  > Peak Jerk: {peak_jerk:.2f} m/s³")
    return peak_jerk, last_date, last_time, last_lat, last_lon


def calculate_severity(confidence: float, jerk: float) -> float:
    """
    Calculates severity based on ML confidence (Primary) and Jerk (Secondary).
    Formula: 0.7 * confidence + 0.3 * (jerk_norm ^ 2)
    """
    jerk_norm = (jerk - J_MIN) / (J_MAX - J_MIN)
    jerk_norm = max(0.0, min(1.0, jerk_norm))
    
    if confidence < CONF_THRESHOLD:
        return 0.0
        
    severity = 0.7 * confidence + 0.3 * (jerk_norm ** 2)
    return round(severity, 2)


def draw_visuals(frame: cv2.VideoWriter, 
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


def main():
    # 1. Setup Source
    video_source = None
    
    if LIVE_MODE:
        print(f"--- LIVE MODE ENABLED ---")
        print(f"CONNECTING TO ESP32 AT: {ESP32_STREAM_URL}")
        print(f"Ensure your ESP32 is powered on and connected to the same WiFi.")
        print(f"Update 'ESP32_IP' in the script if connection fails.")
        video_source = ESP32_STREAM_URL
    else:
        print(f"--- FILE MODE ---")
        print(f"Searching for videos in: {VIDEO_DIR}")
        video_search_pattern = os.path.join(VIDEO_DIR, '*.mp4')
        video_files = glob.glob(video_search_pattern)
        if not video_files:
            print(f"Error: No video file found in '{VIDEO_DIR}' directory.")
            return
        video_source = video_files[0]
        print(f"Loading video: {video_source}")
    
    print(f"Loading model from: {MODEL_PATH}")

    # 2. Initialize Components
    try:
        detector = PotholeDetector(MODEL_PATH, conf_thres=CONF_THRESHOLD)
        tracker = PotholeTracker(max_age=TRACKER_MAX_AGE, min_hits=TRACKER_MIN_HITS, iou_threshold=TRACKER_IOU_THRESH)
    except Exception as e:
        print(f"Failed to initialize components: {e}")
        return

    # 3. Stream Setup
    if LIVE_MODE:
        class ThreadedMJPEGStreamReader:
            def __init__(self, url):
                self.url = url
                self.frame = None
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
                                    # Clear old data if buffer is too large
                                    if len(bytes_data) > 1024 * 1024:
                                        bytes_data = bytes()
                    except Exception as e:
                        print(f"Stream thread error: {e}. Reconnecting...")
                        time.sleep(1)

            def read(self):
                with self.lock:
                    return self.frame

            def stop(self):
                self.stopped = True
                self.thread.join(timeout=1)

        print("Starting threaded stream reader...")
        stream_reader = ThreadedMJPEGStreamReader(video_source).start()
        
        # Wait for first frame
        timeout = time.time() + 10
        while stream_reader.read() is None:
            if time.time() > timeout:
                print("Error: Timeout waiting for first frame from stream.")
                return
            time.sleep(0.1)
        
        print("  > Stream connected!")
        width, height = 320, 240 # Default QVGA
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
    os.makedirs(os.path.dirname(OUTPUT_VIDEO_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(OUTPUT_VIDEO_PATH, fourcc, fps, (width, height))
    
    csv_file = open(LOG_PATH, 'w', newline='')
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
    
    print(f"Processing started...")
    print("Press 'q' to stop.")

    frame_idx = 0
    while True:
        if LIVE_MODE:
            frame = stream_reader.read()
            if frame is None:
                time.sleep(0.01)
                continue
        else:
            ret, frame = cap.read()
            if not ret:
                break

        
        
        # Initialize actual frame dimensions once frame is loaded
        if width == 800 and height == 600 and frame is not None:
             height, width = frame.shape[:2]
             ref_y = int(REFERENCE_LINE_RATIO * height)
             out = cv2.VideoWriter(OUTPUT_VIDEO_PATH, fourcc, fps, (width, height))
             
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
            bbox_area = bbox_w * bbox_h
            
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
                
                if best_conf_log < CONF_THRESHOLD:
                    continue

                # --- QUERY SENSOR NODE (EVENT-DRIVEN) ---
                # Only called after SORT + Validity Filter approval
                peak_jerk, rtc_date, rtc_time, lat, lon = get_sensor_burst(ESP32_SENSOR_URL, track_id)
                
                severity_val = calculate_severity(best_conf_log, peak_jerk)
                
                csv_writer.writerow([
                    rtc_date, rtc_time, frame_idx, track_id, f"{best_conf_log:.2f}",
                    bbox_area, f"{aspect_ratio:.2f}", f"{peak_jerk:.2f}", f"{severity_val:.2f}",
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
        
        # 4. Display (Optional / Try-Except to avoid crash during data collection)
        try:
            display_frame = cv2.resize(frame, (width * 2, height * 2))
            cv2.imshow('Pothole Detection', display_frame) # Enable display
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        except cv2.error as e:
            # Fallback if display fails but continue processing/saving
            if "not implemented" in str(e):
                # Only warn once or just continue
                pass
            else:
                print(f"Display error: {e}")
            
            # Allow 'q' to work via console if possible, or just continue
            # For now, we skip waitKey if imshow fails to avoid potential blocking
            pass

            
    if not LIVE_MODE:
        cap.release()
    else:
        stream_reader.stop()
        
    out.release()
    csv_file.close()
    cv2.destroyAllWindows()
    print("Processing complete.")


if __name__ == "__main__":
    main()
