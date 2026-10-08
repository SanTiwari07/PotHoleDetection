# Technical Reference

How IPDS works, based on the code in this repository and on the paper ([Zenodo](https://zenodo.org/records/20760578), [`IPDS_Pothole_Detection.pdf`](IPDS_Pothole_Detection.pdf)). Numbers marked *(paper)* are the authors' reported results; everything else describes what the code does.

For the big picture see [ARCHITECTURE.md](ARCHITECTURE.md); for wiring and assembly see [HARDWARE.md](HARDWARE.md).

---

## 1. Detection model

| Item | Value |
|---|---|
| Architecture | YOLOv8m (Ultralytics), 1 class: `pothole` |
| Weights | `assets/models/pothole_yolov8.pt` (22.5 MB), downloaded automatically from [Releases v1.0](https://github.com/SanTiwari07/PotHoleDetection/releases/tag/v1.0) |
| Dataset *(paper, Table 5)* | [Pothole Detection, andrewmvd (Kaggle)](https://www.kaggle.com/datasets/andrewmvd/pothole-detection): 665 images, Pascal VOC XML converted to YOLO format |
| Split *(paper)* | 598 training / 67 validation; no separate test split |
| Input size | 640 × 640 |

### Validation metrics *(paper, Table 4)*

| mAP@0.5 | mAP@0.5:0.95 | Precision | Recall |
|:---:|:---:|:---:|:---:|
| 81.68% | 55.95% | 82.33% | 74.42% |

### Reproducing the model

```bash
python training/prepare_dataset.py --src path/to/pothole-detection   # VOC -> YOLO, 10% validation
python training/train.py                                              # YOLOv8m, 640 px, 100 epochs, AdamW
```

`prepare_dataset.py` reproduces the paper's split sizes (598 / 67) with a fixed seed. The paper does not publish which images were in each split, so the exact images, and therefore the metrics, may differ slightly. The training settings in `train.py` (100 epochs, AdamW) come from the project's original README; the paper does not state them.

---

## 2. Processing hub (`python/main.py`)

### Modes

| Command | Video source | Sensor data |
|---|---|---|
| `python python/main.py --live` | ESP32-CAM stream `http://<ESP32_CAM_IP>:81/stream` | Queries `http://<ESP32_SENSOR_IP>/query` |
| `python python/main.py --source video.mp4` | Video file (or webcam index, e.g. `0`) | None: jerk/GPS columns left empty |

Device IPs come from `.env` or `--cam-ip` / `--sensor-ip`. Other options: `--model`, `--conf`, `--jerk-threshold`, `--output-dir`, `--no-display`. Ctrl+C (or a service stop) finalises the MP4 and CSV before exiting.

### Pipeline per frame

1. **Frame input.** In live mode, a background thread reads the MJPEG stream and keeps only the newest decoded frame. The main loop processes each new frame once; it never re-processes a frame it has already seen.
2. **Detection.** `PotholeDetector` runs YOLOv8 and keeps boxes with confidence ≥ `CONF_THRESHOLD = 0.25`.
3. **Tracking.** `PotholeTracker` wraps SORT ([Bewley et al., 2016](https://arxiv.org/abs/1602.00763)) with `max_age=30`, `min_hits=3`, `iou_threshold=0.3`.
4. **Geometric filters** (`pothole_detection/filters.py`, paper Section 5.4). A track can't trigger a sensor query while any of these hold:
   - **Area:** box area / frame area > 0.25 (e.g. a vehicle or tunnel entrance)
   - **Aspect ratio:** box width / height > 3.0 (e.g. road markings or tar cracks)
   - **Persistence:** the track's centre has stayed still for more than 10 consecutive frames (e.g. a shadow moving with the vehicle). "Still" means it moved less than 1% of the frame height since the previous frame; the paper doesn't give this tolerance.
5. **Trigger.** When a track's centre y ≥ 0.75 × frame height and the track hasn't been handled yet, the best-matching detection's confidence is checked again (≥ 0.25). The sensor node is then queried, once per track.
6. **Sensor burst.** `get_sensor_burst()` sends 5 requests (0.5 s timeout each) and collects acceleration magnitudes √(ax² + ay² + az²).
7. **Fusion gate.** If the peak jerk is below `--jerk-threshold`, the event is rejected: nothing is logged and the box is labelled `Sev:REJ` in the video (see below).
8. **Logging.** Otherwise severity is computed (section 5) and one CSV row is written. Each pothole is logged at most once.
9. **Output.** Boxes, track IDs, confidence and severity are drawn on the frame and written to the MP4.

### Fusion gate (paper, Section 6.1)

Vision proposes a pothole; the accelerometer must confirm an impact. Both have to agree before a row is logged:

- **Visual false positives** (shadows, manhole covers) are detected by YOLO but produce no jerk spike, so the gate rejects them.
- **Inertial false positives** (speed bumps, railway crossings) produce a spike but no YOLO detection, so the sensor node is never queried.

The paper doesn't give a numeric threshold. The default `JERK_GATE = 1.5 m/s³` (in `fusion.py`) sits just below the smallest peak jerk in the sample field log (1.6). Because the jerk depends on the vehicle and the mounting, calibrate it: drive a smooth road, watch the peak-jerk values the hub prints for rejected and logged events, and pass a value above the smooth-road level with `--jerk-threshold`.

If the sensor node doesn't answer, no impact can be confirmed and the event is rejected; the hub prints a warning. In offline mode (no sensor node) the gate is skipped and every visually confirmed pothole is logged with a vision-only severity.

---

## 3. Sensor node firmware (`ESP_32_Code/esp_32_final`)

| Setting | Value |
|---|---|
| I²C | SDA GPIO21, SCL GPIO22, 100 kHz standard mode |
| Boot self-test | MPU6050 (WHO_AM_I at 0x69) and DS3231 (0x68) must answer, otherwise the node halts and prints a diagnostic every 5 s |
| Calibration | offsets from `ESP_32_Code/mpu6050_calibration` are written to the MPU6050 offset registers at boot once `MPU_OFFSETS_CALIBRATED` is set to 1 |
| MPU6050 | address 0x69 (AD0 high), woken via register 0x6B, 6-byte burst read from 0x3B, ±2 g → `a = raw / 16384 × 9.81` m/s² |
| DS3231 | RTClib; if it lost power, it is set from the firmware build time at boot |
| GPS | TinyGPSPlus on UART2 (RX GPIO16, TX GPIO17), 9600 baud, parsed continuously in `loop()`. A fix older than 5 s counts as invalid. |
| HTTP | port 80. `GET /query?pothole_id=N` returns JSON; `GET /` returns a plain-text health page. |
| WiFi | station mode; reconnects every 5 s without blocking GPS parsing |

### `/query` response

```json
{
  "pothole_id": 42,
  "timestamp": "2026-03-20T13:56:04",
  "latitude": 18.457497,
  "longitude": 73.851289,
  "satellites": 7,
  "ax": 0.12, "ay": -0.05, "az": 9.81,
  "mpu_ok": true,
  "gps_ok": true,
  "rtc_ok": true
}
```

- `latitude` / `longitude` are `0.000000` and `gps_ok` is `false` until the GPS has a fix.
- `timestamp` is `2000-01-01T00:00:00` if no RTC is found; the hub then uses the computer's clock.
- `mpu_ok` is `false` if the MPU6050 doesn't answer the read.

> History: the sensor firmware committed in February 2026 read the GPS. The versions committed from March to June 2026 returned fixed `0.0` coordinates and always reported `mpu_ok: true`. GPS reading and real health flags were restored in the current version.

## 4. Vision node firmware (`ESP_32_Code/esp_32_cam_final`)

| Setting | Value |
|---|---|
| Board | AI-Thinker ESP32-CAM (pins in `camera_pins.h`) |
| Frames | JPEG, QVGA 320×240, quality 10, vertical flip on, 2 frame buffers, `CAMERA_GRAB_LATEST`, XCLK 20 MHz |
| Endpoints | `:81/stream` (MJPEG), `:80/health` (JSON uptime) |
| WiFi | station mode, modem sleep disabled for lower latency |
| Watchdog | `loop()` is on the hardware task watchdog; the board also restarts if WiFi stays down for 30 s |
| On camera init failure | prints the error code and restarts after 3 s |

---

## 5. Severity and jerk (`python/pothole_detection/fusion.py`)

```text
a_i        = sqrt(ax² + ay² + az²)                      for each of the 5 samples
peak_jerk  = max |a_i − a_(i−1)| / 0.05 s               (0 if fewer than 2 samples)
jerk_norm  = min(peak_jerk / J_max, 1)                  J_max = 20 m/s³          (paper Eq. 7)
severity   = 0.7 × confidence + 0.3 × jerk_norm         (0 if confidence < 0.25) (paper Eq. 6)
```

Notes:

- The 0.05 s is an assumed spacing between HTTP reads, not a measured one.
- The weights 0.7 / 0.3 are heuristic *(paper, Section 6.3)*.
- In offline mode the jerk term is 0, so severity = 0.7 × confidence.

---

## 6. Output files

### `outputs/logs/pothole_log.csv`

| Column | Meaning |
|---|---|
| `date`, `time` | RTC timestamp from the sensor node (computer clock as fallback) |
| `frame_id` | frame counter of the processed video, for finding the event in the MP4 |
| `pothole_id` | SORT track ID |
| `confidence` | YOLOv8 confidence of the matched detection |
| `bounding_box_area` | box area in pixels |
| `aspect_ratio` | box width / height |
| `peak_jerk` | m/s³ (empty in offline mode) |
| `severity` | numeric score from section 5, 0–1 |
| `latitude`, `longitude` | WGS-84 from the GPS; `0` without a fix, empty in offline mode |

### `outputs/videos/output_pothole_detection.mp4`

The input frames with a green trigger line, per-track boxes labelled `ID / Conf / Sev`, and a running count of unique track IDs.

---

## 7. Reported system results *(paper)*

| Result | Value |
|---|---|
| Inference throughput | 10–15 FPS on a CPU-only laptop, 320×240 input |
| End-to-end latency (frame → CSV) | ~170–200 ms |
| Hardware cost | under ₹2,500 per unit |

### False-positive trials *(paper, Table 6)*

| Scenario | Stage the paper attributes the rejection to | Reported outcome |
|---|---|---|
| Road shadow | Persistence filter | rejected 15/15 |
| Manhole cover | Sensor fusion gate (no jerk spike) | rejected 15/15 |
| Speed bump | No YOLO detection | rejected 20/20 |
| Tar crack / stripe | Aspect-ratio filter | rejected 20/20 |
| Large vehicle / tunnel | Area filter | rejected 10/10 |
| Railroad crossing | No YOLO detection | rejected 10/10 |
| Confirmed pothole | All stages | logged 10/10 |

Each of these stages is implemented in the code: confidence threshold, SORT `min_hits`, the three geometric filters, and the fusion gate.

---

## 8. Sample field log

[`outputs/sample_logs/output.csv`](../outputs/sample_logs/output.csv) contains 50 rows dated 20 March 2026, 1:56–2:08 pm. Its `severity` column uses text bands rather than the numeric score `main.py` writes:

| Band | Rows | Peak-jerk range in the file |
|---|:---:|---|
| Low | 8 | 1.6 – 2.7 |
| Medium | 22 | 3.0 – 5.9 |
| High | 20 | 6.0 – 9.4 |

The current `main.py` writes a numeric severity score instead, so this file comes from an earlier version of the pipeline or was post-processed into bands.

---

## 9. Limitations

*(paper, Section 7.3, plus code facts)*

- **GPS accuracy:** about 2.5–5 m with the NEO-6M.
- **Night:** low light reduces OV2640 image quality and YOLO confidence.
- **Severity across vehicles:** peak jerk depends on the vehicle's suspension, so severity is not directly comparable between vehicles.
- **Network:** all three devices need one shared 2.4 GHz WiFi network.
- **Throughput:** CPU-only inference limits frame rate; a GPU host would raise it.
- **Water-filled potholes** can lower detection confidence.
- **Jerk estimate:** it comes from 5 HTTP reads with an assumed 50 ms spacing, so it is a coarse estimate of the impact, not a high-rate accelerometer trace.
- **Calibration needed:** the MPU6050 must be calibrated once per installation with `ESP_32_Code/mpu6050_calibration`, and the fusion gate threshold should be tuned per vehicle.

## 10. Future work *(paper, Section 8)*

- Quantized on-device inference (ESP32-S3 / ESP32-P4) to remove the laptop
- Cloud dashboard with geospatial heatmaps
- LoRaWAN instead of WiFi for rural roads
- Per-vehicle suspension calibration to normalise jerk across fleets
- Stereo camera or LiDAR for depth measurement
- Larger, more diverse training data (night, rain, other regions)
- Better image sensor and an automotive-grade IMU

---

## 11. Testing

| What | How |
|---|---|
| Unit tests (fusion maths and gate, geometric filters, SORT tracking, dataset conversion) | `pytest tests` (also run in CI on Python 3.10 and 3.12) |
| Offline pipeline | `python python/main.py --source <video> --no-display` |
| Firmware | compiles with ESP32 Arduino core 3.3.1 (`arduino-cli compile`) |
| Sensor node, no hardware | Wokwi simulation in [`PotHoleSimu/`](../PotHoleSimu/) |
