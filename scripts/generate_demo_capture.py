"""Generate a valid PerceptionFrame bundle with 3 distinct objects.

Writes `data/captures/demo_scene/` with depth+mask carved out so the
reconstruction pipeline has something real to back-project. Used for the
G3 full-demo-scene artifact check.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

OBJECTS = [
    {"track_id": 1, "class": "chair",
     "bbox2d": [80, 120, 280, 420],
     "bbox3d": {"center": [-0.4, 0.0, 1.5], "size": [0.6, 0.9, 0.6]},
     "distance_m": 1.5, "conf": 0.93},
    {"track_id": 2, "class": "table",
     "bbox2d": [340, 180, 780, 500],
     "bbox3d": {"center": [0.2, -0.2, 2.0], "size": [1.2, 0.8, 0.7]},
     "distance_m": 2.0, "conf": 0.89},
    {"track_id": 3, "class": "cup",
     "bbox2d": [820, 260, 940, 380],
     "bbox3d": {"center": [0.8, 0.3, 1.2], "size": [0.12, 0.15, 0.12]},
     "distance_m": 1.2, "conf": 0.85},
]

WIDTH, HEIGHT = 1280, 720
INTR_CX, INTR_CY = WIDTH / 2.0, HEIGHT / 2.0
FX = FY = 750.0


def main() -> int:
    out = Path("data/captures/demo_scene")
    frames = out / "frames"
    frames.mkdir(parents=True, exist_ok=True)

    # RGB — a soft gradient so JPEG compresses cleanly.
    rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    rgb[..., 0] = np.linspace(80, 180, WIDTH, dtype=np.uint8)[None, :]
    rgb[..., 1] = np.linspace(60, 150, HEIGHT, dtype=np.uint8)[:, None]
    rgb[..., 2] = 110
    Image.fromarray(rgb).save(frames / "00000.rgb.jpg", "JPEG", quality=88)

    # Depth — wall at 3m; each object cut to its bbox at its distance.
    depth = np.full((HEIGHT, WIDTH), 3000, dtype=np.uint16)
    mask_track = np.zeros((HEIGHT, WIDTH), dtype=np.uint16)
    mask_class = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    for i, obj in enumerate(OBJECTS, start=1):
        x0, y0, x1, y1 = obj["bbox2d"]
        z_mm = int(obj["distance_m"] * 1000)
        depth[y0:y1, x0:x1] = z_mm
        mask_track[y0:y1, x0:x1] = obj["track_id"]
        mask_class[y0:y1, x0:x1] = i
    Image.fromarray(depth).save(frames / "00000.depth.png")
    Image.fromarray(mask_track).save(frames / "00000.mask_track.png")
    Image.fromarray(mask_class).save(frames / "00000.mask_class.png")
    Image.fromarray(np.full((HEIGHT, WIDTH), 240, dtype=np.uint8)).save(
        frames / "00000.conf.png"
    )

    (frames / "00000.pose.json").write_text(json.dumps({
        "translation": [0.0, 1.1, 0.0],
        "rotation_quat": [0.0, 0.0, 0.0, 1.0],
    }, indent=2))
    (frames / "00000.imu.jsonl").write_text(json.dumps({
        "timestamp_ns": int(time.time() * 1e9),
        "accel": [0.0, -9.81, 0.0], "gyro": [0.0, 0.0, 0.0],
    }) + "\n")
    (frames / "00000.objects.json").write_text(json.dumps(OBJECTS, indent=2))

    (out / "intrinsics.json").write_text(json.dumps({
        "camera_matrix": [[FX, 0.0, INTR_CX], [0.0, FY, INTR_CY], [0.0, 0.0, 1.0]],
        "resolution": [WIDTH, HEIGHT],
        "baseline_m": 0.075,
    }, indent=2))
    (out / "capture_manifest.json").write_text(json.dumps({
        "session_id": "demo_scene",
        "device_serial": "synthetic",
        "firmware_version": "synthetic-1.0",
        "capture_fps": 15,
        "frame_count": 1,
        "class_prompts": ["chair", "table", "cup"],
        "timebase_ns": int(time.time() * 1e9),
    }, indent=2))
    print(f"wrote {out} ({len(OBJECTS)} objects)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
