"""Edge-case tests to pin the remaining branches in fusion.py and
icp_align.py — lifts coverage to 100% on both."""

from __future__ import annotations

import numpy as np

from reconstruction.fusion import _lsq_refit
from reconstruction.icp_align import _best_similarity


def test_lsq_refit_returns_identity_when_mask_too_small() -> None:
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([2.0, 4.0, 6.0])
    # Only one inlier — below the 2-point minimum, so we degrade to identity.
    mask = np.array([True, False, False])
    s, t = _lsq_refit(x, y, mask)
    assert s == 1.0 and t == 0.0


def test_best_similarity_handles_reflection_determinant() -> None:
    # Construct a src/dst pair whose best-fit rotation has det < 0 before
    # the sign flip — exercises the s_sign[-1] = -1 branch.
    src = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [-1.0, 0.0, 0.0],
    ])
    # Dst is the reflection through x axis — requires a sign flip to
    # stay a proper rotation.
    dst = src.copy()
    dst[:, 0] *= -1
    s, r, t = _best_similarity(src, dst)
    # The solver should return a proper rotation (det +1) after the flip.
    assert np.linalg.det(r) > 0.9
    assert np.isfinite(s)
    assert t.shape == (3,)
