"""End-to-end hero-object reconstruction (G2).

Reads one PerceptionFrame bundle, runs the full Stream-02 pipeline on a
chosen keyframe and track id, and writes a ReconstructedObject set.

Pipeline:

    bundle/<frame> → fused depth → masked back-projection (world)
           ↓                              ↓
     VIO world-pose                observed point cloud
                                         ↓
        RunPod Hunyuan3D (fallback TripoSG / SF3D / stub)
                                         ↓
                   unit-cube raw mesh bytes (glb)
                                         ↓
                   ICP align (scale + rotation + translation)
                                         ↓
                        mesh decimation to ≤50k tris
                                         ↓
       data/reconstructed/<id>/objects/<tid>_<class>/{mesh.glb, ...}

This module is deliberately composable: every stage is a separate
function so G4 coverage tests can exercise them independently. The
heavy external actors (RunPod, DA3) are injected — callers pass a
`ReconstructorConfig` with pluggable hooks for tests.
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import trimesh
from PIL import Image

from .backproject import Intrinsics, backproject, load_intrinsics, pose_from_pose_json
from .decimate import decimate_mesh
from .fusion import FusionConfig, FusionResult, fuse_depth
from .icp_align import AlignConfig, AlignResult, align
from .runpod_client import MeshCall, RunPodClient
from .vio import WorldPose, world_pose

logger = logging.getLogger(__name__)


DA3Fn = Callable[[np.ndarray], np.ndarray]  # rgb_uint8 HxWx3 -> depth HxW
GenFn = Callable[[bytes, bytes, str], MeshCall]


@dataclass
class ReconstructorConfig:
    out_root: Path = Path("data/reconstructed")
    fusion: FusionConfig = field(default_factory=FusionConfig)
    align: AlignConfig = field(default_factory=AlignConfig)
    max_tris: int = 50_000
    primary_model: str = "hunyuan3d"


def _load_rgb(path: Path) -> np.ndarray:
    try:
        return np.asarray(Image.open(path).convert("RGB"))
    except OSError as exc:
        logger.warning("rgb unreadable at %s (%s); using grey placeholder", path, exc)
        return np.full((480, 640, 3), 127, dtype=np.uint8)


def _load_depth_mm(path: Path) -> np.ndarray:
    if not path.exists():
        return np.zeros((1, 1), dtype=np.float32)
    img = Image.open(path)
    arr = np.asarray(img)
    # uint16 mm → metres
    if arr.dtype == np.uint16:
        return (arr.astype(np.float32) / 1000.0)
    return arr.astype(np.float32)


def _load_conf(path: Path) -> Optional[np.ndarray]:
    if not path.exists():
        return None
    img = Image.open(path)
    return np.asarray(img)


def _load_mask_track(path: Path, track_id: int) -> np.ndarray:
    if not path.exists():
        return np.zeros((1, 1), dtype=bool)
    img = Image.open(path)
    arr = np.asarray(img)
    return arr == track_id


def _rgb_crop_jpeg(rgb: np.ndarray, bbox2d: list[float]) -> bytes:
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = (int(v) for v in bbox2d)
    x0 = max(0, min(w - 1, x0))
    y0 = max(0, min(h - 1, y0))
    x1 = max(x0 + 1, min(w, x1))
    y1 = max(y0 + 1, min(h, y1))
    img = Image.fromarray(rgb[y0:y1, x0:x1])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _mask_png(mask: np.ndarray, bbox2d: list[float]) -> bytes:
    h, w = mask.shape
    x0, y0, x1, y1 = (int(v) for v in bbox2d)
    x0 = max(0, min(w - 1, x0))
    y0 = max(0, min(h - 1, y0))
    x1 = max(x0 + 1, min(w, x1))
    y1 = max(y0 + 1, min(h, y1))
    sub = mask[y0:y1, x0:x1]
    img = Image.fromarray((sub.astype(np.uint8) * 255), mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _glb_to_scene(glb_bytes: bytes) -> trimesh.Scene:
    """Parse a GLB and return a Scene, preserving textures/materials.

    SF3D ships a UV-mapped textured mesh inside a Scene. Previously we
    called ``trimesh.load(..., force='mesh')`` which collapses Scene →
    single Trimesh (one uniform material), destroying the texture atlas
    at load time. Keep the Scene intact so ``scene.apply_transform(...)``
    + ``scene.export('glb')`` carry the baked texture end-to-end.

    Stub fallback (12-byte dummy glb) parses to a Trimesh; we wrap it in
    a Scene so the rest of the pipeline has a uniform interface.
    """
    loaded = trimesh.load(io.BytesIO(glb_bytes), file_type="glb")
    if isinstance(loaded, trimesh.Scene):
        if not loaded.geometry:
            raise ValueError("glb scene had no geometry")
        return loaded
    if isinstance(loaded, trimesh.Trimesh):
        return trimesh.Scene(geometry={"mesh": loaded})
    raise TypeError(f"glb did not parse to a Scene or Trimesh: got {type(loaded)}")


def _scene_vertex_cloud(scene: trimesh.Scene) -> np.ndarray:
    """Return all vertices concatenated into one (N, 3) array for ICP.

    ``scene.dump(concatenate=True)`` returns a flattened Trimesh we can
    throw away after reading ``.vertices`` — the original Scene is not
    mutated, so materials remain intact on export.
    """
    flat = scene.dump(concatenate=True)
    return np.asarray(flat.vertices)


def _scene_total_faces(scene: trimesh.Scene) -> int:
    return sum(len(g.faces) for g in scene.geometry.values()
               if hasattr(g, "faces"))


def _rotation_to_quat(r: np.ndarray) -> tuple[float, float, float, float]:
    m = np.asarray(r, dtype=np.float64)
    t = np.trace(m)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2.0
        qw = 0.25 * s
        qx = (m[2, 1] - m[1, 2]) / s
        qy = (m[0, 2] - m[2, 0]) / s
        qz = (m[1, 0] - m[0, 1]) / s
    else:
        if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
            s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
            qw = (m[2, 1] - m[1, 2]) / s
            qx = 0.25 * s
            qy = (m[0, 1] + m[1, 0]) / s
            qz = (m[0, 2] + m[2, 0]) / s
        elif m[1, 1] > m[2, 2]:
            s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
            qw = (m[0, 2] - m[2, 0]) / s
            qx = (m[0, 1] + m[1, 0]) / s
            qy = 0.25 * s
            qz = (m[1, 2] + m[2, 1]) / s
        else:
            s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
            qw = (m[1, 0] - m[0, 1]) / s
            qx = (m[0, 2] + m[2, 0]) / s
            qy = (m[1, 2] + m[2, 1]) / s
            qz = 0.25 * s
    return (float(qx), float(qy), float(qz), float(qw))


def fused_depth_for_frame(
    capture_dir: Path,
    frame: int,
    da3_fn: Optional[DA3Fn] = None,
    cfg: Optional[FusionConfig] = None,
) -> FusionResult:
    """Build one frame's fused depth map.

    DA3 is pluggable: on M3 Max we pass a real MPS runner; in tests and
    CI we pass a synthetic depth-from-rgb function (or None — fall back
    to stereo-only).
    """
    prefix = f"{frame:05d}"
    frames = capture_dir / "frames"
    stereo = _load_depth_mm(frames / f"{prefix}.depth.png")
    conf = _load_conf(frames / f"{prefix}.conf.png")

    if da3_fn is not None:
        rgb = _load_rgb(frames / f"{prefix}.rgb.jpg")
        da3 = da3_fn(rgb)
    else:
        # No DA3 available — pipeline still works, fusion collapses to
        # stereo-only (s=1, t=0).
        da3 = stereo.copy()
        da3[da3 == 0] = np.nan

    return fuse_depth(stereo, da3, conf=conf, cfg=cfg)


def observed_cloud(
    fused: np.ndarray,
    mask: np.ndarray,
    intrinsics: Intrinsics,
    world_from_cam: np.ndarray,
) -> np.ndarray:
    if fused.shape != mask.shape:
        # Mask may be at RGB resolution; nearest-neighbour resize to
        # depth resolution. Cheap and adequate for the hackathon.
        from PIL import Image as _Img

        mask_img = _Img.fromarray((mask.astype(np.uint8) * 255))
        mask = np.asarray(mask_img.resize(fused.shape[::-1], resample=0)) > 0
    return backproject(fused, intrinsics, mask=mask,
                       pose_world_from_cam=world_from_cam)


def reconstruct_one_object(
    capture_dir: Path,
    session_id: str,
    frame: int,
    track_id: int,
    class_name: str,
    *,
    bbox2d: list[float],
    runpod_client: RunPodClient,
    da3_fn: Optional[DA3Fn] = None,
    world: Optional[WorldPose] = None,
    cfg: Optional[ReconstructorConfig] = None,
) -> Path:
    """Produce one per-object bundle under `data/reconstructed/<session>/`.

    Returns the object directory path.
    """
    cfg = cfg or ReconstructorConfig()
    world = world or world_pose(capture_dir, prefer_vio=True)

    # --- inputs ---
    intr_json = json.loads((capture_dir / "intrinsics.json").read_text())
    intr = load_intrinsics(intr_json)
    fused = fused_depth_for_frame(capture_dir, frame, da3_fn=da3_fn, cfg=cfg.fusion)
    prefix = f"{frame:05d}"
    mask = _load_mask_track(capture_dir / "frames" / f"{prefix}.mask_track.png", track_id)
    rgb = _load_rgb(capture_dir / "frames" / f"{prefix}.rgb.jpg")
    crop_jpeg = _rgb_crop_jpeg(rgb, bbox2d)
    mask_png = _mask_png(mask, bbox2d)

    # --- back-project to world frame ---
    world_from_cam = world.world_from_cam(world.origin_keyframe) \
        if world.keyframes else np.eye(4)
    cloud = observed_cloud(fused.fused, mask, intr, world_from_cam)

    # --- ask RunPod (or fallback) for a unit-cube raw mesh ---
    import time
    t_gen_start = time.monotonic()
    call = runpod_client.generate_mesh(crop_jpeg, mask_png,
                                       model=cfg.primary_model)
    t_gen_total = time.monotonic() - t_gen_start

    # --- load + align + (skip) decimate ---
    # Keep the SF3D-baked Scene (textures + UVs) intact through the
    # whole pipeline. Apply ICP via scene.apply_transform(T4x4) so
    # per-primitive materials are preserved on export.
    try:
        raw_scene = _glb_to_scene(call.glb_bytes)
    except Exception as exc:  # noqa: BLE001
        # Stub payload is a 12-byte dummy glb — fall through with a
        # primitive cube so the downstream pipeline stays honest and
        # Person 3 gets *something* to assemble.
        logger.warning("glb unreadable (%s); substituting unit cube", exc)
        raw_scene = trimesh.Scene(
            geometry={"mesh": trimesh.creation.box(extents=(1.0, 1.0, 1.0))}
        )

    raw_vertices = _scene_vertex_cloud(raw_scene)

    t_align_start = time.monotonic()
    if cloud.shape[0] >= 8:
        result: AlignResult = align(raw_vertices, cloud, cfg=cfg.align)
    else:
        # Not enough observed points — bbox-centred identity pose, flag
        # in provenance.
        result = AlignResult(
            scale=1.0, rotation=np.eye(3), translation=np.zeros(3),
            residual=float("inf"), iterations=0, azimuth_deg=0.0,
        )
    # Build a 4x4 similarity from (scale, R, t) and apply it to the
    # whole scene. trimesh's Scene.apply_transform walks the scene graph
    # and transforms each primitive's geometry in place, leaving
    # visual.material untouched.
    T4 = np.eye(4, dtype=np.float64)
    T4[:3, :3] = float(result.scale) * np.asarray(result.rotation, dtype=np.float64)
    T4[:3, 3] = np.asarray(result.translation, dtype=np.float64)
    aligned_scene = raw_scene.copy()
    aligned_scene.apply_transform(T4)
    t_align = time.monotonic() - t_align_start

    # Decimation strips UVs / textures in trimesh's quadric path. SF3D
    # ships meshes well under cfg.max_tris already (~14 K faces), so we
    # only invoke decimation on the rare oversize mesh, and accept the
    # texture loss in that path with a warning.
    in_tris = _scene_total_faces(aligned_scene)
    out_tris = in_tris
    if in_tris > cfg.max_tris:
        logger.warning(
            "mesh has %d faces > cap %d — decimating (textures will be "
            "stripped). Consider raising max_tris if this is SF3D output.",
            in_tris, cfg.max_tris,
        )
        flat = aligned_scene.dump(concatenate=True)
        decimated_flat, (in_tris, out_tris) = decimate_mesh(
            flat, max_tris=cfg.max_tris,
        )
        aligned_scene = trimesh.Scene(geometry={"mesh": decimated_flat})

    # --- write artifacts ---
    obj_dir = (cfg.out_root / session_id / "objects" /
               f"{track_id}_{class_name}")
    obj_dir.mkdir(parents=True, exist_ok=True)
    glb_buf = io.BytesIO()
    aligned_scene.export(glb_buf, file_type="glb")
    (obj_dir / "mesh.glb").write_bytes(glb_buf.getvalue())
    (obj_dir / "crop.jpg").write_bytes(crop_jpeg)

    aligned_bounds = aligned_scene.bounds  # (2, 3) min / max, all geoms
    bbox_min = aligned_bounds[0].tolist()
    bbox_max = aligned_bounds[1].tolist()
    center = ((np.asarray(bbox_min) + np.asarray(bbox_max)) / 2.0).tolist()
    rot_quat = _rotation_to_quat(result.rotation)

    manifest = {
        "track_id": int(track_id),
        "class": class_name,
        "id": f"{class_name}_{track_id:02d}",
        "best_crop_path": "crop.jpg",
        "mesh_path": "mesh.glb",
        "transform_world": {
            "translation": center,
            "rotation_quat": list(rot_quat),
            "scale": 1.0,
        },
        "bbox_world": {"min": bbox_min, "max": bbox_max},
        "provenance": {
            "depth_origin": "stereo+da3_ransac" if da3_fn else "stereo_only",
            "pose_origin": world.pose_origin,
            "mesh_origin_detail": call.mesh_origin_detail,
            "mesh_origin": call.mesh_origin,
            "icp_residual": float(result.residual
                                  if np.isfinite(result.residual)
                                  else -1.0),
            "s_stereo_da3": float(fused.s),
            "t_stereo_da3": float(fused.t),
            "ran_on": call.ran_on,
            "pod_id": call.pod_id,
            "generation_s": float(t_gen_total),
            "alignment_s": float(t_align),
            "decimate_input_tris": int(in_tris),
            "decimate_output_tris": int(out_tris),
            "azimuth_deg": float(result.azimuth_deg),
            "icp_iterations": int(result.iterations),
        },
    }
    (obj_dir / "object_manifest.json").write_text(json.dumps(manifest, indent=2))
    return obj_dir


def write_session_index(
    session_id: str,
    objects: list[tuple[int, str, Path]],
    world: WorldPose,
    out_root: Path = Path("data/reconstructed"),
) -> Path:
    """Emit `reconstructed.json` + `world_pose.json` for Stream 03.

    `objects` is a list of (track_id, class_name, obj_dir) tuples — the
    `reconstruct_one_object` return values, in order.
    """
    session_dir = out_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "world_pose.json").write_text(json.dumps(world.to_json(), indent=2))

    index = {"session_id": session_id, "objects": []}
    for track_id, class_name, obj_dir in objects:
        manifest = json.loads((obj_dir / "object_manifest.json").read_text())
        index["objects"].append({
            "id": manifest["id"],
            "class": class_name,
            "mesh_path": f"objects/{track_id}_{class_name}/mesh.glb",
            "crop_image_path": f"objects/{track_id}_{class_name}/crop.jpg",
            "mesh_origin": manifest["provenance"]["mesh_origin"],
            "center": manifest["transform_world"]["translation"],
            "rotation_quat": manifest["transform_world"]["rotation_quat"],
            "bbox_min": manifest["bbox_world"]["min"],
            "bbox_max": manifest["bbox_world"]["max"],
            "lowest_points": [[
                manifest["transform_world"]["translation"][0],
                float(manifest["bbox_world"]["min"][1]),
                manifest["transform_world"]["translation"][2],
            ]],
        })
    (session_dir / "reconstructed.json").write_text(json.dumps(index, indent=2))
    return session_dir
