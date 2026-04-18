"""glTF + sidecar physics JSON exporter (primary).

Per ADR: `KHR_physics_rigid_bodies` is still unratified, so we keep
physics in a `scene.glb.physics.json` sidecar file. The sidecar is
indexed by scene-object id so the viewer can look it up after loading
the glTF.

This exporter concatenates every object's glTF into a single `scene.glb`
using trimesh's Scene. The ground plane is added as a large flat quad.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh


GROUND_SIZE_M = 10.0


@dataclass(frozen=True)
class GLTFResult:
    scene_glb: Path
    sidecar: Path


def export_gltf(scene: dict, session_dir: Path, out_dir: Path) -> GLTFResult:
    """Concatenate object meshes + ground into `scene.glb`; write sidecar."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tscene = trimesh.Scene()

    for obj in scene["objects"]:
        mesh = trimesh.load(session_dir / obj["mesh"], force="mesh")
        tr = _transform_matrix(obj["transform"])
        tscene.add_geometry(mesh, node_name=obj["id"], transform=tr)

    ground_mesh = _ground_quad(scene["ground"], size=GROUND_SIZE_M)
    tscene.add_geometry(ground_mesh, node_name="ground")

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

    return GLTFResult(scene_glb=scene_glb, sidecar=sidecar)


def _transform_matrix(t: dict) -> np.ndarray:
    import numpy as np
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
    return mesh
