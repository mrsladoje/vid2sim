"""Generate a synthetic PerceptionFrame bundle without the camera.

Used by CI and by downstream streams (Reconstruction, Scene Building) so
they can develop against the real on-disk layout even when the OAK-4 is
unavailable. Every output file has the spec-required shape/dtype, matching
what `src.perception.capture` writes against real hardware.

Defaults: 150 frames (10 s @ 15 fps), 1920x1080 RGB, ~27 IMU samples/frame.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

# Ensure `src` is importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.perception.bundle import (  # noqa: E402
    BundleWriter,
    FrameRecord,
    ImuSample,
    Intrinsics,
    Manifest,
    ObjectRecord,
    Pose,
    RGB_HEIGHT,
    RGB_WIDTH,
)

logger = logging.getLogger(__name__)

DEFAULT_PROMPTS = ["chair", "table"]
IMU_HZ = 400


def _gradient_rgb(h: int, w: int, t: float) -> np.ndarray:
    """Synthetic BGR frame: a shifting colour gradient + a moving rectangle.
    Cheap but non-trivial so JPEG encoding produces a real-sized file."""
    ys = np.linspace(0, 1, h, dtype=np.float32).reshape(-1, 1)
    xs = np.linspace(0, 1, w, dtype=np.float32).reshape(1, -1)
    r = (ys + 0.1 * np.sin(2 * np.pi * (xs + t))) * 255
    g = (xs + 0.1 * np.cos(2 * np.pi * (ys + t))) * 255
    b = (1 - (xs + ys) * 0.5) * 255
    frame = np.stack([b, g, r], axis=-1).clip(0, 255).astype(np.uint8)
    # Moving rectangle (the stand-in "chair") near frame centre.
    cx = int(w * (0.4 + 0.15 * np.sin(2 * np.pi * t)))
    cy = int(h * 0.5)
    rw, rh = 220, 300
    x1, x2 = max(cx - rw // 2, 0), min(cx + rw // 2, w)
    y1, y2 = max(cy - rh // 2, 0), min(cy + rh // 2, h)
    frame[y1:y2, x1:x2] = [30, 30, 180]
    return frame, (x1, y1, x2, y2)


def _depth_for(h: int, w: int, rect: tuple[int, int, int, int]) -> np.ndarray:
    """Linearly increasing depth with a closer region over the rectangle."""
    ys = np.linspace(800, 2500, h, dtype=np.float32).reshape(-1, 1)
    xs = np.linspace(-100, 100, w, dtype=np.float32).reshape(1, -1)
    depth = (ys + xs).clip(200, 6000).astype(np.uint16)
    x1, y1, x2, y2 = rect
    depth[y1:y2, x1:x2] = 1500  # chair at ~1.5 m
    return depth


def _conf_for(shape: tuple[int, int]) -> np.ndarray:
    """Most of the frame 'high' confidence, a patch at the bottom-left 'low'."""
    h, w = shape
    conf = np.full((h, w), 220, dtype=np.uint8)
    conf[int(h * 0.8):, : int(w * 0.2)] = 40
    return conf


def _imu_batch(t0_ns: int, period_ns: int, rate_hz: int, gravity_dir=(0.0, -9.80665, 0.0)) -> list[ImuSample]:
    n = max(int(rate_hz * period_ns / 1e9), 1)
    out = []
    for i in range(n):
        ts = t0_ns + int(i * 1e9 / rate_hz)
        # Add tiny noise so test_imu_sanity has realistic variance.
        jitter = np.random.normal(0, 0.01, 3)
        accel = (gravity_dir[0] + jitter[0], gravity_dir[1] + jitter[1], gravity_dir[2] + jitter[2])
        gyro = tuple(np.random.normal(0, 0.002, 3))
        out.append(ImuSample(ts, accel, gyro))
    return out


def generate_stub(outdir: str | Path, num_frames: int = 150, fps: int = 15,
                  prompts: list[str] | None = None, session_id: str | None = None) -> None:
    outdir = Path(outdir)
    prompts = prompts or DEFAULT_PROMPTS
    session_id = session_id or outdir.name

    import time
    timebase_ns = time.time_ns()
    period_ns = int(1e9 / fps)

    manifest = Manifest(
        session_id=session_id,
        device_serial="STUB-0000",
        firmware_version="stub",
        capture_fps=fps,
        frame_count=0,
        class_prompts=prompts,
        timebase_ns=timebase_ns,
    )
    intrinsics = Intrinsics(
        camera_matrix=[[1450.0, 0.0, 960.0], [0.0, 1450.0, 540.0], [0.0, 0.0, 1.0]],
        resolution=(RGB_WIDTH, RGB_HEIGHT),
        baseline_m=0.075,
    )
    writer = BundleWriter(outdir, manifest, intrinsics)

    np.random.seed(42)  # deterministic IMU noise across runs
    for i in range(num_frames):
        t = i / max(num_frames - 1, 1)
        rgb, rect = _gradient_rgb(RGB_HEIGHT, RGB_WIDTH, t)
        depth = _depth_for(RGB_HEIGHT, RGB_WIDTH, rect)
        conf = _conf_for((RGB_HEIGHT, RGB_WIDTH))

        mask_class = np.zeros((RGB_HEIGHT, RGB_WIDTH), dtype=np.uint8)
        mask_track = np.zeros((RGB_HEIGHT, RGB_WIDTH), dtype=np.uint16)
        x1, y1, x2, y2 = rect
        mask_class[y1:y2, x1:x2] = 1  # class index 1 -> prompts[0]
        mask_track[y1:y2, x1:x2] = 1

        imu = _imu_batch(timebase_ns + i * period_ns, period_ns, IMU_HZ)

        objects = [ObjectRecord(
            track_id=1,
            cls=prompts[0],
            bbox2d=(x1, y1, x2, y2),
            bbox3d_center=(0.0, 0.0, 1.5),
            bbox3d_size=(0.5, 1.0, 0.5),
            conf=0.92,
        )]

        writer.write(FrameRecord(
            index=i, rgb=rgb, depth_mm=depth, conf=conf,
            mask_class=mask_class, mask_track=mask_track,
            pose=Pose(), imu=imu, objects=objects,
        ))

    writer.close()
    logger.info("Wrote %d frames to %s", writer.n_written, outdir)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--outdir", default="data/captures/stub_01")
    p.add_argument("--frames", type=int, default=150)
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--prompts", nargs="+", default=DEFAULT_PROMPTS)
    return p.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    generate_stub(args.outdir, num_frames=args.frames, fps=args.fps, prompts=args.prompts)


if __name__ == "__main__":
    main()
