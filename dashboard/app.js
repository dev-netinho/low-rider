"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const ui = {
  connectionPill: $("#connectionPill"),
  connectionText: $("#connectionText"),
  connectionShort: $("#connectionShort"),
  networkSettingsButton: $("#networkSettingsButton"),
  networkDialog: $("#networkDialog"),
  networkDialogClose: $("#networkDialogClose"),
  networkCameraUrl: $("#networkCameraUrl"),
  networkRobotUrl: $("#networkRobotUrl"),
  networkWifiSsid: $("#networkWifiSsid"),
  networkWifiPassword: $("#networkWifiPassword"),
  networkSaveEndpoints: $("#networkSaveEndpoints"),
  networkProvisionWifi: $("#networkProvisionWifi"),
  networkDialogStatus: $("#networkDialogStatus"),
  usbConnectButton: $("#usbConnectButton"),
  usbSendWifi: $("#usbSendWifi"),
  usbBoardTarget: $("#usbBoardTarget"),
  usbPortStatus: $("#usbPortStatus"),
  localClock: $("#localClock"),
  emergencyButton: $("#emergencyButton"),
  standbyButton: $("#standbyButton"),
  modeReadout: $("#modeReadout"),
  modeButtons: $$("[data-mode]"),
  panelTabs: $$("[data-panel-tab]"),
  tabPanels: $$("[data-panel]"),
  visionPanel: $("#visionPanel"),
  directionButtons: $$("[data-drive]"),
  stopButton: $("#stopButton"),
  speedLimit: $("#speedLimit"),
  speedOutput: $("#speedOutput"),
  pumpButton: $("#pumpButton"),
  pumpStatus: $("#pumpStatus"),
  soundButton: $("#soundButton"),
  soundStatus: $("#soundStatus"),
  soundCommands: $$("[data-sound-action]"),
  soundVolume: $("#soundVolume"),
  soundVolumeOutput: $("#soundVolumeOutput"),
  cameraFeed: $("#cameraFeed"),
  cameraFreshness: $("#cameraFreshness"),
  cameraState: $("#cameraState"),
  cameraLastReceived: $("#cameraLastReceived"),
  cameraLastDisplayed: $("#cameraLastDisplayed"),
  cameraHubStatus: $("#cameraHubStatus"),
  cameraRecordState: $("#cameraRecordState"),
  cameraUrl: $("#cameraUrl"),
  connectCamera: $("#connectCamera"),
  autonomousModeStatus: $("#autonomousModeStatus"),
  autonomousModeDetail: $("#autonomousModeDetail"),
  safetyMessage: $("#safetyMessage"),
  safetyReason: $("#safetyReason"),
  cameraFps: $("#cameraFps"),
  cameraMaxGap: $("#cameraMaxGap"),
  cameraLatency: $("#cameraLatency"),
  visionClock: $("#visionClock"),
  targetReadout: $("#targetReadout"),
  targetDistance: $("#targetDistance"),
  targetConfidence: $("#targetConfidence"),
  autonomousAction: $("#autonomousAction"),
  poseReadout: $("#poseReadout"),
  cameraCanvas: $("#cameraCanvas"),
  leftMotorValue: $("#leftMotorValue"),
  rightMotorValue: $("#rightMotorValue"),
  leftMotorBar: $("#leftMotorBar"),
  rightMotorBar: $("#rightMotorBar"),
  batteryValue: $("#batteryValue"),
  batteryBar: $("#batteryBar"),
  rssiValue: $("#rssiValue"),
  transportValue: $("#transportValue"),
  signalBars: $("#signalBars"),
  systemState: $("#systemState"),
  heartbeatAge: $("#heartbeatAge"),
  obstacleRange: $("#obstacleRange"),
  obstacleOutput: $("#obstacleOutput"),
  linkToggle: $("#linkToggle"),
  resetButton: $("#resetButton"),
  scenarioButtons: $$("[data-scenario]"),
  eventLog: $("#eventLog"),
  eventCount: $("#eventCount"),
  footerUptime: $("#footerUptime"),
  toastRegion: $("#toastRegion"),
  throttleJoystick: $("#throttleJoystick"),
  steeringJoystick: $("#steeringJoystick"),
  throttleReadout: $("#throttleReadout"),
  steeringReadout: $("#steeringReadout"),
};

const app = {
  state: null,
  online: false,
  polling: false,
  activeDirections: new Set(),
  manualAxes: { throttle: 0, steering: 0 },
  lastDriveSignature: "",
  lastRenderedEvent: 0,
  obstaclePending: null,
  drawFrame: 0,
  cameraLoopRunning: false,
  cameraFrameRequest: null,
  activePanel: "manual",
  reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)"),
  camera: {
    controller: null,
    reconnectTimer: null,
    reconnectDelay: 1000,
    generation: 0,
    lastReceivedAt: 0,
    lastDisplayedAt: 0,
    streamOpenedAt: 0,
    metricsFirstFrameAt: 0,
    frameTimes: [],
    maxGapMs: null,
    displayDelayMs: null,
    lastSequence: 0,
    streamOpen: false,
    objectUrl: "",
    lastStopAttemptAt: 0,
    hubStatus: null,
  },
  usb: {
    port: null,
    board: "",
  },
};

const criticalStates = new Set(["EMERGENCIA", "SEM_CONEXAO", "SEM_COMANDO", "SEM_VISAO", "OBSTACULO"]);
const warningStates = new Set(["PARADO"]);

const textDecoder = new TextDecoder();

class BrowserMjpegParser {
  constructor(boundary) {
    this.boundary = new TextEncoder().encode(`--${boundary}`);
    this.buffer = new Uint8Array(0);
  }

  append(chunk) {
    const merged = new Uint8Array(this.buffer.length + chunk.length);
    merged.set(this.buffer);
    merged.set(chunk, this.buffer.length);
    this.buffer = merged;
    const frames = [];
    while (true) {
      const marker = this.indexOf(this.boundary);
      if (marker < 0) {
        const keep = Math.max(0, this.boundary.length - 1);
        this.buffer = this.buffer.slice(Math.max(0, this.buffer.length - keep));
        break;
      }
      if (marker > 0) this.buffer = this.buffer.slice(marker);
      const markerEnd = this.boundary.length;
      if (this.buffer.length < markerEnd + 2) break;
      if (this.buffer[markerEnd] !== 13 || this.buffer[markerEnd + 1] !== 10) {
        this.buffer = this.buffer.slice(markerEnd);
        continue;
      }
      const headerEnd = this.indexOf(new Uint8Array([13, 10, 13, 10]), markerEnd + 2);
      if (headerEnd < 0) break;
      const headers = textDecoder.decode(this.buffer.slice(markerEnd + 2, headerEnd)).split("\r\n");
      const contentLengthLine = headers.find((line) => line.toLowerCase().startsWith("content-length:"));
      const contentLength = contentLengthLine ? Number(contentLengthLine.split(":", 2)[1].trim()) : NaN;
      if (!Number.isInteger(contentLength) || contentLength <= 0) {
        this.buffer = this.buffer.slice(headerEnd + 4);
        continue;
      }
      const bodyStart = headerEnd + 4;
      const bodyEnd = bodyStart + contentLength;
      if (this.buffer.length < bodyEnd) break;
      const jpeg = this.buffer.slice(bodyStart, bodyEnd);
      this.buffer = this.buffer.slice(bodyEnd);
      if (this.buffer[0] === 13 && this.buffer[1] === 10) this.buffer = this.buffer.slice(2);
      if (jpeg[0] === 0xff && jpeg[1] === 0xd8 && jpeg[jpeg.length - 2] === 0xff && jpeg[jpeg.length - 1] === 0xd9) {
        frames.push(jpeg);
      }
    }
    return frames;
  }

  indexOf(needle, start = 0) {
    outer: for (let index = start; index <= this.buffer.length - needle.length; index += 1) {
      for (let offset = 0; offset < needle.length; offset += 1) {
        if (this.buffer[index + offset] !== needle[offset]) continue outer;
      }
      return index;
    }
    return -1;
  }
}

function formatAge(timestamp) {
  if (!timestamp) return "—";
  const age = Math.max(0, performance.now() - timestamp);
  if (age < 1000) return `${Math.round(age)} ms atrás`;
  return `${(age / 1000).toFixed(1).replace(".", ",")} s atrás`;
}

function formatMeasured(value, suffix = "") {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "não medido"
    : `${value}${suffix}`;
}

function resetCameraMetrics() {
  app.camera.lastReceivedAt = 0;
  app.camera.lastDisplayedAt = 0;
  app.camera.streamOpenedAt = 0;
  app.camera.metricsFirstFrameAt = 0;
  app.camera.frameTimes = [];
  app.camera.maxGapMs = null;
  app.camera.displayDelayMs = null;
  renderCameraMetrics();
}

function renderCameraMetrics() {
  const now = performance.now();
  app.camera.frameTimes = app.camera.frameTimes.filter((timestamp) => now - timestamp <= 5000);
  const observedMs = app.camera.metricsFirstFrameAt
    ? Math.min(5000, now - app.camera.metricsFirstFrameAt)
    : 0;
  const fps = app.camera.frameTimes.length >= 2 && observedMs >= 1000
    ? app.camera.frameTimes.length * 1000 / observedMs
    : null;
  ui.cameraFps.textContent = `FPS medido: ${formatMeasured(fps === null ? null : Math.round(fps * 10) / 10)}`;
  ui.cameraMaxGap.textContent = `Maior intervalo: ${formatMeasured(app.camera.maxGapMs === null ? null : Math.round(app.camera.maxGapMs), " ms")}`;
  ui.cameraLatency.textContent = `Recebido → exibido: ${formatMeasured(app.camera.displayDelayMs === null ? null : Math.round(app.camera.displayDelayMs), " ms")}`;
}

function setCameraStatus(state, detail = "") {
  ui.cameraFreshness.dataset.state = state;
  const labels = {
    connecting: "Conectando à câmera…",
    live: "QUADRO NOVO · ao vivo",
    stale: "VÍDEO SEM QUADRO NOVO",
    offline: "VÍDEO INDISPONÍVEL",
  };
  ui.cameraState.textContent = detail || labels[state] || labels.offline;
  ui.cameraRecordState.lastChild.textContent = state === "live" ? " AO VIVO" : " CÂMERA";
  // A telemetria de distância é sintética; nunca a desenhamos sobre uma
  // imagem real nem deixamos um JPEG antigo parecer atual quando o fluxo para.
  if (state !== "live") {
    ui.targetReadout.hidden = true;
    ui.cameraFeed.hidden = true;
  }
}

function updateCameraFreshness() {
  ui.cameraLastReceived.textContent = formatAge(app.camera.lastReceivedAt);
  ui.cameraLastDisplayed.textContent = formatAge(app.camera.lastDisplayedAt);
  const reference = app.camera.lastReceivedAt || app.camera.streamOpenedAt;
  if (reference && performance.now() - reference > 2500) {
    setCameraStatus("stale");
  }
  renderCameraMetrics();
}

async function pollCameraHubStatus() {
  try {
    const response = await fetch("/api/camera/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`hub HTTP ${response.status}`);
    const status = await response.json();
    app.camera.hubStatus = status;
    const error = status.last_error ? ` · erro: ${status.last_error}` : "";
    ui.cameraHubStatus.textContent =
      `Hub: seq ${status.sequence} · enviados ${status.downstream_frames_sent} · upstream ${status.upstream_connects}${error}`;
  } catch (error) {
    app.camera.hubStatus = null;
    ui.cameraHubStatus.textContent = `Hub: não disponível (${error.message || "erro"})`;
  }
}

function displayCameraFrame(jpeg, receivedAt) {
  const previousUrl = app.camera.objectUrl;
  const nextUrl = URL.createObjectURL(new Blob([jpeg], { type: "image/jpeg" }));
  app.camera.objectUrl = nextUrl;
  ui.cameraFeed.hidden = false;
  ui.cameraFeed.onload = () => {
    if (nextUrl !== app.camera.objectUrl) return;
    app.camera.lastDisplayedAt = performance.now();
    app.camera.displayDelayMs = Math.max(0, app.camera.lastDisplayedAt - receivedAt);
    if (previousUrl) URL.revokeObjectURL(previousUrl);
    updateCameraFreshness();
  };
  ui.cameraFeed.src = nextUrl;
}

function scheduleCameraReconnect() {
  if (app.camera.reconnectTimer !== null || document.hidden) return;
  const delay = app.camera.reconnectDelay;
  app.camera.reconnectDelay = Math.min(10000, delay * 2);
  app.camera.reconnectTimer = window.setTimeout(() => {
    app.camera.reconnectTimer = null;
    startCameraStream();
  }, delay);
}

function stopCameraStream() {
  app.camera.generation += 1;
  app.camera.streamOpen = false;
  app.camera.controller?.abort();
  app.camera.controller = null;
}

async function startCameraStream() {
  stopCameraStream();
  if (app.camera.reconnectTimer !== null) {
    window.clearTimeout(app.camera.reconnectTimer);
    app.camera.reconnectTimer = null;
  }
  const generation = app.camera.generation;
  const controller = new AbortController();
  app.camera.controller = controller;
  app.camera.streamOpen = false;
  resetCameraMetrics();
  setCameraStatus("connecting");
  try {
    const response = await fetch("/api/camera/stream", { cache: "no-store", signal: controller.signal });
    if (!response.ok || !response.body) throw new Error(`stream HTTP ${response.status}`);
    const contentType = response.headers.get("Content-Type") || "";
    const boundaryPart = contentType.split(";").find((part) => part.trim().toLowerCase().startsWith("boundary="));
    const boundary = boundaryPart?.split("=", 2)[1]?.trim().replace(/^"|"$/g, "");
    if (!boundary) throw new Error("boundary MJPEG ausente");
    app.camera.streamOpen = true;
    // Uma conexão bem-sucedida não deve herdar o atraso acumulado de falhas
    // anteriores; novas quedas voltam a usar reconexão gradual.
    app.camera.reconnectDelay = 1000;
    app.camera.streamOpenedAt = performance.now();
    const reader = response.body.getReader();
    const parser = new BrowserMjpegParser(boundary);
    while (generation === app.camera.generation) {
      const { value, done } = await reader.read();
      if (done) throw new Error("stream encerrado");
      const frames = parser.append(value);
      if (!frames.length) continue;
      // Se a rede entregou vários quadros juntos, descarta os antigos e exibe
      // apenas o mais recente: não criamos uma fila artificial no navegador.
      const receivedAt = performance.now();
      if (!app.camera.metricsFirstFrameAt) app.camera.metricsFirstFrameAt = receivedAt;
      for (let index = 0; index < frames.length; index += 1) {
        if (app.camera.lastReceivedAt) {
          app.camera.maxGapMs = Math.max(app.camera.maxGapMs ?? 0, receivedAt - app.camera.lastReceivedAt);
        }
        app.camera.frameTimes.push(receivedAt);
        app.camera.lastReceivedAt = receivedAt;
      }
      displayCameraFrame(frames[frames.length - 1], receivedAt);
      app.camera.lastSequence += frames.length;
      setCameraStatus("live");
      updateCameraFreshness();
    }
  } catch (error) {
    if (controller.signal.aborted || generation !== app.camera.generation) return;
    app.camera.streamOpen = false;
    setCameraStatus("offline", error?.message || "VÍDEO INDISPONÍVEL");
    requestSafetyStop();
    scheduleCameraReconnect();
  } finally {
    if (generation === app.camera.generation) app.camera.streamOpen = false;
  }
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 1800);
  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || `Falha HTTP ${response.status}`);
    }
    setConnection(true);
    return data;
  } finally {
    window.clearTimeout(timer);
  }
}

function setNetworkDialogStatus(message, kind = "") {
  if (!ui.networkDialogStatus) return;
  ui.networkDialogStatus.textContent = message;
  ui.networkDialogStatus.dataset.kind = kind;
}

function setUsbStatus(message, kind = "") {
  if (!ui.usbPortStatus) return;
  ui.usbPortStatus.textContent = message;
  ui.usbPortStatus.dataset.kind = kind;
}

function serialSupported() {
  return "serial" in navigator;
}

async function serialWrite(line) {
  if (!app.usb.port?.writable) throw new Error("Nenhuma porta USB aberta.");
  const writer = app.usb.port.writable.getWriter();
  try {
    await writer.write(new TextEncoder().encode(`${line}\n`));
  } finally {
    writer.releaseLock();
  }
}

async function serialReadFor(timeoutMs = 1800) {
  if (!app.usb.port?.readable) return "";
  const reader = app.usb.port.readable.getReader();
  const decoder = new TextDecoder();
  let output = "";
  const deadline = performance.now() + timeoutMs;
  try {
    while (performance.now() < deadline) {
      const remaining = Math.max(1, deadline - performance.now());
      const result = await Promise.race([
        reader.read(),
        new Promise((resolve) => window.setTimeout(() => resolve({ timeout: true }), remaining)),
      ]);
      if (result.timeout) break;
      if (result.done) break;
      output += decoder.decode(result.value, { stream: true });
      if (output.includes("PONG") || output.includes("CFG_OK") || output.includes("CFG_ERROR")) break;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  return output;
}

async function connectUsbBoard() {
  if (!serialSupported()) {
    setUsbStatus("Este navegador não oferece Web Serial.", "error");
    setNetworkDialogStatus("Use Chrome, Edge ou Brave em HTTPS/localhost para acessar a USB.", "error");
    return;
  }
  try {
    if (app.usb.port) await app.usb.port.close().catch(() => {});
    app.usb.port = await navigator.serial.requestPort();
    await app.usb.port.open({ baudRate: 115200, dataBits: 8, stopBits: 1, parity: "none", flowControl: "none" });
    setUsbStatus("Porta aberta; identificando…", "active");
    await serialWrite("PING");
    const response = await serialReadFor();
    const match = response.match(/PONG\s+(C6|CAM)/i);
    app.usb.board = match ? match[1].toLowerCase() : "";
    if (app.usb.board && ui.usbBoardTarget.value === "auto") ui.usbBoardTarget.value = app.usb.board;
    setUsbStatus(app.usb.board ? `Conectado: ESP32-${app.usb.board.toUpperCase()}` : "Porta aberta; placa não identificada", app.usb.board ? "success" : "warning");
    ui.usbSendWifi.disabled = false;
    setNetworkDialogStatus(app.usb.board ? "USB pronta para configuração." : "Escolha a placa alvo e envie a rede.");
  } catch (error) {
    app.usb.port = null;
    ui.usbSendWifi.disabled = true;
    setUsbStatus(`USB indisponível: ${error.message}`, "error");
  }
}

async function sendWifiByUsb() {
  const ssid = ui.networkWifiSsid.value.trim();
  const password = ui.networkWifiPassword.value;
  const target = ui.usbBoardTarget.value === "auto" ? app.usb.board : ui.usbBoardTarget.value;
  if (!app.usb.port) {
    setNetworkDialogStatus("Selecione primeiro uma porta USB.", "error");
    return;
  }
  if (!target) {
    setNetworkDialogStatus("Não identifiquei a placa; selecione ESP32-C6 ou ESP32-CAM.", "error");
    return;
  }
  if (!ssid || ssid.length > 32 || password.length > 63) {
    setNetworkDialogStatus("SSID ou senha inválidos.", "error");
    return;
  }
  setNetworkDialogStatus("Enviando configuração pela USB…");
  try {
    await serialWrite(`WIFI\t${ssid}\t${password}`);
    const response = await serialReadFor(2500);
    if (!response.includes("CFG_OK WIFI")) throw new Error(response.includes("CFG_ERROR") ? response.trim() : "a placa não confirmou o recebimento");
    ui.networkWifiPassword.value = "";
    setNetworkDialogStatus(`Wi‑Fi salvo na ESP32-${target.toUpperCase()}; ela reiniciará agora.`, "success");
    setUsbStatus("Configuração aceita; aguardando reinício…", "success");
  } catch (error) {
    setNetworkDialogStatus(`Falha no envio USB: ${error.message}`, "error");
  }
}

async function loadNetworkConfig() {
  try {
    const config = await request("/api/config", { headers: {} });
    ui.networkCameraUrl.value = config.camera_url || "";
    ui.networkRobotUrl.value = config.robot_url || "";
    setNetworkDialogStatus("Endereços atuais carregados.");
  } catch (error) {
    setNetworkDialogStatus(`Não foi possível ler a configuração: ${error.message}`, "error");
  }
}

async function saveNetworkEndpoints() {
  const cameraUrl = ui.networkCameraUrl.value.trim();
  const robotUrl = ui.networkRobotUrl.value.trim();
  if (!cameraUrl) {
    setNetworkDialogStatus("Informe a URL da câmera.", "error");
    return;
  }
  setNetworkDialogStatus("Aplicando endereços e reiniciando apenas o consumidor da câmera…");
  try {
    await request("/api/config", {
      method: "POST",
      body: JSON.stringify({ camera_url: cameraUrl, robot_url: robotUrl }),
    });
    setNetworkDialogStatus("Endereços salvos. O hub já está usando a nova câmera.", "success");
    stopCameraStream();
    scheduleCameraReconnect();
  } catch (error) {
    setNetworkDialogStatus(`Falha ao salvar endereços: ${error.message}`, "error");
  }
}

async function provisionRobotWifi() {
  const ssid = ui.networkWifiSsid.value.trim();
  const password = ui.networkWifiPassword.value;
  if (!ssid) {
    setNetworkDialogStatus("Informe o nome da rede 2,4 GHz.", "error");
    return;
  }
  if (/5g|5 ghz/i.test(ssid)) {
    setNetworkDialogStatus("Essa rede parece ser 5 GHz; o ESP32-C6 precisa de uma rede 2,4 GHz.", "error");
    return;
  }
  setNetworkDialogStatus("Enviando credenciais ao C6…");
  try {
    const result = await request("/api/robot/wifi", {
      method: "POST",
      body: JSON.stringify({ ssid, password }),
    });
    ui.networkWifiPassword.value = "";
    setNetworkDialogStatus(result.message || "Wi‑Fi aceito pelo C6; aguardando reconexão.", "success");
  } catch (error) {
    setNetworkDialogStatus(`Falha no provisioning: ${error.message}`, "error");
  }
}

function bindNetworkSettings() {
  if (!ui.networkDialog || !ui.networkSettingsButton) return;
  ui.networkSettingsButton.addEventListener("click", () => {
    ui.networkDialog.showModal();
    loadNetworkConfig();
  });
  ui.networkDialog.addEventListener("click", (event) => {
    if (event.target === ui.networkDialog) ui.networkDialog.close();
  });
  ui.networkSaveEndpoints.addEventListener("click", saveNetworkEndpoints);
  ui.networkProvisionWifi.addEventListener("click", provisionRobotWifi);
  ui.usbConnectButton?.addEventListener("click", connectUsbBoard);
  ui.usbSendWifi?.addEventListener("click", sendWifiByUsb);
}

async function command(payload, quiet = false) {
  try {
    const state = await request("/api/command", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    app.state = state;
    renderState(state);
    return state;
  } catch (error) {
    setConnection(false);
    if (payload.action === "drive" || payload.action === "heartbeat") {
      neutralizeDriveUi();
      // Isto é uma tentativa explícita de parada; a garantia real continua
      // sendo o timeout do backend e, no hardware, o timeout independente do C6.
      if (performance.now() - app.camera.lastStopAttemptAt > 500 && (payload.action !== "drive" || payload.throttle !== 0 || payload.steering !== 0)) {
        app.camera.lastStopAttemptAt = performance.now();
        command({ action: "drive", throttle: 0, steering: 0 }, true);
      }
    }
    if (!quiet) showToast(error.message || "Não foi possível enviar o comando.", "error");
    return null;
  }
}

async function simulate(payload, quiet = false) {
  try {
    const state = await request("/api/simulation", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    app.state = state;
    renderState(state);
    return state;
  } catch (error) {
    setConnection(false);
    if (!quiet) showToast(error.message || "Não foi possível alterar o cenário.", "error");
    return null;
  }
}

function setConnection(online) {
  app.online = online;
  ui.connectionPill.dataset.status = online ? "online" : "offline";
  ui.connectionText.textContent = online ? "Painel conectado · hardware não confirmado" : "Servidor indisponível";
  ui.connectionShort.textContent = online ? "OK" : "OFF";
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  ui.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 3600);
}

function signedPercent(value) {
  const rounded = Math.round(value);
  return `${rounded > 0 ? "+" : ""}${rounded}%`;
}

function setBipolarMeter(element, value) {
  const width = Math.abs(value) / 2;
  if (value >= 0) {
    element.style.left = "50%";
    element.style.width = `${width}%`;
    element.style.background = "var(--aqua)";
  } else {
    element.style.left = `${50 - width}%`;
    element.style.width = `${width}%`;
    element.style.background = "var(--warning)";
  }
}

function renderState(state) {
  const { motors, actuators, sensors, power, network, pose } = state;

  // Este painel pode estar ligado apenas ao gêmeo digital. Nunca apresente
  // isso como hardware conectado sem telemetria/ponte confirmada.
  ui.connectionText.textContent = state.hardware_online
    ? "ESP32-C6 conectado"
    : (app.online ? "Painel conectado · hardware não confirmado" : "Servidor indisponível");

  ui.modeReadout.textContent = state.mode;
  ui.modeButtons.forEach((button) => {
    const active = app.activePanel !== "sound" && button.dataset.mode === state.mode;
    button.setAttribute("aria-pressed", String(active));
    button.setAttribute("aria-selected", String(active));
  });

  ui.autonomousModeStatus.textContent = state.mode === "AUTONOMO"
    ? (state.emergency ? "Autônomo bloqueado" : "Autônomo ativo")
    : "Aguardando ativação";
  ui.autonomousModeDetail.textContent = state.mode === "AUTONOMO"
    ? (state.emergency ? "Libere a parada de emergência para continuar." : "A câmera é a única referência de navegação.")
    : "Selecione Autônomo para liberar a máquina de estados.";

  const manualEnabled = state.mode === "MANUAL" && !state.emergency && state.link_online;
  ui.directionButtons.forEach((button) => { button.disabled = !manualEnabled; });
  ui.stopButton.disabled = !manualEnabled;

  ui.emergencyButton.setAttribute("aria-pressed", String(state.emergency));
  $("strong", ui.emergencyButton).textContent = state.emergency ? "LIBERAR" : "PARADA";

  ui.pumpButton.classList.toggle("is-active", actuators.pump);
  ui.pumpButton.style.setProperty("--progress", actuators.pump ? String(actuators.pump_remaining_ms / 3000) : "0");
  ui.pumpStatus.textContent = actuators.pump
    ? `desliga em ${(actuators.pump_remaining_ms / 1000).toFixed(1).replace(".", ",")} s`
    : "Pulso máximo de 3 s";
  ui.soundButton.setAttribute("aria-pressed", String(actuators.sound));
  ui.soundStatus.textContent = actuators.sound ? "Habilitada" : "Desligada";

  ui.safetyMessage.dataset.level = criticalStates.has(state.system_state)
    ? "critical"
    : warningStates.has(state.system_state) ? "warning" : "safe";
  $("strong", ui.safetyMessage).textContent = criticalStates.has(state.system_state)
    ? "Proteção ativa"
    : state.mode === "PARADO" ? "Saídas em repouso" : "Operação autorizada";
  ui.safetyReason.textContent = state.safety_reason;

  ui.visionClock.textContent = `T+${state.uptime_s.toFixed(1).padStart(5, "0")}`;
  const realVision = sensors.vision_source === "COLOR_TARGET";
  const distanceValid = sensors.vision_distance_valid !== false;
  ui.targetReadout.hidden = !realVision || !app.camera.lastReceivedAt;
  ui.targetReadout.dataset.detected = String(realVision ? sensors.vision_decision !== "STOP" : sensors.vision_detected);
  if (realVision) {
    const decision = sensors.vision_decision || "STOP";
    const labels = { LEFT: "ESQUERDA", RIGHT: "DIREITA", FORWARD: "FRENTE", STOP: "PARAR" };
    ui.targetDistance.textContent = labels[decision] || decision;
    const targetX = sensors.vision_target_x;
    ui.targetConfidence.textContent = targetX == null
      ? `${sensors.vision_reason || "sem alvo"} · confiança ${Math.round(sensors.vision_confidence * 100)}%`
      : `alvo ${Math.round(targetX * 100)}% da largura · confiança ${Math.round(sensors.vision_confidence * 100)}%`;
  } else if (distanceValid) {
    ui.targetDistance.textContent = sensors.vision_detected ? `${Math.round(sensors.vision_front_cm)} cm` : "livre";
    ui.targetConfidence.textContent = sensors.vision_detected
      ? `L ${Math.round(sensors.vision_left_cm)} · R ${Math.round(sensors.vision_right_cm)} cm · ${Math.round(sensors.vision_confidence * 100)}%`
      : "visão sintética; não é sensor físico";
  } else {
    ui.targetDistance.textContent = "não medido";
    ui.targetConfidence.textContent = "distância não disponível pela câmera";
  }
  ui.autonomousAction.textContent = state.mode === "AUTONOMO"
    ? state.autonomous_action
    : state.system_state.replaceAll("_", " ");
  ui.poseReadout.textContent = `X ${pose.x_m.toFixed(2).replace(".", ",")} · Y ${pose.y_m.toFixed(2).replace(".", ",")} · ${String(Math.round(pose.heading_deg)).padStart(3, "0")}°`;

  ui.leftMotorValue.textContent = signedPercent(motors.left);
  ui.rightMotorValue.textContent = signedPercent(motors.right);
  setBipolarMeter(ui.leftMotorBar, motors.left);
  setBipolarMeter(ui.rightMotorBar, motors.right);

  ui.batteryValue.textContent = `${Math.round(power.battery_percent)}%`;
  ui.batteryBar.style.width = `${power.battery_percent}%`;
  ui.batteryBar.style.background = power.battery_percent < 20 ? "var(--critical)" : "var(--rail)";
  ui.rssiValue.textContent = `${network.rssi_dbm < 0 ? "−" : ""}${Math.abs(network.rssi_dbm)} dBm`;
  ui.transportValue.textContent = network.transport;
  ui.signalBars.style.opacity = state.link_online ? "1" : "0.25";
  ui.systemState.textContent = state.system_state.replaceAll("_", " ");
  ui.heartbeatAge.textContent = state.mode === "MANUAL"
    ? `heartbeat ${state.heartbeat_age_ms} ms`
    : "heartbeat —";

  if (document.activeElement !== ui.obstacleRange && app.obstaclePending === null) {
    ui.obstacleRange.value = String(Math.round(sensors.vision_front_cm));
    ui.obstacleOutput.value = `${Math.round(sensors.vision_front_cm)} cm`;
  }
  ui.linkToggle.checked = state.link_online;
  ui.footerUptime.textContent = `sessão ${Math.floor(state.uptime_s)} s`;
  renderEvents(state.events);
}

function setPanel(name) {
  app.activePanel = name;
  ui.panelTabs.forEach((tab) => {
    const active = tab.dataset.panelTab === name;
    tab.setAttribute("aria-selected", String(active));
    tab.setAttribute("aria-pressed", String(active));
  });
  ui.tabPanels.forEach((panel) => {
    panel.hidden = panel.dataset.panel !== name;
  });
  if (ui.visionPanel) ui.visionPanel.hidden = false;
}

function loadCamera() {
  startCameraStream();
}

function renderEvents(events) {
  if (!events?.length) return;
  const newest = events[0].id;
  if (newest === app.lastRenderedEvent) return;
  app.lastRenderedEvent = newest;

  const visibleEvents = events.slice(0, 12);
  const currentIds = new Set(visibleEvents.map((event) => String(event.id)));
  const existingIds = new Set();
  $$("[data-event-id]", ui.eventLog).forEach((item) => {
    if (!currentIds.has(item.dataset.eventId)) item.remove();
    else existingIds.add(item.dataset.eventId);
  });
  $(".event-empty", ui.eventLog)?.remove();

  visibleEvents.filter((event) => !existingIds.has(String(event.id))).reverse().forEach((event) => {
    const item = document.createElement("li");
    item.dataset.level = event.level;
    item.dataset.eventId = String(event.id);
    const timestamp = document.createElement("time");
    timestamp.textContent = event.at;
    const source = document.createElement("strong");
    source.textContent = event.source;
    const message = document.createElement("span");
    message.textContent = event.message;
    item.append(timestamp, source, message);
    ui.eventLog.prepend(item);
  });
  ui.eventCount.textContent = `${events.length} ${events.length === 1 ? "evento" : "eventos"}`;
}

function computeDrive() {
  if (!app.state || app.state.mode !== "MANUAL") return { throttle: 0, steering: 0 };
  const speed = Number(ui.speedLimit.value);
  let throttle = app.manualAxes.throttle * speed / 100;
  let steering = app.manualAxes.steering * speed / 100;
  if (app.manualAxes.throttle === 0 && app.manualAxes.steering === 0) {
    if (app.activeDirections.has("forward")) throttle += speed;
    if (app.activeDirections.has("backward")) throttle -= speed;
    if (app.activeDirections.has("left")) steering -= speed;
    if (app.activeDirections.has("right")) steering += speed;
  }
  if (throttle !== 0 && steering !== 0) steering *= 0.62;
  return { throttle, steering };
}

function sendDrive(force = false) {
  const drive = computeDrive();
  const signature = `${Math.round(drive.throttle)}:${Math.round(drive.steering)}`;
  if (!force && signature === app.lastDriveSignature) return;
  app.lastDriveSignature = signature;
  command({ action: "drive", ...drive }, true);
}

function setDirection(direction, active) {
  if (active) app.activeDirections.add(direction);
  else app.activeDirections.delete(direction);
  ui.directionButtons.forEach((button) => {
    button.classList.toggle("is-active", app.activeDirections.has(button.dataset.drive));
  });
  sendDrive();
}

function neutralizeDriveUi() {
  app.activeDirections.clear();
  app.manualAxes.throttle = 0;
  app.manualAxes.steering = 0;
  ui.directionButtons.forEach((button) => button.classList.remove("is-active"));
  [ui.throttleJoystick, ui.steeringJoystick].forEach((joystick) => {
    if (!joystick) return;
    joystick.dataset.value = "0";
    joystick.setAttribute("aria-valuenow", "0");
    joystick.querySelector(".joystick-knob").style.transform = "translate(-50%, -50%)";
  });
  if (ui.throttleReadout) ui.throttleReadout.textContent = "0%";
  if (ui.steeringReadout) ui.steeringReadout.textContent = "0%";
  app.lastDriveSignature = "";
}

function setJoystickValue(axis, value) {
  const normalized = Math.max(-100, Math.min(100, Math.round(value)));
  app.manualAxes[axis] = normalized;
  const joystick = axis === "throttle" ? ui.throttleJoystick : ui.steeringJoystick;
  const readout = axis === "throttle" ? ui.throttleReadout : ui.steeringReadout;
  if (joystick) {
    joystick.dataset.value = String(normalized);
    joystick.setAttribute("aria-valuenow", String(normalized));
    const x = axis === "steering" ? normalized / 2 : 0;
    const y = axis === "throttle" ? -normalized / 2 : 0;
    joystick.querySelector(".joystick-knob").style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;
  }
  if (readout) readout.textContent = `${normalized > 0 ? "+" : ""}${normalized}%`;
  sendDrive();
}

function bindJoystick(joystick, axis) {
  if (!joystick) return;
  const updateFromPointer = (event) => {
    const rect = joystick.getBoundingClientRect();
    const fraction = axis === "throttle"
      ? (rect.bottom - event.clientY) / rect.height * 2 - 1
      : (event.clientX - rect.left) / rect.width * 2 - 1;
    setJoystickValue(axis, fraction * 100);
  };
  joystick.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    joystick.setPointerCapture?.(event.pointerId);
    updateFromPointer(event);
  });
  joystick.addEventListener("pointermove", (event) => {
    if (joystick.hasPointerCapture?.(event.pointerId)) updateFromPointer(event);
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((name) => {
    joystick.addEventListener(name, () => setJoystickValue(axis, 0));
  });
  joystick.addEventListener("keydown", (event) => {
    const step = event.shiftKey ? 25 : 10;
    if (axis === "throttle" && ["ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      setJoystickValue(axis, app.manualAxes[axis] + (event.key === "ArrowUp" ? step : -step));
    } else if (axis === "steering" && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      setJoystickValue(axis, app.manualAxes[axis] + (event.key === "ArrowRight" ? step : -step));
    }
  });
  joystick.addEventListener("keyup", (event) => {
    if ((axis === "throttle" && ["ArrowUp", "ArrowDown"].includes(event.key)) || (axis === "steering" && ["ArrowLeft", "ArrowRight"].includes(event.key))) {
      event.preventDefault();
      setJoystickValue(axis, 0);
    }
  });
}

function isInteractiveTarget(target) {
  return target instanceof Element
    && Boolean(target.closest("button, input, select, textarea, a, [role='slider'], [contenteditable='true']"));
}

function stopDrive({ notifyServer = true } = {}) {
  neutralizeDriveUi();
  if (notifyServer && app.state?.mode === "MANUAL") sendDrive(true);
}

function requestSafetyStop() {
  neutralizeDriveUi();
  if (performance.now() - app.camera.lastStopAttemptAt < 500) return;
  app.camera.lastStopAttemptAt = performance.now();
  if (app.state?.mode === "MANUAL") {
    sendDrive(true);
  } else if (app.state?.mode === "AUTONOMO") {
    // No modo autônomo, drive=0 não altera o estado de navegação; PARADO
    // solicita explicitamente ao backend a parada das saídas.
    command({ action: "set_mode", mode: "PARADO" }, true);
  }
}

function bindControls() {
  bindJoystick(ui.throttleJoystick, "throttle");
  bindJoystick(ui.steeringJoystick, "steering");
  ui.panelTabs.forEach((tab) => {
    tab.addEventListener("click", async () => {
      const panel = tab.dataset.panelTab;
      setPanel(panel);
      if (panel === "sound") {
        stopDrive();
        return;
      }
      stopDrive();
      if (tab.dataset.mode) await command({ action: "set_mode", mode: tab.dataset.mode });
    });
  });

  ui.directionButtons.forEach((button) => {
    button.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      button.setPointerCapture?.(event.pointerId);
      setDirection(button.dataset.drive, true);
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach((eventName) => {
      button.addEventListener(eventName, () => setDirection(button.dataset.drive, false));
    });
    button.addEventListener("keydown", (event) => {
      if ((event.key === " " || event.key === "Enter") && !event.repeat) {
        event.preventDefault();
        setDirection(button.dataset.drive, true);
      }
    });
    button.addEventListener("keyup", (event) => {
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        setDirection(button.dataset.drive, false);
      }
    });
    button.addEventListener("blur", () => setDirection(button.dataset.drive, false));
  });

  ui.stopButton.addEventListener("click", stopDrive);
  ui.standbyButton.addEventListener("click", async () => {
    stopDrive();
    setPanel("manual");
    await command({ action: "set_mode", mode: "PARADO" });
  });
  ui.speedLimit.addEventListener("input", () => {
    ui.speedOutput.value = `${ui.speedLimit.value}%`;
    sendDrive(true);
  });

  ui.emergencyButton.addEventListener("click", () => {
    stopDrive();
    command({ action: "emergency", active: !app.state?.emergency });
  });

  ui.pumpButton.addEventListener("click", () => {
    const active = app.state?.actuators?.pump;
    command({ action: "pump", enabled: !active, duration_ms: 3000 });
  });
  ui.soundButton.addEventListener("click", () => {
    command({ action: "sound", enabled: !app.state?.actuators?.sound });
  });
  ui.soundCommands.forEach((button) => {
    button.addEventListener("click", () => {
      const labels = {
        mode: "MODE · alternar rádio/Bluetooth",
        previous: "ANTERIOR · faixa ou volume −",
        play: "PAUSAR/SCAN",
        next: "AVANÇAR · faixa ou volume +",
      };
      showToast(`${labels[button.dataset.soundAction] || "Comando de áudio"}. Relés ainda não conectados.`, "info");
    });
  });
  ui.soundVolume.addEventListener("input", () => {
    ui.soundVolumeOutput.textContent = `${ui.soundVolume.value}%`;
  });
  ui.connectCamera.addEventListener("click", () => {
    loadCamera();
    showToast("Conectando à ESP32-CAM…", "info");
  });
  ui.resetButton.addEventListener("click", () => command({ action: "reset" }));

  ui.obstacleRange.addEventListener("input", () => {
    ui.obstacleOutput.value = `${ui.obstacleRange.value} cm`;
    window.clearTimeout(app.obstaclePending);
    app.obstaclePending = window.setTimeout(async () => {
      await simulate({ vision_front_cm: Number(ui.obstacleRange.value), vision_confidence: 0.9 }, true);
      app.obstaclePending = null;
    }, 90);
  });
  ui.linkToggle.addEventListener("change", () => {
    simulate({ link_online: ui.linkToggle.checked });
  });

  const scenarios = {
    clear: { vision_front_cm: 180, vision_left_cm: 52, vision_right_cm: 52, vision_confidence: 0.9, link_online: true },
    obstacle: { vision_front_cm: 18, vision_left_cm: 24, vision_right_cm: 76, vision_confidence: 0.9, link_online: true },
    disconnect: { link_online: false },
  };
  ui.scenarioButtons.forEach((button) => {
    button.addEventListener("click", () => simulate(scenarios[button.dataset.scenario]));
  });

  const keyMap = {
    w: "forward", ArrowUp: "forward",
    s: "backward", ArrowDown: "backward",
    a: "left", ArrowLeft: "left",
    d: "right", ArrowRight: "right",
  };
  window.addEventListener("keydown", (event) => {
    if (event.repeat || isInteractiveTarget(event.target)) return;
    if (event.code === "Space") {
      event.preventDefault();
      stopDrive();
      return;
    }
    const direction = keyMap[event.key];
    if (direction) {
      event.preventDefault();
      setDirection(direction, true);
    }
  });
  window.addEventListener("keyup", (event) => {
    const direction = keyMap[event.key];
    if (direction) {
      event.preventDefault();
      setDirection(direction, false);
    }
  });
  window.addEventListener("blur", stopDrive);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopDrive();
      stopCameraStream();
      if (app.cameraFrameRequest !== null) {
        window.cancelAnimationFrame(app.cameraFrameRequest);
        app.cameraFrameRequest = null;
      }
      app.cameraLoopRunning = false;
    } else {
      if (!app.camera.streamOpen) startCameraStream();
    }
  });
}

async function pollState() {
  if (app.polling) return;
  app.polling = true;
  try {
    const state = await request("/api/state", { headers: {} });
    app.state = state;
    renderState(state);
  } catch {
    setConnection(false);
  } finally {
    app.polling = false;
  }
}

function updateClock() {
  const now = new Date();
  ui.localClock.textContent = now.toLocaleTimeString("pt-BR", { hour12: false });
  ui.localClock.dateTime = now.toISOString();
}

function drawCamera() {
  app.cameraLoopRunning = true;
  app.cameraFrameRequest = null;
  const canvas = ui.cameraCanvas;
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const state = app.state;
  const distance = state?.sensors?.vision_front_cm ?? 148;
  const detected = state?.sensors?.vision_detected ?? true;
  const moving = ((state?.motors?.left ?? 0) + (state?.motors?.right ?? 0)) / 200;
  if (!app.reducedMotion.matches) app.drawFrame += moving * 1.8;

  context.fillStyle = "#8b9e91";
  context.fillRect(0, 0, width, height * 0.45);
  context.fillStyle = "#bcc7b8";
  context.fillRect(0, height * 0.45, width, height * 0.55);

  context.fillStyle = "#25332d";
  context.beginPath();
  context.moveTo(width * 0.40, height * 0.42);
  context.lineTo(width * 0.60, height * 0.42);
  context.lineTo(width * 0.93, height);
  context.lineTo(width * 0.07, height);
  context.closePath();
  context.fill();

  context.strokeStyle = "#d7ddcf";
  context.lineWidth = 5;
  context.setLineDash([28, 34]);
  context.lineDashOffset = app.drawFrame;
  context.beginPath();
  context.moveTo(width * 0.5, height * 0.45);
  context.lineTo(width * 0.5, height);
  context.stroke();
  context.setLineDash([]);

  context.fillStyle = "#33493f";
  context.fillRect(0, height * 0.39, width, 5);
  for (let index = 0; index < 10; index += 1) {
    const x = index * (width / 9);
    const tower = 18 + ((index * 29) % 44);
    context.fillRect(x, height * 0.39 - tower, 5, tower);
  }

  if (detected) {
    const proximity = Math.max(0, Math.min(1, (185 - distance) / 180));
    const boxW = 60 + proximity * 230;
    const boxH = 45 + proximity * 165;
    const centerX = width * (0.61 - proximity * 0.08);
    const top = height * (0.49 - proximity * 0.04);
    context.fillStyle = distance <= 25 ? "#d7462f" : "#637267";
    context.fillRect(centerX - boxW / 2, top, boxW, boxH);
    context.fillStyle = "#1a2621";
    context.fillRect(centerX - boxW * 0.31, top + boxH * 0.18, boxW * 0.62, boxH * 0.24);
    context.strokeStyle = distance <= 25 ? "#ff7758" : "#b7e44c";
    context.lineWidth = 3;
    context.strokeRect(centerX - boxW / 2 - 10, top - 10, boxW + 20, boxH + 20);
    const corner = 24;
    context.lineWidth = 7;
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([sx, sy]) => {
      const x = centerX + sx * (boxW / 2 + 10);
      const y = top + (sy > 0 ? boxH + 10 : -10);
      context.beginPath();
      context.moveTo(x, y + sy * corner);
      context.lineTo(x, y);
      context.lineTo(x - sx * corner, y);
      context.stroke();
    });
  }

  context.strokeStyle = "rgba(227, 239, 229, 0.7)";
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(width / 2 - 20, height / 2);
  context.lineTo(width / 2 + 20, height / 2);
  context.moveTo(width / 2, height / 2 - 20);
  context.lineTo(width / 2, height / 2 + 20);
  context.stroke();

  if (!document.hidden && !app.reducedMotion.matches) {
    app.cameraFrameRequest = window.requestAnimationFrame(drawCamera);
  } else {
    app.cameraLoopRunning = false;
  }
}

function start() {
  bindControls();
  bindNetworkSettings();
  setPanel("manual");
  ui.cameraCanvas.hidden = true;
  updateClock();
  pollState();
  pollCameraHubStatus();
  startCameraStream();
  window.setInterval(updateClock, 1000);
  window.setInterval(pollState, 250);
  window.setInterval(pollCameraHubStatus, 1000);
  window.setInterval(() => {
    if (app.state?.mode === "MANUAL" && app.online) {
      command({ action: "heartbeat" }, true);
    }
  }, 300);
  window.setInterval(() => {
    updateCameraFreshness();
    const cameraReference = app.camera.lastReceivedAt || app.camera.streamOpenedAt;
    if (cameraReference && performance.now() - cameraReference > 2500) {
      if (app.camera.streamOpen) {
        setCameraStatus("stale");
        requestSafetyStop();
      }
      if (app.camera.streamOpen) {
        stopCameraStream();
        scheduleCameraReconnect();
      }
    }
    // Se uma interrupção abortou a requisição antes de seu catch conseguir
    // agendar a próxima tentativa, o watchdog garante uma única reconexão
    // controlada, sem abrir consumidores paralelos.
    if (!document.hidden && !app.camera.streamOpen && app.camera.reconnectTimer === null) {
      scheduleCameraReconnect();
    }
  }, 250);
}

start();
