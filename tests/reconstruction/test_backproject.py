"""Back-projection tests (pinhole → world frame)."""

from __future__ import annotations

import numpy as np
import pytest

from reconstruction.backproject import (
    Intrinsics,
    backproject,
    load_intrinsics,
    pose_from_pose_json,
    quat_to_matrix,
)


def test_principal_point_maps_to_optical_axis() -> None:
    intr = Intrinsics(fx=800, fy=800, cx=10, cy=10)
    depth = np.zeros((21, 21), dtype=np.float32)
    depth[10, 10] = 1.5  # only the principal pixel has depth

    pts = backproject(depth, intr)

    assert pts.shape == (1, 3)
    np.testing.assert_allclose(pts[0], [0.0, 0.0, 1.5], atol=1e-6)


def test_unit_depth_forward_translation() -> None:
    intr = Intrinsics(fx=100, fy=100, cx=50, cy=50)
    depth = np.full((101, 101), 2.0, dtype=np.float32)
    pose = np.eye(4)
    pose[:3, 3] = [5.0, 0.0, 0.0]

    pts = backproject(depth, intr, pose_world_from_cam=pose)

    # Every point should have been shifted +5 in X.
    assert pts[:, 0].min() > 3.0
    assert pts[:, 0].max() < 7.0  # only a narrow pyramid at z=2


def test_mask_filters_points() -> None:
    intr = Intrinsics(fx=50, fy=50, cx=25, cy=25)
    depth = np.full((51, 51), 1.0, dtype=np.float32)
    mask = np.zeros_like(depth, dtype=bool)
    mask[25, 25] = True

    pts = backproject(depth, intr, mask=mask)

    assert pts.shape == (1, 3)
    np.testing.assert_allclose(pts[0], [0.0, 0.0, 1.0], atol=1e-6)


def test_invalid_depths_are_dropped() -> None:
    intr = Intrinsics(fx=50, fy=50, cx=1, cy=1)
    depth = np.array([[0.0, 1.0, np.inf], [np.nan, 2.0, -1.0]], dtype=np.float32)

    pts = backproject(depth, intr)

    # Two valid depths (1.0 at (0,1), 2.0 at (1,1))
    assert pts.shape == (2, 3)


def test_depth_out_of_clip_range_is_dropped() -> None:
    intr = Intrinsics(fx=50, fy=50, cx=1, cy=1)
    depth = np.array([[0.0005, 100.0], [0.5, 1.5]], dtype=np.float32)

    pts = backproject(depth, intr, min_depth=0.01, max_depth=10.0)

    assert pts.shape == (2, 3)
    assert np.all(pts[:, 2] >= 0.01)
    assert np.all(pts[:, 2] <= 10.0)


def test_shape_mismatch_mask_raises() -> None:
    intr = Intrinsics(fx=1, fy=1, cx=0, cy=0)
    depth = np.ones((4, 4), dtype=np.float32)
    mask = np.ones((5, 5), dtype=bool)
    with pytest.raises(ValueError):
        backproject(depth, intr, mask=mask)


def test_pose_rotation_about_y_axis() -> None:
    # 90° yaw: (1,0,0) in camera → (0,0,-1) in world.
    intr = Intrinsics(fx=100, fy=100, cx=50, cy=50)
    depth = np.zeros((101, 101), dtype=np.float32)
    depth[50, 150 if False else 60] = 1.0  # pixel slightly to the right → +x

    # But depth shape is 101x101, cant go to 60 if cx=50 — adjust:
    depth2 = np.zeros((101, 101), dtype=np.float32)
    depth2[50, 60] = 1.0
    # camera point is (x=(60-50)/100 * 1 = 0.1, y=0, z=1)
    # 90° rotation about +Y: x→-z, z→+x ⇒ (0.1,0,1) → (1, 0, -0.1)
    pose = np.eye(4)
    # Build a 90° yaw (positive rotation about +Y axis in right-handed
    # frame). The matrix used below rotates the camera frame such that
    # the camera's +X ends up along world -Z. We just verify direction
    # (sign) — the absolute value depends on convention.
    c, s = 0.0, 1.0  # cos(90°)=0, sin(90°)=1
    pose[:3, :3] = np.array([
        [c, 0, s],
        [0, 1, 0],
        [-s, 0, c],
    ])
    pts = backproject(depth2, intr, pose_world_from_cam=pose)
    # Forward (+Z) in camera is now +X in world.
    assert pts[0, 0] == pytest.approx(1.0, abs=1e-6)


def test_empty_returns_empty() -> None:
    intr = Intrinsics(fx=1, fy=1, cx=0, cy=0)
    depth = np.zeros((4, 4), dtype=np.float32)
    pts = backproject(depth, intr)
    assert pts.shape == (0, 3)


def test_intrinsics_from_matrix_roundtrip() -> None:
    intr = Intrinsics.from_matrix(np.array([[800, 0, 960], [0, 800, 540], [0, 0, 1]]))
    assert intr.fx == 800 and intr.fy == 800
    assert intr.cx == 960 and intr.cy == 540


def test_intrinsics_from_matrix_rejects_bad_shape() -> None:
    with pytest.raises(ValueError):
        Intrinsics.from_matrix(np.zeros((2, 3)))


def test_load_intrinsics_json_contract() -> None:
    intr = load_intrinsics({
        "camera_matrix": [[800, 0, 960], [0, 800, 540], [0, 0, 1]],
        "resolution": [1920, 1080],
        "baseline_m": 0.075,
    })
    assert intr.cx == 960

    with pytest.raises(KeyError):
        load_intrinsics({"resolution": [1920, 1080]})


def test_quat_identity() -> None:
    r = quat_to_matrix((0.0, 0.0, 0.0, 1.0))
    np.testing.assert_allclose(r, np.eye(3), atol=1e-9)


def test_quat_to_matrix_normalises() -> None:
    # Non-unit quaternion should still produce a rotation (normalised).
    r = quat_to_matrix((0.0, 0.0, 0.0, 2.0))
    np.testing.assert_allclose(r, np.eye(3), atol=1e-9)


def test_pose_from_pose_json_roundtrip() -> None:
    m = pose_from_pose_json({"translation": [1.0, 2.0, 3.0],
                             "rotation_quat": [0.0, 0.0, 0.0, 1.0]})
    assert m.shape == (4, 4)
    np.testing.assert_allclose(m[:3, 3], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(m[:3, :3], np.eye(3), atol=1e-9)
