"""Scene assembler — the heart of Stream 03.

Reads a Stream 02 session directory, runs VLM physics inference (with
lookup fallback), optional convex decomposition, ground plane estimation,
and emits a validated `scene.json` plus a `meshes/` directory ready for
the exporters.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import lookup, schema, scale_clamp, vlm
from .decomp import DecompConfig, decompose
from .ground import GroundEstimate, estimate_ground
from .reconstructed import ReconstructedObject, load_session

logger = logging.getLogger(__name__)

SPHERE_CLASSES = {"ball", "orange", "apple", "sphere"}
DYNAMIC_CLASSES_DEFAULT = {"ball", "book", "mug", "cup", "bottle", "apple", "orange"}


@dataclass(frozen=True)
class AssemblerConfig:
    up_axis: str = "y"
    gravity: tuple[float, float, float] = (0.0, -9.81, 0.0)
    use_vlm: bool = True
    decompose_dynamic: bool = True
    decomp: DecompConfig = DecompConfig()
    dynamic_classes: frozenset[str] = frozenset(DYNAMIC_CLASSES_DEFAULT)
    camera_pose: dict | None = None
    # When True (the default), drop each object so its world-space AABB minimum
    # along the up-axis sits exactly on the ground plane. Stream 02's per-object
    # transforms are inlier-based and don't always put the bottom of the mesh
    # on the floor; without this the visual scene shows objects floating /
    # buried.
    snap_to_ground: bool = True


@dataclass(frozen=True)
class AssembleResult:
    """Aggregate output of a single end-to-end run."""

    scene: dict
    out_dir: Path
    artifacts: dict[str, Path] = field(default_factory=dict)
    wall_time_s: float = 0.0


class SceneAssembler:
    def __init__(self, config: AssemblerConfig | None = None,
                 vlm_client: vlm.VLMClient | None = None):
        self.config = config or AssemblerConfig()
        self.vlm_client = vlm_client
        # Per-object stage cache populated during a single assemble() call so
        # collider / translation logic can reuse what _stage_mesh learned.
        self._stage_info: dict[str, dict] = {}

    # ---- public ----------------------------------------------------------

    def assemble(self, session_dir: Path, out_dir: Path) -> dict:
        result = self.assemble_full(session_dir, out_dir, run_exporters=False)
        return result.scene

    def assemble_full(
        self,
        session_dir: Path,
        out_dir: Path,
        run_exporters: bool = True,
    ) -> AssembleResult:
        """Full end-to-end run: scene.json + every exporter + PROVENANCE.md."""
        t0 = time.perf_counter()
        self._stage_info = {}

        raw_objects = load_session(session_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "meshes").mkdir(exist_ok=True)
        (out_dir / "hulls").mkdir(exist_ok=True)

        # Run scale-clamp first so ground fit sees corrected bboxes.
        clamps = [scale_clamp.clamp_object_scale(o) for o in raw_objects]
        objects = [c.obj for c in clamps]

        ground = estimate_ground(objects, up_axis=self.config.up_axis)
        scene_objects = [
            self._build_object(obj, clamp, session_dir, out_dir, ground)
            for obj, clamp in zip(objects, clamps)
        ]

        scene = {
            "version": "1.0",
            "world": {
                "gravity": list(self.config.gravity),
                "up_axis": self.config.up_axis,
                "unit": "meters",
            },
            "ground": ground.to_scene_block(),
            "objects": scene_objects,
            "camera_pose": self.config.camera_pose or {
                "translation": [0.0, 1.2, 0.0],
                "rotation_quat": [0.0, 0.0, 0.0, 1.0],
                "scale": 1.0,
            },
        }
        schema.validate(scene)

        scene_path = out_dir / "scene.json"
        with scene_path.open("w") as fh:
            json.dump(scene, fh, indent=2)
        logger.info("Wrote %s (%d objects)", scene_path, len(scene_objects))

        artifacts: dict[str, Path] = {"scene_json": scene_path}
        if run_exporters:
            artifacts.update(self._run_exporters(scene, out_dir))

        wall_time_s = time.perf_counter() - t0
        provenance_path = self._write_provenance(
            scene, raw_objects, ground, out_dir, wall_time_s,
        )
        artifacts["provenance"] = provenance_path

        return AssembleResult(
            scene=scene,
            out_dir=out_dir,
            artifacts=artifacts,
            wall_time_s=wall_time_s,
        )

    # ---- per-object ------------------------------------------------------

    def _build_object(
        self,
        obj: ReconstructedObject,
        clamp: scale_clamp.ClampResult,
        session_dir: Path,
        out_dir: Path,
        ground: GroundEstimate,
    ) -> dict:
        mesh_rel = self._stage_mesh(obj, session_dir, out_dir, mesh_scale=clamp.scale)
        # The staged mesh has the source's world rotation *baked in* during
        # staging (see ``_stage_mesh``), so we must NOT re-apply it here —
        # otherwise objects double-rotate. Translation still comes from the
        # ReconstructedObject world centre (or ground-snap of it).
        translation = list(obj.center)
        if self.config.snap_to_ground:
            translation = self._snap_to_ground(obj, translation, ground)
        rotation_quat = [0.0, 0.0, 0.0, 1.0]
        collider = self._build_collider(obj, session_dir, out_dir)
        physics_block, material_class, source_block = self._physics(obj, session_dir)

        return {
            "id": obj.id,
            "class": obj.class_name,
            "mesh": mesh_rel,
            "transform": {
                "translation": translation,
                "rotation_quat": rotation_quat,
                "scale": 1.0,
            },
            "collider": collider,
            "physics": physics_block,
            "material_class": material_class,
            "source": source_block,
        }

    def _stage_mesh(self, obj, session_dir: Path, out_dir: Path,
                    mesh_scale: float = 1.0) -> str:
        """Stage a source mesh into ``out_dir/meshes/<id>.glb``.

        The staged mesh ends up centered at the origin, with the source's
        embedded node transform (which usually encodes Stream 02's world
        placement, including rotation) **baked into vertices**, then
        uniformly scaled so its up-axis extent lies in the class prior
        range. ``scene.json`` therefore drives placement via
        ``transform.translation`` only — rotation is set to identity at
        the call site so we don't apply it twice.

        Always loads as a Scene (no ``force="mesh"``) so PBR atlases
        survive. The trimesh GLB exporter preserves materials when given
        a Scene with an inner Trimesh whose ``visual.material`` is set.
        """
        import trimesh

        src = session_dir / obj.mesh_path
        dst = out_dir / "meshes" / f"{obj.id}.glb"

        scene = trimesh.load(src)
        if not isinstance(scene, trimesh.Scene):
            scene = trimesh.Scene(scene)

        if scene.bounds is None:
            raise RuntimeError(
                f"Mesh for {obj.id} produced no bounds — cannot stage. "
                f"Source: {src}"
            )

        up_idx = {"x": 0, "y": 1, "z": 2}[self.config.up_axis]
        # ``Scene.bounds`` already accounts for embedded node transforms.
        world_bounds = scene.bounds.copy()
        world_center = 0.5 * (world_bounds[0] + world_bounds[1])
        world_extent_up = float(world_bounds[1, up_idx] - world_bounds[0, up_idx])

        if world_extent_up <= 0:
            raise RuntimeError(
                f"Degenerate up-axis extent for {obj.id}: {world_extent_up:.6f} m"
            )

        effective_scale = scale_clamp.mesh_aware_scale(
            obj.class_name, world_extent_up, fallback=mesh_scale,
        )

        # Compose: T(-world_center) first, then S(effective_scale).
        # Result: staged mesh is centered at origin and uniformly scaled.
        translate = np.eye(4)
        translate[:3, 3] = -world_center
        scale = np.eye(4)
        for i in range(3):
            scale[i, i] = effective_scale
        scene.apply_transform(scale @ translate)

        scene.export(dst)

        scaled_extents = (world_bounds[1] - world_bounds[0]) * effective_scale
        self._stage_info[obj.id] = {
            "src": src,
            "dst": dst,
            "effective_scale": effective_scale,
            "world_center": world_center.tolist(),
            "world_extent_up": world_extent_up,
            "scaled_extents": scaled_extents.tolist(),
        }
        return f"meshes/{obj.id}.glb"

    def _snap_to_ground(
        self,
        obj: ReconstructedObject,
        translation: list[float],
        ground: GroundEstimate,
    ) -> list[float]:
        """Translate so the staged mesh's lowest point sits on the ground.

        ``_stage_mesh`` produces a mesh centered at the origin with the
        source rotation baked in, so the staged mesh's local AABB already
        matches its world-frame AABB once placed at any translation. Half
        the up-axis extent is therefore the lowest point's depth below
        the translation.
        """
        info = self._stage_info.get(obj.id)
        if info is None:
            return translation
        up_idx = {"x": 0, "y": 1, "z": 2}[self.config.up_axis]
        half_extent = 0.5 * float(info["scaled_extents"][up_idx])
        translation = list(translation)
        translation[up_idx] = float(ground.offset) + half_extent
        return translation

    def _build_collider(self, obj, session_dir: Path, out_dir: Path) -> dict:
        if obj.class_name in SPHERE_CLASSES:
            size = [b - a for a, b in zip(obj.bbox_min, obj.bbox_max)]
            radius = max(max(size) / 2.0, 1e-3)
            return {"shape": "sphere", "convex_decomposition": False, "radius": radius}

        is_dynamic = obj.class_name in self.config.dynamic_classes
        if is_dynamic and self.config.decompose_dynamic:
            staged_mesh = out_dir / "meshes" / f"{obj.id}.glb"
            try:
                hull_paths = decompose(
                    staged_mesh,
                    out_dir / "hulls",
                    self.config.decomp,
                )
                return {
                    "shape": "mesh",
                    "convex_decomposition": True,
                    "hull_paths": [f"hulls/{p.name}" for p in hull_paths],
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("CoACD failed for %s (%s); using mesh collider",
                               obj.id, exc)

        return {"shape": "mesh", "convex_decomposition": False}

    def _physics(self, obj, session_dir: Path):
        if self.config.use_vlm:
            bbox_size = tuple(b - a for a, b in zip(obj.bbox_min, obj.bbox_max))
            estimate = vlm.estimate_physics(
                obj.class_name,
                session_dir / obj.crop_image_path,
                bbox_size_m=bbox_size,
                client=self.vlm_client,
            )
            physics_block = {
                "mass_kg": estimate.mass_kg,
                "friction": estimate.friction,
                "restitution": estimate.restitution,
                "is_rigid": estimate.is_rigid,
            }
            material_class = estimate.material
            source_block = {
                "mesh_origin": obj.mesh_origin,
                "physics_origin": estimate.source,
                "vlm_reasoning": estimate.reasoning,
            }
        else:
            physics_block = lookup.physics_for(obj.class_name)
            material_class = lookup.material_for(obj.class_name)
            source_block = {
                "mesh_origin": obj.mesh_origin,
                "physics_origin": "lookup",
                "vlm_reasoning": "",
            }
        return physics_block, material_class, source_block

    # ---- exporters / provenance ------------------------------------------

    def _run_exporters(self, scene: dict, out_dir: Path) -> dict[str, Path]:
        from .exporters import export_gltf, export_mjcf, export_mujoco_py

        artifacts: dict[str, Path] = {}
        gltf_res = export_gltf(scene, session_dir=out_dir, out_dir=out_dir)
        artifacts["scene_gltf"] = gltf_res.scene_gltf
        artifacts["scene_glb"] = gltf_res.scene_glb
        artifacts["sidecar"] = gltf_res.sidecar

        mjcf_path = export_mjcf(scene, out_dir)
        artifacts["scene_mjcf"] = mjcf_path

        mujoco_path = export_mujoco_py(scene, out_dir)
        artifacts["scene_py"] = mujoco_path

        try:
            from .exporters import export_usd  # type: ignore[attr-defined]
            usd_path = export_usd(scene, session_dir=out_dir, out_dir=out_dir)
            artifacts["scene_usd"] = usd_path
        except Exception as exc:  # pragma: no cover — usd is optional
            logger.info("Skipping USD exporter: %s", exc)

        return artifacts

    def _write_provenance(
        self,
        scene: dict,
        raw_objects: list[ReconstructedObject],
        ground: GroundEstimate,
        out_dir: Path,
        wall_time_s: float,
    ) -> Path:
        session_id = out_dir.name
        ground_block = ground.to_scene_block()
        vlm_lines: list[str] = []
        for o in scene["objects"]:
            origin = o["source"]["physics_origin"]
            reasoning = o["source"].get("vlm_reasoning", "")
            vlm_lines.append(
                f"- `{o['id']}` ({o['class']}): physics_origin=`{origin}`"
                + (f" — {reasoning}" if reasoning else "")
            )
        if not vlm_lines:
            vlm_lines.append("- (no objects)")

        mesh_lines = [
            f"- `{obj.id}` ({obj.class_name}): `{obj.mesh_path}`"
            f" (mesh_origin=`{obj.mesh_origin}`)"
            for obj in raw_objects
        ]

        text = (
            f"# PROVENANCE — {session_id}\n\n"
            f"Generated by `scene.assembler` at"
            f" {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}.\n\n"
            f"## Input session\n"
            f"- `session_id`: `{session_id}`\n"
            f"- objects loaded: {len(raw_objects)}\n\n"
            f"## Source meshes\n"
            + "\n".join(mesh_lines) + "\n\n"
            f"## Ground plane\n"
            f"- type: `{ground_block['type']}`\n"
            f"- normal: `{ground_block['normal']}`\n"
            f"- material: friction=`{ground_block['material']['friction']}`,"
            f" restitution=`{ground_block['material']['restitution']}`\n"
            f"- offset (along up-axis): `{ground.offset:.6f}` m\n\n"
            f"## VLM queries\n"
            f"- use_vlm: `{self.config.use_vlm}`\n"
            + "\n".join(vlm_lines) + "\n\n"
            f"## Wall time\n"
            f"- total: `{wall_time_s:.2f}` s\n"
        )
        path = out_dir / "PROVENANCE.md"
        path.write_text(text)
        return path


# ----- helpers ---------------------------------------------------------------


def _aabb_corners(bounds: np.ndarray) -> np.ndarray:
    """Return the 8 corners of an AABB given by [[xmin,ymin,zmin], [xmax,ymax,zmax]]."""
    lo, hi = bounds[0], bounds[1]
    return np.array([
        [lo[0], lo[1], lo[2]],
        [lo[0], lo[1], hi[2]],
        [lo[0], hi[1], lo[2]],
        [lo[0], hi[1], hi[2]],
        [hi[0], lo[1], lo[2]],
        [hi[0], lo[1], hi[2]],
        [hi[0], hi[1], lo[2]],
        [hi[0], hi[1], hi[2]],
    ], dtype=np.float64)


def _quat_to_matrix(q: tuple[float, float, float, float]) -> np.ndarray:
    qx, qy, qz, qw = q
    n = (qx * qx + qy * qy + qz * qz + qw * qw)
    if n < 1e-12:
        return np.eye(3)
    s = 2.0 / n
    return np.array([
        [1 - s * (qy * qy + qz * qz), s * (qx * qy - qz * qw), s * (qx * qz + qy * qw)],
        [s * (qx * qy + qz * qw), 1 - s * (qx * qx + qz * qz), s * (qy * qz - qx * qw)],
        [s * (qx * qz - qy * qw), s * (qy * qz + qx * qw), 1 - s * (qx * qx + qy * qy)],
    ], dtype=np.float64)


# ----- CLI -------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="scene.assembler",
        description="Build a Stream 03 scene package from a Stream 02 reconstruction.",
    )
    parser.add_argument("--reconstructed", required=True, type=Path,
                        help="Path to reconstructed.json (or its session dir).")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output directory for the scene package.")
    parser.add_argument("--use-vlm", action="store_true",
                        help="Call the VLM for physics estimates (defaults to lookup-only).")
    parser.add_argument("--no-decompose", action="store_true",
                        help="Skip CoACD convex decomposition for dynamic objects.")
    parser.add_argument("--no-snap-to-ground", action="store_true",
                        help="Trust Stream 02 translations verbatim (do not stand on ground).")
    parser.add_argument("--log-level", default="INFO",
                        help="Python logging level (DEBUG, INFO, WARNING, ...).")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    rec_path = args.reconstructed
    session_dir = rec_path.parent if rec_path.is_file() else rec_path

    cfg = AssemblerConfig(
        use_vlm=args.use_vlm,
        decompose_dynamic=not args.no_decompose,
        snap_to_ground=not args.no_snap_to_ground,
    )
    assembler = SceneAssembler(cfg)
    result = assembler.assemble_full(session_dir, args.out, run_exporters=True)
    logger.info(
        "Scene package ready at %s (wall=%.2fs, %d artifacts)",
        result.out_dir, result.wall_time_s, len(result.artifacts),
    )
    for name, path in sorted(result.artifacts.items()):
        logger.info("  %s -> %s", name, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
