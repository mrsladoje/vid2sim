"""Stub ReconstructedObject emitter.

Purpose: unblock Person 3 from H2 onwards by producing a fake but
structurally-complete `data/reconstructed/<session>/` bundle from any
PerceptionFrame capture directory — long before the real fusion/ICP/
RunPod path is online. Also kept as the break-glass fallback if every
real path fails on demo day.

Given a capture dir, for each active track_id on the chosen keyframe:
- builds a unit-cube mesh at the object's bbox3d,
- crops the RGB to the 2D bbox,
- writes `objects/<tid>_<class>/{mesh.glb,crop.jpg,object_manifest.json}`,
- writes session-level `reconstructed.json` matching the contract Person
  3's `src/scene/reconstructed.py` consumes.

No RunPod, no DA3, no VIO. This emitter is deliberately not clever; it
is the honest floor for what Stream 02 can guarantee to hand off.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StubConfig:
    keyframe: int = 0
    out_root: Path = Path("data/reconstructed")
    min_object_size_m: float = 0.05


def _make_unit_box_glb(size: tuple[float, float, float]) -> bytes:
    w, h, d = (max(v, 1e-3) for v in size)
    mesh = trimesh.creation.box(extents=(w, h, d))
    # Centered at origin → caller applies world transform via manifest.
    buf = BytesIO()
    mesh.export(buf, file_type="glb")
    return buf.getvalue()


def _placeholder_crop(size: tuple[int, int] = (64, 64)) -> bytes:
    img = Image.new("RGB", size, color=(127, 127, 127))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _crop_jpg(rgb_path: Path, bbox2d: list[float]) -> bytes:
    try:
        img = Image.open(rgb_path).convert("RGB")
        w, h = img.size
    except (OSError, ValueError) as exc:
        logger.warning("stub emitter: source rgb %s unreadable (%s); "
                       "substituting placeholder", rgb_path, exc)
        return _placeholder_crop()
    x0, y0, x1, y1 = bbox2d
    x0 = int(max(0, min(w - 1, x0)))
    y0 = int(max(0, min(h - 1, y0)))
    x1 = int(max(x0 + 1, min(w, x1)))
    y1 = int(max(y0 + 1, min(h, y1)))
    try:
        crop = img.crop((x0, y0, x1, y1))
        buf = BytesIO()
        crop.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except OSError as exc:
        logger.warning("stub emitter: crop failed on %s (%s); substituting",
                       rgb_path, exc)
        return _placeholder_crop()


def _safe_id(class_name: str, track_id: int) -> str:
    return f"{class_name}_{track_id:02d}"


def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name)


def emit_stub(
    capture_dir: Path,
    session_id: str,
    cfg: StubConfig | None = None,
) -> Path:
    """Write a stub ReconstructedObject set and return the session dir."""
    cfg = cfg or StubConfig()
    kf = cfg.keyframe
    prefix = f"{kf:05d}"
    frames_dir = capture_dir / "frames"
    rgb_path = frames_dir / f"{prefix}.rgb.jpg"
    objects_path = frames_dir / f"{prefix}.objects.json"
    if not rgb_path.exists() or not objects_path.exists():
        raise FileNotFoundError(
            f"capture {capture_dir} missing keyframe {prefix} files"
        )

    with objects_path.open() as fh:
        objects_meta = json.load(fh)

    session_dir = cfg.out_root / session_id
    objs_root = session_dir / "objects"
    session_dir.mkdir(parents=True, exist_ok=True)
    objs_root.mkdir(parents=True, exist_ok=True)

    index = {"session_id": session_id, "objects": []}
    for meta in objects_meta:
        tid = int(meta["track_id"])
        class_name = _sanitize(str(meta["class"]))
        obj_id = _safe_id(class_name, tid)
        obj_dir = objs_root / f"{tid}_{class_name}"
        obj_dir.mkdir(parents=True, exist_ok=True)

        bbox3d = meta.get("bbox3d") or {}
        size = tuple(bbox3d.get("size", [cfg.min_object_size_m] * 3))
        center = tuple(bbox3d.get("center", [0.0, 0.0, 0.0]))

        mesh_glb = _make_unit_box_glb(size)  # type: ignore[arg-type]
        (obj_dir / "mesh.glb").write_bytes(mesh_glb)
        (obj_dir / "crop.jpg").write_bytes(_crop_jpg(rgb_path, meta["bbox2d"]))

        half = np.array(size, dtype=float) / 2.0
        center_arr = np.array(center, dtype=float)
        bbox_min = (center_arr - half).tolist()
        bbox_max = (center_arr + half).tolist()

        manifest = {
            "track_id": tid,
            "class": class_name,
            "id": obj_id,
            "best_crop_path": "crop.jpg",
            "mesh_path": "mesh.glb",
            "transform_world": {
                "translation": list(center),
                "rotation_quat": [0.0, 0.0, 0.0, 1.0],
                "scale": 1.0,
            },
            "bbox_world": {"min": bbox_min, "max": bbox_max},
            "provenance": {
                "depth_origin": "stub",
                "pose_origin": "identity",
                "mesh_origin_detail": "stub",
                "mesh_origin": "identity",
                "icp_residual": 0.0,
                "s_stereo_da3": 1.0,
                "t_stereo_da3": 0.0,
                "ran_on": "stub",
                "pod_id": "",
                "generation_s": 0.0,
                "alignment_s": 0.0,
                "decimate_input_tris": 12,
                "decimate_output_tris": 12,
            },
        }
        with (obj_dir / "object_manifest.json").open("w") as fh:
            json.dump(manifest, fh, indent=2)

        index["objects"].append({
            "id": obj_id,
            "class": class_name,
            "mesh_path": f"objects/{tid}_{class_name}/mesh.glb",
            "crop_image_path": f"objects/{tid}_{class_name}/crop.jpg",
            "mesh_origin": "identity",
            "center": list(center),
            "rotation_quat": [0.0, 0.0, 0.0, 1.0],
            "bbox_min": bbox_min,
            "bbox_max": bbox_max,
            "lowest_points": [[center[0], float(bbox_min[1]), center[2]]],
        })

    with (session_dir / "reconstructed.json").open("w") as fh:
        json.dump(index, fh, indent=2)
    with (session_dir / "world_pose.json").open("w") as fh:
        json.dump({
            "up_axis": "y",
            "unit": "meters",
            "origin_keyframe": kf,
            "keyframes": [
                {"frame": kf, "translation": [0, 0, 0],
                 "rotation_quat": [0, 0, 0, 1]}
            ],
            "pose_origin": "identity",
        }, fh, indent=2)

    logger.info("wrote stub session to %s (%d objects)",
                session_dir, len(index["objects"]))
    # Copy a minimal capture sidecar so debugging is one less hop.
    try:
        shutil.copy2(capture_dir / "intrinsics.json",
                     session_dir / "intrinsics.json")
    except FileNotFoundError:
        pass
    return session_dir
