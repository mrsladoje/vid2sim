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


def build_pipeline(rgb_fps: int, stereo_fps: int, rgb_size: tuple[int, int], preset: str = "DENSITY"):
    p = dai.Pipeline()
    cam = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    left = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
    right = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)

    rgb_out = cam.requestOutput(rgb_size, dai.ImgFrame.Type.NV12, fps=rgb_fps)
    # Stereo cameras stay at native mono resolution / fps — depth quality and
    # USB bandwidth come from there, not from the RGB stream.
    l_out = left.requestOutput((640, 400), dai.ImgFrame.Type.GRAY8, fps=stereo_fps)
    r_out = right.requestOutput((640, 400), dai.ImgFrame.Type.GRAY8, fps=stereo_fps)

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
    ap.add_argument(
        "--rgb-size", default="1080p",
        help="RGB resolution: '4k' (3840x2160), '1080p' (1920x1080), '720p' (1280x720), or 'WxH'",
    )
    ap.add_argument("--rgb-fps", type=int, default=10,
                    help="RGB fps — matches the capture pipeline budget over the current cable scaffolding")
    ap.add_argument("--stereo-fps", type=int, default=15,
                    help="Mono + depth fps — independent of RGB fps")
    ap.add_argument("--max-depth-mm", type=int, default=4000)
    ap.add_argument(
        "--preset", default="DENSITY",
        choices=["DEFAULT", "ROBOTICS", "DENSITY", "ACCURACY", "HIGH_DETAIL", "FAST_DENSITY", "FAST_ACCURACY", "FACE"],
        help="StereoDepth preset — DENSITY fills more pixels, ROBOTICS is cleaner",
    )
    args = ap.parse_args()

    rgb_presets = {"4k": (3840, 2160), "1080p": (1920, 1080), "720p": (1280, 720)}
    if args.rgb_size.lower() in rgb_presets:
        rgb_w, rgb_h = rgb_presets[args.rgb_size.lower()]
    else:
        rgb_w, rgb_h = (int(v) for v in args.rgb_size.lower().split("x"))

    pipeline, q = build_pipeline(
        rgb_fps=args.rgb_fps,
        stereo_fps=args.stereo_fps,
        rgb_size=(rgb_w, rgb_h),
        preset=args.preset,
    )
    # 4K on a 1280x720 screen is unreadable — scale RGB window down for display
    # without losing the underlying stream.
    display_scale = min(1.0, 1280 / rgb_w)
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
            cv2.putText(rgb,
                        f"RGB {rgb.shape[1]}x{rgb.shape[0]} @ {args.rgb_fps} fps",
                        (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3, cv2.LINE_AA)
            cv2.putText(depth_vis,
                        f"depth {depth.shape[1]}x{depth.shape[0]}  preset={args.preset}  valid={valid_pct:4.1f}%",
                        (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            if display_scale < 1.0:
                rgb_disp = cv2.resize(rgb, (int(rgb.shape[1] * display_scale),
                                            int(rgb.shape[0] * display_scale)),
                                      interpolation=cv2.INTER_AREA)
            else:
                rgb_disp = rgb
            cv2.imshow("OAK-4 RGB", rgb_disp)
            cv2.imshow("OAK-4 depth", depth_vis)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
