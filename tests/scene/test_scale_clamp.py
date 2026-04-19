"""Tests for class-aware bbox scale clamping."""

from __future__ import annotations

import pytest

from scene.reconstructed import ReconstructedObject
from scene.scale_clamp import SCALE_BOUNDS, clamp_object_scale


def _obj(class_name: str, height: float, cx: float = 0.0, cz: float = 0.0,
         base_y: float = 0.0, width: float = 0.2, depth: float = 0.2) -> ReconstructedObject:
    return ReconstructedObject(
        id=f"{class_name}_t",
        class_name=class_name,
        mesh_path="meshes/x.glb",
        crop_image_path="crops/x.png",
        mesh_origin="identity",
        center=(cx, base_y + height / 2.0, cz),
        rotation_quat=(0.0, 0.0, 0.0, 1.0),
        bbox_min=(cx - width / 2.0, base_y, cz - depth / 2.0),
        bbox_max=(cx + width / 2.0, base_y + height, cz + depth / 2.0),
        lowest_points=[(cx, base_y, cz)],
    )


def test_in_range_passes_through_unchanged():
    obj = _obj("chair", height=0.9)
    res = clamp_object_scale(obj)
    assert res.clamped is False
    assert res.scale == pytest.approx(1.0)
    assert res.obj is obj  # same instance returned


def test_oversize_chair_clamped_to_max():
    obj = _obj("chair", height=3.0)
    res = clamp_object_scale(obj)
    assert res.clamped is True
    max_h = SCALE_BOUNDS["chair"][1]
    assert res.scale == pytest.approx(max_h / 3.0)
    new_h = res.obj.bbox_max[1] - res.obj.bbox_min[1]
    assert new_h == pytest.approx(max_h)


def test_undersize_mug_clamped_to_min():
    obj = _obj("mug", height=0.01)
    res = clamp_object_scale(obj)
    assert res.clamped is True
    min_h = SCALE_BOUNDS["mug"][0]
    new_h = res.obj.bbox_max[1] - res.obj.bbox_min[1]
    assert new_h == pytest.approx(min_h)


def test_pivot_preserves_resting_surface():
    # Mug sitting on a 0.76m table, but observed 3m tall — after clamp
    # its bottom should still be at y=0.76, not drift to the floor.
    obj = _obj("mug", height=3.0, base_y=0.76)
    res = clamp_object_scale(obj)
    assert res.obj.bbox_min[1] == pytest.approx(0.76)
    # lowest_points follow the pivot too
    assert res.obj.lowest_points[0][1] == pytest.approx(0.76)


def test_scaled_lowest_points_shrink_horizontally():
    obj = _obj("chair", height=3.0, width=1.5, depth=1.5)
    res = clamp_object_scale(obj)
    new_w = res.obj.bbox_max[0] - res.obj.bbox_min[0]
    assert new_w == pytest.approx(1.5 * res.scale)


def test_unknown_class_uses_lax_default():
    # A 2m "widget" fits in the default (0.01, 3.0) range — not clamped.
    obj = _obj("widget", height=2.0)
    assert clamp_object_scale(obj).clamped is False
    # A 5m widget does get clamped though.
    big = _obj("widget", height=5.0)
    res = clamp_object_scale(big)
    assert res.clamped is True
    new_h = res.obj.bbox_max[1] - res.obj.bbox_min[1]
    assert new_h == pytest.approx(3.0)
