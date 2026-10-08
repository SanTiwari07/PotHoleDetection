#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <MPU6050.h>
#include <RTClib.h>
#include <TinyGPS++.h>

// ================= WOKWI WIFI CONFIGURATION =================
const char* ssid = "Wokwi-GUEST";
const char* password = "";

// ================= SETTINGS =================
#define I2C_SDA 21
#define I2C_SCL 22

#define GPS_RX 16   // GPS TX → ESP32 RX
#define GPS_TX 17   // GPS RX → ESP32 TX

const float POTHOLE_THRESHOLD = 1.8; // Z Acc (g)

// ================= GLOBAL OBJECTS =================
WebServer server(80);
MPU6050 mpu;
RTC_DS1307 rtc;
TinyGPSPlus gps;

float ax_g, ay_g, az_g;
bool potholeDetected = false;

// ----------- WEB RESPONSE ------------------
void handleQuery() {
  // Read latest sensor data (normally handled in loop, but we ensure fresh GPS process here)
  while (Serial2.available()) {
    gps.encode(Serial2.read());
  }

  // Python query looks like: http://<IP>/query?pothole_id=42
  int req_id = 0;
  if(server.hasArg("pothole_id")) {
    req_id = server.arg("pothole_id").toInt();
  }

  // Fetch RTC Date & Time safely
  String timestamp = "2000-01-01T00:00:00";
  bool rtc_ok = false;
  try {
    DateTime now = rtc.now();
    timestamp = String(now.timestamp());
    rtc_ok = true;
  } catch (...) {
  }

  // Ensure fresh acceleration
  int16_t ax, ay, az;
  mpu.getAcceleration(&ax, &ay, &az);
  ax_g = ax / 16384.0;
  ay_g = ay / 16384.0;
  az_g = az / 16384.0;

  // For python json.loads(), we need ms2
  float ax_ms2 = ax_g * 9.81;
  float ay_ms2 = ay_g * 9.81;
  float az_ms2 = az_g * 9.81;

  // Construct JSON Payload adhering to python's json.loads() expectations
  String json = "{";
  json += "\"pothole_id\":" + String(req_id) + ",";
  json += "\"timestamp\":\"" + timestamp + "\",";
  
  if (gps.location.isValid()) {
    json += "\"latitude\":" + String(gps.location.lat(), 6) + ",";
    json += "\"longitude\":" + String(gps.location.lng(), 6) + ",";
    json += "\"gps_ok\":true,";
  } else {
    json += "\"latitude\":0.000000,";
    json += "\"longitude\":0.000000,";
    json += "\"gps_ok\":false,";
  }

  json += "\"ax\":" + String(ax_ms2, 2) + ",";
  json += "\"ay\":" + String(ay_ms2, 2) + ",";
  json += "\"az\":" + String(az_ms2, 2) + ",";
  json += "\"mpu_ok\":true,";
  json += "\"rtc_ok\":" + String(rtc_ok ? "true" : "false");
  json += "}";

  if (potholeDetected) {
     potholeDetected = false;
  }

  server.send(200, "application/json", json);
}

// ================= SETUP ===================
void setup() {
  Serial.begin(115200);

  // GPS UART
  Serial2.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);

  // I2C
  Wire.begin(I2C_SDA, I2C_SCL);

  // MPU6050 init
  mpu.initialize();
  if (!mpu.testConnection()) {
    Serial.println("MPU6050 not connected");
  } else {
    Serial.println("MPU6050 connected");
  }

  // RTC init
  if (!rtc.begin()) {
    Serial.println("RTC not found");
  }

  if (!rtc.isrunning()) {
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  }
  
  // WiFi
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
    Serial.println("\nFailed to connect to WiFi.");
  }

  // Start Server
  server.on("/query", handleQuery);
  server.begin();
  Serial.println("HTTP Server started on port 80.");
  Serial.println("ESP32 Pothole System Ready");
}

// ================= LOOP ====================
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    // Reconnect logic if WiFi drops
    WiFi.reconnect();
    delay(1000);
  }
  
  // Listen for Python queries
  server.handleClient();

  // ----- Read GPS -----
  while (Serial2.available()) {
    gps.encode(Serial2.read());
  }

  // ----- Read MPU6050 Background -----
  int16_t ax, ay, az;
  mpu.getAcceleration(&ax, &ay, &az);
  az_g = az / 16384.0;

  // ----- Pothole Detection (Console only, as server relies on query) -----
  if (abs(az_g) > POTHOLE_THRESHOLD && gps.location.isValid()) {
    potholeDetected = true;
    Serial.println("POTHOLE DETECTED");
    
    DateTime now = rtc.now();
    Serial.print("Time: ");
    Serial.print(now.hour());
    Serial.print(":");
    Serial.print(now.minute());
    Serial.print(":");
    Serial.println(now.second());

    Serial.print("Latitude : ");
    Serial.println(gps.location.lat(), 6);
    Serial.print("Longitude: ");
    Serial.println(gps.location.lng(), 6);
    Serial.print("Z Acc (g): ");
    Serial.println(az_g);
    Serial.println("---------------------------");

    delay(2000);  // avoid duplicates
  }

  delay(50); // slight debounce
}
