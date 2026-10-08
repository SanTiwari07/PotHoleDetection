# Hardware Guide

IPDS uses **two ESP32 boards**: an ESP32-CAM that only streams video, and an ESP32 DevKit that reads the sensors when asked. Detection runs on a laptop or edge computer (the processing hub), not on the ESP32s. The paper reports a hardware cost of **under ₹2,500 per unit**.

## Components

| Component | Role | Notes |
|---|---|---|
| ESP32-CAM (AI-Thinker, OV2640) | Vision node | Streams 320×240 MJPEG over WiFi. Needs a USB-to-serial adapter to flash. |
| ESP32 DevKit (38-pin DevKitC or similar) | Sensor node | Hosts the `/query` HTTP endpoint |
| MPU6050 (GY-521 module) | Accelerometer | Read over I²C at ±2 g (16384 LSB/g) |
| DS3231 (ZS-042 module) + CR2032 | Real-time clock | Timestamps each event without internet |
| NEO-6M (GY-NEO6MV2 module) + antenna | GPS | NMEA over UART at 9600 baud |
| 2 × 4.7 kΩ resistors | I²C pull-ups | SDA and SCL to 3V3 |
| 5 V power bank | Power | The paper's component table specifies 5 V regulated, > 600 mA peak |
| Laptop or Jetson-class computer | Processing hub | Runs `python/main.py` |

## Sensor node wiring

These pins match the firmware ([`esp_32_final.ino`](../ESP_32_Code/esp_32_final/esp_32_final.ino)) and the PCB ([`KiCad/IPDS_SensorNode`](../KiCad/IPDS_SensorNode/)).

| Module pin | ESP32 DevKit pin | Notes |
|---|---|---|
| MPU6050 VCC | 3V3 | |
| MPU6050 GND | GND | |
| MPU6050 SCL | GPIO22 | shared I²C bus |
| MPU6050 SDA | GPIO21 | shared I²C bus |
| MPU6050 **AD0** | **3V3** | selects I²C address **0x69** (see below) |
| MPU6050 INT, XDA, XCL | not connected | |
| DS3231 VCC / GND | 3V3 / GND | |
| DS3231 SCL / SDA | GPIO22 / GPIO21 | shared I²C bus |
| DS3231 32K, SQW | not connected | |
| NEO-6M VCC / GND | 3V3 / GND | |
| NEO-6M TX | GPIO16 (RX2) | GPS → ESP32 |
| NEO-6M RX | GPIO17 (TX2) | ESP32 → GPS |
| 4.7 kΩ | SDA → 3V3, SCL → 3V3 | I²C pull-ups |

### I²C addresses

| Device | Address |
|---|---|
| DS3231 RTC | 0x68 (fixed) |
| AT24C32 EEPROM on the ZS-042 board | 0x57 (unused) |
| MPU6050 | 0x69 with AD0 high |

The MPU6050 defaults to 0x68 when AD0 is low, which is the same address as the DS3231, so the two would collide on the bus. Tying AD0 to 3V3 moves the MPU6050 to 0x69, which is what the firmware expects (`MPU_ADDR 0x69`).

> The paper's Table 2 lists AD0 → GND (0x68) and the DS3231 at 0x57. 0x57 is the EEPROM on the ZS-042 module; the DS3231 clock itself is at 0x68. Wire AD0 to 3V3 as shown above.

## Vision node (ESP32-CAM)

The firmware ([`esp_32_cam_final.ino`](../ESP_32_Code/esp_32_cam_final/esp_32_cam_final.ino)) uses the AI-Thinker pin map in `camera_pins.h`. The camera settings are QVGA (320×240), JPEG quality 12, two frame buffers (in PSRAM when available) and "grab latest frame" mode. No extra wiring is needed beyond 5 V power.

**Flashing:** the ESP32-CAM has no USB port. Use a USB-to-serial adapter:

1. Connect adapter TX → U0R (GPIO3), RX → U0T (GPIO1), GND → GND, 5V → 5V.
2. Tie **GPIO0 to GND** and reset the board to enter flash mode.
3. Upload with board **AI Thinker ESP32-CAM** selected.
4. Remove the GPIO0–GND link and reset. The Serial Monitor (115200 baud) prints the board's IP address.

## Setting up the firmware

1. Copy `.env.example` to `.env`, set `WIFI_SSID` / `WIFI_PASSWORD`, and run `python update_wifi.py`. This generates the git-ignored `credentials.h` for both sketches.
2. Install the ESP32 Arduino core 3.x and the **RTClib** and **TinyGPSPlus** libraries.
3. Flash both boards and note the IP addresses printed on the Serial Monitor.
4. Open `http://<sensor-node-ip>/` in a browser. It shows whether the MPU6050, DS3231 and GPS respond, and how many GPS satellites are in view.
5. Put both IPs in `.env` (`ESP32_CAM_IP`, `ESP32_SENSOR_IP`) and run `python python/main.py --live`.

If the DS3231 has lost power (no or flat coin cell), the firmware sets it from the firmware build time at boot. If the RTC isn't found at all, the hub falls back to the computer's clock.

## PCB

A 2-layer carrier board for the sensor node, with sockets for the ESP32 DevKit and the three modules, is in [`KiCad/IPDS_SensorNode/`](../KiCad/IPDS_SensorNode/). It passes KiCad's ERC and DRC with 0 violations. Gerbers, BOM and a schematic PDF are in its `fabrication/` folder. Before ordering, read that folder's README, especially the ESP32 row-spacing check.

## Mounting on a vehicle

These recommendations come from the paper (Sections 3.4 and 5.5):

- **Camera:** pitch the ESP32-CAM about **35° downwards** so the sky is out of frame. At that angle, the trigger line at 75% of the frame height corresponds to about **1 m in front of the bumper**.
- **MPU6050:** mount it rigidly to the vehicle body, not on foam, so impacts are not damped.
- **GPS antenna:** give it a clear view of the sky. Metal enclosures block the signal.

## Known hardware limitations

From the paper's Section 7.3:

- **GPS accuracy:** the NEO-6M is accurate to about 2.5–5 m. That is fine for road-level mapping but not lane-level.
- **Low light:** the OV2640 performs poorly at night, so detection confidence drops.
- **Vehicle dependence:** peak jerk depends on the vehicle's suspension, so severity values are only directly comparable within one vehicle.
- **WiFi range:** all nodes must share one 2.4 GHz network.
- **MPU6050 calibration:** the paper describes an offset-calibration routine for the MPU6050. That calibration sketch is **not included in this repository yet**; the current firmware reads uncalibrated values.
