// Minimal ESP32-C6/TB6612 two-channel bench test.
// The driver VM supply remains external; this sketch only drives logic pins.
constexpr int PWMA = 23;
constexpr int AIN1 = 18;
constexpr int AIN2 = 19;
constexpr int PWMB = 22;
constexpr int BIN1 = 20;
constexpr int BIN2 = 21;
constexpr uint32_t PWM_FREQUENCY_HZ = 20000;
constexpr uint8_t PWM_RESOLUTION_BITS = 10;
constexpr uint8_t PWM_CHANNEL_A = 0;
constexpr uint8_t PWM_CHANNEL_B = 1;
int pwmDuty = 180; // ~70%; adjustable with keys 0..9
unsigned long lastMotionCommand = 0;
constexpr unsigned long COMMAND_TIMEOUT_MS = 800;

int clampPercent(int value) {
  return value < -100 ? -100 : (value > 100 ? 100 : value);
}

void setupPwm() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PWMA, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcAttach(PWMB, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
#else
  ledcSetup(PWM_CHANNEL_A, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcSetup(PWM_CHANNEL_B, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcAttachPin(PWMA, PWM_CHANNEL_A);
  ledcAttachPin(PWMB, PWM_CHANNEL_B);
#endif
}

void writePwm(int pwmPin, uint32_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(pwmPin, duty);
#else
  ledcWrite(pwmPin == PWMA ? PWM_CHANNEL_A : PWM_CHANNEL_B, duty);
#endif
}

void setChannel(int pwmPin, int in1, int in2, int percent) {
  percent = clampPercent(percent);
  if (percent == 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
    writePwm(pwmPin, 0);
    return;
  }
  if (percent > 0) {
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);
  } else {
    digitalWrite(in1, LOW);
    digitalWrite(in2, HIGH);
  }
  writePwm(pwmPin, map(abs(percent), 0, 100, 0, (1 << PWM_RESOLUTION_BITS) - 1));
}

void drivePercent(int left, int right) {
  setChannel(PWMA, AIN1, AIN2, left);
  setChannel(PWMB, BIN1, BIN2, right);
  lastMotionCommand = millis();
}

void stopMotor() {
  drivePercent(0, 0);
}

void forwardMotors() {
  drivePercent(pwmDuty * 100 / 255, pwmDuty * 100 / 255);
}

void reverseMotors() {
  drivePercent(-(pwmDuty * 100 / 255), -(pwmDuty * 100 / 255));
}

void processCommand(String line) {
  line.trim();
  if (line.length() == 0) return;

  int left = 0;
  int right = 0;
  if ((line[0] == 'M' || line[0] == 'm') && sscanf(line.c_str() + 1, "%d %d", &left, &right) == 2) {
    drivePercent(left, right);
    return;
  }

  const char command = line[0];
  if (command == 'f' || command == 'F') forwardMotors();
  else if (command == 'r' || command == 'R') reverseMotors();
  else if (command == 's' || command == 'S') stopMotor();
  else if (command >= '0' && command <= '9') {
    pwmDuty = map(command - '0', 0, 9, 0, 255);
    Serial.print("PWM=");
    Serial.println(pwmDuty);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PWMA, OUTPUT);
  pinMode(AIN1, OUTPUT);
  pinMode(AIN2, OUTPUT);
  pinMode(PWMB, OUTPUT);
  pinMode(BIN1, OUTPUT);
  pinMode(BIN2, OUTPUT);
  setupPwm();
  stopMotor();
  Serial.println("C6 motor control ready: M <left> <right>, f/r/s, 0..9=speed");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    processCommand(line);
  }
  if (millis() - lastMotionCommand > COMMAND_TIMEOUT_MS) stopMotor();
}
