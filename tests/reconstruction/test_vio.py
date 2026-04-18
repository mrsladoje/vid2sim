"""VIO tests (single-keyframe fallback + identity)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from reconstruction.vio import (
    WorldPose,
    iter_pose_frames,
    single_keyframe_pose,
    try_rtabmap_vio,
    world_pose,
)


def _write_pose(cap: Path, frame: int, trans, quat) -> None:
    frames = cap / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    (frames / f"{frame:05d}.pose.json").write_text(
        json.dumps({"translation": list(trans), "rotation_quat": list(quat)})
    )


def test_try_rtabmap_vio_stub_returns_none(tmp_path: Path) -> None:
    assert try_rtabmap_vio(tmp_path) is None


def test_single_keyframe_reads_pose_json(tmp_path: Path) -> None:
    _write_pose(tmp_path, 0, [1.0, 2.0, 3.0], [0.0, 0.0, 0.0, 1.0])
    wp = single_keyframe_pose(tmp_path, frame=0)
    assert wp.pose_origin == "single_keyframe"
    assert wp.keyframes[0].translation == (1.0, 2.0, 3.0)


def test_single_keyframe_identity_when_missing(tmp_path: Path) -> None:
    wp = single_keyframe_pose(tmp_path, frame=0)
    assert wp.pose_origin == "identity"
    assert wp.keyframes[0].translation == (0.0, 0.0, 0.0)


def test_world_pose_prefers_vio_then_falls_back(tmp_path: Path) -> None:
    _write_pose(tmp_path, 0, [0.5, 0.5, 0.5], [0.0, 0.0, 0.0, 1.0])
    wp = world_pose(tmp_path, prefer_vio=True)
    assert wp.pose_origin == "single_keyframe"


def test_world_pose_to_json_shape(tmp_path: Path) -> None:
    _write_pose(tmp_path, 5, [0, 0, 0], [0, 0, 0, 1])
    wp = single_keyframe_pose(tmp_path, frame=5)
    j = wp.to_json()
    assert j["pose_origin"] == "single_keyframe"
    assert j["origin_keyframe"] == 5
    assert j["up_axis"] == "y" and j["unit"] == "meters"
    assert j["keyframes"][0]["frame"] == 5


def test_world_from_cam_returns_4x4(tmp_path: Path) -> None:
    _write_pose(tmp_path, 0, [1, 0, 0], [0, 0, 0, 1])
    wp = single_keyframe_pose(tmp_path, frame=0)
    m = wp.world_from_cam(0)
    assert m.shape == (4, 4)
    np.testing.assert_allclose(m[:3, 3], [1, 0, 0])


def test_world_from_cam_missing_raises(tmp_path: Path) -> None:
    wp = single_keyframe_pose(tmp_path, frame=0)
    with pytest.raises(KeyError):
        wp.world_from_cam(99)


def test_iter_pose_frames_skips_missing(tmp_path: Path) -> None:
    _write_pose(tmp_path, 0, [0, 0, 0], [0, 0, 0, 1])
    _write_pose(tmp_path, 2, [1, 0, 0], [0, 0, 0, 1])
    frames = iter_pose_frames(tmp_path, [0, 1, 2, 3])
    assert [k.frame for k in frames] == [0, 2]
