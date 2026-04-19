#!/usr/bin/env python3
"""
Expose an OAK camera as a standard UVC webcam so the frontend's
live-capture tab (browser `getUserMedia()`) can consume it.

Why this script exists
----------------------
OAK devices do NOT advertise themselves as UVC webcams by default. They boot
with DepthAI firmware and require a host-side pipeline to enable the UVC
output node. Once this script is running, the OAK shows up in the browser's
camera picker (and in `navigator.mediaDevices.enumerateDevices()`) just like
any other webcam — at that point the frontend's OAK-preference logic
auto-selects it.

Usage
-----
  pip install depthai                 # one-time
  python scripts/oak_uvc.py           # keep running while recording

Optional flags
  --load-and-exit   Load the UVC pipeline onto the device and exit the host
                    process. The OAK keeps streaming UVC until it's power-cycled.
                    Useful for a "set and forget" demo setup.
  --flash-app       Persist the UVC pipeline to the device's flash so it
                    boots directly into UVC mode from then on. Requires a
                    power cycle afterward. Older OAK devices only.

OAK-4 / RVC4 notes
------------------
OAK-4 (RVC4) uses DepthAI v3. The `createUVC()` node below is a v2 API. If
this script errors on OAK-4 with "unknown node" or similar, you need the
v3 path:

  1. Install DepthAI v3:      pip install --pre depthai
  2. Build an OAK App with a UVC node and deploy via oakctl:
     https://docs.luxonis.com/software-v3/oak-apps/oakctl/
  3. `oakctl app run ./uvc_app` — this launches the UVC app on-device.

This script is the right tool for OAK-D / OAK-D Lite / OAK-D Pro / OAK-1
families. For OAK-4 specifically, the oakctl UVC app path is preferred.
"""
from __future__ import annotations

import argparse
import sys
import time


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--load-and-exit", action="store_true",
                   help="Load UVC pipeline then terminate host; device keeps streaming until power-cycle.")
    p.add_argument("--flash-app", action="store_true",
                   help="Flash UVC pipeline to the device's persistent storage (older OAKs).")
    p.add_argument("--width", type=int, default=1920, help="UVC output width  (default 1920)")
    p.add_argument("--height", type=int, default=1080, help="UVC output height (default 1080)")
    return p.parse_args()


def _build_pipeline(width: int, height: int):
    import depthai as dai

    pipeline = dai.Pipeline()

    cam_rgb = pipeline.createColorCamera()
    cam_rgb.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    cam_rgb.setInterleaved(False)
    cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)

    uvc = pipeline.createUVC()
    cam_rgb.video.link(uvc.input)

    config = dai.Device.Config()
    config.board.uvc = dai.BoardConfig.UVC(width, height)
    config.board.uvc.frameType = dai.ImgFrame.Type.NV12
    pipeline.setBoardConfig(config.board)

    return pipeline, dai


def _flash(pipeline) -> None:
    import depthai as dai

    _f, bl = dai.DeviceBootloader.getFirstAvailableDevice()
    bootloader = dai.DeviceBootloader(bl, True)

    def progress(p: float) -> None:
        print(f"flashing: {p * 100:.1f}%", flush=True)

    start = time.monotonic()
    if pipeline is None:
        print("flashing bootloader…", flush=True)
        bootloader.flashBootloader(progress)
    else:
        print("flashing UVC application pipeline…", flush=True)
        bootloader.flash(progress, pipeline)
    print(f"done in {time.monotonic() - start:.1f}s. power-cycle the device.", flush=True)


def main() -> int:
    args = _parse_args()

    if args.load_and_exit:
        # Disable device watchdog BEFORE importing depthai so the device stays
        # up after we exit the host process.
        import os
        os.environ["DEPTHAI_WATCHDOG"] = "0"

    try:
        pipeline, dai = _build_pipeline(args.width, args.height)
    except ImportError:
        print("error: depthai is not installed. run `pip install depthai` first.", file=sys.stderr)
        return 2
    except AttributeError as e:
        # v3 devices (OAK-4/RVC4) don't expose createUVC on the v2 API.
        print(
            "error: this OAK device doesn't support the v2 createUVC() node:\n"
            f"  {e}\n\n"
            "if you have an OAK-4 / RVC4, follow the v3 path instead:\n"
            "  https://docs.luxonis.com/software-v3/oak-apps/oakctl/\n"
            "build + deploy a UVC OAK App with:\n"
            "  oakctl app run ./uvc_app",
            file=sys.stderr,
        )
        return 3

    if args.flash_app:
        _flash(pipeline)
        return 0

    if args.load_and_exit:
        device = dai.Device(pipeline)
        print("\nUVC pipeline loaded. device continues streaming until power-cycled.")
        print("the OAK should now appear in the browser's camera picker.\n")
        # Force-terminate so the device-close destructor doesn't run.
        import os
        import signal
        os.kill(os.getpid(), signal.SIGTERM)
        return 0

    with dai.Device(pipeline):
        print("\noak_uvc: UVC pipeline running. keep this process alive.")
        print(f"         resolution {args.width}x{args.height} NV12")
        print("         open the frontend → live capture → your OAK should auto-select.")
        print("         ctrl+c to stop.\n", flush=True)
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\noak_uvc: stopping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
