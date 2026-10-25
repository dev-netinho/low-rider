import http.client
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from server import CameraStreamHub, MultipartJpegParser, RobotHTTPServer, RobotSimulation


BOUNDARY = b"frame"
JPEG_A = b"\xff\xd8fake-a\xff\xd9"
JPEG_B = b"\xff\xd8fake-b\xff\xd9"


def multipart_part(jpeg: bytes) -> bytes:
    return (
        b"--frame\r\nContent-Type: image/jpeg\r\n"
        + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
        + jpeg
        + b"\r\n"
    )


class UpstreamState:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.connections = 0
        self.lock = threading.Lock()


class FakeCameraHandler(BaseHTTPRequestHandler):
    state: UpstreamState

    def log_message(self, *_args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        with self.state.lock:
            self.state.connections += 1
            connection_number = self.state.connections
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        self.wfile.flush()
        frames = [JPEG_A, JPEG_B] if self.state.mode == "freeze" else [JPEG_A]
        for jpeg in frames:
            try:
                self.wfile.write(multipart_part(jpeg))
                self.wfile.flush()
            except OSError:
                return
            time.sleep(0.08)
        if self.state.mode == "freeze":
            # Mantém o upstream aberto sem JPEG novo; o teste verifica que o
            # hub não duplica consumidores nem devolve uma fila antiga.
            time.sleep(0.8)
        elif connection_number >= 2:
            time.sleep(0.1)


class FastHub(CameraStreamHub):
    RECONNECT_DELAYS_S = (0.05, 0.05, 0.05)


class CameraHubTests(unittest.TestCase):
    def start_upstream(self, mode: str):
        state = UpstreamState(mode)
        handler = type("BoundFakeCameraHandler", (FakeCameraHandler,), {"state": state})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return state, server, thread

    def stop_upstream(self, server, thread) -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)

    def test_parser_validates_complete_jpeg_and_discards_incomplete_tail(self) -> None:
        parser = MultipartJpegParser(BOUNDARY)
        body = multipart_part(JPEG_A) + multipart_part(JPEG_B)
        frames = []
        for offset in range(0, len(body), 3):
            frames.extend(parser.feed(body[offset:offset + 3]))
        self.assertEqual(frames, [JPEG_A, JPEG_B])

    def test_hub_keeps_latest_only_and_one_upstream_during_freeze(self) -> None:
        state, upstream, thread = self.start_upstream("freeze")
        hub = FastHub(f"http://127.0.0.1:{upstream.server_address[1]}/stream")
        hub.start()
        try:
            first = hub.wait_for_frame(0, timeout=1.0)
            self.assertIsNotNone(first)
            second = hub.wait_for_frame(first[0], timeout=1.0)
            self.assertIsNotNone(second)
            sequence = second[0]
            latest = hub.latest_frame()
            self.assertIsNotNone(latest)
            self.assertEqual(latest[1], JPEG_B)
            self.assertIsNone(hub.wait_for_frame(sequence, timeout=0.2))
            with state.lock:
                self.assertEqual(state.connections, 1)

            results = []
            waiters = [threading.Thread(target=lambda: results.append(hub.wait_for_frame(sequence, 0.1))) for _ in range(2)]
            for waiter in waiters:
                waiter.start()
            for waiter in waiters:
                waiter.join(timeout=0.5)
            self.assertEqual(results, [None, None])
            with state.lock:
                self.assertEqual(state.connections, 1)
        finally:
            hub.stop()
            self.stop_upstream(upstream, thread)

    def test_hub_reconnects_one_consumer_after_upstream_eof(self) -> None:
        state, upstream, thread = self.start_upstream("reconnect")
        hub = FastHub(f"http://127.0.0.1:{upstream.server_address[1]}/stream")
        hub.start()
        try:
            first = hub.wait_for_frame(0, timeout=1.0)
            self.assertIsNotNone(first)
            second = hub.wait_for_frame(first[0], timeout=2.0)
            self.assertIsNotNone(second)
            with state.lock:
                self.assertGreaterEqual(state.connections, 2)
            self.assertEqual(hub.status()["upstream_connects"], state.connections)
        finally:
            hub.stop()
            self.stop_upstream(upstream, thread)

    def test_stream_thread_does_not_block_stop_command(self) -> None:
        state, upstream, upstream_thread = self.start_upstream("freeze")
        hub = FastHub(f"http://127.0.0.1:{upstream.server_address[1]}/stream")
        simulation = RobotSimulation()
        http_server = RobotHTTPServer(("127.0.0.1", 0), simulation, hub)
        server_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        server_thread.start()
        hub.start()
        stream_connection = http.client.HTTPConnection("127.0.0.1", http_server.server_address[1], timeout=1.0)
        second_stream = None
        try:
            setup = http.client.HTTPConnection("127.0.0.1", http_server.server_address[1], timeout=1.0)
            for payload in (
                {"action": "set_mode", "mode": "MANUAL"},
                {"action": "drive", "throttle": 60, "steering": 0},
            ):
                setup.request("POST", "/api/command", body=json.dumps(payload), headers={"Content-Type": "application/json"})
                setup.getresponse().read()
            setup.close()
            stream_connection.request("GET", "/api/camera/stream")
            response = stream_connection.getresponse()
            self.assertEqual(response.status, 200)
            second_stream = http.client.HTTPConnection("127.0.0.1", http_server.server_address[1], timeout=1.0)
            second_stream.request("GET", "/api/camera/stream")
            second_response = second_stream.getresponse()
            self.assertEqual(second_response.status, 200)
            time.sleep(0.1)
            with state.lock:
                self.assertEqual(state.connections, 1)
            control = http.client.HTTPConnection("127.0.0.1", http_server.server_address[1], timeout=1.0)
            started = time.monotonic()
            control.request(
                "POST",
                "/api/command",
                body=json.dumps({"action": "drive", "throttle": 0, "steering": 0}),
                headers={"Content-Type": "application/json"},
            )
            command_response = control.getresponse()
            elapsed = time.monotonic() - started
            stopped_state = json.loads(command_response.read().decode("utf-8"))
            control.close()
            self.assertEqual(command_response.status, 200)
            self.assertLess(elapsed, 0.5)
            self.assertEqual(stopped_state["motors"]["left"], 0)
            self.assertEqual(stopped_state["motors"]["right"], 0)
        finally:
            stream_connection.close()
            if second_stream is not None:
                second_stream.close()
            hub.stop()
            http_server.shutdown()
            http_server.server_close()
            server_thread.join(timeout=1)
            self.stop_upstream(upstream, upstream_thread)


if __name__ == "__main__":
    unittest.main()
