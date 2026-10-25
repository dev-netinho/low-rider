"""Percepção visual mínima para a demonstração física do Grupo 2.

O detector trabalha somente no JPEG mais recente publicado pelo CameraStreamHub.
Ele não mantém fila e não usa a imagem sintética de distância do gêmeo digital.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class ColorTargetDetector:
    """Detecta o maior alvo de uma cor forte e decide uma ação direcional."""

    RANGES = {
        "red": (((0, 70, 50), (12, 255, 255)), ((168, 70, 50), (180, 255, 255))),
        "blue": (((90, 70, 45), (135, 255, 255)),),
        "green": (((38, 55, 45), (88, 255, 255)),),
        "yellow": (((18, 70, 55), (38, 255, 255)),),
    }

    def __init__(self, color: str = "red") -> None:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised on setup
            raise RuntimeError("OpenCV/numpy não instalados; visão autônoma indisponível") from exc
        self.cv2 = cv2
        self.np = np
        self.color = color if color in self.RANGES else "red"

    def detect(self, jpeg: bytes) -> dict[str, Any]:
        cv2, np = self.cv2, self.np
        encoded = np.frombuffer(jpeg, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            return self._result("STOP", 0.0, None, 0.0, "jpeg_invalido")

        height, width = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = np.zeros((height, width), dtype=np.uint8)
        for lower, upper in self.RANGES[self.color]:
            mask |= cv2.inRange(hsv, np.array(lower), np.array(upper))
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return self._result("STOP", 0.0, None, 0.0, "alvo_ausente")

        contour = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(contour))
        image_area = float(width * height)
        area_ratio = area / image_area
        minimum_ratio = 0.002
        if area_ratio < minimum_ratio:
            return self._result("STOP", 0.0, None, area_ratio, "alvo_pequeno")

        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            return self._result("STOP", 0.0, None, area_ratio, "centro_indisponivel")
        center_x = float(moments["m10"] / moments["m00"] / width)
        confidence = min(1.0, max(0.0, (area_ratio - minimum_ratio) / 0.08))

        # O objeto muito grande está próximo demais para avançar somente por
        # imagem; sem sensor de distância, a decisão segura é parar.
        if area_ratio >= 0.20:
            decision, reason = "STOP", "alvo_muito_proximo_por_area"
        elif center_x < 0.40:
            decision, reason = "LEFT", "alvo_a_esquerda"
        elif center_x > 0.60:
            decision, reason = "RIGHT", "alvo_a_direita"
        else:
            decision, reason = "FORWARD", "alvo_centralizado"
        return self._result(decision, confidence, center_x, area_ratio, reason)

    @staticmethod
    def _result(decision: str, confidence: float, center_x: float | None, area: float, reason: str) -> dict[str, Any]:
        return {
            "decision": decision,
            "confidence": round(float(confidence), 3),
            "target_x": None if center_x is None else round(float(center_x), 4),
            "target_area": round(float(area), 5),
            "reason": reason,
            "source": "COLOR_TARGET",
            "distance_valid": False,
        }


class VisionAutonomyWorker:
    """Consome apenas o frame mais recente e atualiza a máquina de estados."""

    def __init__(self, camera_hub: Any, simulation: Any, color: str = "red") -> None:
        self.camera_hub = camera_hub
        self.simulation = simulation
        self.detector = ColorTargetDetector(color)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_sequence = 0
        self.last_error = ""

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="vision-autonomy", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            item = self.camera_hub.latest_frame()
            if item is None or item[0] == self.last_sequence:
                self._stop.wait(0.02)
                continue
            sequence, jpeg, _captured_at = item
            self.last_sequence = sequence
            try:
                result = self.detector.detect(jpeg)
                result["frame_sequence"] = sequence
                self.simulation.receive_vision(result)
                self.last_error = ""
            except Exception as exc:  # preserve safety: invalid vision means stop
                self.last_error = str(exc)
                self.simulation.receive_vision({
                    "decision": "STOP",
                    "confidence": 0.0,
                    "target_x": None,
                    "target_area": 0.0,
                    "source": "COLOR_TARGET",
                    "distance_valid": False,
                    "reason": "falha_detector",
                })

