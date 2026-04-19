#!/usr/bin/env python3
"""
Bridge an OAK camera into the frontend's live-capture flow.

The script auto-detects how the OAK is connected and chooses the best path:

  * USB-attached OAK → UVC webcam mode via the depthai pipeline. The device
    appears in the browser's `getUserMedia()` list and the frontend's
    OAK-preference logic auto-selects it.
  * Network-attached OAK (TCP/IP, e.g. OAK-4 over ethernet) → MJPEG bridge
    on `http://127.0.0.1:8765/stream.mjpg`. UVC requires USB and cannot
    work over IP, so we stream the color camera as MJPEG and let the
    frontend consume it via an `<img>` tag + `canvas.captureStream()`.

Usage
-----
    pip install depthai opencv-python      # one-time
    python scripts/oak_uvc.py              # keep running while recording

The frontend's Vite dev server auto-spawns this script via the
`oakUvcBridge` plugin; you normally don't run it by hand.

DepthAI versions supported: v3 (preferred, required for OAK-4/RVC4) and
v2 (older OAK-D / OAK-D Lite / OAK-1 in UVC-capable firmware).
"""
from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
import threading
import time

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765
BRIDGE_BOUNDARY = "FRAME"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--width", type=int, default=1280, help="stream width (default 1280)")
    p.add_argument("--height", type=int, default=720, help="stream height (default 720)")
    p.add_argument("--fps", type=int, default=30, help="stream FPS (default 30)")
    p.add_argument("--force", choices=("auto", "uvc", "bridge"), default="auto",
                   help="force a specific path (default: auto-detect by protocol)")
    return p.parse_args()


# --------------------------------------------------------------------------
# Device discovery
# --------------------------------------------------------------------------

def _pick_device():
    """Return the first connected OAK device and its protocol label."""
    import depthai as dai
    devices = dai.Device.getAllConnectedDevices()
    if not devices:
        return None, None
    dev = devices[0]
    proto = getattr(dev, "protocol", None)
    is_usb = proto == getattr(dai.XLinkProtocol, "X_LINK_USB_VSC", None)
    is_tcp = proto == getattr(dai.XLinkProtocol, "X_LINK_TCP_IP", None)
    if is_usb:
        return dev, "usb"
    if is_tcp:
        return dev, "tcp"
    return dev, f"unknown:{proto}"


# --------------------------------------------------------------------------
# UVC path (USB)
# --------------------------------------------------------------------------

def _run_uvc_v3(width: int, height: int) -> int:
    import depthai as dai

    pipeline = dai.Pipeline()
    cam = pipeline.create(dai.node.Camera).build(boardSocket=dai.CameraBoardSocket.CAM_A)
    out = cam.requestOutput((width, height), type=dai.ImgFrame.Type.NV12, fps=30)

    uvc = pipeline.create(dai.node.UVC)
    out.link(uvc.input)

    config = dai.Device.Config()
    config.board.uvc = dai.BoardConfig.UVC(width, height)
    config.board.uvc.frameType = dai.ImgFrame.Type.NV12
    pipeline.setBoardConfig(config.board)

    print(f"oak_uvc (v3 UVC): streaming {width}x{height} NV12 over USB.", flush=True)
    pipeline.start()
    try:
        while pipeline.isRunning():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\noak_uvc: stopping.", flush=True)
    finally:
        try:
            pipeline.stop()
        except Exception:  # noqa: BLE001
            pass
    return 0


def _run_uvc_v2(width: int, height: int) -> int:
    import depthai as dai

    pipeline = dai.Pipeline()
    cam = pipeline.createColorCamera()
    cam.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    cam.setInterleaved(False)
    cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    uvc = pipeline.createUVC()
    cam.video.link(uvc.input)

    cfg = dai.Device.Config()
    cfg.board.uvc = dai.BoardConfig.UVC(width, height)
    cfg.board.uvc.frameType = dai.ImgFrame.Type.NV12
    pipeline.setBoardConfig(cfg.board)

    print(f"oak_uvc (v2 UVC): streaming {width}x{height} NV12 over USB.", flush=True)
    with dai.Device(pipeline):
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\noak_uvc: stopping.", flush=True)
    return 0


# --------------------------------------------------------------------------
# MJPEG-over-HTTP bridge (for TCP/IP-connected OAK, e.g. OAK-4 on ethernet)
# --------------------------------------------------------------------------

class _SharedFrame:
    """Thread-safe latest-frame holder."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jpg: bytes | None = None
        self._seq = 0

    def put(self, jpg: bytes) -> None:
        with self._lock:
            self._jpg = jpg
            self._seq += 1

    def get(self) -> tuple[bytes | None, int]:
        with self._lock:
            return self._jpg, self._seq


def _make_handler(shared: _SharedFrame, target_fps: int):
    interval = max(1.0 / target_fps, 1.0 / 60.0)

    class Handler(http.server.BaseHTTPRequestHandler):
        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")

        def log_message(self, fmt, *args) -> None:  # noqa: N802 (stdlib API)
            # Suppress default access logs — keep the Vite terminal clean.
            pass

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/health", "/healthz"):
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true,"source":"oak-ip-bridge"}')
                return

            if self.path in ("/stream.mjpg", "/stream", "/"):
                self.send_response(200)
                self._cors()
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header(
                    "Content-Type",
                    f"multipart/x-mixed-replace; boundary={BRIDGE_BOUNDARY}",
                )
                self.end_headers()
                last_seq = -1
                try:
                    while True:
                        jpg, seq = shared.get()
                        if jpg is None or seq == last_seq:
                            time.sleep(interval)
                            continue
                        last_seq = seq
                        self.wfile.write(f"--{BRIDGE_BOUNDARY}\r\n".encode())
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                        time.sleep(interval)
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception:  # noqa: BLE001
                    return
                return

            self.send_response(404)
            self._cors()
            self.end_headers()

    return Handler


class _ThreadedTCPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _run_bridge(width: int, height: int, fps: int) -> int:
    import depthai as dai

    try:
        import cv2
    except ImportError:
        print(
            "error: opencv-python is required for the OAK→MJPEG bridge.\n"
            "       pip install opencv-python",
            file=sys.stderr,
        )
        return 6

    if not (hasattr(dai, "node") and hasattr(dai.node, "Camera")):
        print(
            "error: bridge requires depthai v3. install via `pip install --pre depthai`.",
            file=sys.stderr,
        )
        return 7

    pipeline = dai.Pipeline()
    cam = pipeline.create(dai.node.Camera).build(boardSocket=dai.CameraBoardSocket.CAM_A)
    out = cam.requestOutput((width, height), type=dai.ImgFrame.Type.BGR888i, fps=fps)
    queue = out.createOutputQueue(maxSize=4, blocking=False)

    shared = _SharedFrame()
    stop_event = threading.Event()

    def producer() -> None:
        # Reads ImgFrames off the OAK, JPEG-encodes, puts into shared holder.
        while not stop_event.is_set():
            try:
                frame = queue.get()
            except Exception:  # noqa: BLE001 — queue closed during shutdown
                break
            bgr = frame.getCvFrame()
            ok, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if ok:
                shared.put(jpg.tobytes())

    prod_thread = threading.Thread(target=producer, name="oak-producer", daemon=True)

    pipeline.start()
    prod_thread.start()

    handler = _make_handler(shared, fps)
    try:
        server = _ThreadedTCPServer((BRIDGE_HOST, BRIDGE_PORT), handler)
    except OSError as e:
        print(f"error: cannot bind {BRIDGE_HOST}:{BRIDGE_PORT}: {e}", file=sys.stderr)
        stop_event.set()
        pipeline.stop()
        return 8

    print(
        f"oak_uvc (IP bridge): MJPEG at http://{BRIDGE_HOST}:{BRIDGE_PORT}/stream.mjpg\n"
        f"                    health at http://{BRIDGE_HOST}:{BRIDGE_PORT}/health\n"
        f"                    {width}x{height} @ {fps}fps  ·  ctrl+c to stop",
        flush=True,
    )

    server_thread = threading.Thread(target=server.serve_forever, name="oak-http", daemon=True)
    server_thread.start()

    try:
        while pipeline.isRunning() and prod_thread.is_alive():
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\noak_uvc: stopping.", flush=True)
    finally:
        stop_event.set()
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass
        try:
            pipeline.stop()
        except Exception:  # noqa: BLE001
            pass
    return 0


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def _has_v3_api() -> bool:
    try:
        import depthai as dai
    except ImportError:
        return False
    return hasattr(dai, "node") and hasattr(dai.node, "Camera")


def _has_v2_api() -> bool:
    try:
        import depthai as dai
    except ImportError:
        return False
    return hasattr(dai.Pipeline(), "createColorCamera")


def main() -> int:
    args = _parse_args()

    try:
        import depthai as dai
    except ImportError:
        print(
            "error: depthai is not installed in this venv.\n"
            "       for OAK-4 / RVC4:  pip install --pre depthai\n"
            "       for older OAKs:    pip install depthai",
            file=sys.stderr,
        )
        return 2

    version = getattr(dai, "__version__", "unknown")

    dev, protocol = _pick_device()
    if dev is None:
        print("error: no OAK device found on USB or network.", file=sys.stderr)
        return 9

    dev_label = getattr(dev, "name", "oak") or "oak"
    print(
        f"oak_uvc: depthai v{version}, device={dev_label} protocol={protocol}",
        flush=True,
    )

    path = args.force
    if path == "auto":
        if protocol == "usb":
            path = "uvc"
        elif protocol == "tcp":
            path = "bridge"
            print(
                "oak_uvc: OAK is network-attached. UVC is USB-only, so we fall back to an\n"
                "         MJPEG bridge the frontend can consume via fetch+<img>+canvas.",
                flush=True,
            )
        else:
            path = "bridge"  # safe default for unknown protocols

    if path == "uvc":
        if _has_v3_api():
            try:
                return _run_uvc_v3(args.width, args.height)
            except RuntimeError as e:
                # Some devices advertise the UVC node but don't support it in
                # runtime — fall back to the bridge so the demo still works.
                print(
                    f"oak_uvc: UVC on-device runtime missing ({e}); falling back to IP bridge.",
                    file=sys.stderr,
                )
                return _run_bridge(args.width, args.height, args.fps)
        if _has_v2_api():
            return _run_uvc_v2(args.width, args.height)
        print("error: depthai has neither v3 nor v2 UVC primitives.", file=sys.stderr)
        return 5

    if path == "bridge":
        return _run_bridge(args.width, args.height, args.fps)

    print(f"error: unknown --force value: {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
