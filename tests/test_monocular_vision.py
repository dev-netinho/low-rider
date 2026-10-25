import math
import sys
import unittest
from pathlib import Path


CONTROLLER_DIR = (
    Path(__file__).resolve().parents[1]
    / "simulation"
    / "webots"
    / "controllers"
    / "carro_vision"
)
sys.path.insert(0, str(CONTROLLER_DIR))

from monocular_vision import estimate_clearances  # noqa: E402


def corridor_image(front_row: int, center_offset: int = 0):
    width, height = 320, 240

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        half_width = 24 + max(0, y - front_row) * 0.72
        center = width / 2 + center_offset
        floor = y >= front_row and center - half_width <= x <= center + half_width
        return (52, 64, 57) if floor else (205, 210, 203)

    return width, height, pixel


class MonocularVisionTests(unittest.TestCase):
    def estimate(self, front_row: int, center_offset: int = 0):
        width, height, pixel = corridor_image(front_row, center_offset)
        return estimate_clearances(width, height, math.radians(66), pixel)

    def test_centered_corridor_has_balanced_clearance(self) -> None:
        estimate = self.estimate(front_row=78)
        self.assertAlmostEqual(estimate.left_cm, estimate.right_cm, delta=3.0)
        self.assertGreater(estimate.confidence, 0.5)

    def test_image_shift_reveals_more_space_on_the_right(self) -> None:
        estimate = self.estimate(front_row=78, center_offset=34)
        self.assertGreater(estimate.right_cm, estimate.left_cm)

    def test_lower_floor_boundary_means_nearer_wall(self) -> None:
        far = self.estimate(front_row=78)
        near = self.estimate(front_row=168)
        self.assertLess(near.front_cm, far.front_cm)


if __name__ == "__main__":
    unittest.main()
