# Intelligent Pothole Detection System (IPDS)

> **Real-Time Pothole Detection Based on Vision-Dominant Sensor Fusion and Dual ESP32 Architecture**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![YOLOv8](https://img.shields.io/badge/model-YOLOv8m-orange.svg)](https://ultralytics.com)
[![Zenodo](https://img.shields.io/badge/Zenodo-10.5281%2Fzenodo.20760578-blue.svg)](https://zenodo.org/records/20760578)

An embedded IoT research system that detects potholes in real-time using a dual ESP32 hardware architecture, a custom-trained YOLOv8m vision model, and multi-sensor data fusion (camera, GPS, RTC, and MPU6050 accelerometer). The system produces geo-tagged severity logs and annotated video suitable for road-maintenance prioritization.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Research Motivation](#2-research-motivation)
3. [System Architecture](#3-system-architecture)
4. [Hardware Components](#4-hardware-components)
5. [Software Stack](#5-software-stack)
6. [Dataset Information](#6-dataset-information)
7. [Model Weights](#7-model-weights)
8. [Validation Metrics](#8-validation-metrics)
9. [Installation Guide](#9-installation-guide)
10. [Usage Instructions](#10-usage-instructions)
11. [Sample Field-Test Data](#11-sample-field-test-data)
12. [Zenodo](#12-zenodo)
13. [Sample Results](#13-sample-results)
14. [Repository Structure](#14-repository-structure)
15. [Future Scope](#15-future-scope)
16. [Citation](#16-citation)
17. [Authors](#17-authors)
18. [License](#18-license)

---

## 1. Project Overview

The **Intelligent Pothole Detection System (IPDS)** automates road quality assessment by fusing computer-vision outputs with physical vibration data collected during a vehicle traverse. The system:

- Streams live video from a **WiFi-enabled ESP32-CAM** to a Python processing hub.
- Runs **YOLOv8m** frame-by-frame to detect potholes with bounding-box precision.
- Applies a **SORT (Simple Online and Realtime Tracking)** algorithm to maintain unique IDs across frames and prevent duplicate counting.
- Fires an HTTP query to a second **ESP32 Sensor Node** exactly when the vehicle axle crosses a detected hazard, collecting peak-jerk (m/s²), GPS coordinates, and RTC timestamp simultaneously.
- Computes a **combined Severity Score** (Low / Medium / High) by fusing YOLO confidence, bounding-box area, aspect ratio, and accelerometer jerk.
- Writes a structured **CSV field-test log** and an **annotated MP4** for every detection session.

---

## 2. Research Motivation

Poor road infrastructure causes an estimated **50 million road accidents** per year globally, a significant fraction attributable to potholes and surface defects. Traditional inspection relies on slow citizen-reporting pipelines or periodic surveys by municipal workers, leaving hazards unaddressed for weeks.

This work proposes a low-cost, vehicle-mountable system that:
- Eliminates manual inspection with automated computer vision.
- Produces quantitative severity data rather than binary "pothole / no pothole" labels.
- Requires only commodity microcontrollers (ESP32, ~$5 each) and a standard laptop/edge computer.
- Generates structured, Firebase-ready output compatible with existing GIS pipelines.

---

## 3. System Architecture

The system is built on an **Event-Driven Dual ESP32 Architecture** that cleanly separates the blocking concerns of frame capture and sensor polling.

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Hardware Layer                                  │
│                                                                      │
│  ┌──────────────────┐   WiFi/MJPEG   ┌──────────────────────────┐  │
│  │  ESP32-CAM       │ ─────────────► │                          │  │
│  │  (Vision Node)   │                │   Python Processing Hub   │  │
│  │  OV2640 Camera   │                │                          │  │
│  └──────────────────┘                │   ┌──────────────────┐   │  │
│                                      │   │ YOLOv8m Detector │   │  │
│  ┌──────────────────┐   WiFi/HTTP    │   │ SORT Tracker     │   │  │
│  │  ESP32 Dev Board │ ◄────────────► │   │ Severity Fuser   │   │  │
│  │  (Sensor Node)   │                │   │ CSV Logger       │   │  │
│  │  MPU6050  GPS    │                │   │ Video Annotator  │   │  │
│  │  NEO-6M   DS3231 │                │   └──────────────────┘   │  │
│  └──────────────────┘                └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow (Step-by-Step)

| Step | Component | Action |
|------|-----------|--------|
| 1 | ESP32-CAM | Streams 320×240 MJPEG frames over WiFi |
| 2 | Python Hub | Receives frame → passes to YOLOv8m → updates SORT tracker |
| 3 | Python Hub | Checks if tracked pothole crosses the vehicle-bumper reference line |
| 4 | Python Hub | Issues HTTP GET to Sensor Node: `http://<IP>/query?pothole_id=N` |
| 5 | ESP32 Sensor | Reads MPU6050 via I²C, NEO-6M via UART, DS3231 via I²C → returns JSON |
| 6 | Python Hub | Fuses confidence + bounding-box metrics + peak jerk → computes severity |
| 7 | Python Hub | Appends row to CSV; paints bounding box + label on video frame |

### Design Rationale — Dual ESP32

Running I²C sensor reads on the ESP32-CAM blocks the `esp_camera_fb_get()` call, causing severe frame-rate drops. Offloading all sensor I/O to a dedicated sensor ESP32 resolves this concurrency issue while keeping both nodes inexpensive.

---

## 4. Hardware Components

| Component | Role | Notes |
|-----------|------|-------|
| **ESP32-CAM** (AI-Thinker) | Vision Node — continuous MJPEG stream | OV2640 camera module onboard |
| **ESP32 Dev Board** | Sensor Node — I²C/UART data hub | Queries sensors only on event |
| **MPU6050** | 6-axis accelerometer + gyroscope | Measures peak jerk (m/s²) during traverse |
| **NEO-6M GPS** | GNSS receiver | Provides WGS-84 latitude/longitude |
| **DS3231 RTC** | Real-time clock | Hardware-accurate date/time stamp |
| **Processing Hub** | YOLOv8 inference | Laptop or edge device (e.g., NVIDIA Jetson Nano) |

Wiring schematics and KiCad PCB files are located in [`KiCad/`](KiCad/) and interactive HTML diagrams are in [`Diagrams/`](Diagrams/).

---

## 5. Software Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Object Detection** | Ultralytics YOLOv8m | ≥ 8.0 |
| **Multi-Object Tracking** | SORT (Kalman + Hungarian) | FilterPy-based |
| **Image Processing** | OpenCV | ≥ 4.8 |
| **Numerical Computing** | NumPy, SciPy | latest |
| **Firmware** | C++ / Arduino Framework | ESP32 Arduino Core ≥ 2.0 |
| **Environment Management** | python-dotenv | latest |
| **Simulation** | PotHoleSimu (custom) | — |

Full Python dependencies are in [`requirements.txt`](requirements.txt).

---

## 6. Dataset Information

### Training Dataset

The YOLOv8m model was fine-tuned on the publicly available **Kaggle Pothole Image Dataset**:

- **Source:** [Pothole Image Dataset — Kaggle](https://www.kaggle.com/datasets/atulyakumar98/pothole-detection-dataset)
- **Classes:** 1 (pothole)
- **Annotation format:** YOLO `.txt` (normalised `[class cx cy w h]`)
- **Split:** Standard train / validation split (≈ 80 / 20)
- **Augmentation:** Applied via Ultralytics built-in pipeline (mosaic, flip, HSV jitter, rotation)

### Model Architecture

| Parameter | Value |
|-----------|-------|
| Base model | YOLOv8m (medium) |
| Input resolution | 640 × 640 |
| Epochs | 100 |
| Optimizer | AdamW |
| Device | GPU (CUDA) / CPU |

---

## 7. Model Weights

The trained model weights (`pothole_yolov8.pt`) are distributed as a **GitHub Release asset** to keep the repository size manageable.

### Download

1. Navigate to the [**Releases page → v1.0**](https://github.com/SanTiwari07/PotHoleDetection/releases/tag/v1.0).
2. Download `pothole_yolov8.pt`.
3. Place the file at:
   ```
   assets/models/pothole_yolov8.pt
   ```

### Usage (Python)

```python
from ultralytics import YOLO

model = YOLO("assets/models/pothole_yolov8.pt")
results = model.predict(source="path/to/image_or_video.mp4", conf=0.5)
results[0].show()
```

---

## 8. Validation Metrics

The model was evaluated on the held-out validation split of the Kaggle Pothole Dataset.

| Metric | Value |
|--------|-------|
| **mAP@0.5** | **81.68 %** |
| **mAP@0.5:0.95** | **55.95 %** |
| **Precision** | **82.33 %** |
| **Recall** | **74.42 %** |

> mAP@0.5:0.95 follows the COCO-style metric computed across 10 IoU thresholds (0.50 → 0.95, step 0.05).

---

## 9. Installation Guide

### Prerequisites

- Python 3.10 or newer
- pip package manager
- Arduino IDE 2.x with the ESP32 board package installed
- (Optional) A CUDA-capable GPU for faster inference

### Step 1 — Clone the Repository

```bash
git clone https://github.com/SanTiwari07/PotHoleDetection.git
cd PotHoleDetection
```

### Step 2 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Configure WiFi Credentials

1. Open `.env` in the project root.
2. Fill in your hotspot credentials:

```env
WIFI_SSID=YourNetworkName
WIFI_PASSWORD=YourPassword
```

3. Propagate the credentials to all ESP32 sketches:

```bash
python update_wifi.py
```

### Step 4 — Flash ESP32 Firmware

| Sketch | Target board | Notes |
|--------|-------------|-------|
| `ESP_32_Code/esp_32_cam_final/esp_32_cam_final.ino` | AI-Thinker ESP32-CAM | Note the IP printed in Serial Monitor |
| `ESP_32_Code/esp_32_final/esp_32_final.ino` | ESP32 Dev Module | Note the IP printed in Serial Monitor |

### Step 5 — Set Device IPs

Open `python/main.py` and update the two constants at the top of the file:

```python
ESP32_CAM_IP    = "192.168.X.X"   # IP of the ESP32-CAM
ESP32_SENSOR_IP = "192.168.X.Y"   # IP of the Sensor ESP32
```

### Step 6 — Download Model Weights

Follow [Section 7](#7-model-weights) to download `pothole_yolov8.pt` and place it in `assets/models/`.

---

## 10. Usage Instructions

### Live Detection (Full Hardware Stack)

```bash
python python/main.py
```

- A video window will open showing the annotated live feed with bounding boxes, tracking IDs, and severity labels.
- Press **`q`** to terminate gracefully.
- Session logs are saved to `outputs/logs/` and annotated videos to `outputs/videos/`.

### Offline / Simulation Mode

If hardware is unavailable, you can run detection against a pre-recorded video:

```bash
python python/main.py --source path/to/video.mp4
```

*(Refer to `python/main.py` CLI flags for all options.)*

---

## 11. Sample Field-Test Data

A curated sample log from a real field-test session (20 March 2026, Pune, Maharashtra) is provided in:

```
outputs/
└── sample_logs/
    └── output.csv
```

### Column Reference

| Column | Type | Description |
|--------|------|-------------|
| `date` | `YYYY-MM-DD` | Date of detection event |
| `time` | `HH:MM am/pm` | Time at the moment of detection (DS3231 RTC) |
| `frame_id` | `int` | Video frame number when the event was triggered |
| `pothole_id` | `string` | Unique string ID assigned by the SORT tracker (e.g., `pothole_001`) |
| `confidence` | `float [0–1]` | YOLOv8 detection confidence score |
| `bounding_box_area` | `int (px²)` | Pixel area of the detection bounding box |
| `aspect_ratio` | `float` | Width-to-height ratio of the bounding box |
| `peak_jerk` | `float (m/s²)` | Peak acceleration magnitude recorded by MPU6050 at moment of traverse |
| `severity` | `Low/Medium/High` | Fused severity classification |
| `latitude` | `float` | WGS-84 latitude from NEO-6M GPS |
| `longitude` | `float` | WGS-84 longitude from NEO-6M GPS |

### Severity Thresholds

| Severity | Condition |
|----------|-----------|
| **Low** | `peak_jerk < 3.0 m/s²` |
| **Medium** | `3.0 ≤ peak_jerk < 6.0 m/s²` |
| **High** | `peak_jerk ≥ 6.0 m/s²` |

### Sample Rows

```csv
date,time,frame_id,pothole_id,confidence,bounding_box_area,aspect_ratio,peak_jerk,severity,latitude,longitude
2026-03-20,01:56 pm,15,pothole_001,0.88,2955,0.8,3.0,Medium,18.457497,73.851289
2026-03-20,01:56 pm,30,pothole_002,0.85,5828,1.42,7.8,High,18.457465,73.850264
2026-03-20,01:59 pm,225,pothole_015,0.92,2756,0.87,1.9,Low,18.457848,73.849876
```

> The full 50-detection sample log is available at [`outputs/sample_logs/output.csv`](outputs/sample_logs/output.csv).

---

## 12. Zenodo

The full research paper and associated datasets are archived on Zenodo:

📄 **[IPDS — Real-Time Pothole Detection (Zenodo)](https://zenodo.org/records/20760578)**

This record includes the complete manuscript describing the system design, experimental methodology, validation metrics, and field-test results, along with citable DOI metadata for academic references.

---

## 13. Sample Results

The field-test session (50 detections, ~12 minutes) recorded on Pune city roads produced the following distribution:

| Severity | Count | Percentage |
|----------|-------|------------|
| Low | 8 | 16 % |
| Medium | 23 | 46 % |
| High | 19 | 38 % |

An annotated sample video is available on request. The raw detection output (`output_pothole_detection.mp4`) is excluded from the repository due to file size (≈ 13 MB) but can be shared via the [Releases page](https://github.com/SanTiwari07/PotHoleDetection/releases).

---

## 14. Repository Structure

```text
PotHoleDetection/
│
├── .env                              # WiFi credentials (NOT committed — see .gitignore)
├── .gitignore                        # Excludes secrets, caches, runtime outputs
├── LICENSE                           # MIT License
├── CITATION.cff                      # Machine-readable citation metadata
├── README.md                         # This file
├── requirements.txt                  # Python dependencies
│
├── python/                           # Python processing hub
│   ├── main.py                       # Entry point — YOLOv8 + SORT + sensor fusion
│   └── pothole_detection/            # Supporting modules (YOLO wrapper, SORT)
│
├── ESP_32_Code/
│   ├── esp_32_cam_final/
│   │   └── esp_32_cam_final.ino      # ESP32-CAM MJPEG server firmware
│   └── esp_32_final/
│       └── esp_32_final.ino          # ESP32 Sensor Node REST API firmware
│
├── assets/
│   ├── models/                       # Model weights (pothole_yolov8.pt — via Releases)
│   └── videos/                       # Reference/demo videos
│
├── outputs/
│   ├── sample_logs/
│   │   └── output.csv                # Curated sample field-test log (tracked)
│   ├── logs/                         # Runtime CSV outputs (git-ignored)
│   └── videos/                       # Runtime annotated MP4s (git-ignored)
│
├── Diagrams/                         # Interactive HTML block diagrams & flowcharts
├── KiCad/                            # PCB schematics and KiCad project files
├── docs/
│   ├── IPDS_Pothole_Detection.pdf    # ← Preprint manuscript (submitted)
│   ├── ARCHITECTURE.md               # Full system architecture documentation
│   ├── HARDWARE.md                   # Detailed hardware wiring & pinout guide
│   └── DETAIL.md                     # In-depth technical specification
│
├── auto_pad.py                       # Utility — bounding-box padding helper
├── detector.py                       # Standalone detector wrapper
├── sort.py                           # SORT tracking algorithm implementation
├── tracker.py                        # Tracker orchestrator
├── update_wifi.py                    # Injects WiFi credentials into ESP32 sketches
└── PotHoleSimu/                      # Road-condition simulation scripts
```

---

## 15. Future Scope

- **Dashcam / Smartphone Integration** — Passive crowdsourcing via ubiquitous consumer devices.
- **Cloud Scalability** — Migrate inference to distributed AWS/GCP microservices with Kubernetes orchestration.
- **Government Dashboards** — Real-time heatmaps and predictive analytics for municipal budget allocation.
- **Navigation Alerts** — Integration with OpenStreetMap (OSM) for proactive driver warnings.
- **Spatial Database** — PostGIS-backed REST API for researchers and autonomous-vehicle pipelines.
- **Advanced Sensors** — LiDAR or thermal cameras for 24/7 all-weather visibility.
- **Predictive Maintenance** — Detect micro-cracks and model freeze-thaw cycles to predict failures before potholes form.
- **V2X Communication** — Broadcast hazard coordinates to trailing autonomous vehicles in real-time.
- **True Edge Acceleration** — Deploy on dedicated AI ASICs (Google Coral TPU, Hailo-8) for fully offline inference.

---

## 16. Citation

If you use this system, dataset, or code in academic work, please cite:

```bibtex
@software{tiwari2026ipds,
  author    = {Tiwari, Sanskar and Bansod, Swarali and Kognole, Eshwari and Shinde, Shruti},
  title     = {Real-Time Pothole Detection Based on Vision-Dominant Sensor Fusion
               and Dual ESP32 Architecture},
  year      = {2026},
  version   = {1.0.0},
  license   = {MIT},
  url       = {https://github.com/SanTiwari07/PotHoleDetection}
}
```

A machine-readable `CITATION.cff` file is also included in the root of this repository.

---

## 17. Authors

This project was developed by students of the Department of Electronics and Telecommunication Engineering, **Pune Institute of Computer Technology (PICT)**, Pune, Maharashtra, India.

| Name | Role |
|------|------|
| **Sanskar Tiwari** | Core Architecture & ML Pipeline |
| **Swarali Bansod** | Sensor Integration & Firmware |
| **Eshwari Kognole** | Hardware Design & Testing |
| **Shruti Shinde** | Data Collection & Validation |

> Department of Electronics and Telecommunication Engineering
> Pune Institute of Computer Technology (PICT)
> Pune, Maharashtra, India

---

## 18. License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for full details.

© 2026 Sanskar Tiwari, Swarali Bansod, Eshwari Kognole, Shruti Shinde.
