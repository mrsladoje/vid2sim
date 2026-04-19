"""Class-aware scale clamping.

When Stream 02's reconstruction produces a wrong-scale observation (e.g.
monocular depth drift making a chair 3 m tall), the bbox in
`reconstructed.json` lies. This module checks the observed bbox height
against a per-class prior range and, if outside, rescales the object
uniformly about the bottom-center of its bbox so it lands in range while
staying on whatever surface Stream 02 saw it on.

Used by the assembler as a belt-and-suspenders safety net — the primary
defense is metric-depth capture + bbox-aware mesh fitting in Stream 02.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import NamedTuple

from .reconstructed import ReconstructedObject

logger = logging.getLogger(__name__)


# (min_height_m, max_height_m) — conservative ranges for indoor furniture.
# Tuned to catch catastrophic scale errors, not reject unusual-but-real sizes.
SCALE_BOUNDS: dict[str, tuple[float, float]] = {
    "chair":     (0.50, 1.30),
    "table":     (0.40, 1.20),
    "sofa":      (0.60, 1.20),
    "bed":       (0.30, 1.20),
    "bookshelf": (0.50, 2.50),
    "lamp":      (0.20, 2.00),
    "plant":     (0.10, 2.50),
    "book":      (0.01, 0.35),
    "mug":       (0.06, 0.15),
    "cup":       (0.05, 0.15),
    "bottle":    (0.10, 0.40),
    "ball":      (0.02, 0.30),
    "laptop":    (0.01, 0.06),
    "apple":     (0.04, 0.12),
    "orange":    (0.05, 0.12),
}

# Lax fallback for unknown classes — catches order-of-magnitude errors only.
DEFAULT_BOUNDS: tuple[float, float] = (0.01, 3.0)


class ClampResult(NamedTuple):
    obj: ReconstructedObject
    scale: float        # uniform multiplier applied (1.0 = unchanged)
    clamped: bool       # True if the object was modified


def bounds_for(class_name: str) -> tuple[float, float]:
    return SCALE_BOUNDS.get(class_name, DEFAULT_BOUNDS)


def clamp_object_scale(obj: ReconstructedObject) -> ClampResult:
    """Return a version of `obj` with bbox height inside its class range.

    Pivots around the bottom-center of the bbox so the object's resting
    surface is preserved. Also scales `lowest_points` consistently.
    """
    lo, hi = bounds_for(obj.class_name)
    height = obj.bbox_max[1] - obj.bbox_min[1]
    if lo <= height <= hi:
        return ClampResult(obj, 1.0, False)

    target = lo if height < lo else hi
    k = target / max(height, 1e-9)

    pivot = (obj.center[0], obj.bbox_min[1], obj.center[2])

    def _scaled(p):
        return tuple(pivot[i] + (p[i] - pivot[i]) * k for i in range(3))

    new_min = _scaled(obj.bbox_min)
    new_max = _scaled(obj.bbox_max)
    new_center = tuple((new_min[i] + new_max[i]) / 2.0 for i in range(3))
    new_lowest = [_scaled(p) for p in obj.lowest_points]

    logger.warning(
        "scale_clamp: %s (class=%s) observed height %.3fm outside [%.2f, %.2f] — rescaled by %.3f",
        obj.id, obj.class_name, height, lo, hi, k,
    )

    clamped = dataclasses.replace(
        obj,
        center=new_center,
        bbox_min=new_min,
        bbox_max=new_max,
        lowest_points=new_lowest,
    )
    return ClampResult(clamped, k, True)
