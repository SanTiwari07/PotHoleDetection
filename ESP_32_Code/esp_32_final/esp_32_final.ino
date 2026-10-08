/*************************************************
 *  ESP32 SENSOR NODE
 *  MPU6050 (I2C) + DS3231 RTC (I2C) + NEO-6M GPS (UART2)
 *  Answers  GET /query?pothole_id=N  with one JSON sensor snapshot.
 *
 *  Wiring (matches KiCad/IPDS_SensorNode):
 *    I2C  SDA = GPIO21, SCL = GPIO22 (4.7k pull-ups to 3V3)
 *    GPS  TX -> GPIO16 (RX2), GPS RX <- GPIO17 (TX2), 9600 baud
 *    MPU6050 AD0 -> 3V3 so it sits at 0x69 (the DS3231 already owns 0x68)
 *
 *  Libraries: RTClib, TinyGPSPlus
 *************************************************/

#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <RTClib.h>
#include <TinyGPSPlus.h>

// ================= WIFI CONFIGURATION =================
// [USER ACTION REQUIRED]: Edit the .env file in the root folder and run python update_wifi.py
#include "credentials.h"

// ================= SETTINGS =================
#define MPU_ADDR 0x69 // AD0 = HIGH. 0x68 is taken by the DS3231 RTC on the same bus
#define SDA_PIN 21
#define SCL_PIN 22

#define GPS_RX_PIN 16 // ESP32 RX2  <- GPS TX
#define GPS_TX_PIN 17 // ESP32 TX2  -> GPS RX
#define GPS_BAUD 9600
#define GPS_MAX_AGE_MS 5000 // Treat fixes older than this as stale

// Threshold for physical detection (Optional, maintained from original code)
#define POTHOLE_THRESHOLD 20000

#define WIFI_RETRY_MS 5000

// ================= GLOBAL OBJECTS =================
WebServer server(80);
RTC_DS3231 rtc;
TinyGPSPlus gps;
HardwareSerial gpsSerial(2);

float ax_ms2, ay_ms2, az_ms2;
bool potholeDetected = false;
bool rtc_found = false;
unsigned long lastWifiRetry = 0;

// ----------- MPU WAKE FUNCTION -------------
bool initMPU() {
  Serial.println("Initializing MPU6050/6500...");

  // WHO_AM_I: 0x68 for MPU6050, 0x70 for MPU6500, 0x71 for MPU9250
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x75);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom((uint16_t)MPU_ADDR, (uint8_t)1, true) != 1) {
    Serial.printf("MPU not found at 0x%02X. Is AD0 tied to 3V3?\n", MPU_ADDR);
    return false;
  }
  Serial.printf("MPU WHO_AM_I = 0x%02X\n", Wire.read());

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);   // Power management register
  Wire.write(0x00);   // Wake up
  byte error = Wire.endTransmission();

  if (error == 0) {
    Serial.println("MPU Ready!");
    return true;
  }
  Serial.print("MPU Error: ");
  Serial.println(error);
  return false;
}

// ----------- READ ACCEL --------------------
// Returns false if the MPU did not answer (values are zeroed in that case)
bool readMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B); // ACCEL_XOUT_H
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom((uint16_t)MPU_ADDR, (uint8_t)6, true) != 6) {
    ax_ms2 = 0.0; ay_ms2 = 0.0; az_ms2 = 0.0;
    return false;
  }

  int16_t raw_ax = Wire.read() << 8 | Wire.read();
  int16_t raw_ay = Wire.read() << 8 | Wire.read();
  int16_t raw_az = Wire.read() << 8 | Wire.read();

  // The Python algorithm expects m/s^2 for severity calculation:
  // J_MAX is 20.0 m/s^3. Default MPU scaling is +/- 2g = 16384 LSB/g.
  // 1g = 9.81 m/s^2.
  ax_ms2 = (raw_ax / 16384.0) * 9.81;
  ay_ms2 = (raw_ay / 16384.0) * 9.81;
  az_ms2 = (raw_az / 16384.0) * 9.81;

  // Background threshold detection (legacy code)
  if (abs(raw_ax) > POTHOLE_THRESHOLD || abs(raw_ay) > POTHOLE_THRESHOLD || abs(raw_az) > POTHOLE_THRESHOLD) {
    potholeDetected = true;
  }
  return true;
}

// ----------- GPS ---------------------------
void feedGPS() {
  while (gpsSerial.available()) {
    gps.encode(gpsSerial.read());
  }
}

bool gpsFixValid() {
  return gps.location.isValid() && gps.location.age() < GPS_MAX_AGE_MS;
}

// ----------- WEB RESPONSE ------------------
void handleQuery() {
  feedGPS();

  // Read latest sensor data
  bool mpu_ok = readMPU();

  // Python query looks like: http://<IP>/query?pothole_id=42
  int req_id = 0;
  if (server.hasArg("pothole_id")) {
    req_id = server.arg("pothole_id").toInt();
  }

  // Fetch RTC Date & Time safely
  String timestamp = "2000-01-01T00:00:00";
  bool rtc_ok = false;

  if (rtc_found) {
    DateTime now = rtc.now();
    char buf[25];
    snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
             now.year(), now.month(), now.day(),
             now.hour(), now.minute(), now.second());
    timestamp = String(buf);

    // Check if RTC lost power (Year 2000 is default)
    if (now.year() > 2000) {
        rtc_ok = true;
    }
  }

  bool gps_ok = gpsFixValid();

  // Construct JSON Payload adhering to python's json.loads() expectations
  String json = "{";
  json += "\"pothole_id\":" + String(req_id) + ",";
  json += "\"timestamp\":\"" + timestamp + "\",";
  json += "\"latitude\":" + String(gps_ok ? gps.location.lat() : 0.0, 6) + ",";
  json += "\"longitude\":" + String(gps_ok ? gps.location.lng() : 0.0, 6) + ",";
  json += "\"satellites\":" + String(gps.satellites.isValid() ? gps.satellites.value() : 0) + ",";
  json += "\"ax\":" + String(ax_ms2, 2) + ",";
  json += "\"ay\":" + String(ay_ms2, 2) + ",";
  json += "\"az\":" + String(az_ms2, 2) + ",";
  json += "\"mpu_ok\":" + String(mpu_ok ? "true" : "false") + ",";
  json += "\"gps_ok\":" + String(gps_ok ? "true" : "false") + ",";
  json += "\"rtc_ok\":" + String(rtc_ok ? "true" : "false");
  json += "}";

  if (potholeDetected) {
     potholeDetected = false;
  }

  server.send(200, "application/json", json);
}

// Human-readable health check for bring-up: open http://<IP>/ in a browser
void handleRoot() {
  feedGPS();
  String body = "IPDS sensor node\n";
  body += "MPU6050 @0x" + String(MPU_ADDR, HEX) + ": " + String(readMPU() ? "OK" : "NOT RESPONDING") + "\n";
  body += "DS3231:  " + String(rtc_found ? "OK" : "NOT FOUND") + "\n";
  body += "GPS:     " + String(gps.charsProcessed()) + " chars received, ";
  body += String(gpsFixValid() ? "fix OK" : "no fix yet") + ", ";
  body += String(gps.satellites.isValid() ? gps.satellites.value() : 0) + " satellites\n";
  server.send(200, "text/plain", body);
}

// ================= SETUP ===================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(SDA_PIN, SCL_PIN);
  initMPU();

  // Initialize RTC
  Serial.println("Initializing RTC...");
  rtc_found = rtc.begin();
  if (!rtc_found) {
    Serial.println("RTC NOT found!");
  } else {
    Serial.println("RTC found.");
    if (rtc.lostPower()) {
      // Coin cell missing/flat: start from the firmware build time rather than year 2000
      Serial.println("RTC lost power, setting time from firmware build time.");
      rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    }
  }

  // GPS on UART2
  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  Serial.println("GPS UART started (fix can take 30s+ outdoors on a cold start).");

  // IMPORTANT FIX: Sensor node MUST be a Station (WIFI_STA) connecting to
  // same router as ESP32-CAM and PC. It previously hosted an isolated Access Point!
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.println("\nConnecting to WiFi...");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected!");
    Serial.print("ESP32 Sensor IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nFailed to connect. Will continue trying in loop...");
  }

  // Start Server
  server.on("/", handleRoot);
  server.on("/query", handleQuery);
  server.begin();
  Serial.println("HTTP Server started on port 80.");
}

// ================= LOOP ====================
void loop() {
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiRetry > WIFI_RETRY_MS) {
    // Reconnect logic if WiFi drops (non-blocking so GPS keeps being parsed)
    lastWifiRetry = millis();
    WiFi.reconnect();
  }

  // Keep the GPS parser fed so a fix is ready when Python asks
  feedGPS();

  // Listen for Python queries
  server.handleClient();
}
