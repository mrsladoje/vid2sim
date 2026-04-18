from __future__ import annotations

from scene.ground import estimate_ground
from scene.reconstructed import ReconstructedObject


def _obj(low_y: float) -> ReconstructedObject:
    return ReconstructedObject(
        id="x", class_name="book", mesh_path="x.glb", crop_image_path="x.png",
        mesh_origin="identity", center=(0, 0, 0), rotation_quat=(0, 0, 0, 1),
        bbox_min=(-0.1, low_y, -0.1), bbox_max=(0.1, low_y + 0.2, 0.1),
        lowest_points=[(0, low_y, 0), (0.1, low_y, 0.1), (-0.1, low_y, 0.1), (0, low_y, -0.1)],
    )


def test_ground_normal_is_up_axis_for_flat_floor():
    objs = [_obj(0.0), _obj(0.01), _obj(-0.005)]
    est = estimate_ground(objs, up_axis="y")
    assert est.normal[1] > 0.9  # essentially pointing up


def test_ground_falls_back_without_points():
    objs = [_obj(0.3)]
    # strip points so we hit the fallback branch
    objs = [
        ReconstructedObject(
            id=o.id, class_name=o.class_name, mesh_path=o.mesh_path,
            crop_image_path=o.crop_image_path, mesh_origin=o.mesh_origin,
            center=o.center, rotation_quat=o.rotation_quat,
            bbox_min=o.bbox_min, bbox_max=o.bbox_max, lowest_points=[],
        )
        for o in objs
    ]
    est = estimate_ground(objs, up_axis="y")
    assert est.normal == (0.0, 1.0, 0.0)
    assert est.offset == 0.3


def test_ground_default_material():
    est = estimate_ground([], up_axis="y")
    block = est.to_scene_block()
    assert block["type"] == "plane"
    assert 0.0 <= block["material"]["restitution"] <= 1.0
