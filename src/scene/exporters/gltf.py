"""glTF + sidecar physics JSON exporter (primary).

Per ADR: ``KHR_physics_rigid_bodies`` is still unratified, so we keep
physics in a ``scene.glb.physics.json`` sidecar file. The sidecar is
indexed by scene-object id so the viewer can look it up after loading
the glTF.

This exporter composes every object's mesh into a single ``trimesh.Scene``
and writes it out twice:

* ``scene.gltf`` (+ ``.bin`` companions) — JSON glTF, three.js loader
  opens it directly via ``GLTFLoader.load('scene.gltf')``.
* ``scene.glb`` — single-file binary glTF for drag-and-drop viewers.

**Texture preservation is mandatory.** SF3D output meshes carry baked
1024×1024 PBR atlases inside an inner ``trimesh.Scene``. Any call to
``trimesh.load(..., force="mesh")`` collapses the Scene → single
Trimesh and silently drops materials. We therefore load each object as
a Scene and add its inner geometries (with PBR materials intact) into
the parent Scene under named nodes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh


GROUND_SIZE_M = 10.0
# Light, neutral grey for the ground quad so it doesn't compete with the
# textured objects in the viewer.
GROUND_COLOR_RGBA = (200, 200, 200, 255)


@dataclass(frozen=True)
class GLTFResult:
    scene_gltf: Path
    scene_glb: Path
    sidecar: Path


def export_gltf(scene: dict, session_dir: Path, out_dir: Path) -> GLTFResult:
    """Compose object meshes + ground into a glTF scene.

    ``session_dir`` is the directory that contains the per-object meshes
    referenced by ``scene["objects"][i]["mesh"]`` (relative paths). For an
    in-place build (the assembler's normal mode) this is the same as
    ``out_dir``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tscene = trimesh.Scene()

    for obj in scene["objects"]:
        mesh_path = session_dir / obj["mesh"]
        loaded = trimesh.load(mesh_path)
        # Always treat as a Scene so PBR materials survive — see module
        # docstring for the textures-are-load-bearing rationale.
        if isinstance(loaded, trimesh.Trimesh):
            sub_scene = trimesh.Scene(loaded)
        else:
            sub_scene = loaded
        tr = _transform_matrix(obj["transform"])
        for inner_name, geom in sub_scene.geometry.items():
            node_name = f"{obj['id']}_{inner_name}"
            tscene.add_geometry(
                geom,
                node_name=node_name,
                geom_name=node_name,
                transform=tr,
            )

    ground_mesh = _ground_quad(scene["ground"], size=GROUND_SIZE_M)
    tscene.add_geometry(ground_mesh, node_name="ground", geom_name="ground")

    scene_gltf = out_dir / "scene.gltf"
    tscene.export(scene_gltf)
    scene_glb = out_dir / "scene.glb"
    tscene.export(scene_glb)

    sidecar = out_dir / "scene.glb.physics.json"
    payload = {
        "version": scene["version"],
        "world": scene["world"],
        "ground": scene["ground"],
        "objects": [
            {
                "id": o["id"],
                "class": o["class"],
                "physics": o["physics"],
                "collider": o["collider"],
                "material_class": o["material_class"],
            }
            for o in scene["objects"]
        ],
    }
    with sidecar.open("w") as fh:
        json.dump(payload, fh, indent=2)

    return GLTFResult(scene_gltf=scene_gltf, scene_glb=scene_glb, sidecar=sidecar)


def _transform_matrix(t: dict) -> np.ndarray:
    tx, ty, tz = t["translation"]
    qx, qy, qz, qw = t["rotation_quat"]
    s = float(t.get("scale", 1.0))
    # quat → rotation matrix (xyzw)
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    rot = np.array([
        [1 - 2 * (yy + zz), 2 * (xy - wz),     2 * (xz + wy)],
        [2 * (xy + wz),     1 - 2 * (xx + zz), 2 * (yz - wx)],
        [2 * (xz - wy),     2 * (yz + wx),     1 - 2 * (xx + yy)],
    ])
    m = np.eye(4)
    m[:3, :3] = rot * s
    m[:3, 3] = [tx, ty, tz]
    return m


def _ground_quad(ground: dict, size: float) -> trimesh.Trimesh:
    normal = np.asarray(ground["normal"], dtype=np.float64)
    normal = normal / (np.linalg.norm(normal) + 1e-12)
    # two orthogonal vectors in the plane
    tangent = np.array([1.0, 0.0, 0.0])
    if abs(normal @ tangent) > 0.9:
        tangent = np.array([0.0, 1.0, 0.0])
    bitangent = np.cross(normal, tangent)
    bitangent /= np.linalg.norm(bitangent)
    tangent = np.cross(bitangent, normal)
    half = size / 2.0
    corners = np.stack([
        -half * tangent - half * bitangent,
        -half * tangent + half * bitangent,
        half * tangent + half * bitangent,
        half * tangent - half * bitangent,
    ])
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    mesh = trimesh.Trimesh(vertices=corners, faces=faces, process=False)
    # Give the ground a PBR material so it renders in shaded viewers.
    mesh.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=GROUND_COLOR_RGBA,
            roughnessFactor=0.9,
            metallicFactor=0.0,
        )
    )
    return mesh
