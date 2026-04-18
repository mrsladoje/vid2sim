"""ICP similarity alignment tests."""

from __future__ import annotations

import numpy as np
import pytest

from reconstruction.icp_align import (
    AlignConfig,
    align,
    apply_similarity,
    _best_similarity,
    _yaw_matrix,
)


def _unit_cube_vertices(n_per_side: int = 10) -> np.ndarray:
    # Dense point cloud of a unit cube surface (deterministic seed for testability).
    rng = np.random.default_rng(0)
    pts = rng.uniform(-0.5, 0.5, size=(n_per_side ** 3, 3))
    return pts.astype(np.float64)


def _apply_sim(pts: np.ndarray, scale: float, r: np.ndarray, t: np.ndarray) -> np.ndarray:
    return (scale * pts @ r.T) + t


def test_umeyama_recovers_known_similarity() -> None:
    # Hand-picked (s, R, t); verify closed-form solver finds them.
    rng = np.random.default_rng(1)
    src = rng.uniform(-1, 1, size=(200, 3))
    r = _yaw_matrix(30.0)
    s, t = 2.5, np.array([0.3, -0.2, 1.5])
    dst = _apply_sim(src, s, r, t)

    rec_s, rec_r, rec_t = _best_similarity(src, dst)
    assert rec_s == pytest.approx(s, rel=1e-5)
    np.testing.assert_allclose(rec_r, r, atol=1e-5)
    np.testing.assert_allclose(rec_t, t, atol=1e-5)


def test_align_recovers_simple_scale_and_translation() -> None:
    unit = _unit_cube_vertices(10)
    scale_truth = 0.8
    t_truth = np.array([1.0, 0.3, 2.5])
    observed = _apply_sim(unit, scale_truth, np.eye(3), t_truth)

    out = align(unit, observed, cfg=AlignConfig(max_iterations=30))

    assert out.scale == pytest.approx(scale_truth, rel=5e-2)
    np.testing.assert_allclose(out.translation, t_truth, atol=0.05)
    assert out.residual < 0.05


def test_align_recovers_90_degree_azimuth() -> None:
    unit = _unit_cube_vertices(10)
    # Build an asymmetric point cloud by stretching one axis so yaw matters.
    unit_asym = unit * np.array([1.0, 1.0, 0.3])
    r_truth = _yaw_matrix(90.0)
    t_truth = np.array([0.0, 0.0, 0.0])
    observed = _apply_sim(unit_asym, 1.0, r_truth, t_truth)

    out = align(unit_asym, observed, cfg=AlignConfig(max_iterations=40))

    # Seed azimuth sweep must land at 90° (mod tolerance).
    assert out.residual < 0.1
    # Rotation matrix should match yaw(90) within tolerance.
    rec_r = out.rotation
    # Compare R·(1,0,0)ᵀ ≈ (0,0,-1)
    mapped = rec_r @ np.array([1.0, 0.0, 0.0])
    np.testing.assert_allclose(mapped, [0.0, 0.0, -1.0], atol=0.1)


def test_align_empty_inputs_returns_identity() -> None:
    out = align(np.empty((0, 3)), np.empty((0, 3)))
    assert out.residual == float("inf")
    assert out.scale == 1.0
    assert out.iterations == 0
    np.testing.assert_allclose(out.rotation, np.eye(3))


def test_apply_similarity_roundtrips() -> None:
    unit = _unit_cube_vertices(6)
    # Use an axis-aligned (0° azimuth) ground truth so the seed grid
    # covers it without ambiguity. 45° is inherently ambiguous against
    # a cube under an azimuth-only search (the plan explicitly
    # constrains us to 0/90/180/270 seeds — per ADR-style failure mode
    # on symmetric objects).
    r = _yaw_matrix(0.0)
    observed = _apply_sim(unit, 1.3, r, np.array([0.5, 0, 1.0]))
    out = align(unit, observed, cfg=AlignConfig(max_iterations=60))
    recovered = apply_similarity(unit, out)
    err = np.linalg.norm(recovered - observed, axis=1).mean()
    assert err < 0.1


def test_align_subsamples_large_clouds() -> None:
    unit = _unit_cube_vertices(10)
    # Create a giant observed cloud so subsample kicks in.
    obs_big = np.tile(unit, (8, 1)) + np.random.default_rng(0).normal(scale=0.001, size=(unit.shape[0] * 8, 3))
    out = align(unit, obs_big, cfg=AlignConfig(max_cloud_points=500, max_mesh_points=400))
    assert out.residual < 0.1


def test_align_residual_decreases_with_iterations() -> None:
    unit = _unit_cube_vertices(8)
    observed = _apply_sim(unit, 1.5, _yaw_matrix(10.0), np.array([0.2, 0.1, 0.3]))
    # Run with 1 iter vs many — the many-iter one must win or tie.
    r_short = align(unit, observed, cfg=AlignConfig(max_iterations=1))
    r_long = align(unit, observed, cfg=AlignConfig(max_iterations=50))
    assert r_long.residual <= r_short.residual + 1e-6


def test_align_handles_noisy_observed_cloud() -> None:
    unit = _unit_cube_vertices(8)
    rng = np.random.default_rng(2)
    r = _yaw_matrix(0.0)
    observed = _apply_sim(unit, 1.0, r, np.zeros(3)) + rng.normal(scale=0.01, size=unit.shape)
    out = align(unit, observed)
    # Residual should be of the same order as the noise floor.
    assert out.residual < 0.05


def test_yaw_matrix_is_orthonormal() -> None:
    for deg in (0, 30, 45, 90, 180, 270, 359):
        r = _yaw_matrix(float(deg))
        np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-9)
        assert np.linalg.det(r) == pytest.approx(1.0, abs=1e-9)
