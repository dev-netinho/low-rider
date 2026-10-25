import unittest

from server import RobotSimulation


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class RobotSimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.robot = RobotSimulation(clock=self.clock)

    def advance(self, seconds: float) -> dict:
        self.clock.advance(seconds)
        return self.robot.snapshot()

    def test_boots_with_every_output_off(self) -> None:
        state = self.robot.snapshot()
        self.assertEqual(state["mode"], "PARADO")
        self.assertEqual(state["motors"]["left"], 0)
        self.assertEqual(state["motors"]["right"], 0)
        self.assertFalse(state["actuators"]["pump"])
        self.assertFalse(state["actuators"]["sound"])

    def test_manual_mixing_drives_each_side(self) -> None:
        self.robot.apply_command({"action": "set_mode", "mode": "MANUAL"})
        self.robot.apply_command({"action": "drive", "throttle": 60, "steering": 20})
        state = self.advance(0.2)
        self.assertGreater(state["motors"]["left"], state["motors"]["right"])
        self.assertGreater(state["motors"]["right"], 0)
        self.assertEqual(state["system_state"], "OPERANDO")

    def test_manual_timeout_stops_motion(self) -> None:
        self.robot.apply_command({"action": "set_mode", "mode": "MANUAL"})
        self.robot.apply_command({"action": "drive", "throttle": 70, "steering": 0})
        self.advance(0.2)
        state = self.advance(0.8)
        self.assertEqual(state["system_state"], "SEM_COMANDO")
        self.assertEqual(state["motors"]["left"], 0)
        self.assertEqual(state["motors"]["right"], 0)

    def test_releasing_manual_command_stops_immediately(self) -> None:
        self.robot.apply_command({"action": "set_mode", "mode": "MANUAL"})
        self.robot.apply_command({"action": "drive", "throttle": 70, "steering": 0})
        self.advance(0.2)
        state = self.robot.apply_command({"action": "drive", "throttle": 0, "steering": 0})
        self.assertEqual(state["motors"]["left"], 0)
        self.assertEqual(state["motors"]["right"], 0)

    def test_manual_mode_does_not_choose_path_from_camera(self) -> None:
        self.robot.apply_command({"action": "set_mode", "mode": "MANUAL"})
        self.robot.receive_vision({"front_cm": 18, "left_cm": 20, "right_cm": 70, "confidence": 0.9})
        self.robot.apply_command({"action": "drive", "throttle": 80, "steering": 0})
        state = self.advance(0.2)
        self.assertEqual(state["system_state"], "OPERANDO")
        self.assertGreater(state["motors"]["left"], 0)
        self.assertGreater(state["motors"]["right"], 0)

    def test_pump_has_hard_time_limit(self) -> None:
        state = self.robot.apply_command({"action": "pump", "enabled": True, "duration_ms": 3000})
        self.assertTrue(state["actuators"]["pump"])
        state = self.advance(3.1)
        self.assertFalse(state["actuators"]["pump"])

    def test_link_loss_disables_all_outputs(self) -> None:
        self.robot.apply_command({"action": "set_mode", "mode": "MANUAL"})
        self.robot.apply_command({"action": "drive", "throttle": 60, "steering": 0})
        self.robot.apply_command({"action": "sound", "enabled": True})
        self.robot.apply_command({"action": "pump", "enabled": True, "duration_ms": 2000})
        state = self.robot.apply_simulation({"link_online": False})
        self.assertEqual(state["system_state"], "SEM_CONEXAO")
        self.assertEqual(state["motors"]["left"], 0)
        self.assertFalse(state["actuators"]["pump"])
        self.assertFalse(state["actuators"]["sound"])

    def test_autonomous_mode_uses_camera_clearance_to_choose_path(self) -> None:
        self.robot.apply_command({"action": "set_mode", "mode": "AUTONOMO"})
        self.robot.receive_vision({"front_cm": 20, "left_cm": 24, "right_cm": 78, "confidence": 0.9})
        state = self.advance(0.2)
        self.assertGreater(state["motors"]["left"], 0)
        self.assertLess(state["motors"]["right"], 0)
        self.assertIn("direita", state["autonomous_action"])

    def test_autonomous_mode_stops_when_camera_data_expires(self) -> None:
        self.robot.apply_command({"action": "set_mode", "mode": "AUTONOMO"})
        self.robot.receive_vision({"front_cm": 120, "left_cm": 50, "right_cm": 50, "confidence": 0.9})
        self.advance(0.2)
        state = self.advance(1.6)
        self.assertEqual(state["system_state"], "SEM_VISAO")
        self.assertEqual(state["motors"]["left"], 0)
        self.assertEqual(state["motors"]["right"], 0)

    def test_webots_wheel_speeds_are_exposed_to_the_virtual_bench(self) -> None:
        wheel_rad_s = {"m1": 9.8, "m2": 9.7, "m3": 8.6, "m4": 8.5}
        state = self.robot.receive_telemetry({"simulation": "WEBOTS", "wheel_rad_s": wheel_rad_s})
        self.assertTrue(state["hardware_online"])
        self.assertEqual(state["remote_telemetry"]["simulation"], "WEBOTS")
        self.assertEqual(state["remote_telemetry"]["wheel_rad_s"], wheel_rad_s)

    def test_emergency_latches_safe_mode(self) -> None:
        state = self.robot.apply_command({"action": "emergency", "active": True})
        self.assertTrue(state["emergency"])
        self.assertEqual(state["mode"], "PARADO")
        with self.assertRaises(ValueError):
            self.robot.apply_command({"action": "set_mode", "mode": "MANUAL"})


if __name__ == "__main__":
    unittest.main()
