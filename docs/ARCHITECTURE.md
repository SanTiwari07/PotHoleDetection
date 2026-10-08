# System Architecture

IPDS is split across three physical tiers: two ESP32 boards that acquire data, a Python processing hub (laptop or edge computer) that runs the AI, and the output files it writes.

```text
┌──────────────────┐   WiFi · MJPEG over HTTP (:81/stream)   ┌──────────────────────────────┐
│  ESP32-CAM       │ ──────────────────────────────────────► │  Python processing hub       │
│  vision node     │                                         │  python/main.py              │
│  OV2640, QVGA    │                                         │                              │
└──────────────────┘                                         │  YOLOv8m → SORT → filters    │
                                                             │        │ crosses 75% line    │
┌──────────────────┐   WiFi · HTTP GET /query?pothole_id=N   │        ▼                     │
│  ESP32 DevKit    │ ◄────────────────────────────────────── │  sensor burst (5 queries)    │
│  sensor node     │ ──────────────── JSON ────────────────► │        │                     │
│  MPU6050, DS3231,│                                         │        ▼                     │
│  NEO-6M GPS      │                                         │  peak jerk → severity → CSV  │
└──────────────────┘                                         │  annotated MP4               │
                                                             └──────────────────────────────┘
```

All three devices must be on the same 2.4 GHz WiFi network (a phone hotspot works).

## Why two ESP32 boards?

On the ESP32-CAM, `esp_camera_fb_get()` blocks while a frame is captured and JPEG-encoded. Doing I²C sensor reads on the same board competes with that loop and causes dropped and stuttering frames. The camera board therefore only streams video, and a second ESP32 handles every sensor. It reads them only when the hub asks, so no clock synchronisation between video and sensors is needed.

## Components

| Tier | Component | Code | Role |
|---|---|---|---|
| Acquisition | ESP32-CAM (AI-Thinker) | [`ESP_32_Code/esp_32_cam_final/`](../ESP_32_Code/esp_32_cam_final/) | MJPEG stream on port 81, `/health` on port 80 |
| Acquisition | ESP32 DevKit + MPU6050 + DS3231 + NEO-6M | [`ESP_32_Code/esp_32_final/`](../ESP_32_Code/esp_32_final/) | REST endpoint `/query` returning one JSON sensor snapshot; status page `/` |
| Processing | Detector | [`python/pothole_detection/detector.py`](../python/pothole_detection/detector.py) | YOLOv8m inference via Ultralytics |
| Processing | Tracker | [`tracker.py`](../python/pothole_detection/tracker.py), [`sort.py`](../python/pothole_detection/sort.py) | SORT (Kalman filter + Hungarian matching) for persistent IDs |
| Processing | Fusion | [`fusion.py`](../python/pothole_detection/fusion.py) | Peak jerk and severity score |
| Processing | Orchestrator | [`python/main.py`](../python/main.py) | Stream reading, filters, trigger line, sensor query, logging |
| Output | CSV log + MP4 | `outputs/logs/`, `outputs/videos/` | One row per logged pothole; annotated video |

## Data flow for one pothole

1. The ESP32-CAM streams 320×240 JPEG frames. A background thread on the hub decodes them, and the main loop only processes frames it hasn't seen yet.
2. YOLOv8m detects potholes with confidence ≥ 0.25.
3. SORT assigns each pothole a persistent track ID (`max_age=30`, `min_hits=3`, IoU threshold 0.3).
4. Geometric filters skip tracks whose box covers more than 25% of the frame, whose width/height ratio is above 3.0, or which have been tracked for more than 10 frames.
5. When a track's centre crosses the reference line at 75% of the frame height (and it hasn't been logged yet), the hub sends 5 `GET /query?pothole_id=N` requests to the sensor node.
6. The sensor node answers each request with acceleration (m/s²), RTC timestamp, GPS position and health flags.
7. The hub computes peak jerk from the 5 samples, then a severity score, appends a CSV row and marks the track as logged so it is never logged twice.

See [DETAIL.md](DETAIL.md) for the formulas, JSON schema and CSV schema.

## Communication

| Link | Protocol |
|---|---|
| Camera → hub | HTTP `multipart/x-mixed-replace` MJPEG stream, port 81 |
| Hub → sensor node | HTTP GET, port 80, JSON response, 0.5 s timeout per request |
| Sensor node ↔ MPU6050, DS3231 | I²C, GPIO21 (SDA) / GPIO22 (SCL) |
| Sensor node ↔ NEO-6M | UART2, GPIO16 (RX2) / GPIO17 (TX2), 9600 baud |

## Offline mode

Without hardware, `python python/main.py --source video.mp4` runs the same detection, tracking, filtering and trigger logic on a recorded video. No sensor node is queried, so the jerk, latitude and longitude columns are left empty and severity uses the vision term only.

## Extending the system

Because the sensor node is a plain HTTP endpoint, more cameras could each stream to the hub and query the same sensor node. A different camera only needs a different stream URL.
