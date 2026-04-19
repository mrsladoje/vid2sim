"""MJCF exporter.

Template-driven, rigid bodies only (per plan §5 G1). Each scene object
becomes a ``<body>`` carrying a free joint, a visual ``<geom>`` referencing
the staged collider mesh, and (when CoACD ran) one collider ``<geom>`` per
convex hull.

MuJoCo cannot read GLB. We bake an OBJ copy of every staged mesh into a
``mjcf_meshes/`` sub-directory next to ``scene.mjcf`` and reference those
OBJ files from the ``<asset>`` block. Hull GLBs from ``decomp.py`` are
similarly converted to OBJs.

Known drift from Rapier semantics is documented in ADR-004. We do not
attempt to unify — MuJoCo export is for judges with a MuJoCo install and
for the headless ``scene.py`` runner.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh

logger = logging.getLogger(__name__)

MJCF_MESH_DIR = "mjcf_meshes"


def export_mjcf(scene: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    mesh_root = out_dir / MJCF_MESH_DIR
    mesh_root.mkdir(exist_ok=True)

    mujoco = ET.Element("mujoco", {"model": "vid2sim_scene"})

    gravity = " ".join(str(g) for g in scene["world"]["gravity"])
    ET.SubElement(mujoco, "option", {"gravity": gravity, "timestep": "0.002"})

    ET.SubElement(mujoco, "compiler", {
        "coordinate": "local",
        "angle": "radian",
        "meshdir": MJCF_MESH_DIR,
    })

    asset = ET.SubElement(mujoco, "asset")

    # Stage each visual mesh as OBJ + register hull OBJs.
    object_assets: dict[str, dict] = {}
    for obj in scene["objects"]:
        visual_obj_name = f"mesh_{obj['id']}"
        visual_obj_file = _stage_obj(out_dir / obj["mesh"], mesh_root,
                                     f"{obj['id']}.obj")
        ET.SubElement(asset, "mesh", {
            "name": visual_obj_name,
            "file": visual_obj_file,
        })

        hull_assets: list[str] = []
        for hull_rel in obj.get("collider", {}).get("hull_paths", []) or []:
            hull_src = out_dir / hull_rel
            hull_obj_name = f"hull_{Path(hull_rel).stem}"
            hull_obj_file = _stage_obj(hull_src, mesh_root,
                                       f"{Path(hull_rel).stem}.obj")
            ET.SubElement(asset, "mesh", {
                "name": hull_obj_name,
                "file": hull_obj_file,
            })
            hull_assets.append(hull_obj_name)

        object_assets[obj["id"]] = {
            "visual_mesh": visual_obj_name,
            "hull_meshes": hull_assets,
        }

    # Worldbody
    worldbody = ET.SubElement(mujoco, "worldbody")
    ground_mat = scene["ground"]["material"]
    ground_attrs = {
        "name": "ground",
        "type": "plane",
        "size": "5 5 0.1",
        "friction": f"{ground_mat['friction']} 0.005 0.0001",
    }
    # MuJoCo's plane geom has an implicit +z normal in its local frame; for a
    # y-up scene we rotate the plane so its normal aligns with +y world.
    if scene["world"]["up_axis"] == "y":
        # 90° about +x maps +z → +y; quaternion (w x y z).
        ground_attrs["quat"] = "0.7071067811865476 0.7071067811865476 0 0"
    ET.SubElement(worldbody, "geom", ground_attrs)

    for obj in scene["objects"]:
        tx, ty, tz = obj["transform"]["translation"]
        qx, qy, qz, qw = obj["transform"]["rotation_quat"]
        body = ET.SubElement(worldbody, "body", {
            "name": obj["id"],
            "pos": f"{tx} {ty} {tz}",
            # MuJoCo quaternions are wxyz
            "quat": f"{qw} {qx} {qy} {qz}",
        })
        if obj["physics"]["is_rigid"]:
            ET.SubElement(body, "freejoint", {"name": f"{obj['id']}_free"})

        # Visual-only geom (group 0 renders, contype=0 so it doesn't collide).
        ET.SubElement(body, "geom", {
            "name": f"{obj['id']}_visual",
            "type": "mesh",
            "mesh": object_assets[obj["id"]]["visual_mesh"],
            "contype": "0",
            "conaffinity": "0",
            "group": "0",
            "mass": "0",  # mass lives on the collider geoms below
        })

        friction_str = f"{obj['physics']['friction']} 0.005 0.0001"
        hull_meshes = object_assets[obj["id"]]["hull_meshes"]
        if hull_meshes:
            mass_per_hull = float(obj["physics"]["mass_kg"]) / len(hull_meshes)
            for i, hname in enumerate(hull_meshes):
                ET.SubElement(body, "geom", {
                    "name": f"{obj['id']}_hull_{i:02d}",
                    "type": "mesh",
                    "mesh": hname,
                    "friction": friction_str,
                    "group": "1",
                    "mass": f"{mass_per_hull}",
                })
        else:
            # No CoACD hulls — fall back to using the visual mesh (treated
            # as a single convex hull by MuJoCo).
            ET.SubElement(body, "geom", {
                "name": f"{obj['id']}_collider",
                "type": "mesh",
                "mesh": object_assets[obj["id"]]["visual_mesh"],
                "friction": friction_str,
                "group": "1",
                "mass": f"{float(obj['physics']['mass_kg'])}",
            })

    tree = ET.ElementTree(mujoco)
    ET.indent(tree, space="  ")
    out = out_dir / "scene.mjcf"
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return out


# ----- helpers ---------------------------------------------------------------


def _stage_obj(src: Path, mesh_root: Path, obj_filename: str) -> str:
    """Convert any trimesh-loadable mesh (GLB/PLY/STL/...) into a Wavefront
    OBJ at ``mesh_root / obj_filename``. Returns the file's basename relative
    to ``mesh_root`` (which is the ``meshdir`` MuJoCo expects).

    Materials are intentionally dropped — MuJoCo needs *geometry* for
    collision; the visual textures live in the glTF path.
    """
    if not src.exists():
        raise FileNotFoundError(f"MJCF asset missing: {src}")
    loaded = trimesh.load(src, force="mesh")
    if loaded is None or len(loaded.vertices) == 0:
        raise RuntimeError(f"MJCF asset {src} loaded but had no geometry.")
    dst = mesh_root / obj_filename
    loaded.export(dst, file_type="obj", include_texture=False,
                  write_texture=False)
    return obj_filename


