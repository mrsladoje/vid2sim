#!/usr/bin/env python3
"""
Bridge an OAK camera into the frontend's live-capture flow AND orchestrate
the full Stream 01 → 02 → 03 pipeline end-to-end.

Two modes, sharing one HTTP server:

  * Live preview (default):
      - Opens OAK (USB UVC or TCP/IP MJPEG bridge, auto-detected)
      - Serves MJPEG at /stream.mjpg for the frontend's <img>→canvas path
      - Health at /health

  * Pipeline run (on demand):
      - Client POSTs /pipeline/run with a duration (seconds)
      - Server stops the preview (releases the OAK)
      - Runs  python -m src.perception.capture          (Stream 01)
      - Runs  python scripts/reconstruct_demo_scene.py  (Stream 02)
      - Runs  python -m src.scene.assembler             (Stream 03)
      - Symlinks data/scenes/<id> into public/scenes/<id>_assembled
        so the frontend can GET /scenes/<id>_assembled/scene.json
      - Restarts the preview
      - /pipeline/status/<job_id> returns real-time state + log lines

Usage (Vite plugin auto-starts this; manual invocation for debugging):
    python scripts/oak_uvc.py

Environment knobs:
    VID2SIM_RUNPOD_CONFIG   path to config/runpod.yaml (default: auto)
    VID2SIM_PIPELINE_OFFLINE=1  force offline stub path (no RunPod call)
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import signal
import shlex
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
# Project layout — this script lives at FrontendVid2Sim/scripts/; the repo
# root is two levels up. All pipeline subprocesses run with repo root as cwd.
# --------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = FRONTEND_DIR.parent

CAPTURES_DIR = REPO_ROOT / "data" / "captures"
RECONSTRUCTED_DIR = REPO_ROOT / "data" / "reconstructed"
SCENES_DIR = REPO_ROOT / "data" / "scenes"
PUBLIC_SCENES_DIR = FRONTEND_DIR / "public" / "scenes"

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765
BRIDGE_BOUNDARY = "FRAME"

DEFAULT_CAPTURE_DURATION_S = 10.0
MAX_CAPTURE_DURATION_S = 30.0
MAX_OBJECTS = 5
CAPTURE_DURATION_OVERRIDE_ENV = "VID2SIM_PIPELINE_CAPTURE_DURATION_S"


# --------------------------------------------------------------------------
# Device discovery + CLI
# --------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--width", type=int, default=1280, help="preview width  (default 1280)")
    p.add_argument("--height", type=int, default=720, help="preview height (default 720)")
    p.add_argument("--fps", type=int, default=30, help="preview FPS (default 30)")
    p.add_argument("--force", choices=("auto", "uvc", "bridge"), default="auto",
                   help="force a specific preview path (default: auto-detect)")
    return p.parse_args()


def _pick_device():
    import depthai as dai
    devices = dai.Device.getAllConnectedDevices()
    if not devices:
        return None, None
    dev = devices[0]
    proto = getattr(dev, "protocol", None)
    if proto == getattr(dai.XLinkProtocol, "X_LINK_USB_VSC", None):
        return dev, "usb"
    if proto == getattr(dai.XLinkProtocol, "X_LINK_TCP_IP", None):
        return dev, "tcp"
    return dev, f"unknown:{proto}"


# --------------------------------------------------------------------------
# Preview (MJPEG bridge for TCP-connected OAKs) — can be paused/resumed
# --------------------------------------------------------------------------

class _SharedFrame:
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


class _Preview:
    """Manages the OAK preview pipeline so it can be paused for pipeline runs."""

    def __init__(self, width: int, height: int, fps: int) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.shared = _SharedFrame()
        self._pipeline = None
        self._stop = threading.Event()
        self._producer: threading.Thread | None = None
        self._active = False

    def start(self) -> bool:
        """Open OAK + start producer thread. Returns True on success."""
        try:
            import cv2  # noqa: F401 — used inside producer
            import depthai as dai
        except ImportError as e:
            print(f"[preview] import failed: {e}", file=sys.stderr)
            return False

        try:
            pipeline = dai.Pipeline()
            cam = pipeline.create(dai.node.Camera).build(
                boardSocket=dai.CameraBoardSocket.CAM_A
            )
            out = cam.requestOutput(
                (self.width, self.height), type=dai.ImgFrame.Type.BGR888i, fps=self.fps
            )
            queue = out.createOutputQueue(maxSize=4, blocking=False)
        except Exception as e:  # noqa: BLE001
            print(f"[preview] pipeline build failed: {e}", file=sys.stderr)
            return False

        self._pipeline = pipeline
        self._stop.clear()

        def _producer() -> None:
            import cv2
            while not self._stop.is_set():
                try:
                    frame = queue.get()
                except Exception:  # noqa: BLE001
                    break
                try:
                    bgr = frame.getCvFrame()
                    ok, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 82])
                    if ok:
                        self.shared.put(jpg.tobytes())
                except Exception as e:  # noqa: BLE001
                    print(f"[preview] encode error: {e}", file=sys.stderr)

        try:
            pipeline.start()
        except Exception as e:  # noqa: BLE001
            print(f"[preview] pipeline.start() failed: {e}", file=sys.stderr)
            return False

        self._producer = threading.Thread(target=_producer, name="oak-preview", daemon=True)
        self._producer.start()
        self._active = True
        print(f"[preview] active: {self.width}x{self.height} @ {self.fps}fps", flush=True)
        return True

    def stop(self) -> None:
        if not self._active:
            return
        print("[preview] stopping (releasing OAK for pipeline run)", flush=True)
        self._stop.set()
        try:
            if self._pipeline is not None:
                self._pipeline.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._producer is not None:
            self._producer.join(timeout=3.0)
        self._pipeline = None
        self._producer = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active


# --------------------------------------------------------------------------
# Pipeline job orchestration
# --------------------------------------------------------------------------

@dataclass
class PipelineJob:
    job_id: str
    session_id: str
    state: str = "queued"
    stage: str = ""
    log_lines: deque = field(default_factory=lambda: deque(maxlen=2000))
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    scene_path: str | None = None
    duration_s: float = DEFAULT_CAPTURE_DURATION_S
    capture_proc: subprocess.Popen[str] | None = field(default=None, repr=False)
    capture_stop_requested: bool = False
    capture_stop_sent: bool = False
    control_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def append_log(self, line: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"[{stamp}] {line.rstrip()}")

    def attach_capture_proc(self, proc: subprocess.Popen[str]) -> bool:
        with self.control_lock:
            self.capture_proc = proc
            should_stop = self.capture_stop_requested and not self.capture_stop_sent
        return should_stop

    def clear_capture_proc(self) -> None:
        with self.control_lock:
            self.capture_proc = None

    def request_capture_stop(self) -> bool:
        with self.control_lock:
            if self.capture_stop_requested:
                return False
            self.capture_stop_requested = True
            proc = self.capture_proc
            should_signal = proc is not None and not self.capture_stop_sent
            if should_signal:
                self.capture_stop_sent = True
        if should_signal:
            try:
                proc.send_signal(signal.SIGINT)
                self.append_log("stop requested — waiting for capture to flush")
            except Exception as e:  # noqa: BLE001
                self.append_log(f"⚠ failed to signal capture stop: {e}")
        else:
            self.append_log("stop requested — capture subprocess not ready yet")
        return True

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "session_id": self.session_id,
            "state": self.state,
            "stage": self.stage,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_s": (self.finished_at or time.time()) - self.started_at,
            "scene_url": (
                f"/scenes/{self.session_id}_assembled/scene.json"
                if self.scene_path else None
            ),
            "log_lines": list(self.log_lines),
            "duration_s": self.duration_s,
            "capture_stop_requested": self.capture_stop_requested,
        }


class _Jobs:
    """Thread-safe registry of pipeline jobs with a single-at-a-time guarantee."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, PipelineJob] = {}
        self._active: PipelineJob | None = None

    def try_start(self, job: PipelineJob) -> bool:
        with self._lock:
            if self._active is not None and self._active.state in (
                "queued", "capturing", "reconstructing", "assembling"
            ):
                return False
            self._active = job
            self._jobs[job.job_id] = job
            return True

    def finish(self, job: PipelineJob) -> None:
        with self._lock:
            if self._active is job:
                self._active = None

    def get(self, job_id: str) -> PipelineJob | None:
        with self._lock:
            return self._jobs.get(job_id)


JOBS = _Jobs()


def _stream_subprocess(job: PipelineJob, argv: list[str], stage: str, *, cwd: Path) -> int:
    """Run a subprocess and forward every line of stdout/stderr into job.log_lines."""
    job.stage = stage
    job.append_log(f"→ ({stage}) " + " ".join(shlex.quote(a) for a in argv))
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            env=env,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as e:
        job.append_log(f"✗ ({stage}) executable not found: {e}")
        return 127

    assert proc.stdout is not None
    for line in proc.stdout:
        job.append_log(line.rstrip())
        # Mirror to dev-server terminal with a visible prefix.
        print(f"[pipeline:{stage}] {line.rstrip()}", flush=True)
    rc = proc.wait()
    job.append_log(f"← ({stage}) exit={rc}")
    return rc


def _stream_capture_subprocess(job: PipelineJob, argv: list[str], *, cwd: Path) -> int:
    """Run capture.py, allow /pipeline/stop to interrupt it via SIGINT, and stream logs."""
    job.stage = "capture"
    job.append_log("→ (capture) " + " ".join(shlex.quote(a) for a in argv))
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            env=env,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as e:
        job.append_log(f"✗ (capture) executable not found: {e}")
        return 127

    should_stop_immediately = job.attach_capture_proc(proc)
    if should_stop_immediately:
        try:
            proc.send_signal(signal.SIGINT)
            job.append_log("stop was already requested; sent SIGINT to capture")
        except Exception as e:  # noqa: BLE001
            job.append_log(f"⚠ failed to send initial SIGINT to capture: {e}")

    assert proc.stdout is not None
    for line in proc.stdout:
        job.append_log(line.rstrip())
        print(f"[pipeline:capture] {line.rstrip()}", flush=True)
    rc = proc.wait()
    job.clear_capture_proc()
    job.append_log(f"← (capture) exit={rc}")
    return rc


def _resolve_python() -> str:
    """Use the same interpreter that's running this script for subprocesses."""
    return sys.executable


def _ensure_public_scene_symlink(session_id: str, target_dir: Path) -> Path:
    """Create/update symlink so Vite serves the scene over HTTP."""
    PUBLIC_SCENES_DIR.mkdir(parents=True, exist_ok=True)
    link = PUBLIC_SCENES_DIR / f"{session_id}_assembled"
    if link.is_symlink() or link.exists():
        try:
            link.unlink()
        except OSError:
            pass
    try:
        # Relative target keeps the symlink valid regardless of repo layout.
        rel = os.path.relpath(target_dir, PUBLIC_SCENES_DIR)
        link.symlink_to(rel)
    except OSError:
        # Fallback to absolute if relative fails (e.g. cross-volume).
        link.symlink_to(target_dir)
    return link


def _run_pipeline(job: PipelineJob, preview: _Preview) -> None:
    """Runs on a worker thread: orchestrates capture → reconstruct → assemble."""
    session_id = job.session_id
    capture_dir = CAPTURES_DIR / session_id
    reconstructed_dir = RECONSTRUCTED_DIR / session_id
    scene_dir = SCENES_DIR / session_id

    # Pause preview so the capture subprocess can own the OAK.
    preview_was_active = preview.active
    preview.stop()
    preview_resumed = False

    python = _resolve_python()
    runpod_cfg = os.environ.get("VID2SIM_RUNPOD_CONFIG", str(REPO_ROOT / "config" / "runpod.yaml"))
    offline = os.environ.get("VID2SIM_PIPELINE_OFFLINE") == "1"

    try:
        # ---- Stage 01: capture ---------------------------------------
        job.state = "capturing"
        capture_dir.mkdir(parents=True, exist_ok=True)
        duration = max(3.0, min(job.duration_s, MAX_CAPTURE_DURATION_S))
        override_raw = os.environ.get(CAPTURE_DURATION_OVERRIDE_ENV)
        if override_raw:
            try:
                duration = max(3.0, min(float(override_raw), MAX_CAPTURE_DURATION_S))
                job.append_log(
                    f"{CAPTURE_DURATION_OVERRIDE_ENV}={duration:.1f} — overriding requested duration"
                )
            except ValueError:
                job.append_log(
                    f"ignoring invalid {CAPTURE_DURATION_OVERRIDE_ENV}={override_raw!r}"
                )
        cap_rc = _stream_capture_subprocess(
            job,
            [
                python, "-m", "src.perception.capture",
                "--outdir", str(capture_dir),
                "--duration", str(duration),
                # Keep every COCO class so the demo works on arbitrary scenes
                # rather than only the default household whitelist.
                "--prompts", "all",
            ],
            cwd=REPO_ROOT,
        )
        if cap_rc == 3:
            job.state = "failed"
            job.error = (
                "capture saw zero tracked objects — point the OAK at the scene and try again"
            )
            return
        if cap_rc != 0:
            job.state = "failed"
            job.error = f"capture exited {cap_rc}"
            return

        if preview_was_active:
            try:
                preview.start()
                preview_resumed = True
            except Exception as e:  # noqa: BLE001
                job.append_log(f"⚠ preview restart failed after capture: {e}")

        # ---- Stage 02: reconstruction --------------------------------
        job.state = "reconstructing"
        rec_argv = [
            python, "scripts/reconstruct_demo_scene.py",
            "--capture", str(capture_dir),
            "--session", session_id,
            "--out", str(RECONSTRUCTED_DIR),
            "--max-objects", str(MAX_OBJECTS),
        ]
        if offline or not Path(runpod_cfg).exists():
            rec_argv.append("--offline")
            job.append_log(
                "VID2SIM_PIPELINE_OFFLINE=1 (or no runpod config found) — "
                "using local stub mesh generator."
            )
        else:
            rec_argv += ["--config", runpod_cfg]
        rec_rc = _stream_subprocess(job, rec_argv, stage="reconstruct", cwd=REPO_ROOT)
        if rec_rc != 0:
            job.state = "failed"
            job.error = f"reconstruction exited {rec_rc}"
            return

        # ---- Stage 03: scene assembly --------------------------------
        job.state = "assembling"
        if not reconstructed_dir.exists():
            # scripts/reconstruct_demo_scene.py names its session dir via
            # ReconstructorConfig.out_root / session. Verify + fallback.
            reconstructed_dir = RECONSTRUCTED_DIR / session_id
        asm_rc = _stream_subprocess(
            job,
            [
                python, "-m", "src.scene.assembler",
                "--reconstructed", str(reconstructed_dir),
                "--out", str(scene_dir),
            ],
            stage="assemble",
            cwd=REPO_ROOT,
        )
        if asm_rc != 0:
            job.state = "failed"
            job.error = f"scene assembly exited {asm_rc}"
            return

        scene_json = scene_dir / "scene.json"
        if not scene_json.exists():
            job.state = "failed"
            job.error = f"assembler succeeded but {scene_json} missing"
            return

        link = _ensure_public_scene_symlink(session_id, scene_dir)
        job.append_log(f"symlinked {link} → {scene_dir}")
        job.scene_path = str(scene_dir)
        job.state = "done"
        job.append_log("pipeline complete.")
    finally:
        job.finished_at = time.time()
        JOBS.finish(job)
        # Resume preview so the next recording has a live RGB feed again.
        if preview_was_active and not preview_resumed:
            try:
                preview.start()
            except Exception as e:  # noqa: BLE001
                job.append_log(f"⚠ preview restart failed: {e}")


# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------

def _make_handler(preview: _Preview):
    stream_interval = max(1.0 / preview.fps, 1.0 / 60.0)

    class Handler(http.server.BaseHTTPRequestHandler):
        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")

        def log_message(self, fmt, *args) -> None:  # noqa: N802
            pass

        def _send_json(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _read_json_body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                return {}

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            # /health — liveness probe
            if self.path in ("/health", "/healthz"):
                self._send_json(200, {
                    "ok": True,
                    "source": "oak-ip-bridge",
                    "preview_active": preview.active,
                })
                return

            # /pipeline/status/<job_id>
            if self.path.startswith("/pipeline/status/"):
                job_id = self.path.removeprefix("/pipeline/status/").split("?", 1)[0]
                job = JOBS.get(job_id)
                if job is None:
                    self._send_json(404, {"error": f"unknown job_id {job_id}"})
                    return
                self._send_json(200, job.as_dict())
                return

            # /stream.mjpg — live preview multipart MJPEG
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
                        jpg, seq = preview.shared.get()
                        if jpg is None or seq == last_seq:
                            time.sleep(stream_interval)
                            continue
                        last_seq = seq
                        self.wfile.write(f"--{BRIDGE_BOUNDARY}\r\n".encode())
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                        time.sleep(stream_interval)
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception:  # noqa: BLE001
                    return
                return

            self.send_response(404)
            self._cors()
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            if self.path in ("/pipeline/run", "/pipeline/start"):
                body = self._read_json_body()
                duration_key = "max_duration_s" if self.path == "/pipeline/start" else "duration_s"
                duration_s = float(body.get(duration_key, DEFAULT_CAPTURE_DURATION_S))
                duration_s = max(3.0, min(duration_s, MAX_CAPTURE_DURATION_S))

                now = datetime.now()
                session_id = body.get("session_id") or f"live_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
                job = PipelineJob(
                    job_id=uuid.uuid4().hex,
                    session_id=session_id,
                    duration_s=duration_s,
                )
                job.append_log(
                    f"queued session_id={session_id} duration_s={duration_s:.1f}"
                )
                if not JOBS.try_start(job):
                    self._send_json(409, {
                        "error": "another pipeline run is already in flight",
                    })
                    return

                threading.Thread(
                    target=_run_pipeline,
                    args=(job, preview),
                    name=f"pipeline-{job.job_id[:6]}",
                    daemon=True,
                ).start()
                self._send_json(202, job.as_dict())
                return

            if self.path.startswith("/pipeline/stop/"):
                job_id = self.path.removeprefix("/pipeline/stop/").split("?", 1)[0]
                job = JOBS.get(job_id)
                if job is None:
                    self._send_json(404, {"error": f"unknown job_id {job_id}"})
                    return
                if job.state != "capturing":
                    self._send_json(409, {
                        "error": f"job {job_id} is not capturing",
                        "job": job.as_dict(),
                    })
                    return
                accepted = job.request_capture_stop()
                self._send_json(202, {
                    "accepted": accepted,
                    "job": job.as_dict(),
                })
                return

            self.send_response(404)
            self._cors()
            self.end_headers()

    return Handler


class _ThreadedTCPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> int:
    args = _parse_args()

    try:
        import depthai as dai  # noqa: F401
    except ImportError:
        print(
            "error: depthai is not installed. `pip install --pre depthai opencv-python`",
            file=sys.stderr,
        )
        return 2

    try:
        import cv2  # noqa: F401
    except ImportError:
        print(
            "error: opencv-python is required. `pip install opencv-python`",
            file=sys.stderr,
        )
        return 2

    import depthai as dai

    dev, protocol = _pick_device()
    if dev is None:
        print("error: no OAK device found on USB or network.", file=sys.stderr)
        print("       plug in via USB-C or connect over ethernet and retry.", file=sys.stderr)
        return 9

    version = getattr(dai, "__version__", "unknown")
    print(
        f"oak_uvc: depthai v{version}, device={getattr(dev, 'name', 'oak')} protocol={protocol}",
        flush=True,
    )
    if protocol == "usb":
        print(
            "oak_uvc: note — even USB-attached OAKs are served via the MJPEG bridge in this\n"
            "         server so the pipeline orchestration path is consistent. Native UVC is\n"
            "         only relevant to legacy preview-only scripts.",
            flush=True,
        )

    preview = _Preview(args.width, args.height, args.fps)
    if not preview.start():
        print(
            "error: could not open the OAK preview pipeline. check that no other process\n"
            "       holds the OAK (Luxonis Hub, another depthai script, a previous run).",
            file=sys.stderr,
        )
        return 10

    handler = _make_handler(preview)
    try:
        server = _ThreadedTCPServer((BRIDGE_HOST, BRIDGE_PORT), handler)
    except OSError as e:
        preview.stop()
        print(f"error: cannot bind {BRIDGE_HOST}:{BRIDGE_PORT}: {e}", file=sys.stderr)
        return 8

    print(
        f"oak_uvc: HTTP server at http://{BRIDGE_HOST}:{BRIDGE_PORT}\n"
        f"         GET  /health\n"
        f"         GET  /stream.mjpg\n"
        f"         POST /pipeline/run      {{\"duration_s\": 10}}\n"
        f"         GET  /pipeline/status/<job_id>\n"
        f"         ctrl+c to stop",
        flush=True,
    )

    srv_thread = threading.Thread(
        target=server.serve_forever, name="oak-http", daemon=True
    )
    srv_thread.start()
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\noak_uvc: stopping.", flush=True)
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass
        preview.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
