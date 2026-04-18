"""Visual-inertial odometry — host-side pose recovery.

Two paths:

1. **RTAB-Map VIO** via the DepthAI v3 host-node example. Marked
   *early-access preview* at the time of writing; requires `depthai-core`
   develop branch on the laptop. If it converges, we get per-keyframe
   6-DoF poses in a metric world frame.

2. **Single-keyframe fallback.** Use the first frame with any valid
   on-device pose as the world-frame origin; treat every subsequent
   observation as being in the same frame. The pitch becomes "single-
   shot" instead of "multi-view" — see PRD §13 risks.

We implement (2) in full (it is the pitch-safe path) and expose a
`try_rtabmap_vio` stub that returns `None` so callers always have a
deterministic entry point.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from .backproject import pose_from_pose_json

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Keyframe:
    frame: int
    translation: tuple[float, float, float]
    rotation_quat: tuple[float, float, float, float]


@dataclass(frozen=True)
class WorldPose:
    origin_keyframe: int
    pose_origin: str  # "rtabmap_vio" | "single_keyframe" | "identity"
    keyframes: list[Keyframe] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "up_axis": "y",
            "unit": "meters",
            "origin_keyframe": self.origin_keyframe,
            "pose_origin": self.pose_origin,
            "keyframes": [
                {"frame": k.frame, "translation": list(k.translation),
                 "rotation_quat": list(k.rotation_quat)}
                for k in self.keyframes
            ],
        }

    def world_from_cam(self, frame_idx: int) -> np.ndarray:
        for k in self.keyframes:
            if k.frame == frame_idx:
                return pose_from_pose_json({
                    "translation": list(k.translation),
                    "rotation_quat": list(k.rotation_quat),
                })
        raise KeyError(f"frame {frame_idx} has no world pose")


def try_rtabmap_vio(capture_dir: Path) -> WorldPose | None:
    """Attempt to run the DepthAI v3 RTAB-Map host-node integration.

    On real hardware this would call into the `depthai-core` develop
    branch's VSLAM example. We cannot run it in tests / CI, so the stub
    returns None and callers fall back. Wired here so the rest of the
    code has a single, honest entry point.
    """
    _ = capture_dir
    logger.info("RTAB-Map VIO stub: returning None; will use single-keyframe fallback")
    return None


def single_keyframe_pose(capture_dir: Path, frame: int = 0) -> WorldPose:
    """Build a WorldPose from the on-device pose of a single keyframe.

    Reads `frames/XXXXX.pose.json` from the bundle. If it's missing,
    falls back to identity.
    """
    pose_path = capture_dir / "frames" / f"{frame:05d}.pose.json"
    if pose_path.exists():
        data = json.loads(pose_path.read_text())
        kf = Keyframe(
            frame=frame,
            translation=tuple(data.get("translation", [0.0, 0.0, 0.0])),
            rotation_quat=tuple(data.get("rotation_quat", [0.0, 0.0, 0.0, 1.0])),
        )
        return WorldPose(
            origin_keyframe=frame,
            pose_origin="single_keyframe",
            keyframes=[kf],
        )
    logger.warning("no pose.json for frame %d in %s; using identity",
                   frame, capture_dir)
    return WorldPose(
        origin_keyframe=frame,
        pose_origin="identity",
        keyframes=[Keyframe(frame=frame,
                            translation=(0.0, 0.0, 0.0),
                            rotation_quat=(0.0, 0.0, 0.0, 1.0))],
    )


def world_pose(capture_dir: Path, prefer_vio: bool = True) -> WorldPose:
    """Top-level pose recovery; tries VIO, falls back to single-keyframe.

    Callers should write the returned WorldPose to `world_pose.json` in
    the reconstructed session dir to satisfy `spec/reconstructed_object.md`.
    """
    if prefer_vio:
        vio = try_rtabmap_vio(capture_dir)
        if vio is not None:
            return vio
    return single_keyframe_pose(capture_dir)


def iter_pose_frames(capture_dir: Path, frames: Iterable[int]) -> list[Keyframe]:
    """Utility: load pose.json for a subset of frames."""
    out: list[Keyframe] = []
    for f in frames:
        p = capture_dir / "frames" / f"{f:05d}.pose.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        out.append(Keyframe(
            frame=f,
            translation=tuple(d.get("translation", [0.0, 0.0, 0.0])),
            rotation_quat=tuple(d.get("rotation_quat", [0.0, 0.0, 0.0, 1.0])),
        ))
    return out
