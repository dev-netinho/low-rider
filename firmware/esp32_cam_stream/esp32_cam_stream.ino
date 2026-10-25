#include "esp_camera.h"
#include "esp_http_server.h"
#include <ESPmDNS.h>
#include <Preferences.h>
#include <WiFi.h>

#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

constexpr char DEFAULT_WIFI_SSID[] = "CONFIGURE_WIFI_SSID";
constexpr char DEFAULT_WIFI_PASSWORD[] = "CONFIGURE_WIFI_PASSWORD";
String configured_wifi_ssid;
String configured_wifi_password;
String serial_line;

static constexpr uint32_t STREAM_REPORT_MS = 5000;

struct StreamDiagnostics {
  uint32_t frames_sent = 0;
  uint32_t send_attempts = 0;
  uint32_t send_failures = 0;
  uint64_t send_sum_us = 0;
  uint32_t send_max_us = 0;
  uint64_t jpeg_sum_bytes = 0;
  uint32_t jpeg_max_bytes = 0;
  uint32_t last_jpeg_bytes = 0;
  uint32_t max_frame_interval_ms = 0;
  uint32_t last_frame_sent_ms = 0;
  int32_t last_send_error = ESP_OK;
  const char *last_send_error_name = "ESP_OK";
  const char *last_send_stage = "none";
  int32_t close_error = ESP_OK;
  const char *close_error_name = "ESP_OK";
  uint32_t next_report_ms = STREAM_REPORT_MS;
};

static void report_stream_diagnostics(const StreamDiagnostics &diag,
                                      uint32_t elapsed_ms,
                                      const char *phase,
                                      const char *reason) {
  const uint32_t send_avg_us = diag.send_attempts
                                 ? static_cast<uint32_t>(diag.send_sum_us / diag.send_attempts)
                                 : 0;
  const uint32_t jpeg_avg_bytes = diag.frames_sent
                                    ? static_cast<uint32_t>(diag.jpeg_sum_bytes / diag.frames_sent)
                                    : 0;
  Serial.printf(
      "[CAM_STREAM] phase=%s reason=%s elapsed_ms=%lu frames_sent=%lu "
      "send_attempts=%lu send_failures=%lu send_avg_us=%lu send_max_us=%lu "
      "jpeg_avg_bytes=%lu jpeg_max_bytes=%lu last_jpeg_bytes=%lu "
      "max_frame_interval_ms=%lu "
      "last_send_error=%ld(%s) last_send_stage=%s close_error=%ld(%s)\n",
      phase,
      reason,
      static_cast<unsigned long>(elapsed_ms),
      static_cast<unsigned long>(diag.frames_sent),
      static_cast<unsigned long>(diag.send_attempts),
      static_cast<unsigned long>(diag.send_failures),
      static_cast<unsigned long>(send_avg_us),
      static_cast<unsigned long>(diag.send_max_us),
      static_cast<unsigned long>(jpeg_avg_bytes),
      static_cast<unsigned long>(diag.jpeg_max_bytes),
      static_cast<unsigned long>(diag.last_jpeg_bytes),
      static_cast<unsigned long>(diag.max_frame_interval_ms),
      static_cast<long>(diag.last_send_error),
      diag.last_send_error_name,
      diag.last_send_stage,
      static_cast<long>(diag.close_error),
      diag.close_error_name);
}

static void load_wifi_config() {
  Preferences preferences;
  preferences.begin("wifi", true);
  configured_wifi_ssid = preferences.getString("ssid", DEFAULT_WIFI_SSID);
  configured_wifi_password = preferences.getString("password", DEFAULT_WIFI_PASSWORD);
  preferences.end();
}

static void handle_serial_provisioning() {
  while (Serial.available()) {
    const char character = static_cast<char>(Serial.read());
    if (character == '\r') continue;
    if (character != '\n') {
      if (serial_line.length() < 160) serial_line += character;
      continue;
    }
    serial_line.trim();
    if (serial_line == "PING") {
      Serial.println("PONG CAM");
    } else if (serial_line.startsWith("WIFI\t")) {
      const int separator = serial_line.indexOf('\t', 5);
      if (separator < 0) {
        Serial.println("CFG_ERROR FORMAT");
      } else {
        const String ssid = serial_line.substring(5, separator);
        const String password = serial_line.substring(separator + 1);
        if (ssid.length() == 0 || ssid.length() > 32 || password.length() > 63) {
          Serial.println("CFG_ERROR CREDENTIALS");
        } else {
          Preferences preferences;
          preferences.begin("wifi", false);
          preferences.putString("ssid", ssid);
          preferences.putString("password", password);
          preferences.end();
          Serial.println("CFG_OK WIFI");
          delay(250);
          ESP.restart();
        }
      }
    } else if (serial_line == "STATUS") {
      Serial.printf("STATUS CAM WIFI=%s IP=%s\n",
                    WiFi.status() == WL_CONNECTED ? "connected" : "offline",
                    WiFi.localIP().toString().c_str());
    } else if (serial_line.length() > 0) {
      Serial.println("CFG_ERROR UNKNOWN_COMMAND");
    }
    serial_line = "";
  }
}

static const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html><html lang="pt-BR"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32-CAM</title><style>body{font-family:system-ui;background:#111;color:#eee;margin:1rem}img{display:block;max-width:100%;height:auto}code{color:#9fe870}</style>
<h1>ESP32-CAM</h1><p>Fluxo contínuo: <code>/stream</code> · captura: <code>/capture</code></p><img src="/stream">
)HTML";

static esp_err_t index_handler(httpd_req_t *req) {
  httpd_resp_set_type(req, "text/html; charset=utf-8");
  return httpd_resp_send(req, INDEX_HTML, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) return httpd_resp_send_500(req);
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  esp_err_t result = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return result;
}

static esp_err_t stream_handler(httpd_req_t *req) {
  static const char *const content_type = "multipart/x-mixed-replace;boundary=frame";
  static const char *const boundary = "\r\n--frame\r\n";
  char frame_prefix[128];
  StreamDiagnostics diag;
  const uint32_t diag_started_ms = millis();
  const char *exit_reason = "unknown";
  httpd_resp_set_type(req, content_type);
  httpd_resp_set_hdr(req, "Cache-Control", "no-cache");

  while (true) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      exit_reason = "camera_fb_get_null";
      break;
    }
    const size_t jpeg_len = fb->len;
    const int prefix_len = snprintf(frame_prefix, sizeof(frame_prefix),
        "%sContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
        boundary, static_cast<unsigned>(jpeg_len));
    if (prefix_len <= 0 || prefix_len >= static_cast<int>(sizeof(frame_prefix))) {
      esp_camera_fb_return(fb);
      exit_reason = "frame_header_too_large";
      break;
    }
    const uint32_t send_started_us = micros();
    diag.send_attempts++;
    const char *send_stage = "boundary_header";
    esp_err_t result = httpd_resp_send_chunk(req, frame_prefix, prefix_len);
    if (result == ESP_OK) {
      send_stage = "jpeg";
      result = httpd_resp_send_chunk(req, (const char *)fb->buf, jpeg_len);
    }
    const uint32_t send_us = micros() - send_started_us;
    esp_camera_fb_return(fb);
    diag.send_sum_us += send_us;
    diag.send_max_us = max(diag.send_max_us, send_us);
    diag.last_send_stage = send_stage;
    if (result == ESP_OK) {
      const uint32_t frame_sent_ms = millis();
      if (diag.frames_sent > 0) {
        diag.max_frame_interval_ms = max(
            diag.max_frame_interval_ms, frame_sent_ms - diag.last_frame_sent_ms);
      }
      diag.frames_sent++;
      diag.last_frame_sent_ms = frame_sent_ms;
      diag.jpeg_sum_bytes += jpeg_len;
      diag.jpeg_max_bytes = max(diag.jpeg_max_bytes, static_cast<uint32_t>(jpeg_len));
      diag.last_jpeg_bytes = jpeg_len;
    } else {
      diag.send_failures++;
      diag.last_send_error = result;
      diag.last_send_error_name = esp_err_to_name(result);
    }
    if (result != ESP_OK) {
      exit_reason = "http_send_chunk_error";
      break;
    }

    const uint32_t elapsed_ms = millis() - diag_started_ms;
    if (elapsed_ms >= diag.next_report_ms) {
      report_stream_diagnostics(diag, elapsed_ms, "periodic", "running");
      diag.next_report_ms = elapsed_ms + STREAM_REPORT_MS;
    }
  }
  const esp_err_t close_result = httpd_resp_send_chunk(req, nullptr, 0);
  if (close_result != ESP_OK) {
    diag.close_error = close_result;
    diag.close_error_name = esp_err_to_name(close_result);
    if (strcmp(exit_reason, "unknown") == 0) exit_reason = "http_stream_close_error";
  }
  const uint32_t final_elapsed_ms = millis() - diag_started_ms;
  report_stream_diagnostics(diag, final_elapsed_ms, "final", exit_reason);
  return ESP_OK;
}

static void start_server() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.send_wait_timeout = 3;
  httpd_handle_t server = nullptr;
  if (httpd_start(&server, &config) != ESP_OK) {
    Serial.println("ERRO_HTTP");
    return;
  }
  httpd_uri_t index_uri = {.uri = "/", .method = HTTP_GET, .handler = index_handler, .user_ctx = nullptr};
  httpd_uri_t capture_uri = {.uri = "/capture", .method = HTTP_GET, .handler = capture_handler, .user_ctx = nullptr};
  httpd_uri_t stream_uri = {.uri = "/stream", .method = HTTP_GET, .handler = stream_handler, .user_ctx = nullptr};
  httpd_register_uri_handler(server, &index_uri);
  httpd_register_uri_handler(server, &capture_uri);
  httpd_register_uri_handler(server, &stream_uri);
}

void setup() {
  Serial.begin(115200);
  load_wifi_config();
  camera_config_t config;
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
  config.jpeg_quality = 15;
  const bool psram_detected = psramFound();
  Serial.printf("[CAM_DIAG_INIT] psram_detected=%s\n", psram_detected ? "true" : "false");
  if (!psram_detected) {
    Serial.println("ERRO_PSRAM_NECESSARIA");
    while (true) delay(1000);
  }
  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("ERRO_CAMERA");
    while (true) delay(1000);
  }
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(configured_wifi_ssid.c_str(), configured_wifi_password.c_str());
  Serial.print("WIFI");
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 15000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("ERRO_WIFI");
    return;
  }
  Serial.print("CAMERA_IP=");
  Serial.println(WiFi.localIP());
  Serial.printf("[CAM_DIAG_WIFI] rssi_dbm=%d\n", WiFi.RSSI());
  if (MDNS.begin("esp32-cam")) {
    Serial.println("CAMERA_MDNS=http://esp32-cam.local/");
  }
  start_server();
}

void loop() {
  handle_serial_provisioning();
  delay(1000);
}
