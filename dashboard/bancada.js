"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const ui = {
  liveStatus: $("#liveStatus"),
  liveStatusTitle: $("#liveStatusTitle"),
  liveStatusDetail: $("#liveStatusDetail"),
  modeChip: $("#modeChip"),
  modeButtons: $$("[data-mode]"),
  driveButtons: $$("[data-drive]"),
  stopButton: $("#stopButton"),
  emergencyButton: $("#emergencyButton"),
  headerEmergencyButton: $("#headerEmergencyButton"),
  diagramScroll: $("#diagramScroll"),
  panHint: $("#panHint"),
  powerSlider: $("#powerSlider"),
  powerOutput: $("#powerOutput"),
  pumpButton: $("#pumpButton"),
  soundButton: $("#soundButton"),
  pumpStatus: $("#pumpStatus"),
  soundStatus: $("#soundStatus"),
  speedSource: $("#speedSource"),
  cameraMetric: $("#cameraMetric"),
  visionValues: $("#visionValues"),
  visionSource: $("#visionSource"),
  systemState: $("#systemState"),
  safetyReason: $("#safetyReason"),
  safetyReadout: $("#safetyReadout"),
  leftChannel: $(".left-channel"),
  rightChannel: $(".right-channel"),
  leftChannelValue: $("#leftChannelValue"),
  rightChannelValue: $("#rightChannelValue"),
  pumpRelay: $("#pumpRelay"),
  soundRelay: $("#soundRelay"),
  pumpUnit: $("#pumpUnit"),
  soundUnit: $("#soundUnit"),
  pumpValue: $("#pumpValue"),
  soundValue: $("#soundValue"),
  toast: $("#toast"),
};

const app = {
  state: null,
  activeDrive: null,
  driveTimer: null,
  pollTimer: null,
  toastTimer: null,
  online: false,
};

const MOTOR_MAX_RAD_S = 22;
const criticalStates = new Set(["EMERGENCIA", "SEM_CONEXAO", "SEM_COMANDO", "SEM_VISAO", "OBSTACULO"]);

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || `Falha HTTP ${response.status}`);
    app.online = true;
    return body;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function command(payload, quiet = false) {
  try {
    const state = await api("/api/command", { method: "POST", body: JSON.stringify(payload) });
    app.state = state;
    render(state);
    return state;
  } catch (error) {
    app.online = false;
    renderConnection();
    if (!quiet) showToast(error.message || "Não foi possível enviar o comando.", true);
    return null;
  }
}

function showToast(message, isError = false) {
  window.clearTimeout(app.toastTimer);
  ui.toast.textContent = message;
  ui.toast.classList.toggle("is-error", isError);
  ui.toast.classList.add("is-visible");
  app.toastTimer = window.setTimeout(() => ui.toast.classList.remove("is-visible"), 3400);
}

function hasLiveWebots(state) {
  return Boolean(
    state?.hardware_online
    && state.remote_telemetry?.simulation === "WEBOTS"
    && state.sensors?.vision_source === "WEBOTS_ESP32_CAM"
  );
}

function renderConnection() {
  if (!app.online) {
    ui.liveStatus.dataset.state = "offline";
    ui.liveStatusTitle.textContent = "Servidor desconectado";
    ui.liveStatusDetail.textContent = "Execute python3 server.py";
    return;
  }
  if (hasLiveWebots(app.state)) {
    ui.liveStatus.dataset.state = "live";
    ui.liveStatusTitle.textContent = "Webots conectado";
    ui.liveStatusDetail.textContent = "velocidade medida nas quatro rodas";
  } else {
    ui.liveStatus.dataset.state = "waiting";
    ui.liveStatusTitle.textContent = "Servidor conectado";
    ui.liveStatusDetail.textContent = "pressione Play no Webots";
  }
}

function formatSigned(value, digits = 0) {
  const rounded = Number(value).toFixed(digits).replace(".", ",");
  return `${value > 0 ? "+" : ""}${rounded}`;
}

function directionLabel(value) {
  if (Math.abs(value) < 0.5) return "parado";
  return value > 0 ? "frente" : "ré";
}

function measuredSpeeds(state) {
  const live = hasLiveWebots(state);
  const measured = state.remote_telemetry?.wheel_rad_s;
  if (live && measured && ["m1", "m2", "m3", "m4"].every((key) => Number.isFinite(Number(measured[key])))) {
    return { live: true, values: ["m1", "m2", "m3", "m4"].map((key) => Number(measured[key])) };
  }
  return {
    live: false,
    values: [state.motors.left, state.motors.left, state.motors.right, state.motors.right]
      .map((percent) => percent / 100 * MOTOR_MAX_RAD_S),
  };
}

function setMotorVisual(index, commandPercent, radS, measured) {
  const number = index + 1;
  const unit = $(`#motorM${number}`);
  const value = $(`#m${number}Value`);
  const speed = $(`#m${number}Speed`);
  const bar = $(`#m${number}Bar`);
  const normalizedDirection = Math.abs(radS) > 0.12 ? Math.sign(radS) : Math.sign(commandPercent);
  const rpm = radS * 60 / (2 * Math.PI);
  const magnitude = Math.min(100, Math.abs(radS) / MOTOR_MAX_RAD_S * 100);

  unit.dataset.motion = magnitude < 0.6 ? "stopped" : normalizedDirection >= 0 ? "forward" : "reverse";
  unit.style.setProperty("--spin-duration", `${Math.max(0.16, 2 * Math.PI / Math.max(0.4, Math.abs(radS)))}s`);
  value.textContent = `${formatSigned(commandPercent)}% · ${formatSigned(rpm)} rpm${measured ? " med." : " sim."}`;
  speed.textContent = `${formatSigned(radS, 1)} rad/s`;

  const width = magnitude / 2;
  bar.style.width = `${width}%`;
  bar.style.left = radS >= 0 ? "50%" : `${50 - width}%`;
  bar.style.background = radS >= 0 ? "var(--motor)" : "var(--pending)";
}

function toggleWireGroup(selector, active) {
  $$(selector).forEach((wire) => wire.classList.toggle("is-active", active));
}

function render(state) {
  app.state = state;
  renderConnection();

  ui.modeChip.textContent = state.mode;
  ui.modeButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.mode === state.mode)));
  const manualEnabled = state.mode === "MANUAL" && !state.emergency && state.link_online;
  ui.driveButtons.forEach((button) => { button.disabled = !manualEnabled; });
  ui.stopButton.disabled = !manualEnabled;
  if (!manualEnabled && app.activeDrive) stopDrive(true);

  [ui.emergencyButton, ui.headerEmergencyButton].forEach((button) => {
    button.setAttribute("aria-pressed", String(state.emergency));
    button.textContent = state.emergency ? "LIBERAR" : "PARAR";
  });

  const left = Number(state.motors.left);
  const right = Number(state.motors.right);
  const speeds = measuredSpeeds(state);
  ui.speedSource.textContent = speeds.live ? "medida pelos encoders no Webots" : "estimada pelo comando do simulador";
  setMotorVisual(0, left, speeds.values[0], speeds.live);
  setMotorVisual(1, left, speeds.values[1], speeds.live);
  setMotorVisual(2, right, speeds.values[2], speeds.live);
  setMotorVisual(3, right, speeds.values[3], speeds.live);

  ui.leftChannel.classList.toggle("is-active", Math.abs(left) > 0.5);
  ui.rightChannel.classList.toggle("is-active", Math.abs(right) > 0.5);
  ui.leftChannelValue.textContent = `${formatSigned(left)}% · ${directionLabel(left)}`;
  ui.rightChannelValue.textContent = `${formatSigned(right)}% · ${directionLabel(right)}`;
  toggleWireGroup(".left-signal, .left-output", Math.abs(left) > 0.5);
  toggleWireGroup(".right-signal, .right-output", Math.abs(right) > 0.5);

  const pump = Boolean(state.actuators.pump);
  const sound = Boolean(state.actuators.sound);
  ui.pumpRelay.classList.toggle("is-active", pump);
  ui.soundRelay.classList.toggle("is-active", sound);
  $(".relay-state", ui.pumpRelay).textContent = pump ? "ON" : "OFF";
  $(".relay-state", ui.soundRelay).textContent = sound ? "ON" : "OFF";
  ui.pumpUnit.classList.toggle("is-active", pump);
  ui.soundUnit.classList.toggle("is-active", sound);
  ui.pumpButton.classList.toggle("is-active", pump);
  ui.soundButton.setAttribute("aria-pressed", String(sound));
  toggleWireGroup(".pump-signal, .pump-output", pump);
  toggleWireGroup(".sound-signal, .sound-output", sound);
  ui.pumpValue.textContent = pump ? `ligada · ${(state.actuators.pump_remaining_ms / 1000).toFixed(1).replace(".", ",")} s` : "desligada";
  ui.soundValue.textContent = sound ? "habilitada" : "desligada";
  ui.pumpStatus.textContent = pump ? `desliga em ${(state.actuators.pump_remaining_ms / 1000).toFixed(1).replace(".", ",")} s` : "pulso de 3 s";
  ui.soundStatus.textContent = sound ? "habilitada" : "desligada";

  const sensors = state.sensors;
  ui.cameraMetric.textContent = `${Math.round(sensors.vision_confidence * 100)}% conf. · ${sensors.vision_age_ms} ms`;
  ui.visionValues.textContent = `frente ${Math.round(sensors.vision_front_cm)} · E ${Math.round(sensors.vision_left_cm)} · D ${Math.round(sensors.vision_right_cm)} cm`;
  ui.visionSource.textContent = `fonte: ${String(sensors.vision_source).toLowerCase().replaceAll("_", " ")}`;

  ui.systemState.textContent = state.system_state.replaceAll("_", " ");
  ui.safetyReason.textContent = state.safety_reason;
  ui.safetyReadout.dataset.level = criticalStates.has(state.system_state)
    ? "critical"
    : state.mode === "PARADO" ? "warning" : "safe";
}

const driveVectors = {
  forward: [1, 0],
  backward: [-1, 0],
  left: [0, -1],
  right: [0, 1],
};

function sendActiveDrive() {
  if (!app.activeDrive || app.state?.mode !== "MANUAL") return;
  const [throttleFactor, steeringFactor] = driveVectors[app.activeDrive];
  const power = Number(ui.powerSlider.value);
  command({ action: "drive", throttle: throttleFactor * power, steering: steeringFactor * power }, true);
}

function startDrive(direction) {
  if (app.state?.mode !== "MANUAL" || app.activeDrive === direction) return;
  stopDrive(true);
  app.activeDrive = direction;
  ui.driveButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.drive === direction));
  sendActiveDrive();
  app.driveTimer = window.setInterval(sendActiveDrive, 220);
}

function stopDrive(quiet = false) {
  if (!app.activeDrive && quiet) return;
  app.activeDrive = null;
  window.clearInterval(app.driveTimer);
  app.driveTimer = null;
  ui.driveButtons.forEach((button) => button.classList.remove("is-active"));
  if (app.state?.mode === "MANUAL") command({ action: "drive", throttle: 0, steering: 0 }, quiet);
}

ui.modeButtons.forEach((button) => button.addEventListener("click", () => command({ action: "set_mode", mode: button.dataset.mode })));
ui.driveButtons.forEach((button) => {
  button.addEventListener("pointerdown", (event) => { event.preventDefault(); button.setPointerCapture?.(event.pointerId); startDrive(button.dataset.drive); });
  button.addEventListener("pointerup", () => stopDrive());
  button.addEventListener("pointercancel", () => stopDrive(true));
  button.addEventListener("lostpointercapture", () => stopDrive(true));
});
ui.stopButton.addEventListener("click", () => stopDrive());
ui.powerSlider.addEventListener("input", () => { ui.powerOutput.value = `${ui.powerSlider.value}%`; if (app.activeDrive) sendActiveDrive(); });
ui.pumpButton.addEventListener("click", () => command({ action: "pump", enabled: !app.state?.actuators?.pump, duration_ms: 3000 }));
ui.soundButton.addEventListener("click", () => command({ action: "sound", enabled: !app.state?.actuators?.sound }));
ui.emergencyButton.addEventListener("click", () => command({ action: "emergency", active: !app.state?.emergency }));
ui.headerEmergencyButton.addEventListener("click", () => command({ action: "emergency", active: !app.state?.emergency }));
ui.diagramScroll.addEventListener("scroll", () => {
  if (ui.diagramScroll.scrollLeft > 8) ui.panHint.classList.add("is-dismissed");
}, { passive: true });

const keyDirections = { w: "forward", ArrowUp: "forward", s: "backward", ArrowDown: "backward", a: "left", ArrowLeft: "left", d: "right", ArrowRight: "right" };
function focusOwnsKeyboard() {
  const active = document.activeElement;
  return Boolean(active?.closest?.("input, button, textarea, select, .diagram-scroll"));
}
window.addEventListener("keydown", (event) => {
  if (event.code === "Space" && !event.repeat && !focusOwnsKeyboard()) {
    event.preventDefault();
    stopDrive(true);
    // Sempre envia uma parada explícita, mesmo quando nenhuma tecla de
    // direção estava marcada como ativa no navegador.
    command({ action: "drive", throttle: 0, steering: 0 }, true);
    return;
  }
  const direction = keyDirections[event.key];
  if (direction && !event.repeat && !focusOwnsKeyboard()) {
    event.preventDefault();
    startDrive(direction);
  }
});
window.addEventListener("keyup", (event) => {
  if (keyDirections[event.key] && !focusOwnsKeyboard()) {
    event.preventDefault();
    stopDrive(true);
  }
});
window.addEventListener("blur", () => stopDrive(true));

async function poll() {
  try {
    const state = await api("/api/state");
    app.state = state;
    render(state);
  } catch {
    app.online = false;
    renderConnection();
  }
}

poll();
app.pollTimer = window.setInterval(poll, 180);
