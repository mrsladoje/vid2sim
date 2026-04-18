"""Ground plane estimator.

Fits a plane to the lowest 10% of reconstructed points across all objects.
Emits the `ground` block of `scene.json`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .reconstructed import ReconstructedObject


@dataclass(frozen=True)
class GroundEstimate:
    normal: tuple[float, float, float]
    offset: float  # plane eq: n · p = offset
    friction: float = 0.8
    restitution: float = 0.1

    def to_scene_block(self) -> dict:
        return {
            "type": "plane",
            "normal": list(self.normal),
            "material": {"friction": self.friction, "restitution": self.restitution},
        }


def estimate_ground(
    objects: list[ReconstructedObject],
    up_axis: str = "y",
    percentile: float = 10.0,
) -> GroundEstimate:
    """Fit a plane to the lowest-quantile points across all objects.

    If there are too few points we fall back to a flat plane at the minimum
    up-axis coordinate across object bboxes — always safe for the demo.
    """
    up_idx = {"x": 0, "y": 1, "z": 2}[up_axis]
    normal = [0.0, 0.0, 0.0]
    normal[up_idx] = 1.0

    points = np.array(
        [p for obj in objects for p in obj.lowest_points], dtype=np.float64
    )
    if points.shape[0] >= 4:
        threshold = np.percentile(points[:, up_idx], percentile)
        floor_points = points[points[:, up_idx] <= threshold]
        centroid = floor_points.mean(axis=0)
        centered = floor_points - centroid
        # svd for plane normal — smallest singular vector
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        fitted_normal = vh[-1]
        # snap toward up-axis if we got a near-horizontal plane
        if abs(fitted_normal[up_idx]) < 0.5:
            fitted_normal = np.array(normal)
        if fitted_normal[up_idx] < 0:
            fitted_normal = -fitted_normal
        normal = [float(x) for x in fitted_normal]
        offset = float(np.dot(fitted_normal, centroid))
        return GroundEstimate(normal=tuple(normal), offset=offset)

    mins = np.array(
        [obj.bbox_min for obj in objects], dtype=np.float64
    ) if objects else np.zeros((1, 3))
    offset = float(mins[:, up_idx].min()) if objects else 0.0
    return GroundEstimate(normal=tuple(normal), offset=offset)
