#!/usr/bin/env python3
import json
import re
import select
import socket
import threading
import time
import urllib.request

HOST = "127.0.0.1"
PORT = 8765
PATH = b"/api/camera/stream"
DURATION = 10.0
OUT = "/tmp/hub_route_diag.jsonl"
FIRST = "/tmp/hub_route_first_blocks.bin"
SERIAL_OUT = "/tmp/hub_route_serial.bin"


def serial_reader(stop):
    try:
        fd = open("/dev/ttyUSB0", "rb", buffering=0)
    except Exception as exc:
        with open(SERIAL_OUT, "ab") as out:
            out.write((f"[serial_open_error] {exc!r}\n").encode())
        return
    with fd, open(SERIAL_OUT, "ab", buffering=0) as out:
        while not stop.is_set():
            ready, _, _ = select.select([fd], [], [], 0.25)
            if ready:
                data = fd.read(4096)
                if data:
                    out.write(data)


def status():
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/api/camera/status", timeout=1.0) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        return {"status_error": repr(exc)}


def parse_parts(buf, frames):
    # The route is direct multipart (not HTTP chunked).
    while True:
        marker = buf.find(b"--frame")
        if marker < 0:
            return buf[-16:]
        hdr_end = buf.find(b"\r\n\r\n", marker)
        if hdr_end < 0:
            return buf[marker:]
        headers = buf[marker:hdr_end].decode("latin1", "replace")
        m = re.search(r"Content-Length:\s*(\d+)", headers, re.I)
        if not m:
            buf = buf[hdr_end + 4:]
            continue
        n = int(m.group(1))
        start = hdr_end + 4
        if len(buf) < start + n + 2:
            return buf[marker:]
        jpeg = buf[start:start + n]
        if jpeg.startswith(b"\xff\xd8") and jpeg.endswith(b"\xff\xd9"):
            frames.append({"bytes": n, "at": time.monotonic()})
        buf = buf[start + n + 2:]


def main():
    open(OUT, "w").close()
    open(FIRST, "wb").close()
    open(SERIAL_OUT, "wb").close()
    stop = threading.Event()
    serial = threading.Thread(target=serial_reader, args=(stop,), daemon=True)
    serial.start()
    time.sleep(0.25)
    started = time.monotonic()
    result = {"started_monotonic": started, "duration_s": DURATION, "reason": None,
              "bytes_read": 0, "recv_blocks": 0, "frames": [], "per_second": []}
    frames = result["frames"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect((HOST, PORT))
        sock.sendall(b"GET " + PATH + b" HTTP/1.0\r\nHost: " + HOST.encode() + b"\r\n\r\n")
        sock.settimeout(0.5)
        buf = b""
        first = []
        next_tick = started
        last_data = started
        last_frame = started
        max_no_data = 0.0
        max_frame_gap = 0.0
        while time.monotonic() - started < DURATION:
            now = time.monotonic()
            try:
                data = sock.recv(65536)
            except socket.timeout:
                data = None
            if data is None:
                pass
            elif not data:
                result["reason"] = "eof"
                break
            else:
                result["bytes_read"] += len(data)
                result["recv_blocks"] += 1
                if len(first) < 2:
                    first.append(data)
                    with open(FIRST, "ab") as out:
                        out.write(data)
                gap = now - last_data
                max_no_data = max(max_no_data, gap)
                last_data = now
                before = len(frames)
                buf += data
                buf = parse_parts(buf, frames)
                if len(frames) > before:
                    for f in frames[before:]:
                        gap = f["at"] - last_frame
                        max_frame_gap = max(max_frame_gap, gap)
                        last_frame = f["at"]
            now = time.monotonic()
            if now >= next_tick:
                st = status()
                result["per_second"].append({"elapsed_s": round(now - started, 3),
                    "sequence": st.get("sequence"), "last_frame_at": st.get("last_frame_at"),
                    "route_frames_received": len(frames), "bytes_read": result["bytes_read"],
                    "hub_last_error": st.get("last_error"), "upstream_connects": st.get("upstream_connects"),
                    "frames_since_tick": sum(1 for f in frames if f["at"] >= next_tick - started + started)})
                with open(OUT, "a") as out:
                    out.write(json.dumps(result["per_second"][-1]) + "\n")
                next_tick += 1.0
        else:
            result["reason"] = "duration_complete"
    except Exception as exc:
        result["reason"] = "exception:" + repr(exc)
    finally:
        try:
            sock.close()
        except Exception:
            pass
        stop.set()
        serial.join(timeout=1.0)
    result["ended_monotonic"] = time.monotonic()
    result["elapsed_s"] = result["ended_monotonic"] - started
    result["max_no_data_s"] = max_no_data if 'max_no_data' in locals() else None
    result["max_frame_gap_s"] = max_frame_gap if 'max_frame_gap' in locals() else None
    result["frames_complete"] = len(frames)
    result["first_blocks"] = [{"bytes": len(x)} for x in first]
    with open(OUT, "a") as out:
        out.write(json.dumps({"final": result}) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
