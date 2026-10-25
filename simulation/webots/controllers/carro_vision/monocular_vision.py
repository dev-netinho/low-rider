"""Estimativa geométrica de corredor usando apenas uma imagem monocular.

O piso escuro é segmentado da parede clara. Os pixels da borda piso/parede
são projetados no plano do chão usando altura, inclinação e campo de visão
conhecidos da câmera. Não há leitura de distância, lidar ou ultrassom.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Callable


PixelReader = Callable[[int, int], tuple[int, int, int]]


@dataclass(frozen=True)
class VisionEstimate:
    front_cm: float
    left_cm: float
    right_cm: float
    confidence: float

    @property
    def corridor_width_cm(self) -> float:
        return self.left_cm + self.right_cm


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def is_floor(pixel: tuple[int, int, int]) -> bool:
    """Classificador deliberadamente simples para o piso do mundo de ensaio."""
    red, green, blue = pixel
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    blue_spray = blue > 115 and blue > red * 1.35
    return luminance < 146 and not blue_spray


def project_to_ground(
    u: float,
    v: float,
    width: int,
    height: int,
    horizontal_fov: float,
    camera_height_m: float,
    pitch_down_rad: float,
) -> tuple[float, float] | None:
    """Retorna (lateral_direita, frente) em metros para um pixel no chão."""
    fx = width / (2.0 * math.tan(horizontal_fov / 2.0))
    vertical_fov = 2.0 * math.atan(math.tan(horizontal_fov / 2.0) * height / width)
    fy = height / (2.0 * math.tan(vertical_fov / 2.0))
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0

    ray_right = (u - cx) / fx
    ray_up = (cy - v) / fy
    ray_forward = 1.0

    vertical = ray_up * math.cos(pitch_down_rad) - ray_forward * math.sin(pitch_down_rad)
    forward = ray_up * math.sin(pitch_down_rad) + ray_forward * math.cos(pitch_down_rad)
    if vertical >= -1e-4 or forward <= 0:
        return None
    scale = camera_height_m / -vertical
    return ray_right * scale, forward * scale


def estimate_clearances(
    width: int,
    height: int,
    horizontal_fov: float,
    pixel_at: PixelReader,
    camera_height_m: float = 0.164,
    pitch_down_rad: float = 0.22,
) -> VisionEstimate:
    """Estima espaços frontal/laterais a partir das bordas visíveis do piso."""
    center = width // 2
    left_samples: list[float] = []
    right_samples: list[float] = []
    sampled_rows = (0.32, 0.36, 0.40, 0.44, 0.48, 0.52, 0.58, 0.64)

    for fraction in sampled_rows:
        row = min(height - 1, max(0, int(height * fraction)))
        if not is_floor(pixel_at(center, row)):
            continue

        left = center
        while left > 1 and is_floor(pixel_at(left, row)):
            left -= 1
        right = center
        while right < width - 2 and is_floor(pixel_at(right, row)):
            right += 1

        left_hit = project_to_ground(
            left + 1, row, width, height, horizontal_fov, camera_height_m, pitch_down_rad
        )
        right_hit = project_to_ground(
            right - 1, row, width, height, horizontal_fov, camera_height_m, pitch_down_rad
        )
        if left > 1 and left_hit is not None:
            left_samples.append(abs(left_hit[0]))
        if right < width - 2 and right_hit is not None:
            right_samples.append(abs(right_hit[0]))

    boundary_row = height - 1
    saw_floor = False
    non_floor_run = 0
    for row in range(height - 1, max(0, int(height * 0.20)), -1):
        if is_floor(pixel_at(center, row)):
            saw_floor = True
            boundary_row = row
            non_floor_run = 0
        elif saw_floor:
            non_floor_run += 1
            if non_floor_run >= 3:
                break

    front_hit = project_to_ground(
        center, boundary_row, width, height, horizontal_fov, camera_height_m, pitch_down_rad
    )
    front_m = front_hit[1] if front_hit else 6.0
    left_m = statistics.median(left_samples) if left_samples else 1.5
    right_m = statistics.median(right_samples) if right_samples else 1.5
    sample_quality = (len(left_samples) + len(right_samples)) / (2.0 * len(sampled_rows))
    confidence = clamp(0.35 + sample_quality * 0.6 + (0.05 if saw_floor else 0.0), 0.0, 0.98)

    return VisionEstimate(
        front_cm=round(clamp(front_m * 100.0, 2.0, 600.0), 1),
        left_cm=round(clamp(left_m * 100.0, 2.0, 300.0), 1),
        right_cm=round(clamp(right_m * 100.0, 2.0, 300.0), 1),
        confidence=round(confidence, 3),
    )
