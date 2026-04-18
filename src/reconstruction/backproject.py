"""Depth → point cloud back-projection.

Pinhole camera model. Given metric depth, intrinsics K, an optional
boolean mask, and an optional world-from-camera pose, project the
selected pixels into world-frame 3D points.

Camera convention (OpenCV):
    X → right   Y → down   Z → forward
World convention (VID2SIM, see `spec/scene.schema.json`):
    Y up, metres. Translation conversion is handled by the caller's pose.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Array = np.ndarray


@dataclass(frozen=True)
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float

    @classmethod
    def from_matrix(cls, k: Array) -> "Intrinsics":
        k = np.asarray(k, dtype=np.float64)
        if k.shape != (3, 3):
            raise ValueError(f"intrinsics matrix must be 3x3, got {k.shape}")
        return cls(fx=float(k[0, 0]), fy=float(k[1, 1]),
                   cx=float(k[0, 2]), cy=float(k[1, 2]))


def _as_pose(pose: Array | None) -> Array:
    if pose is None:
        return np.eye(4, dtype=np.float64)
    pose = np.asarray(pose, dtype=np.float64)
    if pose.shape != (4, 4):
        raise ValueError(f"pose must be 4x4, got {pose.shape}")
    return pose


def backproject(
    depth: Array,
    intrinsics: Intrinsics,
    mask: Array | None = None,
    pose_world_from_cam: Array | None = None,
    min_depth: float = 1e-3,
    max_depth: float = 20.0,
) -> Array:
    """Back-project depth into world-frame (N,3) points.

    Parameters
    ----------
    depth : (H,W) float array in metres. Zero / non-finite / out-of-range
        values are dropped.
    intrinsics : Intrinsics
    mask : optional (H,W) bool or {0,1}-valued uint8. Pixels where the
        mask is falsy are dropped.
    pose_world_from_cam : 4x4 matrix. Identity by default.
    min_depth, max_depth : clamping range (metres).
    """
    depth = np.asarray(depth, dtype=np.float32)
    if depth.ndim != 2:
        raise ValueError(f"depth must be 2-D, got shape {depth.shape}")
    h, w = depth.shape

    if mask is not None:
        mask = np.asarray(mask).astype(bool)
        if mask.shape != depth.shape:
            raise ValueError(
                f"mask shape {mask.shape} does not match depth {depth.shape}"
            )
    else:
        mask = np.ones_like(depth, dtype=bool)

    finite = np.isfinite(depth)
    valid = mask & finite & (depth >= min_depth) & (depth <= max_depth)
    if not valid.any():
        return np.empty((0, 3), dtype=np.float32)

    vs, us = np.nonzero(valid)
    z = depth[vs, us].astype(np.float64)
    x = (us.astype(np.float64) - intrinsics.cx) * z / intrinsics.fx
    y = (vs.astype(np.float64) - intrinsics.cy) * z / intrinsics.fy

    pts_cam = np.stack([x, y, z, np.ones_like(z)], axis=1)  # (N,4)
    pose = _as_pose(pose_world_from_cam)
    pts_world = pts_cam @ pose.T
    return pts_world[:, :3].astype(np.float32)


def load_intrinsics(intr_json: dict) -> Intrinsics:
    """Parse `intrinsics.json` from a PerceptionFrame bundle."""
    if "camera_matrix" not in intr_json:
        raise KeyError("intrinsics.json missing camera_matrix")
    return Intrinsics.from_matrix(np.asarray(intr_json["camera_matrix"]))


def quat_to_matrix(quat: tuple[float, float, float, float]) -> Array:
    """Scalar-last quaternion (x,y,z,w) → 3x3 rotation matrix."""
    qx, qy, qz, qw = [float(v) for v in quat]
    n = np.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if n < 1e-9:
        return np.eye(3, dtype=np.float64)
    qx, qy, qz, qw = qx / n, qy / n, qz / n, qw / n
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
    ], dtype=np.float64)


def pose_from_pose_json(pose_json: dict) -> Array:
    """Convert `XXXXX.pose.json` (translation + rotation_quat) to 4x4."""
    t = np.asarray(pose_json["translation"], dtype=np.float64)
    r = quat_to_matrix(tuple(pose_json["rotation_quat"]))  # type: ignore[arg-type]
    m = np.eye(4, dtype=np.float64)
    m[:3, :3] = r
    m[:3, 3] = t
    return m
