"""TDD tests for RANSAC stereo/DA3 depth fusion (ADR-002)."""

from __future__ import annotations

import numpy as np
import pytest

from reconstruction.fusion import FusionConfig, fuse_depth


def _flat_depth(h: int, w: int, value: float) -> np.ndarray:
    return np.full((h, w), value, dtype=np.float32)


def test_perfect_affine_recovers_params() -> None:
    # stereo = 1.2 · DA3 + 0.3 exactly, everywhere confident.
    h, w = 32, 32
    rng = np.random.default_rng(0)
    da3 = rng.uniform(0.5, 5.0, size=(h, w)).astype(np.float32)
    stereo = 1.2 * da3 + 0.3

    result = fuse_depth(stereo, da3)

    assert result.s == pytest.approx(1.2, abs=1e-3)
    assert result.t == pytest.approx(0.3, abs=1e-3)
    # fused should equal stereo where stereo is valid.
    np.testing.assert_allclose(result.fused, stereo, atol=1e-4)


def test_ransac_fills_stereo_holes_with_aligned_da3() -> None:
    h, w = 40, 40
    rng = np.random.default_rng(1)
    da3 = rng.uniform(1.0, 3.0, size=(h, w)).astype(np.float32)
    truth = 0.9 * da3 + 0.1

    stereo = truth.copy()
    # punch a hole in 40% of pixels (stereo misses).
    hole = rng.random(size=(h, w)) < 0.4
    stereo[hole] = 0.0

    result = fuse_depth(stereo, da3)

    # stereo kept where valid
    np.testing.assert_allclose(result.fused[~hole], stereo[~hole], atol=1e-3)
    # holes filled by aligned DA3, which should track truth closely.
    fill_err = np.abs(result.fused[hole] - truth[hole])
    assert fill_err.max() < 0.02
    assert result.s == pytest.approx(0.9, abs=1e-2)
    assert result.t == pytest.approx(0.1, abs=1e-2)


def test_ransac_is_robust_to_outliers() -> None:
    h, w = 48, 48
    rng = np.random.default_rng(2)
    da3 = rng.uniform(1.0, 4.0, size=(h, w)).astype(np.float32)
    stereo = (1.1 * da3 + 0.2).astype(np.float32)

    # Corrupt 30% of stereo pixels with absurd outliers (multi-metre)
    outlier = rng.random(size=(h, w)) < 0.30
    stereo[outlier] += rng.uniform(2.0, 5.0, size=outlier.sum()).astype(np.float32)

    cfg = FusionConfig(ransac_iterations=512, ransac_inlier_tol=0.05)
    result = fuse_depth(stereo, da3, cfg=cfg)

    assert result.s == pytest.approx(1.1, abs=0.05)
    assert result.t == pytest.approx(0.2, abs=0.10)
    assert result.inliers > 0.5 * h * w  # most pixels still inliers


def test_low_confidence_pixels_excluded_from_fit() -> None:
    h, w = 32, 32
    rng = np.random.default_rng(3)
    da3 = rng.uniform(1.0, 2.5, size=(h, w)).astype(np.float32)
    # Pixels with conf 0 contain garbage stereo; pixels with conf 255 are clean.
    clean = 1.3 * da3 + 0.05
    stereo = clean.copy()
    conf = np.full((h, w), 255, dtype=np.uint8)

    # Lace 40% with low-confidence pixels holding random garbage.
    low = rng.random(size=(h, w)) < 0.4
    stereo[low] = rng.uniform(0.1, 10.0, size=low.sum()).astype(np.float32)
    conf[low] = 20  # below 0.5 threshold

    result = fuse_depth(stereo, da3, conf=conf)

    assert result.s == pytest.approx(1.3, abs=1e-2)
    assert result.t == pytest.approx(0.05, abs=2e-2)


def test_graceful_fallback_when_stereo_is_empty() -> None:
    h, w = 8, 8
    da3 = np.full((h, w), 2.0, dtype=np.float32)
    stereo = np.zeros_like(da3)

    result = fuse_depth(stereo, da3)

    # No solvable points — identity (s=1, t=0) plus DA3 used as fill.
    assert result.inliers == 0
    assert result.s == pytest.approx(1.0)
    assert result.t == pytest.approx(0.0)
    np.testing.assert_allclose(result.fused, da3)


def test_shape_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        fuse_depth(_flat_depth(4, 4, 1.0), _flat_depth(4, 5, 1.0))


def test_float_confidence_input_works() -> None:
    h, w = 24, 24
    rng = np.random.default_rng(4)
    da3 = rng.uniform(1.0, 3.0, size=(h, w)).astype(np.float32)
    stereo = 1.05 * da3
    # float conf 0..1
    conf = np.ones((h, w), dtype=np.float32)

    result = fuse_depth(stereo, da3, conf=conf)
    assert result.s == pytest.approx(1.05, abs=1e-3)
    assert result.t == pytest.approx(0.0, abs=1e-3)


def test_result_preserves_num_stereo_valid_count() -> None:
    h, w = 16, 16
    stereo = np.ones((h, w), dtype=np.float32)
    stereo[:4, :] = 0.0  # 64 invalid pixels
    da3 = np.ones_like(stereo)
    result = fuse_depth(stereo, da3)
    assert result.num_stereo_valid == (h * w) - 4 * w


def test_config_seed_makes_ransac_deterministic() -> None:
    h, w = 32, 32
    rng = np.random.default_rng(5)
    da3 = rng.uniform(1.0, 3.0, size=(h, w)).astype(np.float32)
    stereo = 0.8 * da3 + 0.4
    outlier = rng.random(size=(h, w)) < 0.2
    stereo[outlier] += 3.0

    r1 = fuse_depth(stereo, da3, cfg=FusionConfig(rng_seed=42))
    r2 = fuse_depth(stereo, da3, cfg=FusionConfig(rng_seed=42))
    assert r1.s == r2.s
    assert r1.t == r2.t
    assert r1.inliers == r2.inliers


def test_degenerate_da3_gap_doesnt_crash() -> None:
    # All DA3 pixels identical — RANSAC can never pick two distinct points.
    da3 = np.full((16, 16), 2.0, dtype=np.float32)
    stereo = np.full((16, 16), 2.5, dtype=np.float32)
    result = fuse_depth(stereo, da3)
    # Falls back through lsq or stays at identity; fused must still return
    # a finite array matching stereo where stereo is valid.
    assert np.all(np.isfinite(result.fused))
    assert result.fused[0, 0] == pytest.approx(2.5, abs=1e-3)
