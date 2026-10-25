"""Controlador Webots do carro 4x4 integrado ao servidor local.

Percepção de navegação: somente a câmera frontal. A API do Supervisor é usada
apenas para desenhar o jato de água; ela não fornece pose ou distância ao
algoritmo de navegação.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request

from controller import Camera, Supervisor

from monocular_vision import VisionEstimate, estimate_clearances


TIME_STEP_MS = 32
API_BASE = os.environ.get("WEBOTS_API_BASE", "http://127.0.0.1:8765")
MAX_WHEEL_SPEED = 22.0
FORWARD_SIGN = -1.0
NETWORK_PERIOD_STEPS = 3
NETWORK_FAILSAFE_S = 1.0


def request_json(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=0.22) as response:
        return json.loads(response.read().decode("utf-8"))


class CarroVision(Supervisor):
    def __init__(self) -> None:
        super().__init__()
        self.camera = self.getDevice("ESP32-CAM (visao do robo - pode fechar)")
        self.camera.enable(TIME_STEP_MS)
        self.width = self.camera.getWidth()
        self.height = self.camera.getHeight()
        self.horizontal_fov = self.camera.getFov()

        motor_names = (
            "motor dianteiro esquerdo",
            "motor traseiro esquerdo",
            "motor dianteiro direito",
            "motor traseiro direito",
        )
        sensor_names = (
            "encoder dianteiro esquerdo",
            "encoder traseiro esquerdo",
            "encoder dianteiro direito",
            "encoder traseiro direito",
        )
        self.motors = [self.getDevice(name) for name in motor_names]
        self.position_sensors = [self.getDevice(name) for name in sensor_names]
        for motor in self.motors:
            motor.setPosition(float("inf"))
            motor.setVelocity(0.0)
        for sensor in self.position_sensors:
            sensor.enable(TIME_STEP_MS)

        self.robot_node = self.getSelf()
        self.world_children = self.getRoot().getField("children")
        self.command = {
            "left": 0.0,
            "right": 0.0,
            "pump": False,
            "sound": False,
            "emergency": False,
            "mode": "PARADO",
        }
        self.last_server_contact = 0.0
        self.step_counter = 0
        self.drop_counter = 0
        self.droplets: list[tuple[object, float]] = []
        self.latest_vision = VisionEstimate(600.0, 150.0, 150.0, 0.0)
        self.last_sensor_positions: list[float] | None = None
        self.last_sensor_time: float | None = None
        self.wheel_rad_s = [0.0, 0.0, 0.0, 0.0]
        self.capture_path = os.environ.get("WEBOTS_CAPTURE_PATH")
        self.capture_done = False
        print(f"[Webots] Carro 4x4 iniciado; aguardando servidor em {API_BASE}")

    def estimate_vision(self) -> VisionEstimate:
        image = self.camera.getImage()

        def pixel_at(x: int, y: int) -> tuple[int, int, int]:
            return (
                Camera.imageGetRed(image, self.width, x, y),
                Camera.imageGetGreen(image, self.width, x, y),
                Camera.imageGetBlue(image, self.width, x, y),
            )

        return estimate_clearances(
            self.width,
            self.height,
            self.horizontal_fov,
            pixel_at,
            camera_height_m=0.164,
            pitch_down_rad=0.22,
        )

    def exchange_with_server(self) -> None:
        started = time.monotonic()
        self.latest_vision = self.estimate_vision()
        vision_payload = {
            "front_cm": self.latest_vision.front_cm,
            "left_cm": self.latest_vision.left_cm,
            "right_cm": self.latest_vision.right_cm,
            "confidence": self.latest_vision.confidence,
            "source": "WEBOTS_ESP32_CAM",
        }
        try:
            request_json("/api/vision", "POST", vision_payload)
            request_json(
                "/api/robot/telemetry",
                "POST",
                {
                    "simulation": "WEBOTS",
                    "safety_stop": False,
                    "uptime_ms": int(self.getTime() * 1000),
                    "vision_latency_ms": int((time.monotonic() - started) * 1000),
                    "wheel_rad_s": {
                        "m1": round(self.wheel_rad_s[0], 3),
                        "m2": round(self.wheel_rad_s[1], 3),
                        "m3": round(self.wheel_rad_s[2], 3),
                        "m4": round(self.wheel_rad_s[3], 3),
                    },
                },
            )
            self.command = request_json("/api/robot/command")
            self.last_server_contact = time.monotonic()
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            if time.monotonic() - self.last_server_contact > NETWORK_FAILSAFE_S:
                self.command.update(left=0.0, right=0.0, pump=False, sound=False, emergency=True)
            if self.step_counter % 90 == 0:
                print(f"[Webots] servidor indisponível; saídas em segurança: {error}")

    def apply_motors(self) -> None:
        if self.command.get("emergency"):
            left_percent = right_percent = 0.0
        else:
            left_percent = float(self.command.get("left", 0.0))
            right_percent = float(self.command.get("right", 0.0))
        left_speed = FORWARD_SIGN * left_percent / 100.0 * MAX_WHEEL_SPEED
        right_speed = FORWARD_SIGN * right_percent / 100.0 * MAX_WHEEL_SPEED
        self.motors[0].setVelocity(left_speed)
        self.motors[1].setVelocity(left_speed)
        self.motors[2].setVelocity(right_speed)
        self.motors[3].setVelocity(right_speed)

    def measure_wheel_speeds(self) -> None:
        """Mede a velocidade de cada roda pelos encoders do mundo físico."""
        now = self.getTime()
        positions = [sensor.getValue() for sensor in self.position_sensors]
        if self.last_sensor_positions is None or self.last_sensor_time is None:
            self.last_sensor_positions = positions
            self.last_sensor_time = now
            return
        elapsed = now - self.last_sensor_time
        if elapsed <= 0:
            return
        for index, (position, previous) in enumerate(zip(positions, self.last_sensor_positions)):
            delta = (position - previous + math.pi) % (2 * math.pi) - math.pi
            normalized_speed = FORWARD_SIGN * delta / elapsed
            filtered = self.wheel_rad_s[index] * 0.68 + normalized_speed * 0.32
            self.wheel_rad_s[index] = 0.0 if abs(filtered) < 0.02 else filtered
        self.last_sensor_positions = positions
        self.last_sensor_time = now

    def update_hud(self) -> None:
        left = float(self.command.get("left", 0.0))
        right = float(self.command.get("right", 0.0))
        mode = str(self.command.get("mode", "PARADO"))
        pump = "LIGADA" if self.command.get("pump") else "desligada"
        sound = "LIGADO" if self.command.get("sound") else "desligado"
        hud_x = 0.41
        self.setLabel(0, f"CARRO 4x4 | modo {mode}", hud_x, 0.018, 0.022, 0xF7FAF5)
        labels = ("M1 dianteiro esq.", "M2 traseiro esq.", "M3 dianteiro dir.", "M4 traseiro dir.")
        commands = (left, left, right, right)
        for index, (label, command, speed) in enumerate(zip(labels, commands, self.wheel_rad_s), start=1):
            rpm = speed * 60.0 / (2.0 * math.pi)
            self.setLabel(
                index,
                f"{label}: {command:+.0f}% | {speed:+.1f} rad/s | {rpm:+.0f} rpm",
                hud_x,
                0.018 + index * 0.031,
                0.016,
                0xF7FAF5,
            )
        self.setLabel(5, f"Bomba: {pump} | MS-129BT: {sound}", hud_x, 0.185, 0.017, 0x69D5C2)
        self.setLabel(
            6,
            f"ESP32-CAM: frente {self.latest_vision.front_cm:.0f} cm | E {self.latest_vision.left_cm:.0f} | D {self.latest_vision.right_cm:.0f}",
            hud_x,
            0.216,
            0.016,
            0xCBB8FF,
        )
        self.setLabel(7, "ESP32-CAM: janela auxiliar (pode fechar)", hud_x, 0.247, 0.015, 0xFF9B78)

    @staticmethod
    def transform_local(position: list[float], orientation: list[float], local: tuple[float, float, float]) -> list[float]:
        x, y, z = local
        return [
            position[0] + orientation[0] * x + orientation[1] * y + orientation[2] * z,
            position[1] + orientation[3] * x + orientation[4] * y + orientation[5] * z,
            position[2] + orientation[6] * x + orientation[7] * y + orientation[8] * z,
        ]

    def spawn_water_drop(self) -> None:
        position = self.robot_node.getPosition()
        orientation = self.robot_node.getOrientation()
        nozzle = self.transform_local(position, orientation, (0.18, 0.0, 0.075))
        forward = [orientation[0], orientation[3], orientation[6]]
        phase = self.drop_counter * 1.73
        velocity = [
            forward[0] * 1.45 + math.sin(phase) * 0.08,
            forward[1] * 1.45 + math.cos(phase) * 0.08,
            forward[2] * 1.45 + 0.22 + math.sin(phase * 0.7) * 0.05,
        ]
        name = f"WATER_{self.drop_counter}"
        self.drop_counter += 1
        node_text = f"""DEF {name} Solid {{
          translation {nozzle[0]:.5f} {nozzle[1]:.5f} {nozzle[2]:.5f}
          children [ Shape {{
            appearance PBRAppearance {{ baseColor 0.08 0.55 0.95 transparency 0.16 roughness 0.2 metalness 0 }}
            geometry Sphere {{ radius 0.009 }}
          }} ]
          boundingObject Sphere {{ radius 0.009 }}
          physics Physics {{ density -1 mass 0.001 }}
        }}"""
        self.world_children.importMFNodeFromString(-1, node_text)
        droplet = self.getFromDef(name)
        if droplet is not None:
            droplet.setVelocity([*velocity, 0.0, 0.0, 0.0])
            self.droplets.append((droplet, self.getTime() + 1.2))

    def update_pump_visualization(self) -> None:
        active = bool(self.command.get("pump")) and not bool(self.command.get("emergency"))
        if active and self.step_counter % 2 == 0:
            self.spawn_water_drop()
        alive: list[tuple[object, float]] = []
        for droplet, expires_at in self.droplets:
            if self.getTime() >= expires_at:
                droplet.remove()
            else:
                alive.append((droplet, expires_at))
        self.droplets = alive

    def run(self) -> None:
        while self.step(TIME_STEP_MS) != -1:
            self.step_counter += 1
            self.measure_wheel_speeds()
            if self.step_counter % NETWORK_PERIOD_STEPS == 0:
                self.exchange_with_server()
            self.apply_motors()
            self.update_pump_visualization()
            if self.step_counter % 3 == 0:
                self.update_hud()
            if self.capture_path and not self.capture_done and self.getTime() >= 0.8:
                self.exportImage(self.capture_path, 100)
                self.capture_done = True


if __name__ == "__main__":
    CarroVision().run()
