"""DepthAI v3 capture daemon.

Builds the Camera + StereoDepth + IMU pipeline in Python (DepthAI v3 has no
runtime YAML loader — the YAML under `pipelines/` is a documented spec, not
a loadable graph), subscribes to the host output queues, and writes a
PerceptionFrame bundle to disk via `bundle.BundleWriter`.

Quick start (zero-config — auto-downloads YOLOv8-Seg from the Luxonis Zoo):

    python -m src.perception.capture --outdir data/captures/hero_01 --duration 10

Optional: filter detections to a specific subset of COCO-80 classes:

    python -m src.perception.capture --outdir data/captures/hero_01 \
        --prompts chair bottle cup bowl

Optional: use your own YOLOv8 blob (legacy bbox-rectangle masks; the Zoo
default gives per-instance pixel masks):

    python -m src.perception.capture --outdir data/captures/hero_01 \
        --yolo-blob /path/to/custom.blob --prompts chair

Per-object segmentation is mandatory (PerceptionFrame spec v1.1):
downstream Stream 02 reconstruction needs per-object class/track masks +
object metadata to do per-instance mesh generation. The capture aborts
post-run if zero tracked objects were emitted across the entire session.
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

# Zero-config default: Luxonis Zoo's YOLOv8 instance segmentation nano.
# Outputs per-instance pixel masks (not bbox rectangles) → much cleaner
# per-object point clouds in Stream 02 → cleaner SF3D meshes downstream.
# Auto-downloads on first use via dai.NNModelDescription.
DEFAULT_ZOO_MODEL = "luxonis/yolov8-instance-segmentation-nano:coco-512x288"

# COCO-80 class list — the model's training ontology. Index = label id
# straight from the network. Used for both class-name lookup and the
# whitelist filter applied via --prompts.
COCO_80_CLASSES: tuple[str, ...] = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
)

# Sensible default prompt set for indoor "hero object" capture. Covers
# everything Person 1's typical scenes contain. Override with --prompts.
DEFAULT_HOUSEHOLD_PROMPTS: tuple[str, ...] = (
    "chair", "couch", "dining table", "bed",
    "bottle", "cup", "wine glass", "bowl", "vase",
    "potted plant", "tv", "laptop", "book", "teddy bear",
)


def _nn_resize_u16(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    ys = (np.arange(h) * arr.shape[0] / h).astype(np.int32)
    xs = (np.arange(w) * arr.shape[1] / w).astype(np.int32)
    return arr[np.ix_(ys, xs)].astype(np.uint16)


def _nn_resize_u8(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    ys = (np.arange(h) * arr.shape[0] / h).astype(np.int32)
    xs = (np.arange(w) * arr.shape[1] / w).astype(np.int32)
    return arr[np.ix_(ys, xs)].astype(np.uint8)


def _resize_mask_to_rgb(mask: np.ndarray) -> np.ndarray:
    """Nearest-neighbour upscale a binary instance mask to (RGB_HEIGHT, RGB_WIDTH).

    YOLOv8-Seg masks come out at the model's processing resolution
    (typically 512x288 for the Zoo nano). Stream 02 expects masks at the
    same resolution as the RGB / depth (1920x1080), so we upsample here.
    """
    if mask.shape == (RGB_HEIGHT, RGB_WIDTH):
        return mask
    return _nn_resize_u8(mask.astype(np.uint8), RGB_WIDTH, RGB_HEIGHT)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser("VID2SIM Perception capture daemon")
    p.add_argument("--outdir", required=True, help="Output bundle directory")
    p.add_argument("--duration", type=float, default=DEFAULT_DURATION_S, help="Capture seconds")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help="Target camera FPS")
    p.add_argument(
        "--prompts", nargs="+", default=list(DEFAULT_HOUSEHOLD_PROMPTS),
        help=(
            "Subset of COCO-80 class names to keep in masks. "
            "Default: common household objects. Pass `--prompts all` to "
            "keep every COCO class. Detections in classes outside this set "
            "are dropped before being written to mask_class / mask_track."
        ),
    )
    p.add_argument(
        "--yolo-blob", default=None,
        help=(
            "Optional: path to a custom YOLOv8 detection blob. If omitted, "
            "auto-downloads the Luxonis Zoo's instance-segmentation model "
            f"({DEFAULT_ZOO_MODEL}) which gives per-instance pixel masks. "
            "Custom blobs use the legacy bbox-rectangle mask path."
        ),
    )
    p.add_argument(
        "--zoo-model", default=DEFAULT_ZOO_MODEL,
        help="Luxonis Zoo model identifier to use when --yolo-blob is omitted.",
    )
    p.add_argument(
        "--conf-threshold", type=float, default=0.4,
        help="Per-detection confidence threshold (default: 0.4).",
    )
    p.add_argument("--session-id", default=None, help="Override session_id in manifest")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def _resolve_prompts(prompts: list[str]) -> set[str]:
    """Validate --prompts against COCO-80 and return a fast lookup set."""
    if len(prompts) == 1 and prompts[0].lower() == "all":
        return set(COCO_80_CLASSES)
    coco_set = set(COCO_80_CLASSES)
    bad = [p for p in prompts if p not in coco_set]
    if bad:
        raise ValueError(
            f"Unknown COCO-80 class names in --prompts: {bad}. "
            f"Valid classes (sorted): {sorted(coco_set)}"
        )
    return set(prompts)


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


def _build_pipeline(
    fps: int,
    zoo_model: str,
    yolo_blob: Optional[Path],
    conf_threshold: float,
):
    """Return (pipeline, handles_dict). handles include 'det_mode' = 'seg' | 'bbox'."""
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
        # Legacy: user-supplied blob → plain DetectionNetwork → bbox boxes
        # only. Mask path falls back to bbox-rectangle blits.
        logger.info("Wiring legacy DetectionNetwork with custom blob %s", yolo_blob)
        det = p.create(dai.node.DetectionNetwork)
        det.setBlobPath(yolo_blob)  # type: ignore[arg-type]
        det.setConfidenceThreshold(conf_threshold)
        rgb_out.link(det.input)
        queues["det"] = det.out.createOutputQueue(maxSize=8, blocking=False)
        queues["det_mode"] = "bbox"  # type: ignore[assignment]
    else:
        # Default: Zoo YOLOv8-Seg via depthai_nodes' ParsingNeuralNetwork.
        # Auto-downloads + caches the model; output is ImgDetectionsExtended
        # with per-instance pixel masks (not just bboxes). Massive quality
        # win for Stream 02 reconstruction.
        try:
            from depthai_nodes import ParsingNeuralNetwork  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "depthai_nodes is required for the default Zoo segmentation "
                "path. Install with: pip install depthai-nodes\n"
                "Or pass --yolo-blob /path/to/your.blob to use a custom "
                "detection-only model."
            ) from exc
        logger.info("Wiring ParsingNeuralNetwork with Zoo model %s", zoo_model)
        model_desc = dai.NNModelDescription(zoo_model)
        nn = p.create(ParsingNeuralNetwork).build(rgb_out, model_desc)
        try:
            nn.setConfidenceThreshold(conf_threshold)  # type: ignore[attr-defined]
        except Exception:
            # Some versions of ParsingNeuralNetwork wrap the threshold in
            # the parser config rather than the network node — non-fatal.
            logger.debug("setConfidenceThreshold not available on ParsingNeuralNetwork; "
                         "relying on parser default.")
        queues["det"] = nn.out.createOutputQueue(maxSize=8, blocking=False)
        queues["det_mode"] = "seg"  # type: ignore[assignment]
    return p, queues


def _process_seg_detections(
    det_msg, mask_cls: np.ndarray, mask_trk: np.ndarray, allowed_classes: set[str],
) -> list[ObjectRecord]:
    """Fill mask_cls / mask_trk from an ImgDetectionsExtended message.

    Per-instance binary masks come back at the model's processing
    resolution (e.g. 512x288). We upsample each one to the full RGB
    resolution and stamp class index + track id where the mask is true.
    """
    objects: list[ObjectRecord] = []
    detections = list(getattr(det_msg, "detections", []) or [])
    # `masks` is a single (N, h, w) numpy array per the depthai_nodes
    # ImgDetectionsExtended schema. Some firmware versions expose
    # `det.mask` per detection instead — handle both.
    masks_array = getattr(det_msg, "masks", None)
    for det_idx, det in enumerate(detections):
        cls_idx = int(getattr(det, "label", -1))
        if 0 <= cls_idx < len(COCO_80_CLASSES):
            cls_name = COCO_80_CLASSES[cls_idx]
        else:
            cls_name = "unknown"
        if cls_name not in allowed_classes:
            continue
        # Extract this detection's binary mask.
        binary: Optional[np.ndarray] = None
        per_det_mask = getattr(det, "mask", None)
        if per_det_mask is not None:
            binary = np.asarray(per_det_mask)
        elif masks_array is not None and det_idx < len(masks_array):
            binary = np.asarray(masks_array[det_idx])
        if binary is None or binary.size == 0:
            # Fall back to bbox rectangle if the mask isn't available.
            x1 = int(det.xmin * RGB_WIDTH)
            y1 = int(det.ymin * RGB_HEIGHT)
            x2 = int(det.xmax * RGB_WIDTH)
            y2 = int(det.ymax * RGB_HEIGHT)
            track_id = len(objects) + 1
            mask_cls[y1:y2, x1:x2] = cls_idx + 1
            mask_trk[y1:y2, x1:x2] = track_id
        else:
            full = _resize_mask_to_rgb(binary > 0)
            track_id = len(objects) + 1
            mask_cls[full > 0] = cls_idx + 1
            mask_trk[full > 0] = track_id
        x1 = int(det.xmin * RGB_WIDTH)
        y1 = int(det.ymin * RGB_HEIGHT)
        x2 = int(det.xmax * RGB_WIDTH)
        y2 = int(det.ymax * RGB_HEIGHT)
        objects.append(ObjectRecord(
            track_id=track_id,
            cls=cls_name,
            bbox2d=(x1, y1, x2, y2),
            conf=float(getattr(det, "confidence", 0.0)),
        ))
    return objects


def _process_bbox_detections(
    det_msg, mask_cls: np.ndarray, mask_trk: np.ndarray, allowed_classes: set[str],
) -> list[ObjectRecord]:
    """Legacy fallback: stamp bbox rectangles into mask_cls / mask_trk."""
    objects: list[ObjectRecord] = []
    for d in det_msg.detections:
        cls_idx = int(d.label)
        if 0 <= cls_idx < len(COCO_80_CLASSES):
            cls_name = COCO_80_CLASSES[cls_idx]
        else:
            cls_name = "unknown"
        if cls_name not in allowed_classes:
            continue
        x1 = int(d.xmin * RGB_WIDTH)
        y1 = int(d.ymin * RGB_HEIGHT)
        x2 = int(d.xmax * RGB_WIDTH)
        y2 = int(d.ymax * RGB_HEIGHT)
        track_id = len(objects) + 1
        mask_cls[y1:y2, x1:x2] = cls_idx + 1
        mask_trk[y1:y2, x1:x2] = track_id
        objects.append(ObjectRecord(
            track_id=track_id,
            cls=cls_name,
            bbox2d=(x1, y1, x2, y2),
            conf=float(d.confidence),
        ))
    return objects


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

    yolo_blob = Path(args.yolo_blob) if args.yolo_blob else None
    if yolo_blob is not None and not yolo_blob.exists():
        logger.error("Custom --yolo-blob not found at %s", yolo_blob)
        return 2

    try:
        allowed_classes = _resolve_prompts(args.prompts)
    except ValueError as exc:
        logger.error(str(exc))
        return 2
    logger.info("Active class whitelist (%d classes): %s",
                len(allowed_classes), sorted(allowed_classes))

    pipeline, queues = _build_pipeline(
        args.fps, args.zoo_model, yolo_blob, args.conf_threshold,
    )
    det_mode = queues.get("det_mode", "bbox")
    pipeline.start()
    try:
        device = pipeline.getDefaultDevice()
        logger.info("Connected: %s %s", device.getDeviceName(), device.getDeviceId())
        intrinsics = _build_intrinsics(device)
        timebase_ns = time.time_ns()
        manifest = _build_manifest(device, session_id, args.prompts, args.fps, timebase_ns)

        writer = BundleWriter(outdir, manifest, intrinsics)

        logger.info("Capturing %.1fs into %s (det_mode=%s)", args.duration, outdir, det_mode)

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
                    if det_mode == "seg":
                        objects = _process_seg_detections(
                            det_msg, mask_cls, mask_trk, allowed_classes,
                        )
                    else:
                        objects = _process_bbox_detections(
                            det_msg, mask_cls, mask_trk, allowed_classes,
                        )

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
                "Check that the prompted classes (%s) actually appear in "
                "the scene. The default whitelist covers common household "
                "objects; pass --prompts <coco classes> to broaden it, or "
                "--prompts all to keep every detection.",
                writer.n_written, sorted(allowed_classes)[:5],
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
