"""On-disk PerceptionFrame bundle I/O.

Pure numpy/Pillow/cv2 — no depthai import so the CI side and downstream
consumers can load/write bundles without the camera.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator

import numpy as np

try:
    import cv2  # type: ignore[import-not-found]
except ImportError:
    cv2 = None  # type: ignore[assignment]  # JPEG encode falls back to Pillow
from PIL import Image

logger = logging.getLogger(__name__)

JPEG_QUALITY = 90
RGB_WIDTH = 1920
RGB_HEIGHT = 1080


@dataclass
class ImuSample:
    timestamp_ns: int
    accel: tuple[float, float, float]
    gyro: tuple[float, float, float]

    def to_dict(self) -> dict:
        return {
            "timestamp_ns": int(self.timestamp_ns),
            "accel": list(self.accel),
            "gyro": list(self.gyro),
        }


@dataclass
class ObjectRecord:
    track_id: int
    cls: str
    bbox2d: tuple[int, int, int, int]
    bbox3d_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox3d_size: tuple[float, float, float] = (0.0, 0.0, 0.0)
    conf: float = 0.0

    def to_dict(self) -> dict:
        return {
            "track_id": int(self.track_id),
            "class": self.cls,
            "bbox2d": [int(v) for v in self.bbox2d],
            "bbox3d": {"center": list(self.bbox3d_center), "size": list(self.bbox3d_size)},
            "conf": float(self.conf),
        }


@dataclass
class Pose:
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_quat: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

    def to_dict(self) -> dict:
        return {"translation": list(self.translation), "rotation_quat": list(self.rotation_quat)}


@dataclass
class FrameRecord:
    index: int
    rgb: np.ndarray                  # HxWx3 uint8 BGR or RGB
    depth_mm: np.ndarray             # HxW uint16 millimetres, 0 = invalid
    conf: np.ndarray                 # HxW uint8, 0..255
    mask_class: np.ndarray           # HxW uint8
    mask_track: np.ndarray           # HxW uint16
    pose: Pose = field(default_factory=Pose)
    imu: list[ImuSample] = field(default_factory=list)
    objects: list[ObjectRecord] = field(default_factory=list)


@dataclass
class Manifest:
    session_id: str
    device_serial: str
    firmware_version: str
    capture_fps: int
    frame_count: int
    class_prompts: list[str]
    timebase_ns: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Intrinsics:
    camera_matrix: list[list[float]]
    resolution: tuple[int, int]
    baseline_m: float

    def to_dict(self) -> dict:
        return {
            "camera_matrix": [[float(v) for v in row] for row in self.camera_matrix],
            "resolution": [int(self.resolution[0]), int(self.resolution[1])],
            "baseline_m": float(self.baseline_m),
        }


def _encode_jpeg(rgb: np.ndarray, quality: int = JPEG_QUALITY) -> bytes:
    if cv2 is not None:
        ok, buf = cv2.imencode(".jpg", rgb, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        if not ok:
            raise RuntimeError("cv2.imencode returned False")
        return buf.tobytes()
    # Pillow fallback; expects RGB order.
    img = Image.fromarray(rgb[:, :, ::-1])
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _write_png16(path: Path, arr: np.ndarray) -> None:
    if arr.dtype != np.uint16:
        arr = arr.astype(np.uint16)
    Image.fromarray(arr).save(path, format="PNG")  # Pillow auto-maps uint16 -> I;16


def _write_png8(path: Path, arr: np.ndarray) -> None:
    if arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)
    Image.fromarray(arr).save(path, format="PNG")  # Pillow auto-maps uint8 -> L


class BundleWriter:
    """Append frames to a PerceptionFrame bundle directory.

    Frames are written incrementally — a truncated capture is still a usable
    bundle (per the risk table in docs/plans/01-perception.md §7).
    """

    def __init__(self, outdir: Path | str, manifest: Manifest, intrinsics: Intrinsics) -> None:
        self.outdir = Path(outdir)
        self.frames_dir = self.outdir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self._manifest = manifest
        self._intrinsics = intrinsics
        self._n_written = 0
        self._write_intrinsics()
        self._write_manifest()

    def _write_intrinsics(self) -> None:
        (self.outdir / "intrinsics.json").write_text(
            json.dumps(self._intrinsics.to_dict(), indent=2)
        )

    def _write_manifest(self) -> None:
        m = self._manifest.to_dict()
        m["frame_count"] = self._n_written
        (self.outdir / "capture_manifest.json").write_text(json.dumps(m, indent=2))

    def write(self, frame: FrameRecord) -> None:
        prefix = self.frames_dir / f"{frame.index:05d}"
        rgb = frame.rgb
        if rgb.shape[0] != RGB_HEIGHT or rgb.shape[1] != RGB_WIDTH:
            logger.warning(
                "RGB frame %d has shape %s, spec requires %dx%d",
                frame.index, rgb.shape, RGB_WIDTH, RGB_HEIGHT,
            )
        (prefix.with_suffix(".rgb.jpg")).write_bytes(_encode_jpeg(rgb))
        _write_png16(prefix.with_suffix(".depth.png"), frame.depth_mm)
        _write_png8(prefix.with_suffix(".conf.png"), frame.conf)
        _write_png8(prefix.with_suffix(".mask_class.png"), frame.mask_class)
        _write_png16(prefix.with_suffix(".mask_track.png"), frame.mask_track)
        (prefix.with_suffix(".pose.json")).write_text(json.dumps(frame.pose.to_dict(), indent=2))
        with (prefix.with_suffix(".imu.jsonl")).open("w") as f:
            for sample in frame.imu:
                f.write(json.dumps(sample.to_dict()) + "\n")
        (prefix.with_suffix(".objects.json")).write_text(
            json.dumps([o.to_dict() for o in frame.objects], indent=2)
        )
        self._n_written += 1
        # Rewrite the manifest each time so an interrupted capture is still valid.
        self._write_manifest()

    @property
    def n_written(self) -> int:
        return self._n_written

    def close(self) -> None:
        self._write_manifest()


class BundleReader:
    """Read a bundle from disk. Shared by replay.py and tests."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        if not (self.root / "capture_manifest.json").exists():
            raise FileNotFoundError(f"Not a bundle dir: {self.root}")
        self.manifest = json.loads((self.root / "capture_manifest.json").read_text())
        self.intrinsics = json.loads((self.root / "intrinsics.json").read_text())
        self.frames_dir = self.root / "frames"
        self._prefixes = sorted({
            p.name.split(".", 1)[0]
            for p in self.frames_dir.glob("*.rgb.jpg")
        })

    def __len__(self) -> int:
        return len(self._prefixes)

    def __iter__(self) -> Iterator[FrameRecord]:
        for i, _prefix in enumerate(self._prefixes):
            yield self.read(i)

    def read(self, idx: int) -> FrameRecord:
        prefix = self.frames_dir / self._prefixes[idx]
        rgb = np.asarray(Image.open(prefix.with_suffix(".rgb.jpg")).convert("RGB"))[:, :, ::-1]  # -> BGR
        depth = np.asarray(Image.open(prefix.with_suffix(".depth.png"))).astype(np.uint16)
        conf = np.asarray(Image.open(prefix.with_suffix(".conf.png"))).astype(np.uint8)
        mask_cls = np.asarray(Image.open(prefix.with_suffix(".mask_class.png"))).astype(np.uint8)
        mask_trk = np.asarray(Image.open(prefix.with_suffix(".mask_track.png"))).astype(np.uint16)
        pose_d = json.loads((prefix.with_suffix(".pose.json")).read_text())
        pose = Pose(tuple(pose_d["translation"]), tuple(pose_d["rotation_quat"]))
        imu = []
        imu_p = prefix.with_suffix(".imu.jsonl")
        if imu_p.exists():
            for line in imu_p.read_text().splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                imu.append(ImuSample(d["timestamp_ns"], tuple(d["accel"]), tuple(d["gyro"])))
        objs = []
        for d in json.loads((prefix.with_suffix(".objects.json")).read_text()):
            bb = d["bbox3d"]
            objs.append(ObjectRecord(
                track_id=d["track_id"],
                cls=d["class"],
                bbox2d=tuple(d["bbox2d"]),
                bbox3d_center=tuple(bb["center"]),
                bbox3d_size=tuple(bb["size"]),
                conf=d.get("conf", 0.0),
            ))
        return FrameRecord(
            index=idx,
            rgb=rgb,
            depth_mm=depth,
            conf=conf,
            mask_class=mask_cls,
            mask_track=mask_trk,
            pose=pose,
            imu=imu,
            objects=objs,
        )


def empty_masks(h: int = RGB_HEIGHT, w: int = RGB_WIDTH) -> tuple[np.ndarray, np.ndarray]:
    return np.zeros((h, w), np.uint8), np.zeros((h, w), np.uint16)
