"""DepthAI v3 capture daemon.

Builds the Camera + StereoDepth + IMU pipeline in Python (DepthAI v3 has no
runtime YAML loader — the YAML under `pipelines/` is a documented spec, not
a loadable graph), subscribes to the host output queues, and writes a
PerceptionFrame bundle to disk via `bundle.BundleWriter`.

Usage:
    python -m src.perception.capture --outdir data/captures/hero_01 --duration 10 \
        --prompts bottle popcorn_cup --yolo-blob /path/to/yoloe26.blob

YOLOE-26 open-vocab segmentation is REQUIRED (per PerceptionFrame spec
v1.1): downstream Stream 02 reconstruction needs per-object class/track
masks + object metadata to do per-instance mesh generation. A capture
without these is unusable — `--yolo-blob` and `--prompts` are mandatory,
and the run aborts if the segmenter produced zero tracked objects across
the entire session.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import depthai as dai  # type: ignore[import-not-found]
except ImportError:
    dai = None  # type: ignore[assignment]  # capture needs it, tests and BundleReader don't

from .bundle import (
    BundleWriter,
    FrameRecord,
    ImuSample,
    Intrinsics,
    Manifest,
    ObjectRecord,
    Pose,
    RGB_HEIGHT,
    RGB_WIDTH,
    empty_masks,
)

logger = logging.getLogger(__name__)

DEFAULT_FPS = 15
DEFAULT_DURATION_S = 10
IMU_RATE_HZ = 400


def _nn_resize_u16(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    ys = (np.arange(h) * arr.shape[0] / h).astype(np.int32)
    xs = (np.arange(w) * arr.shape[1] / w).astype(np.int32)
    return arr[np.ix_(ys, xs)].astype(np.uint16)


def _nn_resize_u8(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    ys = (np.arange(h) * arr.shape[0] / h).astype(np.int32)
    xs = (np.arange(w) * arr.shape[1] / w).astype(np.int32)
    return arr[np.ix_(ys, xs)].astype(np.uint8)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser("VID2SIM Perception capture daemon")
    p.add_argument("--outdir", required=True, help="Output bundle directory")
    p.add_argument("--duration", type=float, default=DEFAULT_DURATION_S, help="Capture seconds")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help="Target camera FPS")
    p.add_argument("--prompts", nargs="+", required=True,
                   help="YOLOE open-vocab class prompts (REQUIRED, e.g. 'bottle popcorn_cup chair')")
    p.add_argument("--yolo-blob", required=True,
                   help="Path to YOLOE-26 blob (REQUIRED — per spec v1.1, segmentation is mandatory)")
    p.add_argument("--session-id", default=None, help="Override session_id in manifest")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def _build_intrinsics(device: "dai.Device") -> Intrinsics:
    calib = device.readCalibration()
    matrix = calib.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, RGB_WIDTH, RGB_HEIGHT)
    baseline_cm = calib.getBaselineDistance()
    return Intrinsics(
        camera_matrix=[list(r) for r in matrix],
        resolution=(RGB_WIDTH, RGB_HEIGHT),
        baseline_m=baseline_cm * 1e-2,
    )


def _build_manifest(
    device: "dai.Device", session_id: str, prompts: list[str], fps: int, timebase_ns: int
) -> Manifest:
    try:
        fw = device.getBootloaderVersion()
        fw_str = str(fw) if fw is not None else "unknown"
    except Exception:
        fw_str = "unknown"
    return Manifest(
        session_id=session_id,
        device_serial=device.getDeviceId(),
        firmware_version=fw_str,
        capture_fps=fps,
        frame_count=0,
        class_prompts=list(prompts),
        timebase_ns=timebase_ns,
    )


def _build_pipeline(fps: int, yolo_blob: Optional[Path]):
    """Return (pipeline, handles_dict) — handles expose the output Queues."""
    if dai is None:
        raise RuntimeError("depthai not installed")

    p = dai.Pipeline()

    cam_rgb = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    cam_left = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
    cam_right = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)

    # NV12 on the RGB output: half the USB bandwidth of BGR888i. getCvFrame()
    # converts to BGR888 on the host so downstream code sees the same thing.
    rgb_out = cam_rgb.requestOutput((RGB_WIDTH, RGB_HEIGHT), dai.ImgFrame.Type.NV12, fps=fps)
    left_out = cam_left.requestOutput((640, 400), dai.ImgFrame.Type.GRAY8, fps=fps)
    right_out = cam_right.requestOutput((640, 400), dai.ImgFrame.Type.GRAY8, fps=fps)

    stereo = p.create(dai.node.StereoDepth)
    stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.ROBOTICS)
    stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
    stereo.setLeftRightCheck(True)
    stereo.setSubpixel(True)
    stereo.setExtendedDisparity(False)
    left_out.link(stereo.left)
    right_out.link(stereo.right)

    # Sync RGB + depth + conf on-device so the host sees one grouped message
    # per frame — removes "one stream ahead of the others" drift on USB 2.
    import datetime as _dt
    sync = p.create(dai.node.Sync)
    sync.setSyncThreshold(_dt.timedelta(milliseconds=50))
    rgb_out.link(sync.inputs["rgb"])
    stereo.depth.link(sync.inputs["depth"])
    stereo.confidenceMap.link(sync.inputs["conf"])

    imu = p.create(dai.node.IMU)
    imu.enableIMUSensor(dai.IMUSensor.ACCELEROMETER_RAW, IMU_RATE_HZ)
    imu.enableIMUSensor(dai.IMUSensor.GYROSCOPE_RAW, IMU_RATE_HZ)
    # Batch up IMU reports so the host doesn't drown in queue events — device
    # warns "host is reading IMU packets too slowly" if this is too small.
    imu.setBatchReportThreshold(20)
    imu.setMaxBatchReports(20)

    queues = {
        "sync": sync.out.createOutputQueue(maxSize=4, blocking=False),
        "imu": imu.out.createOutputQueue(maxSize=64, blocking=False),
    }

    if yolo_blob is not None:
        logger.info("Wiring YOLOE-26 DetectionNetwork with blob %s", yolo_blob)
        det = p.create(dai.node.DetectionNetwork)
        det.setBlobPath(yolo_blob)  # type: ignore[arg-type]
        det.setConfidenceThreshold(0.4)
        rgb_out.link(det.input)
        queues["det"] = det.out.createOutputQueue(maxSize=8, blocking=False)
    return p, queues


def _extract_imu_samples(packet, since_ns: int = 0) -> list[ImuSample]:
    """Pull (accel, gyro) pairs from an IMUPacket batch."""
    samples: list[ImuSample] = []
    if not hasattr(packet, "packets"):
        packet_iter = [packet]
    else:
        packet_iter = packet.packets
    for pkt in packet_iter:
        a = pkt.acceleroMeter
        g = pkt.gyroscope
        if a is None or g is None:
            continue
        ts_ns = int(a.getTimestampDevice().total_seconds() * 1e9)
        if ts_ns < since_ns:
            continue
        samples.append(ImuSample(ts_ns, (a.x, a.y, a.z), (g.x, g.y, g.z)))
    return samples


def _drain(queue) -> list:
    """Pull every message currently buffered on a MessageQueue."""
    out: list = []
    while True:
        m = queue.tryGet()
        if m is None:
            return out
        out.append(m)


def run_capture(args: argparse.Namespace) -> int:
    if dai is None:
        logger.error("depthai not installed — cannot run capture.")
        return 2
    outdir = Path(args.outdir)
    session_id = args.session_id or outdir.name
    yolo_blob = Path(args.yolo_blob)
    if not yolo_blob.exists():
        logger.error("YOLO blob not found: %s — segmentation is mandatory per spec v1.1", yolo_blob)
        return 2
    if not args.prompts:
        logger.error("--prompts must contain at least one class label")
        return 2

    pipeline, queues = _build_pipeline(args.fps, yolo_blob)
    pipeline.start()
    try:
        device = pipeline.getDefaultDevice()
        logger.info("Connected: %s %s", device.getDeviceName(), device.getDeviceId())
        intrinsics = _build_intrinsics(device)
        timebase_ns = time.time_ns()
        manifest = _build_manifest(device, session_id, args.prompts, args.fps, timebase_ns)

        writer = BundleWriter(outdir, manifest, intrinsics)

        logger.info("Capturing %.1fs into %s", args.duration, outdir)

        stop_at = time.time() + args.duration
        frame_idx = 0
        last_imu_ts_ns = 0
        imu_buffer: list[ImuSample] = []
        total_tracked_objects = 0  # spec v1.1: must be > 0 across the capture

        # Signal handling so Ctrl+C still flushes the manifest.
        interrupted = {"flag": False}
        def _handle_sigint(_sig, _frm):
            interrupted["flag"] = True
        signal.signal(signal.SIGINT, _handle_sigint)

        while time.time() < stop_at and not interrupted["flag"]:
            group = queues["sync"].tryGet()
            # Always drain IMU, even on frames that didn't sync yet, so we don't
            # back up the on-device queue.
            for pkt in _drain(queues["imu"]):
                for s in _extract_imu_samples(pkt, since_ns=last_imu_ts_ns):
                    imu_buffer.append(s)
                    last_imu_ts_ns = s.timestamp_ns
            if group is None:
                time.sleep(0.005)
                continue

            rgb_msg = group["rgb"]
            depth_msg = group["depth"]
            conf_msg = group["conf"]
            rgb = rgb_msg.getCvFrame()
            depth = depth_msg.getFrame()
            conf = conf_msg.getFrame()
            # StereoDepth on RVC4 can't emit at RGB resolution (setOutputSize is
            # unsupported); upsample nearest-neighbour so all per-frame arrays
            # share the spec's (1080, 1920) shape.
            if depth.shape != rgb.shape[:2]:
                depth = _nn_resize_u16(depth, rgb.shape[1], rgb.shape[0])
                conf = _nn_resize_u8(conf, rgb.shape[1], rgb.shape[0])
            mask_cls, mask_trk = empty_masks(rgb.shape[0], rgb.shape[1])

            objects: list[ObjectRecord] = []
            if "det" in queues:
                det_msg = queues["det"].tryGet()
                if det_msg is not None:
                    for d in det_msg.detections:
                        x1 = int(d.xmin * RGB_WIDTH)
                        y1 = int(d.ymin * RGB_HEIGHT)
                        x2 = int(d.xmax * RGB_WIDTH)
                        y2 = int(d.ymax * RGB_HEIGHT)
                        cls_idx = int(d.label) + 1  # 0 reserved for background
                        track_id = len(objects) + 1
                        mask_cls[y1:y2, x1:x2] = cls_idx
                        mask_trk[y1:y2, x1:x2] = track_id
                        cls_name = args.prompts[d.label] if d.label < len(args.prompts) else "unknown"
                        objects.append(ObjectRecord(
                            track_id=track_id,
                            cls=cls_name,
                            bbox2d=(x1, y1, x2, y2),
                            conf=float(d.confidence),
                        ))

            # Flush buffered IMU samples that arrived before this frame.
            frame_ts_ns = int(rgb_msg.getTimestampDevice().total_seconds() * 1e9)
            imu_samples = [s for s in imu_buffer if s.timestamp_ns <= frame_ts_ns]
            imu_buffer = [s for s in imu_buffer if s.timestamp_ns > frame_ts_ns]

            writer.write(FrameRecord(
                index=frame_idx,
                rgb=rgb,
                depth_mm=depth.astype(np.uint16),
                conf=conf.astype(np.uint8),
                mask_class=mask_cls,
                mask_track=mask_trk,
                pose=Pose(),
                imu=imu_samples,
                objects=objects,
            ))
            total_tracked_objects += len(objects)
            frame_idx += 1

        writer.close()
        logger.info("Wrote %d frames to %s (interrupted=%s)", writer.n_written, outdir, interrupted["flag"])
        if writer.n_written == 0:
            return 1
        # Spec v1.1 invariant: a bundle without any tracked detection is
        # unusable downstream. Fail loud now rather than ship a dead bundle.
        if total_tracked_objects == 0:
            logger.error(
                "INVARIANT VIOLATION: 0 tracked objects across %d frames. "
                "Check the YOLOE blob, prompts (%s), and that the scene "
                "actually contains the prompted classes. Bundle written but "
                "marked invalid.",
                writer.n_written, args.prompts,
            )
            return 3
        logger.info("Capture invariant OK: %d total tracked-object detections across %d frames",
                    total_tracked_objects, writer.n_written)
        return 0
    finally:
        pipeline.stop()


def smoke_test(seconds: float = 3.0) -> int:
    """Tiny 3-second capture used by docs/perception/camera_check.md."""
    if dai is None:
        raise RuntimeError("depthai not installed")
    p = dai.Pipeline()
    cam = p.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    q = cam.requestOutput((RGB_WIDTH, RGB_HEIGHT), dai.ImgFrame.Type.BGR888i, fps=15).createOutputQueue(maxSize=4, blocking=False)
    p.start()
    t0 = time.time()
    n = 0
    while time.time() - t0 < seconds:
        if q.tryGet() is not None:
            n += 1
        time.sleep(0.01)
    p.stop()
    logger.info("smoke_test: %d frames in %.1fs", n, seconds)
    return n


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return run_capture(args)


if __name__ == "__main__":
    sys.exit(main())
