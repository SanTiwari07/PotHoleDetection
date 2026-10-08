/*************************************************
 *  ESP32-CAM VISION NODE
 *************************************************/

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"
#include "esp_task_wdt.h"
#include "camera_pins.h"   // <-- separate pin file

/* ================= WIFI CONFIGURATION ================= */
// [USER ACTION REQUIRED]: Edit the .env file in the root folder and run python update_wifi.py
#include "credentials.h"

/* ================= STREAM CONFIGURATION ================= */
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE =
  "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY =
  "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART =
  "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

/* ================= WATCHDOG CONFIGURATION ================= */
// Restart if WiFi stays down this long (e.g. the WiFi stack hangs under thermal load)
#define WIFI_WATCHDOG_MS 30000

/* ================= GLOBAL OBJECTS ================= */
httpd_handle_t stream_httpd = NULL;
httpd_handle_t control_httpd = NULL;

/* ================= MJPEG STREAM HANDLER ================= */
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  esp_err_t res = ESP_OK;

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;

  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Camera capture failed");
      res = ESP_FAIL;
      break;
    }

    char part_buf[64];
    size_t hlen = snprintf(part_buf, 64, _STREAM_PART, fb->len);

    res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    if (res != ESP_OK) { esp_camera_fb_return(fb); break; }

    res = httpd_resp_send_chunk(req, part_buf, hlen);
    if (res != ESP_OK) { esp_camera_fb_return(fb); break; }

    res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    if (res != ESP_OK) { esp_camera_fb_return(fb); break; }

    esp_camera_fb_return(fb);
    fb = NULL;

    // Yield to the IDLE task briefly so it can feed the watchdog
    vTaskDelay(pdMS_TO_TICKS(10));
  }
  return res;
}

/* ================= HEALTH CHECK HANDLER ================= */
static esp_err_t health_handler(httpd_req_t *req) {
  char json[100];
  snprintf(json, sizeof(json), "{\"status\":\"ok\",\"uptime\":%lu}", millis() / 1000);
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, json, strlen(json));
}

/* ================= START HTTP SERVER ================= */
// /stream runs forever inside its handler, so /health gets its own server
// (port 80) and still answers while a client is streaming from port 81.
void startStreamServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;

  httpd_uri_t health_uri = {};
  health_uri.uri = "/health";
  health_uri.method = HTTP_GET;
  health_uri.handler = health_handler;

  httpd_uri_t stream_uri = {};
  stream_uri.uri = "/stream";
  stream_uri.method = HTTP_GET;
  stream_uri.handler = stream_handler;

  if (httpd_start(&control_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(control_httpd, &health_uri);
  }

  config.server_port = 81;
  config.ctrl_port += 1;
  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.println("HTTP server started: stream on :81/stream, health on :80/health");
  }
}

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);
  delay(1000);

  // ===== WATCHDOG =====
  // The core's task watchdog already guards the idle tasks; re-initialising it here starves
  // IDLE1 and panics. Instead, loop() is subscribed to it below and restarts the board if
  // WiFi stays down for WIFI_WATCHDOG_MS.

  // ===== CAMERA CONFIG =====
  camera_config_t config = {};  // zero-init: core 3.x adds fields (fb_location, grab_mode, ...)
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 10;
  config.fb_count = 2;
  config.grab_mode = CAMERA_GRAB_LATEST;  // always send the newest frame (lowest latency)
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed (0x%x)! Check the camera ribbon cable. Restarting...\n", err);
    delay(3000);
    ESP.restart();
  }

  // Vertical flip enabled as in the paper (Section 3.4); set to 0 if your camera image is upside down
  sensor_t *sensor = esp_camera_sensor_get();
  sensor->set_vflip(sensor, 1);

  // ===== WIFI =====
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // modem sleep adds large latency to the MJPEG stream
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.println(WiFi.localIP());

  startStreamServer();

  // Hardware task watchdog on loop(): resets the board if loop() itself ever hangs
  enableLoopWDT();
}

/* ================= LOOP ================= */
unsigned long lastWifiOk = 0;

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    lastWifiOk = millis();
  } else if (millis() - lastWifiOk > WIFI_WATCHDOG_MS) {
    Serial.println("WiFi down for too long, restarting...");
    ESP.restart();
  }
  delay(100);
}
