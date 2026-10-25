#include <Arduino.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>

// Rede usada pelo robô. O ESP hospeda a página; nenhum notebook é necessário.
constexpr char WIFI_SSID[] = "CONFIGURE_WIFI_SSID";
constexpr char WIFI_PASSWORD[] = "CONFIGURE_WIFI_PASSWORD";
constexpr char AP_SSID[] = "Robo-C6";
constexpr char AP_PASSWORD[] = "robotica123";

constexpr int PWMA = 23;
constexpr int AIN1 = 18;
constexpr int AIN2 = 19;
constexpr int PWMB = 22;
constexpr int BIN1 = 20;
constexpr int BIN2 = 21;
// 20 kHz moves the bridge switching above the audible motor squeal band.
constexpr uint32_t PWM_FREQUENCY_HZ = 20000;
constexpr uint8_t PWM_RESOLUTION_BITS = 10;
constexpr uint8_t PWM_CHANNEL_A = 0;
constexpr uint8_t PWM_CHANNEL_B = 1;
constexpr unsigned long COMMAND_TIMEOUT_MS = 800;

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

WebServer server(80);
String configuredSsid;
String configuredPassword;
String serialLine;
unsigned long lastCommand = 0;
int targetLeft = 0;
int targetRight = 0;
int currentLeft = 0;
int currentRight = 0;

const char PAGE[] PROGMEM = R"HTML(
<!doctype html><html lang="pt-BR"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robô C6</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif}body{max-width:520px;margin:0 auto;padding:24px;background:#101614;color:#eef7f2}h1{margin:0 0 6px}p{color:#b5c8bf}.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;max-width:320px;margin:26px auto}.pad button,#stop{min-height:64px;border:0;border-radius:14px;background:#2b7567;color:white;font-size:1.1rem;font-weight:700;touch-action:none}.pad button:active,#stop:active{background:#8bd33e;color:#102016}.blank{visibility:hidden}#stop{display:block;width:100%;background:#a83f4c;margin-top:12px}.speed{display:block;margin:20px 0;font-weight:700}.speed input{width:100%}#state{padding:12px;border-radius:10px;background:#1c2b26;color:#9ce27d;text-align:center}
</style><h1>Robô C6</h1><p>Controle direto por Wi‑Fi · solte o botão para parar</p><div id="state">Conectando…</div><label class="speed">Potência: <output id="v">45</output>%<input id="speed" type="range" min="15" max="100" value="45" step="5"></label><div class="pad"><span class="blank"></span><button data-drive="f">▲<br>Frente</button><span class="blank"></span><button data-drive="l">◀<br>Esq.</button><button id="stop">STOP</button><button data-drive="r">▶<br>Dir.</button><span class="blank"></span><button data-drive="b">▼<br>Ré</button><span class="blank"></span></div><script>
const state=document.querySelector('#state'),speed=document.querySelector('#speed'),value=document.querySelector('#v');let timer=null,active=null;speed.oninput=()=>value.textContent=speed.value;
const vectors={f:[1,1],b:[-1,-1],l:[.45,1],r:[1,.45]};let requestBusy=false,pending=null;
function send(a,b){pending=[Math.round(a),Math.round(b)];if(requestBusy)return;requestBusy=true;const [left,right]=pending;pending=null;fetch(`/drive?left=${left}&right=${right}`,{cache:'no-store'}).then(()=>state.textContent='Comando ativo').catch(()=>state.textContent='Sem resposta do ESP').finally(()=>{requestBusy=false;if(pending)send(pending[0],pending[1])})}
function stop(){active=null;if(timer){clearInterval(timer);timer=null}send(0,0);state.textContent='Parado'}
function start(name){stop();active=name;const v=vectors[name],tick=()=>send(v[0]*speed.value,v[1]*speed.value);tick();timer=setInterval(tick,100);state.textContent='Movendo'}
document.querySelectorAll('[data-drive]').forEach(b=>{b.onpointerdown=e=>{e.preventDefault();b.setPointerCapture?.(e.pointerId);start(b.dataset.drive)};['pointerup','pointercancel','lostpointercapture'].forEach(t=>b.addEventListener(t,stop))});document.querySelector('#stop').onclick=stop;
const keys=new Set(),keyNames=new Set(['w','s','a','d','ArrowUp','ArrowDown','ArrowLeft','ArrowRight']);let keyTimer=null;
function keyboardDrive(){let t=(keys.has('w')||keys.has('ArrowUp')?1:0)-(keys.has('s')||keys.has('ArrowDown')?1:0),turn=(keys.has('d')||keys.has('ArrowRight')?1:0)-(keys.has('a')||keys.has('ArrowLeft')?1:0);if(!t&&!turn){stop();return}if(!t)t=.45;let l=t+turn*.55,r=t-turn*.55,m=Math.max(1,Math.abs(l),Math.abs(r));send(l/m*speed.value,r/m*speed.value);state.textContent='Curva suave'}
window.onkeydown=e=>{if(e.code==='Space'){e.preventDefault();keys.clear();stop();return}if(keyNames.has(e.key)){e.preventDefault();keys.add(e.key);if(!keyTimer)keyTimer=setInterval(keyboardDrive,100);keyboardDrive()}};window.onkeyup=e=>{if(keyNames.has(e.key)){e.preventDefault();keys.delete(e.key);keyboardDrive()}};window.onblur=()=>{keys.clear();if(keyTimer){clearInterval(keyTimer);keyTimer=null}stop()};send(0,0);
</script></html>
)HTML";

int clampPercent(int value) { return value < -100 ? -100 : (value > 100 ? 100 : value); }

void setChannel(int pwmPin, int in1, int in2, int percent) {
  percent = clampPercent(percent);
  if (percent == 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
    writePwm(pwmPin, 0);
    return;
  }
  if (percent > 0) { digitalWrite(in1, HIGH); digitalWrite(in2, LOW); }
  else { digitalWrite(in1, LOW); digitalWrite(in2, HIGH); }
  const uint32_t duty = map(abs(percent), 0, 100, 0, (1 << PWM_RESOLUTION_BITS) - 1);
  writePwm(pwmPin, duty);
}

void drivePercent(int left, int right) {
  targetLeft = clampPercent(left);
  targetRight = clampPercent(right);
  lastCommand = millis();
}

void stopMotors() {
  targetLeft = targetRight = currentLeft = currentRight = 0;
  setChannel(PWMA, AIN1, AIN2, 0);
  setChannel(PWMB, BIN1, BIN2, 0);
  lastCommand = millis();
}

void updateMotorRamp() {
  if (currentLeft < targetLeft) currentLeft = min(currentLeft + 2, targetLeft);
  if (currentLeft > targetLeft) currentLeft = max(currentLeft - 2, targetLeft);
  if (currentRight < targetRight) currentRight = min(currentRight + 2, targetRight);
  if (currentRight > targetRight) currentRight = max(currentRight - 2, targetRight);
  setChannel(PWMA, AIN1, AIN2, currentLeft);
  setChannel(PWMB, BIN1, BIN2, currentRight);
}

void handleRoot() { server.send_P(200, "text/html; charset=utf-8", PAGE); }

void handleDrive() {
  if (!server.hasArg("left") || !server.hasArg("right")) { server.send(400, "text/plain", "left/right ausentes"); return; }
  drivePercent(server.arg("left").toInt(), server.arg("right").toInt());
  server.send(200, "application/json", "{\"ok\":true}");
}

void handleStop() { stopMotors(); server.send(200, "application/json", "{\"ok\":true}"); }

void loadWifiConfig() {
  Preferences preferences;
  preferences.begin("wifi", true);
  configuredSsid = preferences.getString("ssid", WIFI_SSID);
  configuredPassword = preferences.getString("password", WIFI_PASSWORD);
  preferences.end();
}

void handleWifiConfig() {
  if (!server.hasArg("ssid") || !server.hasArg("password")) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"ssid/password ausentes\"}");
    return;
  }
  const String ssid = server.arg("ssid");
  const String password = server.arg("password");
  if (ssid.length() == 0 || ssid.length() > 32 || password.length() > 63) {
    server.send(400, "application/json", "{\"ok\":false,\"error\":\"credenciais invalidas\"}");
    return;
  }
  Preferences preferences;
  preferences.begin("wifi", false);
  preferences.putString("ssid", ssid);
  preferences.putString("password", password);
  preferences.end();
  server.send(202, "application/json", "{\"ok\":true,\"message\":\"salvo; reiniciando\"}");
  delay(250);
  ESP.restart();
}

void handleSerialProvisioning() {
  while (Serial.available()) {
    const char character = static_cast<char>(Serial.read());
    if (character == '\r') continue;
    if (character != '\n') {
      if (serialLine.length() < 160) serialLine += character;
      continue;
    }
    serialLine.trim();
    if (serialLine == "PING") {
      Serial.println("PONG C6");
    } else if (serialLine.startsWith("WIFI\t")) {
      const int separator = serialLine.indexOf('\t', 5);
      if (separator < 0) {
        Serial.println("CFG_ERROR FORMAT");
      } else {
        const String ssid = serialLine.substring(5, separator);
        const String password = serialLine.substring(separator + 1);
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
    } else if (serialLine == "STATUS") {
      Serial.printf("STATUS C6 WIFI=%s IP=%s\n",
                    WiFi.status() == WL_CONNECTED ? "connected" : "ap",
                    WiFi.localIP().toString().c_str());
    } else if (serialLine.length() > 0) {
      Serial.println("CFG_ERROR UNKNOWN_COMMAND");
    }
    serialLine = "";
  }
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(configuredSsid.c_str(), configuredPassword.c_str());
  Serial.printf("Conectando a %s", configuredSsid.c_str());
  const unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 15000) { delay(300); Serial.print('.'); }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nWi-Fi conectado: http://%s/\n", WiFi.localIP().toString().c_str());
    if (MDNS.begin("robo-c6")) Serial.println("Acesse também http://robo-c6.local/");
    return;
  }
  WiFi.mode(WIFI_AP); WiFi.softAP(AP_SSID, AP_PASSWORD);
  Serial.printf("\nWi-Fi doméstico indisponível; AP ativo: http://%s/\n", WiFi.softAPIP().toString().c_str());
}

void setup() {
  Serial.begin(115200);
  loadWifiConfig();
  pinMode(PWMA, OUTPUT); pinMode(AIN1, OUTPUT); pinMode(AIN2, OUTPUT);
  pinMode(PWMB, OUTPUT); pinMode(BIN1, OUTPUT); pinMode(BIN2, OUTPUT);
  setupPwm();
  stopMotors();
  connectWiFi();
  server.on("/", HTTP_GET, handleRoot);
  server.on("/drive", HTTP_GET, handleDrive);
  server.on("/stop", HTTP_GET, handleStop);
  server.on("/wifi", HTTP_POST, handleWifiConfig);
  server.onNotFound([]() { server.send(404, "text/plain", "Nao encontrado"); });
  server.begin();
  Serial.println("Controle web pronto; timeout de segurança: 800 ms");
}

void loop() {
  handleSerialProvisioning();
  server.handleClient();
  if (millis() - lastCommand > COMMAND_TIMEOUT_MS) targetLeft = targetRight = 0;
  updateMotorRamp();
  delay(2);
}
