#include <Arduino.h>
#include <WiFi.h>

#include "secrets.h"

namespace Pins {
constexpr uint8_t AIN1 = 18;
constexpr uint8_t AIN2 = 19;
constexpr uint8_t PWMA = 23;
constexpr uint8_t BIN1 = 16;
constexpr uint8_t BIN2 = 17;
constexpr uint8_t PWMB = 22;
constexpr uint8_t RELAY_PUMP = 25;
constexpr uint8_t RELAY_SOUND = 26;
constexpr uint8_t BOOT_BUTTON = 0;
}  // namespace Pins

constexpr uint8_t RELAY_OFF = HIGH;
constexpr uint8_t TEST_PWM = 90;       // Aproximadamente 35% de 255.
constexpr uint32_t PULSE_MS = 650;     // Pulso curto para a roda suspensa.
constexpr uint32_t DEBOUNCE_MS = 60;

bool pulseActive = false;
bool nextDirectionForward = true;
bool previousButtonReleased = true;
uint32_t pulseStartedAt = 0;
uint32_t buttonChangedAt = 0;

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(ROBOT_WIFI_SSID, ROBOT_WIFI_PASSWORD);
  Serial.print("Conectando ao Wi-Fi");
  const uint32_t startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 15000) {
    delay(250);
    Serial.print('.');
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(" conectado. IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println(" indisponivel; o teste local pelo BOOT continua funcionando");
  }
}

void stopMotors() {
  analogWrite(Pins::PWMA, 0);
  analogWrite(Pins::PWMB, 0);
  digitalWrite(Pins::AIN1, LOW);
  digitalWrite(Pins::AIN2, LOW);
  digitalWrite(Pins::BIN1, LOW);
  digitalWrite(Pins::BIN2, LOW);
  pulseActive = false;
}

void startMotorAPulse(bool forward) {
  stopMotors();
  digitalWrite(Pins::AIN1, forward ? HIGH : LOW);
  digitalWrite(Pins::AIN2, forward ? LOW : HIGH);
  analogWrite(Pins::PWMA, TEST_PWM);
  pulseStartedAt = millis();
  pulseActive = true;
  Serial.printf("Motor A: %s por %lu ms, PWM=%u\n",
                forward ? "frente" : "re", static_cast<unsigned long>(PULSE_MS),
                TEST_PWM);
}

void setup() {
  Serial.begin(115200);

  digitalWrite(Pins::RELAY_PUMP, RELAY_OFF);
  digitalWrite(Pins::RELAY_SOUND, RELAY_OFF);
  pinMode(Pins::RELAY_PUMP, OUTPUT_OPEN_DRAIN);
  pinMode(Pins::RELAY_SOUND, OUTPUT_OPEN_DRAIN);

  pinMode(Pins::AIN1, OUTPUT);
  pinMode(Pins::AIN2, OUTPUT);
  pinMode(Pins::PWMA, OUTPUT);
  pinMode(Pins::BIN1, OUTPUT);
  pinMode(Pins::BIN2, OUTPUT);
  pinMode(Pins::PWMB, OUTPUT);
  pinMode(Pins::BOOT_BUTTON, INPUT_PULLUP);
  stopMotors();

  connectWiFi();

  Serial.println("Teste seguro do TB6612 pronto.");
  Serial.println("Pressione BOOT depois da inicializacao.");
  Serial.println("Cada toque alterna frente/re e para automaticamente.");
}

void loop() {
  if (pulseActive && millis() - pulseStartedAt >= PULSE_MS) {
    stopMotors();
    Serial.println("Motor A: parado automaticamente");
  }

  const bool buttonReleased = digitalRead(Pins::BOOT_BUTTON) == HIGH;
  if (buttonReleased != previousButtonReleased &&
      millis() - buttonChangedAt >= DEBOUNCE_MS) {
    buttonChangedAt = millis();
    previousButtonReleased = buttonReleased;
    if (!buttonReleased && !pulseActive) {
      startMotorAPulse(nextDirectionForward);
      nextDirectionForward = !nextDirectionForward;
    }
  }

  if (Serial.available()) {
    const char command = static_cast<char>(Serial.read());
    if (command == 'a' && !pulseActive) {
      startMotorAPulse(true);
    } else if (command == 'r' && !pulseActive) {
      startMotorAPulse(false);
    } else if (command == 's') {
      stopMotors();
      Serial.println("Parada solicitada");
    }
  }

  delay(5);
}
