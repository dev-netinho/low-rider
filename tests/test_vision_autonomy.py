import unittest

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None
    np = None

from server import RobotSimulation
from vision_autonomy import ColorTargetDetector


@unittest.skipIf(cv2 is None, "OpenCV não instalado")
class ColorTargetTests(unittest.TestCase):
    def jpeg_with_target(self, x: int) -> bytes:
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        cv2.rectangle(image, (x, 45), (x + 24, 75), (0, 0, 255), -1)
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        self.assertTrue(ok)
        return encoded.tobytes()

    def test_position_decides_direction(self):
        detector = ColorTargetDetector("red")
        self.assertEqual(detector.detect(self.jpeg_with_target(8))["decision"], "LEFT")
        self.assertEqual(detector.detect(self.jpeg_with_target(68))["decision"], "FORWARD")
        self.assertEqual(detector.detect(self.jpeg_with_target(128))["decision"], "RIGHT")

    def test_missing_target_is_stop(self):
        detector = ColorTargetDetector("red")
        image = np.zeros((120, 160, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        result = detector.detect(encoded.tobytes())
        self.assertEqual(result["decision"], "STOP")
        self.assertEqual(result["confidence"], 0.0)


class RealVisionStateTests(unittest.TestCase):
    def test_color_target_drives_only_in_autonomous_mode(self):
        simulation = RobotSimulation()
        simulation.apply_command({"action": "set_mode", "mode": "AUTONOMO"})
        simulation.receive_vision({
            "decision": "LEFT", "confidence": 0.9, "target_x": 0.2,
            "target_area": 0.03, "source": "COLOR_TARGET", "distance_valid": False,
        })
        simulation.tick()
        state = simulation.snapshot()
        self.assertLess(state["motors"]["left"], 0)
        self.assertGreater(state["motors"]["right"], 0)
        self.assertFalse(state["sensors"]["vision_distance_valid"])
        self.assertEqual(state["sensors"]["vision_decision"], "LEFT")

    def test_color_target_stop_has_priority(self):
        simulation = RobotSimulation()
        simulation.apply_command({"action": "set_mode", "mode": "AUTONOMO"})
        simulation.receive_vision({
            "decision": "STOP", "confidence": 0.0, "source": "COLOR_TARGET",
            "distance_valid": False, "reason": "alvo_ausente",
        })
        simulation.tick()
        state = simulation.snapshot()
        self.assertEqual(state["motors"]["left"], 0.0)
        self.assertEqual(state["motors"]["right"], 0.0)
        self.assertEqual(state["system_state"], "SEM_VISAO")

    def test_hardware_link_loss_zeros_requested_motion(self):
        class OfflineHardware:
            enabled = True
            online = False
            last_error = "offline"

            def send_drive(self, left, right, force=False):
                return False

        simulation = RobotSimulation(hardware=OfflineHardware())
        simulation.apply_command({"action": "set_mode", "mode": "MANUAL"})
        simulation.apply_command({"action": "drive", "throttle": 80, "steering": 0})
        state = simulation.snapshot()
        self.assertEqual(state["motors"]["left"], 0.0)
        self.assertEqual(state["motors"]["right"], 0.0)
        self.assertEqual(state["system_state"], "SEM_CONEXAO")


if __name__ == "__main__":
    unittest.main()
