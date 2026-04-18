"""Live OAK-4 preview — RGB + colourised depth side-by-side.

Not part of the capture pipeline — just a viewfinder for aiming the camera.
Press 'q' to quit.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import depthai as dai  # noqa: E402


def build_pipeline(fps: int, preset: str = "DENSITY"):
    p = dai.Pipeline()
    cam = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    left = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
    right = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)

    rgb_out = cam.requestOutput((1280, 720), dai.ImgFrame.Type.NV12, fps=fps)
    l_out = left.requestOutput((640, 400), dai.ImgFrame.Type.GRAY8, fps=fps)
    r_out = right.requestOutput((640, 400), dai.ImgFrame.Type.GRAY8, fps=fps)

    stereo = p.create(dai.node.StereoDepth)
    stereo.setDefaultProfilePreset(getattr(dai.node.StereoDepth.PresetMode, preset))
    stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
    stereo.setLeftRightCheck(True)
    l_out.link(stereo.left)
    r_out.link(stereo.right)

    sync = p.create(dai.node.Sync)
    sync.setSyncThreshold(dt.timedelta(milliseconds=50))
    rgb_out.link(sync.inputs["rgb"])
    stereo.depth.link(sync.inputs["depth"])

    return p, sync.out.createOutputQueue(maxSize=4, blocking=False)


def colourise_depth(depth_mm: np.ndarray, max_mm: int = 4000) -> np.ndarray:
    d = np.clip(depth_mm, 0, max_mm).astype(np.float32) / max_mm
    d8 = (d * 255).astype(np.uint8)
    d8[depth_mm == 0] = 0
    return cv2.applyColorMap(d8, cv2.COLORMAP_TURBO)


def main() -> int:
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--max-depth-mm", type=int, default=4000)
    ap.add_argument(
        "--preset", default="DENSITY",
        choices=["DEFAULT", "ROBOTICS", "DENSITY", "ACCURACY", "HIGH_DETAIL", "FAST_DENSITY", "FAST_ACCURACY", "FACE"],
        help="StereoDepth preset — DENSITY fills more pixels, ROBOTICS is cleaner",
    )
    args = ap.parse_args()

    pipeline, q = build_pipeline(args.fps, preset=args.preset)
    pipeline.start()
    print("Live preview — press 'q' in the window to quit.")
    first = True
    try:
        while True:
            group = q.tryGet()
            if group is None:
                if cv2.waitKey(5) & 0xFF == ord("q"):
                    break
                continue
            rgb = group["rgb"].getCvFrame()
            depth = group["depth"].getFrame()
            if first:
                print(f"Raw shapes: rgb={rgb.shape}, depth={depth.shape}", flush=True)
                first = False
            depth_vis = colourise_depth(depth, args.max_depth_mm)
            valid_pct = float((depth > 0).mean()) * 100
            cv2.putText(rgb, f"RGB {rgb.shape[1]}x{rgb.shape[0]}",
                        (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(depth_vis,
                        f"depth {depth.shape[1]}x{depth.shape[0]}  preset={args.preset}  valid={valid_pct:4.1f}%",
                        (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow("OAK-4 RGB", rgb)
            cv2.imshow("OAK-4 depth", depth_vis)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
