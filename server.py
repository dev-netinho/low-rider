#!/usr/bin/env python3
"""Servidor local e gêmeo digital do Robô de Logística e Fuga."""

from __future__ import annotations

import argparse
import http.client
import json
import math
import mimetypes
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlparse, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "dashboard"
RUNTIME_CONFIG_PATH = PROJECT_ROOT / "runtime_config.json"
DEFAULT_CAMERA_URL = "http://esp32-cam.local/capture"
DEFAULT_ROBOT_URL = "http://robo-c6.local"


def _validated_http_url(value: str, label: str) -> str:
    candidate = str(value or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError(f"{label} precisa ser uma URL HTTP com host.")
    return candidate


def load_runtime_config(camera_url: str, robot_url: str) -> dict[str, str]:
    defaults = {"camera_url": camera_url, "robot_url": robot_url}
    try:
        stored = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return defaults
    if not isinstance(stored, dict):
        return defaults
    result = defaults.copy()
    for key in result:
        value = stored.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def save_runtime_config(config: dict[str, str]) -> None:
    temporary = RUNTIME_CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(RUNTIME_CONFIG_PATH)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class MultipartJpegParser:
    """Extrai JPEGs completos de um corpo multipart sem guardar uma fila."""

    def __init__(self, boundary: bytes) -> None:
        self.boundary = b"--" + boundary
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        frames: list[bytes] = []
        while True:
            marker = self.buffer.find(self.boundary)
            if marker < 0:
                keep = max(0, len(self.boundary) - 1)
                if len(self.buffer) > keep:
                    del self.buffer[:-keep]
                break
            if marker:
                del self.buffer[:marker]
            after_marker = len(self.boundary)
            if len(self.buffer) < after_marker + 2:
                break
            if self.buffer[after_marker:after_marker + 2] != b"\r\n":
                del self.buffer[:after_marker]
                continue
            header_end = self.buffer.find(b"\r\n\r\n", after_marker + 2)
            if header_end < 0:
                break
            header_blob = bytes(self.buffer[after_marker + 2:header_end])
            headers: dict[str, str] = {}
            for line in header_blob.split(b"\r\n"):
                if b":" not in line:
                    continue
                key, value = line.split(b":", 1)
                headers[key.decode("ascii", "ignore").strip().lower()] = value.decode("ascii", "ignore").strip()
            try:
                length = int(headers["content-length"])
            except (KeyError, ValueError):
                del self.buffer[:header_end + 4]
                continue
            body_start = header_end + 4
            body_end = body_start + length
            if len(self.buffer) < body_end:
                break
            jpeg = bytes(self.buffer[body_start:body_end])
            del self.buffer[:body_end]
            if self.buffer.startswith(b"\r\n"):
                del self.buffer[:2]
            if jpeg.startswith(b"\xff\xd8") and jpeg.endswith(b"\xff\xd9"):
                frames.append(jpeg)
        return frames


class CameraStreamHub:
    """Mantém um consumidor upstream e compartilha somente o último JPEG.

    Para uma câmera configurada com ``/capture``, o consumidor faz polling
    sequencial: cada requisição termina antes da próxima começar. O hub nunca
    guarda uma fila de imagens antigas.
    """

    RECONNECT_DELAYS_S = (1.0, 2.0, 4.0, 8.0, 10.0)

    def __init__(self, stream_url: str) -> None:
        parsed = urlsplit(stream_url)
        if parsed.scheme not in {"http"} or not parsed.hostname:
            raise ValueError("A URL da câmera precisa ser HTTP e conter um host.")
        self.stream_url = stream_url
        self._host = parsed.hostname
        self._port = parsed.port or 80
        self._path = parsed.path or "/stream"
        self._capture_mode = self._path.rstrip("/") == "/capture"
        if parsed.query:
            self._path += "?" + parsed.query
        self._condition = threading.Condition()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._connection_lock = threading.Lock()
        self._active_connection: http.client.HTTPConnection | None = None
        self._latest_jpeg: bytes | None = None
        self._sequence = 0
        self._last_frame_at = 0.0
        self._last_error = ""
        self._upstream_connects = 0
        self._capture_count = 0
        self._capture_bytes = 0
        self._capture_duration_ms = 0.0
        self._capture_interval_ms = 0.0
        # Amostra curta para diagnosticar o polling sem imprimir a cada frame.
        # Cada item cobre um ciclo completo: conexão, primeiros bytes, JPEG,
        # publicação e espera antes do próximo ciclo.
        self._capture_poll_samples: list[dict[str, Any]] = []
        self._downstream_next_id = 1
        self._downstream: dict[int, dict[str, Any]] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="camera-stream-upstream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._connection_lock:
            active_connection = self._active_connection
            if active_connection is not None:
                try:
                    active_connection.close()
                except OSError:
                    pass
        with self._condition:
            self._condition.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def reconfigure(self, stream_url: str) -> None:
        """Troca o upstream sem deixar o consumidor anterior ativo."""
        parsed = urlsplit(_validated_http_url(stream_url, "URL da câmera"))
        path = parsed.path or "/stream"
        if parsed.query:
            path += "?" + parsed.query
        self.stop()
        if self._thread and self._thread.is_alive():
            raise RuntimeError("o consumidor anterior da câmera ainda está encerrando")
        self.stream_url = stream_url.strip()
        self._host = parsed.hostname or ""
        self._port = parsed.port or 80
        self._path = path
        self._capture_mode = path.rstrip("/") == "/capture"
        with self._condition:
            self._latest_jpeg = None
            self._sequence = 0
            self._last_frame_at = 0.0
            self._last_error = ""
        self.start()

    def latest_frame(self) -> tuple[int, bytes, float] | None:
        """Interface para o futuro módulo autônomo: sequência, JPEG e monotonic time."""
        with self._condition:
            if self._latest_jpeg is None:
                return None
            return self._sequence, self._latest_jpeg, self._last_frame_at

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def wait_for_frame(self, after_sequence: int, timeout: float = 1.0) -> tuple[int, bytes, float] | None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._sequence <= after_sequence and not self._stop_event.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(timeout=remaining)
            if self._sequence <= after_sequence or self._latest_jpeg is None:
                return None
            return self._sequence, self._latest_jpeg, self._last_frame_at

    def status(self) -> dict[str, Any]:
        with self._condition:
            clients = {
                str(client_id): {
                    "started_at": stats["started_at"],
                    "last_sent_at": stats["last_sent_at"],
                    "frames_sent": stats["frames_sent"],
                    "bytes_sent": stats["bytes_sent"],
                    "last_sequence": stats["last_sequence"],
                }
                for client_id, stats in self._downstream.items()
            }
            downstream_frames = sum(stats["frames_sent"] for stats in self._downstream.values())
            downstream_bytes = sum(stats["bytes_sent"] for stats in self._downstream.values())
            return {
                "sequence": self._sequence,
                "last_frame_at": self._last_frame_at,
                "last_error": self._last_error,
                "upstream_connects": self._upstream_connects,
                "source_mode": "capture" if self._capture_mode else "stream",
                "capture_count": self._capture_count,
                "capture_bytes": self._capture_bytes,
                "capture_duration_ms": self._capture_duration_ms,
                "capture_interval_ms": self._capture_interval_ms,
                "capture_poll_samples": list(self._capture_poll_samples),
                "downstream_frames_sent": downstream_frames,
                "downstream_bytes_sent": downstream_bytes,
                "downstream_active": len(self._downstream),
                "downstream_clients": clients,
            }

    def _store_frame(self, jpeg: bytes, *, captured_at: float) -> None:
        with self._condition:
            if self._capture_mode and self._last_frame_at:
                self._capture_interval_ms = (captured_at - self._last_frame_at) * 1000.0
            self._latest_jpeg = jpeg
            self._sequence += 1
            self._last_frame_at = captured_at
            self._condition.notify_all()

    def register_downstream(self) -> int:
        with self._condition:
            client_id = self._downstream_next_id
            self._downstream_next_id += 1
            self._downstream[client_id] = {
                "started_at": time.monotonic(),
                "last_sent_at": 0.0,
                "frames_sent": 0,
                "bytes_sent": 0,
                "last_sequence": 0,
            }
            return client_id

    def record_downstream(self, client_id: int, sequence: int, bytes_sent: int) -> None:
        with self._condition:
            stats = self._downstream.get(client_id)
            if stats is None:
                return
            stats["last_sent_at"] = time.monotonic()
            stats["frames_sent"] += 1
            stats["bytes_sent"] += bytes_sent
            stats["last_sequence"] = sequence

    def unregister_downstream(self, client_id: int) -> None:
        with self._condition:
            self._downstream.pop(client_id, None)

    def _run(self) -> None:
        delay_index = 0
        persistent_capture_connection: http.client.HTTPConnection | None = None
        while not self._stop_event.is_set():
            if delay_index:
                self._stop_event.wait(self.RECONNECT_DELAYS_S[min(delay_index - 1, len(self.RECONNECT_DELAYS_S) - 1)])
                if self._stop_event.is_set():
                    break
            connection: http.client.HTTPConnection | None = None
            try:
                # A câmera pode demorar alguns segundos entre JPEGs grandes;
                # não transforme uma pausa de transmissão em reconexão do
                # único upstream. O cliente downstream continua protegido
                # pelo timeout próprio de sua conexão.
                cycle_started = time.monotonic()
                previous_cycle_completed = getattr(self, "_capture_previous_cycle_completed", None)
                new_connection = False
                if self._capture_mode and persistent_capture_connection is not None:
                    connection = persistent_capture_connection
                    connect_started = connected_at = cycle_started
                else:
                    connection = http.client.HTTPConnection(self._host, self._port, timeout=10.0)
                    with self._connection_lock:
                        self._active_connection = connection
                    connect_started = time.monotonic()
                    # Explicita o connect apenas para separar seu tempo do
                    # tempo de resposta; continua sendo uma conexão por /capture.
                    connection.connect()
                    connected_at = time.monotonic()
                    new_connection = True
                    if self._capture_mode:
                        persistent_capture_connection = connection
                connection.request("GET", self._path, headers={"Cache-Control": "no-cache"})
                response = connection.getresponse()
                headers_at = time.monotonic()
                if response.status != HTTPStatus.OK:
                    raise ConnectionError(f"camera HTTP {response.status}")
                if self._capture_mode:
                    first_byte_started = time.monotonic()
                    first_byte = response.read(1)
                    first_byte_at = time.monotonic()
                    if not first_byte:
                        raise ConnectionError("camera capture retornou EOF antes do JPEG")
                    jpeg = first_byte + response.read()
                    completed = time.monotonic()
                    if not (jpeg.startswith(b"\xff\xd8") and jpeg.endswith(b"\xff\xd9")):
                        raise ValueError("camera capture não retornou JPEG completo")
                    validation_started = completed
                    with self._condition:
                        self._upstream_connects += 1
                        self._last_error = ""
                        self._capture_count += 1
                        self._capture_bytes += len(jpeg)
                        self._capture_duration_ms = (completed - first_byte_started) * 1000.0
                    self._store_frame(jpeg, captured_at=completed)
                    published_at = time.monotonic()
                    sample = {
                        "cycle": self._capture_count,
                        "started_ms": round(cycle_started * 1000.0, 3),
                        "connect_ms": round((connected_at - connect_started) * 1000.0, 3),
                        "headers_ms": round((headers_at - connect_started) * 1000.0, 3),
                        "first_byte_ms": round((first_byte_at - first_byte_started) * 1000.0, 3),
                        "jpeg_ms": round((completed - first_byte_started) * 1000.0, 3),
                        "validate_publish_ms": round((published_at - validation_started) * 1000.0, 3),
                        "cycle_ms": round((published_at - cycle_started) * 1000.0, 3),
                        "before_next_ms": 0.0,
                        "bytes": len(jpeg),
                        "status": response.status,
                        "connection_will_close": bool(getattr(response, "will_close", False)),
                        "connection_header": response.getheader("Connection", ""),
                        "new_connection": new_connection,
                    }
                    if previous_cycle_completed is not None:
                        sample["interval_before_start_ms"] = round((cycle_started - previous_cycle_completed) * 1000.0, 3)
                    else:
                        sample["interval_before_start_ms"] = None
                    with self._condition:
                        self._capture_poll_samples.append(sample)
                        del self._capture_poll_samples[:-20]
                    self._capture_previous_cycle_completed = published_at
                    if response.will_close:
                        connection.close()
                        persistent_capture_connection = None
                    delay_index = 0
                    # A persistent capture connection must survive this
                    # iteration; the finally block only closes per-cycle or
                    # failed connections.
                    connection = None
                    continue
                content_type = response.getheader("Content-Type", "")
                boundary_text = ""
                for part in content_type.split(";"):
                    if part.strip().lower().startswith("boundary="):
                        boundary_text = part.split("=", 1)[1].strip().strip('"')
                if not boundary_text:
                    raise ValueError("camera multipart boundary ausente")
                # Alguns aplicativos móveis anunciam o delimitador já com
                # os dois hífens do corpo multipart (ex.: boundary=--dcmjpeg).
                # MultipartJpegParser acrescenta esses hífens internamente;
                # normalize para não procurar por ``----dcmjpeg``.
                if boundary_text.startswith("--"):
                    boundary_text = boundary_text[2:]
                with self._condition:
                    self._upstream_connects += 1
                    self._last_error = ""
                parser = MultipartJpegParser(boundary_text.encode("ascii", "ignore"))
                while not self._stop_event.is_set():
                    # ``read(4096)`` pode esperar até preencher o buffer em um
                    # MJPEG sem Content-Length. read1 devolve os bytes já
                    # disponíveis e evita transformar a espera upstream em
                    # uma pausa artificial de segundos.
                    data = response.read1(4096) if hasattr(response, "read1") else response.read(4096)
                    if not data:
                        raise ConnectionError("camera upstream EOF")
                    for jpeg in parser.feed(data):
                        now = time.monotonic()
                        self._store_frame(jpeg, captured_at=now)
                delay_index = 0
            except (OSError, ValueError, ConnectionError, socket.timeout) as exc:
                with self._condition:
                    self._last_error = str(exc)
                delay_index = min(delay_index + 1, len(self.RECONNECT_DELAYS_S))
            finally:
                if connection is not None:
                    connection.close()
                    if connection is persistent_capture_connection:
                        persistent_capture_connection = None
                    with self._connection_lock:
                        if self._active_connection is connection:
                            self._active_connection = None


class C6SerialBridge:
    """Envia comandos diferenciais para o firmware de bancada do ESP32-C6.

    A ponte é opcional: sem ``--serial-port`` o servidor continua sendo apenas
    o gêmeo digital. O firmware recebe pacotes ``M esquerda direita`` em
    percentuais (-100 a 100) e possui seu próprio timeout de segurança.
    """

    def __init__(self, port: str | None = None) -> None:
        self.port = port or ""
        self._lock = threading.RLock()
        self._serial: Any | None = None
        self._last_packet: tuple[int, int] | None = None
        self._last_sent = 0.0
        self._retry_after = 0.0
        self.last_error = ""

    @property
    def enabled(self) -> bool:
        return bool(self.port)

    @property
    def online(self) -> bool:
        return self._serial is not None

    def _connect(self) -> bool:
        if not self.enabled or time.monotonic() < self._retry_after:
            return False
        try:
            import serial  # type: ignore[import-not-found]

            self._serial = serial.Serial(self.port, 115200, timeout=0.1, write_timeout=0.2)
            self._serial.reset_input_buffer()
            self.last_error = ""
            return True
        except Exception as exc:  # hardware is optional during simulation
            self._serial = None
            self.last_error = str(exc)
            self._retry_after = time.monotonic() + 1.0
            return False

    def send_drive(self, left: float, right: float, force: bool = False) -> bool:
        if not self.enabled:
            return False
        packet = (int(round(clamp(left, -100.0, 100.0))), int(round(clamp(right, -100.0, 100.0))))
        now = time.monotonic()
        with self._lock:
            if not force and packet == self._last_packet and now - self._last_sent < 0.2:
                return self.online
            if self._serial is None and not self._connect():
                return False
            try:
                self._serial.write(f"M {packet[0]} {packet[1]}\n".encode("ascii"))
                self._serial.flush()
                self._last_packet = packet
                self._last_sent = now
                return True
            except Exception as exc:
                self.last_error = str(exc)
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
                self._retry_after = now + 1.0
                return False

    def close(self) -> None:
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.write(b"M 0 0\n")
                    self._serial.flush()
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None


class C6HttpBridge:
    """Ponte HTTP para o firmware autônomo do ESP32-C6.

    Mantém um único trabalhador de saída e envia periodicamente o último
    comando. O ESP32-C6 possui watchdog próprio; se esta ponte perder a rede,
    o firmware desliga os motores após COMMAND_TIMEOUT_MS.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self._lock = threading.RLock()
        self._desired = (0, 0)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._online = False
        self.last_error = ""
        if self.enabled:
            self._thread = threading.Thread(target=self._run, name="c6-http-bridge", daemon=True)
            self._thread.start()

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    @property
    def online(self) -> bool:
        with self._lock:
            return self._online

    def send_drive(self, left: float, right: float, force: bool = False) -> bool:
        if not self.enabled:
            return False
        with self._lock:
            self._desired = (
                int(round(clamp(left, -100.0, 100.0))),
                int(round(clamp(right, -100.0, 100.0))),
            )
            return self._online

    def _run(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                left, right = self._desired
            url = f"{self.base_url}/drive?left={left}&right={right}"
            try:
                with urllib.request.urlopen(url, timeout=0.45) as response:
                    response.read(64)
                with self._lock:
                    self._online = True
                    self.last_error = ""
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                with self._lock:
                    self._online = False
                    self.last_error = str(exc)
            self._stop_event.wait(0.10)

    def close(self) -> None:
        if not self.enabled:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        try:
            with urllib.request.urlopen(f"{self.base_url}/stop", timeout=0.5) as response:
                response.read(64)
        except Exception:
            pass


@dataclass
class Pose:
    x_m: float = 0.0
    y_m: float = 0.0
    heading_deg: float = 0.0


class RobotSimulation:
    """Modelo de controle compartilhado pelo painel e pelo futuro ESP32."""

    COMMAND_TIMEOUT_S = 0.75
    VISION_TIMEOUT_S = 1.5
    PUMP_MAX_S = 3.0
    VISION_STOP_CM = 25.0
    MAX_SPEED_MPS = 0.72
    WHEEL_BASE_M = 0.18

    def __init__(self, clock: Callable[[], float] | None = None, hardware: Any | None = None) -> None:
        self._clock = clock or time.monotonic
        self._hardware = hardware
        self._lock = threading.RLock()
        now = self._clock()
        self._started_at = now
        self._last_tick = now
        self._last_command = now
        self._last_heartbeat = now
        self._last_telemetry = 0.0
        self._last_vision = now
        self._pump_until = 0.0
        self._pump_on = False
        self._sound_on = False
        self._mode = "PARADO"
        self._system_state = "PRONTO"
        self._safety_reason = "Inicialização segura"
        self._emergency = False
        self._link_online = True
        self._hardware_online = False
        self._requested_left = 0.0
        self._requested_right = 0.0
        self._motor_left = 0.0
        self._motor_right = 0.0
        self._vision_front_cm = 148.0
        self._vision_left_cm = 52.0
        self._vision_right_cm = 52.0
        self._vision_confidence = 0.81
        self._vision_source = "CAMERA_SINTETICA"
        self._vision_decision = "STOP"
        self._vision_target_x: float | None = None
        self._vision_target_area = 0.0
        self._vision_distance_valid = True
        self._vision_reason = "visão sintética"
        self._battery_percent = 86.0
        self._rssi_dbm = -47
        self._command_seq = 0
        self._autonomous_action = "Aguardando ativação"
        self._pose = Pose()
        self._events: deque[dict[str, Any]] = deque(maxlen=36)
        self._event_counter = 0
        self._last_remote_telemetry: dict[str, Any] = {}
        self._log("Sistema", "Gêmeo digital iniciado em estado seguro", "info")

    def _log(self, source: str, message: str, level: str = "info") -> None:
        self._event_counter += 1
        elapsed = max(0.0, self._clock() - self._started_at)
        self._events.appendleft(
            {
                "id": self._event_counter,
                "at": f"+{elapsed:05.1f}s",
                "source": source,
                "message": message,
                "level": level,
            }
        )

    def _set_drive_targets(self, left: float, right: float) -> None:
        self._requested_left = clamp(left, -100.0, 100.0)
        self._requested_right = clamp(right, -100.0, 100.0)

    def _stop_motion(self, clear_request: bool = True) -> None:
        self._motor_left = 0.0
        self._motor_right = 0.0
        if clear_request:
            self._set_drive_targets(0.0, 0.0)

    def apply_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            action = str(payload.get("action", "")).strip().lower()
            self._last_command = now
            self._command_seq += 1

            if action == "heartbeat":
                self._last_heartbeat = now
            elif action == "set_mode":
                requested = str(payload.get("mode", "")).upper()
                if requested not in {"PARADO", "MANUAL", "AUTONOMO"}:
                    raise ValueError("Modo inválido. Use PARADO, MANUAL ou AUTONOMO.")
                if self._emergency and requested != "PARADO":
                    raise ValueError("Libere a parada de emergência antes de mudar o modo.")
                self._mode = requested
                self._last_heartbeat = now
                self._stop_motion()
                self._system_state = "PRONTO" if requested != "PARADO" else "PARADO"
                self._safety_reason = "Nenhuma restrição ativa"
                self._log("Controle", f"Modo alterado para {requested}")
            elif action == "drive":
                if self._mode != "MANUAL":
                    raise ValueError("Comandos de direção exigem o modo MANUAL.")
                throttle = clamp(float(payload.get("throttle", 0)), -100, 100)
                steering = clamp(float(payload.get("steering", 0)), -100, 100)
                scale = max(100.0, abs(throttle + steering), abs(throttle - steering))
                left = (throttle + steering) * 100.0 / scale
                right = (throttle - steering) * 100.0 / scale
                self._set_drive_targets(left, right)
                self._last_heartbeat = now
            elif action == "pump":
                enabled = bool(payload.get("enabled", True))
                if enabled:
                    if self._emergency or not self._link_online:
                        raise ValueError("A bomba está bloqueada por uma condição de segurança.")
                    duration_ms = clamp(float(payload.get("duration_ms", 2000)), 100, self.PUMP_MAX_S * 1000)
                    self._pump_until = now + duration_ms / 1000.0
                    if not self._pump_on:
                        self._log("Atuador", f"Bomba acionada por {duration_ms / 1000:.1f}s", "warning")
                    self._pump_on = True
                else:
                    self._pump_on = False
                    self._pump_until = 0.0
                    self._log("Atuador", "Bomba desligada")
            elif action == "sound":
                enabled = bool(payload.get("enabled", False))
                if enabled and (self._emergency or not self._link_online):
                    raise ValueError("O som está bloqueado por uma condição de segurança.")
                self._sound_on = enabled
                self._log("Atuador", "Som habilitado" if enabled else "Som desligado")
            elif action == "emergency":
                self._emergency = bool(payload.get("active", True))
                if self._emergency:
                    self._mode = "PARADO"
                    self._system_state = "EMERGENCIA"
                    self._safety_reason = "Parada de emergência acionada"
                    self._stop_motion()
                    self._pump_on = False
                    self._sound_on = False
                    self._log("Segurança", "PARADA DE EMERGÊNCIA", "critical")
                else:
                    self._system_state = "PARADO"
                    self._safety_reason = "Emergência liberada; selecione um modo"
                    self._log("Segurança", "Emergência liberada; saídas permanecem desligadas", "warning")
            elif action == "reset":
                self._events.clear()
                self._mode = "PARADO"
                self._system_state = "PRONTO"
                self._safety_reason = "Simulação reiniciada"
                self._emergency = False
                self._link_online = True
                self._hardware_online = False
                self._stop_motion()
                self._pump_on = False
                self._sound_on = False
                self._vision_front_cm = 148.0
                self._vision_left_cm = 52.0
                self._vision_right_cm = 52.0
                self._vision_confidence = 0.81
                self._vision_source = "CAMERA_SINTETICA"
                self._vision_decision = "STOP"
                self._vision_target_x = None
                self._vision_target_area = 0.0
                self._vision_distance_valid = True
                self._vision_reason = "visão sintética"
                self._last_vision = now
                self._battery_percent = 86.0
                self._pose = Pose()
                self._last_heartbeat = now
                self._log("Sistema", "Simulação reiniciada")
            else:
                raise ValueError("Ação desconhecida.")

            self.tick(now)
            return self._snapshot_unlocked(now)

    def apply_simulation(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            vision_changed = False
            if "vision_front_cm" in payload:
                self._vision_front_cm = clamp(float(payload["vision_front_cm"]), 2.0, 600.0)
                vision_changed = True
            if "vision_left_cm" in payload:
                self._vision_left_cm = clamp(float(payload["vision_left_cm"]), 2.0, 300.0)
                vision_changed = True
            if "vision_right_cm" in payload:
                self._vision_right_cm = clamp(float(payload["vision_right_cm"]), 2.0, 300.0)
                vision_changed = True
            if "vision_confidence" in payload:
                self._vision_confidence = clamp(float(payload["vision_confidence"]), 0.0, 1.0)
                vision_changed = True
            if vision_changed:
                self._vision_source = "CAMERA_SINTETICA"
                self._vision_distance_valid = True
                self._vision_reason = "visão sintética"
                self._last_vision = now
            if "battery_percent" in payload:
                self._battery_percent = clamp(float(payload["battery_percent"]), 0.0, 100.0)
            if "link_online" in payload:
                next_link = bool(payload["link_online"])
                if next_link != self._link_online:
                    self._link_online = next_link
                    self._log(
                        "Rede",
                        "Enlace restaurado" if next_link else "Enlace interrompido pelo simulador",
                        "info" if next_link else "critical",
                    )
            self.tick(now)
            return self._snapshot_unlocked(now)

    def receive_telemetry(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            self._last_telemetry = now
            self._hardware_online = True
            self._last_remote_telemetry = dict(payload)
            return self._snapshot_unlocked(now)

    def receive_vision(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Recebe exclusivamente métricas calculadas a partir do quadro da câmera."""
        with self._lock:
            now = self._clock()
            if "confidence" not in payload:
                raise ValueError("Visão incompleta; falta: confidence.")
            # O formato antigo de corredor permanece para testes do gêmeo
            # digital. O detector real por cor envia decisão/posição, sem
            # inventar uma distância em centímetros.
            for key, minimum, maximum in (("front_cm", 2.0, 600.0), ("left_cm", 2.0, 300.0), ("right_cm", 2.0, 300.0)):
                if key in payload:
                    setattr(self, f"_vision_{key}", clamp(float(payload[key]), minimum, maximum))
            self._vision_confidence = clamp(float(payload["confidence"]), 0.0, 1.0)
            self._vision_source = str(payload.get("source", "ESP32_CAM")).upper()
            self._vision_decision = str(payload.get("decision", "STOP")).upper()
            self._vision_target_x = payload.get("target_x")
            self._vision_target_area = float(payload.get("target_area", 0.0) or 0.0)
            self._vision_distance_valid = bool(payload.get("distance_valid", self._vision_source != "COLOR_TARGET"))
            self._vision_reason = str(payload.get("reason", ""))
            self._last_vision = now
            return self._snapshot_unlocked(now)

    def tick(self, now: float | None = None) -> None:
        with self._lock:
            now = self._clock() if now is None else now
            dt = clamp(now - self._last_tick, 0.0, 0.2)
            self._last_tick = now

            if self._pump_on and now >= self._pump_until:
                self._pump_on = False
                self._pump_until = 0.0
                self._log("Segurança", "Bomba desligada pelo limite de tempo")

            if self._hardware_online and now - self._last_telemetry > 2.0:
                self._hardware_online = False

            if self._emergency:
                self._system_state = "EMERGENCIA"
                self._safety_reason = "Parada de emergência acionada"
                self._stop_motion()
                self._pump_on = False
                self._sound_on = False
            elif not self._link_online:
                self._system_state = "SEM_CONEXAO"
                self._safety_reason = "Enlace de controle indisponível"
                self._stop_motion()
                self._pump_on = False
                self._sound_on = False
            elif self._mode == "PARADO":
                self._system_state = "PARADO"
                self._safety_reason = "Modo seguro selecionado"
                self._stop_motion()
            elif self._mode == "MANUAL":
                if now - self._last_heartbeat > self.COMMAND_TIMEOUT_S:
                    if self._system_state != "SEM_COMANDO":
                        self._log("Segurança", "Timeout de comando: motores parados", "critical")
                    self._system_state = "SEM_COMANDO"
                    self._safety_reason = "Nenhum heartbeat do operador"
                    self._stop_motion()
                else:
                    self._system_state = "OPERANDO"
                    self._safety_reason = "Controle manual ativo"
                    self._apply_requested_drive(dt)
            elif self._mode == "AUTONOMO":
                vision_age = now - self._last_vision
                if vision_age > self.VISION_TIMEOUT_S or self._vision_confidence < 0.35:
                    if self._system_state != "SEM_VISAO":
                        self._log("Visão", "Quadro da câmera ausente ou sem confiança", "critical")
                    self._system_state = "SEM_VISAO"
                    self._safety_reason = "Navegação autônoma sem percepção visual confiável"
                    self._autonomous_action = "Parado: aguardando ESP32-CAM"
                    self._stop_motion()
                else:
                    self._system_state = "OPERANDO"
                    self._safety_reason = f"Guiado somente por visão ({self._vision_source})"
                    if self._vision_source == "COLOR_TARGET":
                        decision = self._vision_decision
                        if decision == "LEFT":
                            self._autonomous_action = "Visão: alvo à esquerda"
                            self._set_drive_targets(-30.0, 30.0)
                        elif decision == "RIGHT":
                            self._autonomous_action = "Visão: alvo à direita"
                            self._set_drive_targets(30.0, -30.0)
                        elif decision == "FORWARD":
                            self._autonomous_action = "Visão: alvo centralizado"
                            self._set_drive_targets(28.0, 28.0)
                        else:
                            self._autonomous_action = "Visão: parado"
                            self._stop_motion()
                            self._system_state = "OBSTACULO" if "proximo" in self._vision_reason else "SEM_VISAO"
                    elif self._vision_front_cm <= self.VISION_STOP_CM:
                        if self._vision_right_cm >= self._vision_left_cm:
                            self._autonomous_action = "Câmera: girando para a direita"
                            self._set_drive_targets(48.0, -48.0)
                        else:
                            self._autonomous_action = "Câmera: girando para a esquerda"
                            self._set_drive_targets(-48.0, 48.0)
                    else:
                        base_speed = 34.0 if self._vision_front_cm < 65.0 else 58.0
                        correction = clamp(
                            (self._vision_right_cm - self._vision_left_cm) * 0.55,
                            -26.0,
                            26.0,
                        )
                        self._autonomous_action = (
                            "Câmera: aproximação cautelosa"
                            if self._vision_front_cm < 65.0
                            else "Câmera: centralizando no corredor"
                        )
                        self._set_drive_targets(base_speed + correction, base_speed - correction)
                    self._apply_requested_drive(dt)

            if (
                self._mode == "AUTONOMO"
                and self._vision_source != "COLOR_TARGET"
                and self._vision_front_cm <= self.VISION_STOP_CM
                and min(self._requested_left, self._requested_right) > 1.0
            ):
                self._motor_left = 0.0
                self._motor_right = 0.0
                self._system_state = "OBSTACULO"
                self._safety_reason = f"Câmera estimou bloqueio a {self._vision_front_cm:.0f} cm"

            if self._hardware is not None and self._hardware.enabled:
                hardware_ok = self._hardware.send_drive(
                    self._motor_left if self._system_state == "OPERANDO" else 0.0,
                    self._motor_right if self._system_state == "OPERANDO" else 0.0,
                )
                self._hardware_online = hardware_ok
                if not hardware_ok:
                    # Não mantenha no painel uma ordem de movimento que o
                    # ESP32-C6 não confirmou. O watchdog do C6 é a segunda
                    # barreira; aqui o backend também passa a estado seguro.
                    self._stop_motion()
                    self._system_state = "SEM_CONEXAO"
                    self._safety_reason = "ESP32-C6 indisponível; saídas zeradas"
                    self._hardware.send_drive(0.0, 0.0, force=True)

            self._integrate_pose(dt)
            load = (abs(self._motor_left) + abs(self._motor_right)) / 200.0
            load += 0.45 if self._pump_on else 0.0
            load += 0.12 if self._sound_on else 0.0
            self._battery_percent = max(0.0, self._battery_percent - load * dt * 0.015)

    def _apply_requested_drive(self, dt: float) -> None:
        max_step = max(8.0, 240.0 * dt)
        if self._requested_left == 0.0:
            self._motor_left = 0.0
        else:
            self._motor_left += clamp(self._requested_left - self._motor_left, -max_step, max_step)
        if self._requested_right == 0.0:
            self._motor_right = 0.0
        else:
            self._motor_right += clamp(self._requested_right - self._motor_right, -max_step, max_step)

    def _integrate_pose(self, dt: float) -> None:
        left_mps = self._motor_left / 100.0 * self.MAX_SPEED_MPS
        right_mps = self._motor_right / 100.0 * self.MAX_SPEED_MPS
        linear = (left_mps + right_mps) / 2.0
        angular = (right_mps - left_mps) / self.WHEEL_BASE_M
        heading_rad = math.radians(self._pose.heading_deg)
        self._pose.x_m += math.cos(heading_rad) * linear * dt
        self._pose.y_m += math.sin(heading_rad) * linear * dt
        self._pose.heading_deg = (self._pose.heading_deg + math.degrees(angular * dt)) % 360.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = self._clock()
            self.tick(now)
            return self._snapshot_unlocked(now)

    def _snapshot_unlocked(self, now: float) -> dict[str, Any]:
        heartbeat_age_ms = int(max(0.0, now - self._last_heartbeat) * 1000)
        vision_age_ms = int(max(0.0, now - self._last_vision) * 1000)
        speed_percent = (abs(self._motor_left) + abs(self._motor_right)) / 2.0
        return {
            "timestamp_ms": int(now * 1000),
            "uptime_s": round(now - self._started_at, 1),
            "seq": self._command_seq,
            "mode": self._mode,
            "system_state": self._system_state,
            "safety_reason": self._safety_reason,
            "link_online": self._link_online,
            "hardware_online": self._hardware_online,
            "emergency": self._emergency,
            "heartbeat_age_ms": heartbeat_age_ms,
            "motors": {
                "left": round(self._motor_left, 1),
                "right": round(self._motor_right, 1),
                "requested_left": round(self._requested_left, 1),
                "requested_right": round(self._requested_right, 1),
                "speed_percent": round(speed_percent, 1),
            },
            "actuators": {
                "pump": self._pump_on,
                "pump_remaining_ms": max(0, int((self._pump_until - now) * 1000)) if self._pump_on else 0,
                "sound": self._sound_on,
            },
            "sensors": {
                "vision_front_cm": round(self._vision_front_cm, 1),
                "vision_left_cm": round(self._vision_left_cm, 1),
                "vision_right_cm": round(self._vision_right_cm, 1),
                "corridor_width_cm": round(self._vision_left_cm + self._vision_right_cm, 1),
                "vision_detected": self._vision_front_cm < 250.0,
                "vision_confidence": round(self._vision_confidence, 2),
                "vision_source": self._vision_source,
                "vision_decision": self._vision_decision,
                "vision_target_x": self._vision_target_x,
                "vision_target_area": round(self._vision_target_area, 5),
                "vision_distance_valid": self._vision_distance_valid,
                "vision_reason": self._vision_reason,
                "vision_age_ms": vision_age_ms,
                # A taxa e a idade do vídeo são medidas no cliente MJPEG;
                # estes campos permanecem somente por compatibilidade da API.
                "camera_fps": None,
                "camera_latency_ms": None,
            },
            "power": {
                "battery_percent": round(self._battery_percent, 1),
                "source": "SIMULADA",
            },
            "network": {"rssi_dbm": self._rssi_dbm, "transport": "HTTP local"},
            "autonomous_action": self._autonomous_action,
            "pose": {
                "x_m": round(self._pose.x_m, 2),
                "y_m": round(self._pose.y_m, 2),
                "heading_deg": round(self._pose.heading_deg, 1),
            },
            "events": list(self._events),
            "simulation": True,
            "remote_telemetry": self._last_remote_telemetry,
            "hardware": {
                "enabled": bool(self._hardware and self._hardware.enabled),
                "online": bool(self._hardware and self._hardware.online),
                "error": self._hardware.last_error if self._hardware else "",
            },
        }

    def hardware_command(self) -> dict[str, Any]:
        state = self.snapshot()
        return {
            "seq": state["seq"],
            "mode": state["mode"],
            "left": state["motors"]["left"],
            "right": state["motors"]["right"],
            "pump": state["actuators"]["pump"],
            "sound": state["actuators"]["sound"],
            "emergency": state["emergency"],
        }


class SimulationRunner(threading.Thread):
    def __init__(self, simulation: RobotSimulation) -> None:
        super().__init__(name="robot-simulation", daemon=True)
        self.simulation = simulation
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(0.05):
            self.simulation.tick()

    def stop(self) -> None:
        self._stop_event.set()


class RobotRequestHandler(BaseHTTPRequestHandler):
    server_version = "Grupo2Robot/1.0"
    static_files = {
        "/": "index.html",
        "/index.html": "index.html",
        "/styles.css": "styles.css",
        "/app.js": "app.js",
        "/bancada": "bancada.html",
        "/bancada.html": "bancada.html",
        "/bancada.css": "bancada.css",
        "/bancada.js": "bancada.js",
    }

    @property
    def simulation(self) -> RobotSimulation:
        return self.server.simulation  # type: ignore[attr-defined]

    @property
    def camera_hub(self) -> CameraStreamHub:
        return self.server.camera_hub  # type: ignore[attr-defined]

    @property
    def runtime_config(self) -> dict[str, str]:
        return self.server.runtime_config  # type: ignore[attr-defined]

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 65536:
            raise ValueError("Corpo JSON ausente ou muito grande.")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON inválido.") from exc
        if not isinstance(data, dict):
            raise ValueError("O corpo precisa ser um objeto JSON.")
        return data

    def _stream_camera(self) -> None:
        """Serve o último quadro disponível sem abrir outro upstream.

        Cada cliente HTTP recebe somente quadros novos a partir de sua última
        sequência observada. O hub mantém um único consumidor da ESP32-CAM e
        não acumula uma fila de JPEGs antigos.
        """
        client_id = self.camera_hub.register_downstream()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.flush()
        # Um navegador lento não pode prender indefinidamente a thread deste
        # cliente; o hub upstream continua independente e /api/command usa
        # outra thread do ThreadingHTTPServer.
        self.connection.settimeout(3.0)

        last_sequence = 0
        try:
            while not self.camera_hub.stopped:
                item = self.camera_hub.wait_for_frame(last_sequence, timeout=1.0)
                if item is None:
                    continue
                sequence, jpeg, _received_at = item
                part = (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                    + jpeg
                    + b"\r\n"
                )
                self.wfile.write(part)
                self.wfile.flush()
                self.camera_hub.record_downstream(client_id, sequence, len(part))
                last_sequence = sequence
        except (BrokenPipeError, ConnectionResetError, socket.timeout, OSError):
            # O cliente saiu ou a rede deixou de aceitar dados; a thread HTTP
            # termina sem afetar o consumidor único mantido pelo hub.
            return
        finally:
            self.camera_hub.unregister_downstream(client_id)

    def _capture_camera(self) -> None:
        """Entrega uma cópia única do JPEG mais recente mantido pelo hub."""
        item = self.camera_hub.latest_frame()
        if item is None:
            self._send_json({"error": "nenhum JPEG recebido da câmera"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        sequence, jpeg, captured_at = item
        age_ms = max(0.0, (time.monotonic() - captured_at) * 1000.0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(jpeg)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("X-Camera-Sequence", str(sequence))
        self.send_header("X-Camera-Frame-Age-Ms", f"{age_ms:.1f}")
        self.end_headers()
        self.wfile.write(jpeg)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/camera/stream":
            self._stream_camera()
            return
        if route == "/api/camera/capture":
            self._capture_camera()
            return
        if route == "/api/state":
            self._send_json(self.simulation.snapshot())
            return
        if route == "/api/robot/command":
            self._send_json(self.simulation.hardware_command())
            return
        if route == "/api/camera/status":
            self._send_json(self.camera_hub.status())
            return
        if route == "/api/config":
            self._send_json({
                "camera_url": self.runtime_config["camera_url"],
                "robot_url": self.runtime_config["robot_url"],
                "wifi_provisioning": "usb_serial_or_http",
            })
            return
        if route == "/api/health":
            self._send_json({"ok": True, "service": "grupo-2-digital-twin"})
            return
        if route in self.static_files:
            path = WEB_ROOT / self.static_files[route]
            if not path.exists():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        try:
            payload = self._read_json()
            if route == "/api/command":
                result = self.simulation.apply_command(payload)
            elif route == "/api/simulation":
                result = self.simulation.apply_simulation(payload)
            elif route == "/api/robot/telemetry":
                result = self.simulation.receive_telemetry(payload)
            elif route == "/api/vision":
                result = self.simulation.receive_vision(payload)
            elif route == "/api/config":
                result = self.server.update_runtime_config(payload)  # type: ignore[attr-defined]
            elif route == "/api/robot/wifi":
                result = self.server.provision_robot_wifi(payload)  # type: ignore[attr-defined]
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._send_json(result)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # defensive boundary for a classroom prototype
            self._send_json({"error": f"Falha interna: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


class RobotHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        simulation: RobotSimulation,
        camera_hub: CameraStreamHub,
        runtime_config: dict[str, str] | None = None,
    ) -> None:
        super().__init__(address, RobotRequestHandler)
        self.simulation = simulation
        self.camera_hub = camera_hub
        self.runtime_config = runtime_config or {"camera_url": camera_hub.stream_url, "robot_url": DEFAULT_ROBOT_URL}
        self._runtime_config_lock = threading.Lock()

    def update_runtime_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._runtime_config_lock:
            camera_url = _validated_http_url(
                payload.get("camera_url", self.runtime_config["camera_url"]),
                "URL da câmera",
            )
            robot_url = str(payload.get("robot_url", self.runtime_config["robot_url"]) or "").strip()
            if robot_url:
                robot_url = _validated_http_url(robot_url, "URL do ESP32-C6").rstrip("/")
            if camera_url != self.runtime_config["camera_url"]:
                self.camera_hub.reconfigure(camera_url)
            self.runtime_config.update({"camera_url": camera_url, "robot_url": robot_url})
            save_runtime_config(self.runtime_config)
            return {
                "ok": True,
                "camera_url": camera_url,
                "robot_url": robot_url,
                "message": "Configuração salva; o hub usa somente um upstream da câmera.",
            }

    def provision_robot_wifi(self, payload: dict[str, Any]) -> dict[str, Any]:
        ssid = str(payload.get("ssid", "")).strip()
        password = str(payload.get("password", ""))
        if not ssid or len(ssid) > 32:
            raise ValueError("SSID inválido (1–32 caracteres).")
        if len(password) > 63:
            raise ValueError("Senha Wi-Fi muito longa (máximo de 63 caracteres).")
        robot_url = self.runtime_config["robot_url"]
        if not robot_url:
            raise ValueError("Configure primeiro a URL atual do ESP32-C6.")
        endpoint = robot_url.rstrip("/") + "/wifi"
        request = urllib.request.Request(
            endpoint,
            data=urlencode({"ssid": ssid, "password": password}).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5.0) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"O firmware atual rejeitou /wifi (HTTP {exc.code}); grave a versão com provisioning primeiro.") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if robot_url.lower().endswith(".local"):
                raise RuntimeError(
                    "robo-c6.local não foi encontrado na rede. Conecte o C6 ao Wi‑Fi atual "
                    "ou use o IP dele; para provisionamento inicial, use o AP Robo-C6 em http://192.168.4.1."
                ) from exc
            raise RuntimeError(f"Não foi possível alcançar o ESP32-C6 em {robot_url}: {exc}") from exc
        return {
            "ok": True,
            "message": "Wi-Fi salvo no ESP32-C6; ele reiniciará e tentará a nova rede.",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard e gêmeo digital do Robô de Logística e Fuga")
    parser.add_argument("--host", default="127.0.0.1", help="Interface de rede (padrão: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Porta HTTP (padrão: 8765)")
    parser.add_argument(
        "--serial-port",
        default=os.environ.get("ROBOT_SERIAL_PORT", ""),
        help="Porta serial do ESP32-C6; omitida mantém apenas a simulação",
    )
    parser.add_argument(
        "--camera-url",
        default=os.environ.get("CAMERA_STREAM_URL", DEFAULT_CAMERA_URL),
        help="URL upstream única da ESP32-CAM (/capture recomendado)",
    )
    parser.add_argument(
        "--robot-url",
        default=os.environ.get("ROBOT_C6_URL", DEFAULT_ROBOT_URL),
        help="URL do ESP32-C6 (por exemplo http://robo-c6.local ou IP descoberto)",
    )
    parser.add_argument(
        "--vision-color",
        choices=("red", "blue", "green", "yellow"),
        default=os.environ.get("VISION_TARGET_COLOR", "red"),
        help="cor forte do alvo visual para o modo AUTONOMO",
    )
    parser.add_argument(
        "--disable-vision",
        action="store_true",
        help="não iniciar o detector visual (útil para diagnóstico do painel)",
    )
    args = parser.parse_args()
    runtime_config = load_runtime_config(args.camera_url, args.robot_url)

    hardware: Any = C6SerialBridge(args.serial_port or None) if args.serial_port else C6HttpBridge(runtime_config["robot_url"] or None)
    simulation = RobotSimulation(hardware=hardware)
    camera_hub = CameraStreamHub(runtime_config["camera_url"])
    vision_worker = None
    if not args.disable_vision:
        try:
            from vision_autonomy import VisionAutonomyWorker

            vision_worker = VisionAutonomyWorker(camera_hub, simulation, args.vision_color)
            simulation.receive_vision({
                "confidence": 0.0,
                "decision": "STOP",
                "source": "COLOR_TARGET",
                "distance_valid": False,
                "reason": "aguardando_primeiro_frame",
            })
        except RuntimeError as exc:
            print(f"Visão autônoma indisponível: {exc}")
    runner = SimulationRunner(simulation)
    server = RobotHTTPServer((args.host, args.port), simulation, camera_hub, runtime_config)
    runner.start()
    camera_hub.start()
    if vision_worker:
        vision_worker.start()
    print(f"Dashboard disponível em http://{args.host}:{args.port}")
    if args.host == "0.0.0.0":
        print(f"Na rede local, abra http://IP-DESTE-COMPUTADOR:{args.port}")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nEncerrando…")
    finally:
        runner.stop()
        if vision_worker:
            vision_worker.stop()
        camera_hub.stop()
        server.server_close()
        hardware.close()


if __name__ == "__main__":
    main()
