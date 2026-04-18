"""MJCF exporter.

Template-driven, rigid bodies only (per plan §5 G1). Each scene object
becomes a `<body>` with a `<geom type="mesh">` and an `<inertial>` block
computed from the VLM / lookup mass. Meshes are referenced through an
`<asset>` section.

Known drift from Rapier semantics is documented in ADR-004. We do not
attempt to unify — MuJoCo export is for judges with a MuJoCo install.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def export_mjcf(scene: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    mujoco = ET.Element("mujoco", {"model": "vid2sim_scene"})

    world_up = scene["world"]["up_axis"]
    gravity = " ".join(str(g) for g in scene["world"]["gravity"])
    ET.SubElement(mujoco, "option", {"gravity": gravity, "timestep": "0.002"})

    compiler = ET.SubElement(mujoco, "compiler", {
        "coordinate": "local",
        "angle": "radian",
        "meshdir": "meshes",
    })
    if world_up == "z":
        compiler.set("eulerseq", "xyz")

    # Assets
    asset = ET.SubElement(mujoco, "asset")
    for obj in scene["objects"]:
        ET.SubElement(asset, "mesh", {
            "name": f"mesh_{obj['id']}",
            "file": Path(obj["mesh"]).name,
        })

    # Worldbody
    worldbody = ET.SubElement(mujoco, "worldbody")
    ground_mat = scene["ground"]["material"]
    ET.SubElement(worldbody, "geom", {
        "name": "ground",
        "type": "plane",
        "size": "5 5 0.1",
        "friction": f"{ground_mat['friction']} 0.005 0.0001",
    })

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
        mass = obj["physics"]["mass_kg"]
        ET.SubElement(body, "inertial", {
            "pos": "0 0 0",
            "mass": str(mass),
            # diagonal approximation — MuJoCo recomputes from mesh if present
            "diaginertia": f"{mass * 0.1} {mass * 0.1} {mass * 0.1}",
        })
        geom_attrs = {
            "type": "mesh",
            "mesh": f"mesh_{obj['id']}",
            "friction": f"{obj['physics']['friction']} 0.005 0.0001",
        }
        if obj["collider"].get("convex_decomposition"):
            geom_attrs["type"] = "mesh"  # MuJoCo treats mesh as convex hull by default
        ET.SubElement(body, "geom", geom_attrs)

    tree = ET.ElementTree(mujoco)
    ET.indent(tree, space="  ")
    out = out_dir / "scene.xml"
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return out
