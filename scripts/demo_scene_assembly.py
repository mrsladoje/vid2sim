"""End-to-end demo of Stream 03 scene assembly with a mocked VLM.

Builds a synthetic `ReconstructedObject` session (what Stream 02 would
produce), runs the assembler, then the three required exporters, and
writes everything to `data/scenes/demo_mock/` so you can open the files
yourself:

    data/scenes/demo_mock/
        scene.json
        scene.glb + scene.glb.physics.json
        scene.xml
        scene.py
        meshes/   hulls/

Open `scene.glb` at https://gltf-viewer.donmccurdy.com/ to spin the scene
in a browser. Peek at `scene.json` with any text editor.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from PIL import Image  # noqa: E402

from scene import SceneAssembler  # noqa: E402
from scene.assembler import AssemblerConfig  # noqa: E402
from scene.exporters import export_gltf, export_mjcf, export_mujoco_py  # noqa: E402


# ---------------------------------------------------------------------------
# Composite silhouette builders. trimesh.creation.cylinder/cone default to the
# Z-axis as their long axis; we flip them so height goes along +Y (the scene's
# up-axis) before translating them into place.
# ---------------------------------------------------------------------------

_Z_TO_Y = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])


def _y_cylinder(radius: float, height: float, sections: int = 24) -> trimesh.Trimesh:
    """Cylinder aligned along Y, centered at the origin (y ∈ [-h/2, +h/2])."""
    c = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    c.apply_transform(_Z_TO_Y)
    return c


def _y_cone(radius: float, height: float, sections: int = 24) -> trimesh.Trimesh:
    """Cone along +Y: base disc at y=0, apex at y=+height."""
    c = trimesh.creation.cone(radius=radius, height=height, sections=sections)
    c.apply_transform(_Z_TO_Y)
    return c


def _chair() -> trimesh.Trimesh:
    seat = trimesh.creation.box(extents=[0.45, 0.05, 0.45])
    seat.apply_translation([0.0, 0.45, 0.0])
    legs = []
    for x, z in [(0.19, 0.19), (-0.19, 0.19), (0.19, -0.19), (-0.19, -0.19)]:
        leg = _y_cylinder(radius=0.02, height=0.45, sections=12)
        leg.apply_translation([x, 0.225, z])
        legs.append(leg)
    back = trimesh.creation.box(extents=[0.45, 0.45, 0.03])
    back.apply_translation([0.0, 0.695, -0.21])
    return trimesh.util.concatenate([seat, *legs, back])


def _table() -> trimesh.Trimesh:
    top = trimesh.creation.box(extents=[1.1, 0.04, 0.65])
    top.apply_translation([0.0, 0.74, 0.0])
    legs = []
    for x, z in [(0.5, 0.28), (-0.5, 0.28), (0.5, -0.28), (-0.5, -0.28)]:
        leg = _y_cylinder(radius=0.025, height=0.72, sections=12)
        leg.apply_translation([x, 0.36, z])
        legs.append(leg)
    return trimesh.util.concatenate([top, *legs])


def _lamp() -> trimesh.Trimesh:
    # base disc — thin flat cylinder (height 0.02 along Y, radius 0.09).
    base = _y_cylinder(radius=0.09, height=0.02, sections=24)
    base.apply_translation([0.0, 0.01, 0.0])
    # thin vertical post from y=0.02 to y=0.52.
    post = _y_cylinder(radius=0.012, height=0.50, sections=12)
    post.apply_translation([0.0, 0.27, 0.0])
    # shade — pointed cone, wide at bottom (y=0.52), apex at top (y=0.72).
    shade = _y_cone(radius=0.13, height=0.20, sections=24)
    shade.apply_translation([0.0, 0.52, 0.0])
    return trimesh.util.concatenate([base, post, shade])


def _bookshelf() -> trimesh.Trimesh:
    h, w, d = 1.20, 0.70, 0.30
    thick = 0.02
    side_l = trimesh.creation.box(extents=[thick, h, d])
    side_l.apply_translation([-w / 2 + thick / 2, h / 2, 0.0])
    side_r = trimesh.creation.box(extents=[thick, h, d])
    side_r.apply_translation([w / 2 - thick / 2, h / 2, 0.0])
    shelves = []
    for y in [0.0, 0.40, 0.80, h - thick]:
        s = trimesh.creation.box(extents=[w - 2 * thick, thick, d])
        s.apply_translation([0.0, y + thick / 2, 0.0])
        shelves.append(s)
    return trimesh.util.concatenate([side_l, side_r, *shelves])


def _mug() -> trimesh.Trimesh:
    body = _y_cylinder(radius=0.04, height=0.09, sections=24)
    body.apply_translation([0.0, 0.045, 0.0])
    # trimesh's torus is already in the XY plane with axis along Z — the
    # correct orientation for a handle on the +X side of a vertical mug, so
    # we only need to translate it outward.
    handle = trimesh.creation.torus(
        major_radius=0.032, minor_radius=0.007,
        major_sections=24, minor_sections=10,
    )
    handle.apply_translation([0.055, 0.045, 0.0])
    return trimesh.util.concatenate([body, handle])


def _book() -> trimesh.Trimesh:
    return trimesh.creation.box(extents=[0.16, 0.025, 0.22])


def _ball() -> trimesh.Trimesh:
    return trimesh.creation.icosphere(subdivisions=3, radius=0.12)


# ---------------------------------------------------------------------------


def _aabb_overlap(a_min, a_max, b_min, b_max):
    """Return (overlap_x, overlap_y, overlap_z). Negative/zero means no overlap on that axis."""
    return (
        min(a_max[0], b_max[0]) - max(a_min[0], b_min[0]),
        min(a_max[1], b_max[1]) - max(a_min[1], b_min[1]),
        min(a_max[2], b_max[2]) - max(a_min[2], b_min[2]),
    )


def resolve_overlap(new_min, new_max, new_center,
                    placed: list[tuple[list[float], list[float]]],
                    margin: float = 0.03) -> tuple[list[float], list[float], list[float]]:
    """Shift a newly-placed object along x/z until its 3D AABB no longer
    overlaps anything already placed. Never shifts along y — an object stays
    on its surface. Best-effort: gives up after 20 iterations."""
    for _ in range(20):
        collided = False
        for e_min, e_max in placed:
            ox, oy, oz = _aabb_overlap(new_min, new_max, e_min, e_max)
            if ox <= 0 or oy <= 0 or oz <= 0:
                continue
            collided = True
            e_cx = (e_min[0] + e_max[0]) / 2
            e_cz = (e_min[2] + e_max[2]) / 2
            # push out along whichever horizontal axis has the smaller overlap
            if ox <= oz:
                sign = 1.0 if new_center[0] >= e_cx else -1.0
                delta = (ox + margin) * sign
                new_min[0] += delta; new_max[0] += delta; new_center[0] += delta
            else:
                sign = 1.0 if new_center[2] >= e_cz else -1.0
                delta = (oz + margin) * sign
                new_min[2] += delta; new_max[2] += delta; new_center[2] += delta
            break
        if not collided:
            return new_min, new_max, new_center
    return new_min, new_max, new_center


def place_on_surface(
    mesh: trimesh.Trimesh,
    xz: tuple[float, float],
    surface_y: float = 0.0,
    touches_floor: bool = True,
) -> tuple[trimesh.Trimesh, list[float], list[float], list[float], list[list[float]]]:
    """Center the mesh at its bbox centroid and lift it so its base rests at
    `surface_y`. Returns (mesh, center, bbox_min, bbox_max, lowest_points).

    `touches_floor=False` zeros the lowest_points list so the object doesn't
    pollute ground-plane estimation (objects sitting on a table are resting
    on the table, not the floor).
    """
    bmin, bmax = mesh.bounds
    centroid = (bmin + bmax) / 2.0
    mesh.apply_translation(-centroid)
    size = bmax - bmin
    half_y = size[1] / 2.0
    world_center = [float(xz[0]), float(surface_y + half_y), float(xz[1])]
    world_min = [float(xz[0]) - size[0] / 2, float(surface_y), float(xz[1]) - size[2] / 2]
    world_max = [float(xz[0]) + size[0] / 2, float(surface_y + size[1]), float(xz[1]) + size[2] / 2]
    if touches_floor:
        lowest = [
            [world_min[0], surface_y, world_min[2]],
            [world_max[0], surface_y, world_min[2]],
            [world_max[0], surface_y, world_max[2]],
            [world_min[0], surface_y, world_max[2]],
        ]
    else:
        lowest = []
    return mesh, world_center, world_min, world_max, lowest


class FakeVLM:
    """Plays the role of Claude Opus 4.7 offline — keyed on class label."""

    TABLE = {
        "chair":     {"mass_kg": 5.2,  "friction": 0.45, "restitution": 0.2,
                      "material": "wood",    "is_rigid": True,
                      "reasoning": "Four-leg wooden dining chair, ~5 kg."},
        "table":     {"mass_kg": 14.0, "friction": 0.5,  "restitution": 0.1,
                      "material": "wood",    "is_rigid": True,
                      "reasoning": "Indoor wooden table, ~14 kg."},
        "lamp":      {"mass_kg": 1.4,  "friction": 0.5,  "restitution": 0.15,
                      "material": "metal",   "is_rigid": True,
                      "reasoning": "Slim floor lamp, cone shade, metal post."},
        "bookshelf": {"mass_kg": 32.0, "friction": 0.55, "restitution": 0.1,
                      "material": "wood",    "is_rigid": True,
                      "reasoning": "Four-shelf particleboard bookshelf."},
        "mug":       {"mass_kg": 0.35, "friction": 0.5,  "restitution": 0.15,
                      "material": "ceramic", "is_rigid": True,
                      "reasoning": "Glazed ceramic mug with handle."},
        "book":      {"mass_kg": 0.8,  "friction": 0.4,  "restitution": 0.1,
                      "material": "paper",   "is_rigid": True,
                      "reasoning": "Hardcover book, ~800 g."},
        "ball":      {"mass_kg": 0.45, "friction": 0.6,  "restitution": 0.75,
                      "material": "rubber",  "is_rigid": True,
                      "reasoning": "Inflated rubber ball, high bounce."},
    }

    def infer(self, class_name: str, image_bytes: bytes) -> dict:
        return self.TABLE.get(class_name, {
            "mass_kg": 1.0, "friction": 0.5, "restitution": 0.2,
            "material": "unknown", "is_rigid": True, "reasoning": "fallback",
        })


# Table top surface (see _table: top box centered at y=0.74 with height 0.04).
TABLE_TOP_Y = 0.76

# (id, class, mesh_origin, builder, xz, crop_rgb, rests_on)
#   rests_on = "floor"  → base at y=0, feeds ground-plane fit
#   rests_on = "table"  → base at y=TABLE_TOP_Y, not a ground-contact object
SPEC = [
    ("table_01",     "table",     "hunyuan3d_2.1", _table,     ( 0.00,  0.00), (130,  80,  40), "floor"),
    ("chair_01",     "chair",     "hunyuan3d_2.1", _chair,     (-0.70,  0.00), (150,  95,  55), "floor"),
    ("bookshelf_01", "bookshelf", "hunyuan3d_2.1", _bookshelf, (-1.40, -0.90), (120,  80,  40), "floor"),
    ("ball_01",      "ball",      "identity",      _ball,      ( 0.90, -0.80), (210,  60,  40), "floor"),
    # small items on the table
    ("mug_01",       "mug",       "triposg_1.5b",  _mug,       ( 0.20,  0.15), (245, 245, 240), "table"),
    ("book_01",      "book",      "sf3d",          _book,      (-0.20, -0.10), ( 60,  85, 190), "table"),
    ("lamp_01",      "lamp",      "triposg_1.5b",  _lamp,      ( 0.40, -0.15), (240, 220, 130), "table"),
]


def build_fake_session(session_dir: Path) -> None:
    """Synthetic Stream 02 output: 7 composite indoor objects on a flat floor."""
    shutil.rmtree(session_dir, ignore_errors=True)
    (session_dir / "meshes").mkdir(parents=True)
    (session_dir / "crops").mkdir()

    objects = []
    placed_aabbs: list[tuple[list[float], list[float]]] = []
    for oid, cls, origin, builder, xz, color, rests_on in SPEC:
        surface_y = 0.0 if rests_on == "floor" else TABLE_TOP_Y
        mesh = builder()
        mesh, center, bmin, bmax, lowest = place_on_surface(
            mesh, xz, surface_y=surface_y, touches_floor=(rests_on == "floor"),
        )
        # Resolve any inter-object overlap by shifting along xz only.
        bmin, bmax, center = resolve_overlap(bmin, bmax, center, placed_aabbs)
        # The lowest_points are axis-aligned corners of the bbox's base —
        # re-derive them from the post-resolution bbox.
        if lowest:
            lowest = [
                [bmin[0], surface_y, bmin[2]],
                [bmax[0], surface_y, bmin[2]],
                [bmax[0], surface_y, bmax[2]],
                [bmin[0], surface_y, bmax[2]],
            ]
        moved = (center[0] != xz[0]) or (center[2] != xz[1])
        if moved:
            print(f"       overlap: {oid} shifted to xz=({center[0]:+.2f}, {center[2]:+.2f})")
        placed_aabbs.append((list(bmin), list(bmax)))
        mesh.export(session_dir / "meshes" / f"{oid}.glb")
        Image.new("RGB", (128, 128), color).save(session_dir / "crops" / f"{oid}.png")
        objects.append({
            "id": oid,
            "class": cls,
            "mesh_path": f"meshes/{oid}.glb",
            "crop_image_path": f"crops/{oid}.png",
            "mesh_origin": origin,
            "center": list(center),
            "rotation_quat": [0.0, 0.0, 0.0, 1.0],
            "bbox_min": list(bmin),
            "bbox_max": list(bmax),
            "lowest_points": lowest,
        })

    with (session_dir / "reconstructed.json").open("w") as fh:
        json.dump({"objects": objects}, fh, indent=2)


def main() -> None:
    session = REPO_ROOT / "data" / "reconstructed" / "demo_mock"
    out     = REPO_ROOT / "data" / "scenes" / "demo_mock"
    shutil.rmtree(out, ignore_errors=True)

    print(f"[1/5] building fake Stream 02 session at {session.relative_to(REPO_ROOT)}")
    build_fake_session(session)

    print("[2/5] running SceneAssembler with mocked VLM (CoACD disabled for speed)")
    cfg = AssemblerConfig(decompose_dynamic=False)
    scene = SceneAssembler(cfg, vlm_client=FakeVLM()).assemble(session, out)

    print("[3/5] exporting glTF + sidecar")
    gltf_res = export_gltf(scene, session_dir=out, out_dir=out)
    print(f"       {gltf_res.scene_glb.relative_to(REPO_ROOT)} "
          f"({gltf_res.scene_glb.stat().st_size:,} bytes)")
    print(f"       {gltf_res.sidecar.relative_to(REPO_ROOT)}")

    print("[4/5] exporting MJCF")
    mjcf = export_mjcf(scene, out)
    print(f"       {mjcf.relative_to(REPO_ROOT)}")

    print("[5/5] exporting MuJoCo .py")
    pyscript = export_mujoco_py(scene, out, steps=500)
    print(f"       {pyscript.relative_to(REPO_ROOT)}")

    print()
    print(f"wrote {len(scene['objects'])} objects and a ground plane")
    print(f"→ open {out.relative_to(REPO_ROOT)}/scene.glb in https://gltf-viewer.donmccurdy.com/")
    print(f"→ inspect {out.relative_to(REPO_ROOT)}/scene.json in any text editor")
    print()
    print("--- scene.json preview ---")
    with (out / "scene.json").open() as fh:
        preview = json.load(fh)
    for obj in preview["objects"]:
        print(f"  {obj['id']:9s}  {obj['class']:6s}  "
              f"mass={obj['physics']['mass_kg']:5.2f}kg  "
              f"μ={obj['physics']['friction']:.2f}  "
              f"e={obj['physics']['restitution']:.2f}  "
              f"{obj['material_class']:8s}  "
              f"via {obj['source']['physics_origin']}")


if __name__ == "__main__":
    main()
