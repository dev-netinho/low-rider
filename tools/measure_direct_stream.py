#!/usr/bin/env python3
"""One-client MJPEG measurement with crash-safe partial results.

This utility does not reset or reconfigure the ESP32-CAM.  It only opens the
HTTP stream and reads the serial log.  Results are appended as JSON Lines and
fsync'ed after every event so a timeout/exception still leaves usable data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import signal
import socket
import sys
import termios
import threading
import time
from pathlib import Path


class ResultLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fp = path.open("a", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()

    def write(self, event: str, **fields: object) -> None:
        row = {"event": event, "time_unix": time.time(), **fields}
        line = json.dumps(row, ensure_ascii=False, sort_keys=True)
        with self.lock:
            self.fp.write(line + "\n")
            self.fp.flush()
            os.fsync(self.fp.fileno())

    def close(self) -> None:
        with self.lock:
            self.fp.flush()
            os.fsync(self.fp.fileno())
            self.fp.close()


class ChunkDecoder:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.need: int | None = None
        self.done = False

    def feed(self, data: bytes) -> bytes:
        self.buffer.extend(data)
        output = bytearray()
        while not self.done:
            if self.need is None:
                end = self.buffer.find(b"\r\n")
                if end < 0:
                    break
                line = bytes(self.buffer[:end])
                del self.buffer[: end + 2]
                try:
                    self.need = int(line.split(b";", 1)[0], 16)
                except ValueError as exc:
                    raise ValueError(f"invalid HTTP chunk size: {line!r}") from exc
                if self.need == 0:
                    self.done = True
                    if self.buffer.startswith(b"\r\n"):
                        del self.buffer[:2]
                    break
            if self.need is not None and len(self.buffer) >= self.need + 2:
                output.extend(self.buffer[: self.need])
                del self.buffer[: self.need + 2]
                self.need = None
            else:
                break
        return bytes(output)


class MultipartParser:
    def __init__(self, boundary: bytes) -> None:
        self.marker = b"--" + boundary
        self.buffer = bytearray()
        self.invalid_parts = 0

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        frames: list[bytes] = []
        while True:
            marker_at = self.buffer.find(self.marker)
            if marker_at < 0:
                keep = max(0, len(self.marker) - 1)
                if len(self.buffer) > keep:
                    del self.buffer[:-keep]
                break
            if marker_at:
                del self.buffer[:marker_at]
            if len(self.buffer) < len(self.marker) + 2:
                break
            if self.buffer[len(self.marker) : len(self.marker) + 2] != b"\r\n":
                del self.buffer[: len(self.marker)]
                self.invalid_parts += 1
                continue
            header_end = self.buffer.find(b"\r\n\r\n", len(self.marker) + 2)
            if header_end < 0:
                break
            headers: dict[bytes, bytes] = {}
            for line in self.buffer[len(self.marker) + 2 : header_end].split(b"\r\n"):
                if b":" in line:
                    key, value = line.split(b":", 1)
                    headers[key.lower().strip()] = value.strip()
            try:
                length = int(headers[b"content-length"])
            except (KeyError, ValueError):
                del self.buffer[: header_end + 4]
                self.invalid_parts += 1
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
            else:
                self.invalid_parts += 1
        return frames


def configure_serial(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY)
    attrs[1] &= ~termios.OPOST
    attrs[2] &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
    attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] &= ~(termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG)
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def serial_capture(path: str, raw_path: Path, log: ResultLog, stop: threading.Event) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        configure_serial(fd)
        with raw_path.open("ab") as raw:
            while not stop.is_set():
                readable, _, _ = select.select([fd], [], [], 0.2)
                if readable:
                    try:
                        data = os.read(fd, 4096)
                    except BlockingIOError:
                        data = b""
                    if data:
                        raw.write(data)
                        raw.flush()
                        os.fsync(raw.fileno())
        os.close(fd)
    except Exception as exc:  # serial failure must not erase HTTP results
        log.write("serial_error", error=repr(exc))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.10")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--path", default="/stream")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--serial", default="/dev/ttyUSB0")
    parser.add_argument("--results", type=Path, default=Path("/tmp/cam_direct_measure.jsonl"))
    parser.add_argument("--serial-raw", type=Path, default=Path("/tmp/cam_direct_serial.raw"))
    args = parser.parse_args()

    log = ResultLog(args.results)
    stop = threading.Event()
    reason = "unknown"
    sock: socket.socket | None = None
    frames = 0
    wire_bytes = 0
    body_bytes = 0
    recv_timeouts = 0
    last_recv_at: float | None = None
    last_frame_at: float | None = None
    max_idle = 0.0
    max_frame_gap = 0.0
    window_counts: dict[int, int] = {}
    sizes: list[int] = []
    hashes: set[str] = set()
    started = time.monotonic()

    def interrupted(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    log.write("start", host=args.host, port=args.port, path=args.path, duration_s=args.duration)
    serial_thread = threading.Thread(
        target=serial_capture,
        args=(args.serial, args.serial_raw, log, stop),
        daemon=True,
    )
    serial_thread.start()
    try:
        connect_started = time.monotonic()
        sock = socket.create_connection((args.host, args.port), timeout=args.connect_timeout)
        log.write("tcp_connected", connect_s=time.monotonic() - connect_started)
        sock.settimeout(1.0)
        request = (
            f"GET {args.path} HTTP/1.1\r\nHost: {args.host}\r\n"
            "Cache-Control: no-cache\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
        sock.sendall(request)
        header_data = bytearray()
        header_deadline = time.monotonic() + args.connect_timeout
        while b"\r\n\r\n" not in header_data and time.monotonic() < header_deadline:
            try:
                data = sock.recv(8192)
            except socket.timeout:
                continue
            if not data:
                reason = "eof_before_headers"
                break
            wire_bytes += len(data)
            header_data.extend(data)
        if b"\r\n\r\n" not in header_data:
            if reason == "unknown":
                reason = "header_timeout"
            log.write("finish", reason=reason, frames=frames, wire_bytes=wire_bytes, body_bytes=body_bytes)
            return 1
        headers, initial_body = bytes(header_data).split(b"\r\n\r\n", 1)
        log.write("headers", text=headers.decode("latin1", "replace"))
        boundary = b"frame"
        for line in headers.split(b"\r\n"):
            if line.lower().startswith(b"content-type:") and b"boundary=" in line:
                boundary = line.split(b"boundary=", 1)[1].strip().strip(b'"')
        decoder = ChunkDecoder()
        multipart = MultipartParser(boundary)
        active_started = time.monotonic()

        def handle_wire(data: bytes) -> None:
            nonlocal body_bytes, last_recv_at, max_idle, frames, last_frame_at, max_frame_gap
            now = time.monotonic()
            wire_len = len(data)
            body_bytes += wire_len
            if last_recv_at is not None:
                max_idle = max(max_idle, now - last_recv_at)
            last_recv_at = now
            decoded = decoder.feed(data)
            for jpeg in multipart.feed(decoded):
                frame_now = time.monotonic()
                frame_time = frame_now - active_started
                if last_frame_at is not None:
                    max_frame_gap = max(max_frame_gap, frame_time - last_frame_at)
                last_frame_at = frame_time
                frames += 1
                sizes.append(len(jpeg))
                digest = hashlib.sha256(jpeg).hexdigest()
                hashes.add(digest)
                window = int(frame_time // 5) * 5
                window_counts[window] = window_counts.get(window, 0) + 1
                log.write(
                    "jpeg",
                    index=frames,
                    elapsed_s=frame_time,
                    bytes=len(jpeg),
                    sha256=digest,
                    window_s=window,
                )

        handle_wire(initial_body)
        while not stop.is_set() and time.monotonic() - active_started < args.duration:
            try:
                data = sock.recv(16384)
            except socket.timeout:
                recv_timeouts += 1
                log.write("read_timeout", count=recv_timeouts, elapsed_s=time.monotonic() - active_started)
                continue
            if not data:
                reason = "eof"
                break
            wire_bytes += len(data)
            handle_wire(data)
            if frames and frames % 25 == 0:
                log.write("progress", frames=frames, wire_bytes=wire_bytes, max_idle_s=max_idle, max_frame_gap_s=max_frame_gap)
        if reason == "unknown":
            reason = "interrupted" if stop.is_set() else "duration_complete"
    except KeyboardInterrupt:
        reason = "interrupted"
    except Exception as exc:
        reason = "exception"
        log.write("exception", error=repr(exc))
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        stop.set()
        serial_thread.join(timeout=2.0)
        elapsed = time.monotonic() - started
        log.write(
            "finish",
            reason=reason,
            elapsed_s=elapsed,
            frames=frames,
            wire_bytes=wire_bytes,
            body_bytes=body_bytes,
            max_idle_s=max_idle,
            max_frame_gap_s=max_frame_gap,
            invalid_parts=getattr(locals().get("multipart", None), "invalid_parts", None),
            recv_timeouts=recv_timeouts,
            unique_sha256=len(hashes),
            window_counts=window_counts,
            jpeg_min=min(sizes) if sizes else None,
            jpeg_avg=(sum(sizes) / len(sizes)) if sizes else None,
            jpeg_max=max(sizes) if sizes else None,
        )
        log.close()
    print(json.dumps({"reason": reason, "elapsed_s": elapsed, "frames": frames, "wire_bytes": wire_bytes, "body_bytes": body_bytes, "max_idle_s": max_idle, "max_frame_gap_s": max_frame_gap, "window_counts": window_counts, "results": str(args.results), "serial_raw": str(args.serial_raw)}, ensure_ascii=False))
    return 0 if reason in {"duration_complete", "eof", "interrupted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
