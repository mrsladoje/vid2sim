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
from dataclasses import dataclass
from pathlib import Path

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


class SceneAssembler:
    def __init__(self, config: AssemblerConfig | None = None,
                 vlm_client: vlm.VLMClient | None = None):
        self.config = config or AssemblerConfig()
        self.vlm_client = vlm_client

    # ---- public ----------------------------------------------------------

    def assemble(self, session_dir: Path, out_dir: Path) -> dict:
        raw_objects = load_session(session_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "meshes").mkdir(exist_ok=True)
        (out_dir / "hulls").mkdir(exist_ok=True)

        # Run scale-clamp first so ground fit sees corrected bboxes.
        clamps = [scale_clamp.clamp_object_scale(o) for o in raw_objects]
        objects = [c.obj for c in clamps]

        ground = estimate_ground(objects, up_axis=self.config.up_axis)
        scene_objects = [
            self._build_object(obj, clamp, session_dir, out_dir)
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
        return scene

    # ---- per-object ------------------------------------------------------

    def _build_object(
        self,
        obj: ReconstructedObject,
        clamp: scale_clamp.ClampResult,
        session_dir: Path,
        out_dir: Path,
    ) -> dict:
        mesh_rel = self._stage_mesh(obj, session_dir, out_dir, mesh_scale=clamp.scale)
        collider = self._build_collider(obj, session_dir, out_dir)
        physics_block, material_class, source_block = self._physics(obj, session_dir)

        return {
            "id": obj.id,
            "class": obj.class_name,
            "mesh": mesh_rel,
            "transform": {
                "translation": list(obj.center),
                "rotation_quat": list(obj.rotation_quat),
                "scale": 1.0,
            },
            "collider": collider,
            "physics": physics_block,
            "material_class": material_class,
            "source": source_block,
        }

    def _stage_mesh(self, obj, session_dir: Path, out_dir: Path,
                    mesh_scale: float = 1.0) -> str:
        src = session_dir / obj.mesh_path
        dst = out_dir / "meshes" / f"{obj.id}.glb"
        if mesh_scale == 1.0:
            shutil.copy2(src, dst)
        else:
            import trimesh
            mesh = trimesh.load(src, force="mesh")
            mesh.apply_scale(mesh_scale)
            mesh.export(dst)
        return f"meshes/{obj.id}.glb"

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
