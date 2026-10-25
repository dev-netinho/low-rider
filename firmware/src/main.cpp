#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

#ifdef USE_LOCAL_WIFI
#include "secrets.h"
#undef WIFI_SSID
#undef WIFI_PASSWORD
#define WIFI_SSID ROBOT_WIFI_SSID
#define WIFI_PASSWORD ROBOT_WIFI_PASSWORD
#endif

#ifndef API_BASE_URL
#define API_BASE_URL "http://host.wokwi.internal:8765"
#endif
#ifndef WIFI_SSID
#define WIFI_SSID "Wokwi-GUEST"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

namespace Pins {
constexpr uint8_t LEFT_IN1 = 18;
constexpr uint8_t LEFT_IN2 = 19;
constexpr uint8_t LEFT_PWM = 23;
constexpr uint8_t RIGHT_IN1 = 16;
constexpr uint8_t RIGHT_IN2 = 17;
constexpr uint8_t RIGHT_PWM = 22;
constexpr uint8_t RELAY_PUMP = 25;
constexpr uint8_t RELAY_SOUND = 26;
constexpr uint8_t EMERGENCY_BUTTON = 32;
}  // namespace Pins

constexpr uint8_t RELAY_ON = LOW;
constexpr uint8_t RELAY_OFF = HIGH;
constexpr uint32_t MOTOR_PWM_FREQUENCY_HZ = 20000;
constexpr uint8_t MOTOR_PWM_RESOLUTION_BITS = 10;
constexpr uint8_t LEFT_PWM_CHANNEL = 0;
constexpr uint8_t RIGHT_PWM_CHANNEL = 1;
constexpr uint32_t COMMAND_TIMEOUT_MS = 1000;
constexpr uint32_t COMMAND_POLL_MS = 120;
constexpr uint32_t TELEMETRY_MS = 700;

struct DesiredState {
  int left = 0;
  int right = 0;
  bool pump = false;
  bool sound = false;
  bool emergency = false;
  uint32_t sequence = 0;
};

DesiredState desired;
uint32_t lastValidCommandMs = 0;
uint32_t lastCommandPollMs = 0;
uint32_t lastTelemetryMs = 0;
bool localSafetyStop = true;

int clampMotor(int value) {
  return constrain(value, -100, 100);
}

void setupMotorPwm() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(Pins::LEFT_PWM, MOTOR_PWM_FREQUENCY_HZ, MOTOR_PWM_RESOLUTION_BITS);
  ledcAttach(Pins::RIGHT_PWM, MOTOR_PWM_FREQUENCY_HZ, MOTOR_PWM_RESOLUTION_BITS);
#else
  ledcSetup(LEFT_PWM_CHANNEL, MOTOR_PWM_FREQUENCY_HZ, MOTOR_PWM_RESOLUTION_BITS);
  ledcSetup(RIGHT_PWM_CHANNEL, MOTOR_PWM_FREQUENCY_HZ, MOTOR_PWM_RESOLUTION_BITS);
  ledcAttachPin(Pins::LEFT_PWM, LEFT_PWM_CHANNEL);
  ledcAttachPin(Pins::RIGHT_PWM, RIGHT_PWM_CHANNEL);
#endif
}

void writeMotorPwm(uint8_t pwmPin, uint32_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(pwmPin, duty);
#else
  ledcWrite(pwmPin == Pins::LEFT_PWM ? LEFT_PWM_CHANNEL : RIGHT_PWM_CHANNEL, duty);
#endif
}

void writeMotor(uint8_t in1, uint8_t in2, uint8_t pwmPin, int signedPower) {
  const int power = clampMotor(signedPower);
  if (power > 0) {
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);
  } else if (power < 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, HIGH);
  } else {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
  }
  writeMotorPwm(pwmPin, map(abs(power), 0, 100, 0, (1 << MOTOR_PWM_RESOLUTION_BITS) - 1));
}

void allOutputsOff() {
  writeMotor(Pins::LEFT_IN1, Pins::LEFT_IN2, Pins::LEFT_PWM, 0);
  writeMotor(Pins::RIGHT_IN1, Pins::RIGHT_IN2, Pins::RIGHT_PWM, 0);
  digitalWrite(Pins::RELAY_PUMP, RELAY_OFF);
  digitalWrite(Pins::RELAY_SOUND, RELAY_OFF);
}

void applyDesiredState() {
  const bool emergencyButton = digitalRead(Pins::EMERGENCY_BUTTON) == LOW;
  const bool timedOut = millis() - lastValidCommandMs > COMMAND_TIMEOUT_MS;
  localSafetyStop = desired.emergency || emergencyButton || timedOut;

  if (localSafetyStop) {
    allOutputsOff();
    return;
  }
  writeMotor(Pins::LEFT_IN1, Pins::LEFT_IN2, Pins::LEFT_PWM, desired.left);
  writeMotor(Pins::RIGHT_IN1, Pins::RIGHT_IN2, Pins::RIGHT_PWM, desired.right);
  digitalWrite(Pins::RELAY_PUMP, desired.pump ? RELAY_ON : RELAY_OFF);
  digitalWrite(Pins::RELAY_SOUND, desired.sound ? RELAY_ON : RELAY_OFF);
}

bool fetchCommand() {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setTimeout(700);
  http.begin(String(API_BASE_URL) + "/api/robot/command");
  const int status = http.GET();
  if (status != HTTP_CODE_OK) {
    http.end();
    return false;
  }

  JsonDocument document;
  const DeserializationError error = deserializeJson(document, http.getStream());
  http.end();
  if (error) return false;

  desired.sequence = document["seq"] | desired.sequence;
  desired.left = c                                                                                                                 l  ampMotor(document["left"] | 0);
  desired.right = clampMotor(document["right"] | 0);
  desired.pump = document["pump"] | false;
  desired.sound = document["sound"] | false;
  desired.emergency = document["emergency"] | false;
  lastValidCommandMs = millis();
  return true;
}

void sendTelemetry() {
  if (WiFi.status() != WL_CONNECTED) return;
  JsonDocument document;
  document["sequence"] = desired.sequence;
  document["safety_stop"] = localSafetyStop;
  document["emergency_button"] = digitalRead(Pins::EMERGENCY_BUTTON) == LOW;
  document["wifi_rssi_dbm"] = WiFi.RSSI();
  document["uptime_ms"] = millis();

  String body;
  serializeJson(document, body);
  HTTPClient http;
  http.setTimeout(700);
  http.begin(String(API_BASE_URL) + "/api/robot/telemetry");
  http.addHeader("Content-Type", "application/json");
  http.POST(body);
  http.end();
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Conectando ao Wi-Fi");
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 12000) {
    delay(250);
    Serial.print('.');
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(" conectado: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println(" indisponível; saídas permanecem desligadas");
  }
}

void setup() {
  Serial.begin(115200);
  // Os relés são acionados em nível baixo. Definir HIGH antes de habilitar a
  // saída evita o pulso LOW que ocorria durante a inicialização do ESP32.
  digitalWrite(Pins::RELAY_PUMP, RELAY_OFF);
  digitalWrite(Pins::RELAY_SOUND, RELAY_OFF);
  pinMode(Pins::RELAY_PUMP, OUTPUT_OPEN_DRAIN);
  pinMode(Pins::RELAY_SOUND, OUTPUT_OPEN_DRAIN);

  pinMode(Pins::LEFT_IN1, OUTPUT);
  pinMode(Pins::LEFT_IN2, OUTPUT);
  pinMode(Pins::LEFT_PWM, OUTPUT);
  pinMode(Pins::RIGHT_IN1, OUTPUT);
  pinMode(Pins::RIGHT_IN2, OUTPUT);
  pinMode(Pins::RIGHT_PWM, OUTPUT);
  setupMotorPwm();
  pinMode(Pins::EMERGENCY_BUTTON, INPUT_PULLUP);
  allOutputsOff();
  connectWiFi();
  lastValidCommandMs = millis();
}

void loop() {
  const uint32_t now = millis();

  if (now - lastCommandPollMs >= COMMAND_POLL_MS) {
    lastCommandPollMs = now;
    fetchCommand();
  }
  applyDesiredState();

  if (now - lastTelemetryMs >= TELEMETRY_MS) {
    lastTelemetryMs = now;
    sendTelemetry();
    Serial.printf(
        "seq=%lu L=%d R=%d safety=%s pump=%s sound=%s\n",
        static_cast<unsigned long>(desired.sequence), desired.left, desired.right,
        localSafetyStop ? "ON" : "OFF", desired.pump ? "ON" : "OFF",
        desired.sound ? "ON" : "OFF");
  }
  delay(5);
}
