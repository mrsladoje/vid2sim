"""Per-frame RANSAC stereo/DA3 depth fusion (ADR-002).

We solve a **per-frame** affine relationship in depth space:

    stereo ≈ s · DA3 + t

over pixels where stereo is *confident*, then use the aligned DA3 to
fill stereo holes and refine noisy stereo. Stereo remains the metric
anchor; DA3 is the fill.

This module is pure numpy — no torch, no open3d — so it is cheap to test
and the 80%-coverage target from the PRD NFR is achievable with
synthetic fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Array = np.ndarray


@dataclass(frozen=True)
class FusionResult:
    """Output of :func:`fuse_depth`.

    `fused` is in the same units as the stereo input (typically metres).
    `s`, `t` are the affine parameters. `inliers` is the number of
    pixels that passed RANSAC after the final least-squares refit.
    `num_stereo_valid` lets callers sanity-check coverage.
    """

    fused: Array
    s: float
    t: float
    inliers: int
    num_stereo_valid: int


@dataclass(frozen=True)
class FusionConfig:
    """Tunables. Defaults are hand-picked for 1080p depth in metres."""

    conf_threshold: float = 0.5  # keep stereo pixels with conf > this (0..1)
    min_stereo_pixels: int = 64
    ransac_iterations: int = 256
    ransac_inlier_tol: float = 0.03  # metres — ~2% of a 1.5 m target
    min_inliers: int = 32
    min_da3_gap: float = 1e-3  # guard against degenerate RANSAC pairs
    rng_seed: int | None = 0  # deterministic in tests


def _confidence_mask(conf: Array | None, shape: tuple[int, int], cfg: FusionConfig) -> Array:
    if conf is None:
        return np.ones(shape, dtype=bool)
    if conf.dtype == np.uint8:
        norm = conf.astype(np.float32) / 255.0
    else:
        norm = conf.astype(np.float32)
    return norm > cfg.conf_threshold


def _stereo_valid_mask(stereo: Array) -> Array:
    # Stereo depth is positive and finite on valid pixels. DepthAI writes
    # zero for invalid, and fused-depth callers may pass NaN for the
    # same reason — both collapse to False here.
    return np.isfinite(stereo) & (stereo > 0)


def _ransac_affine(x: Array, y: Array, cfg: FusionConfig) -> tuple[float, float, Array]:
    """Fit y ≈ s·x + t with RANSAC.

    x: DA3 samples. y: stereo samples (same length). Returns s, t, and
    an inlier boolean mask of shape x.shape.
    """
    rng = np.random.default_rng(cfg.rng_seed)
    n = x.shape[0]
    best_inliers = np.zeros(n, dtype=bool)
    best_count = -1
    best_s = 1.0
    best_t = 0.0

    for _ in range(cfg.ransac_iterations):
        a, b = rng.integers(0, n, size=2)
        if a == b:
            continue
        dx = x[b] - x[a]
        if abs(dx) < cfg.min_da3_gap:
            continue
        s = (y[b] - y[a]) / dx
        t = y[a] - s * x[a]
        # Reject obviously degenerate fits. Depth should scale roughly
        # 1:1; we allow a generous band but not sign-flips.
        if not np.isfinite(s) or not np.isfinite(t) or s <= 0:
            continue
        residuals = np.abs(y - (s * x + t))
        inliers = residuals < cfg.ransac_inlier_tol
        count = int(inliers.sum())
        if count > best_count:
            best_count = count
            best_inliers = inliers
            best_s, best_t = float(s), float(t)

    return best_s, best_t, best_inliers


def _lsq_refit(x: Array, y: Array, mask: Array) -> tuple[float, float]:
    xi = x[mask]
    yi = y[mask]
    if xi.size < 2:
        return 1.0, 0.0
    # Classic closed-form least-squares for y = s·x + t.
    a = np.vstack([xi, np.ones_like(xi)]).T
    sol, *_ = np.linalg.lstsq(a, yi, rcond=None)
    return float(sol[0]), float(sol[1])


def fuse_depth(
    stereo: Array,
    da3: Array,
    conf: Array | None = None,
    cfg: FusionConfig | None = None,
) -> FusionResult:
    """Fuse stereo and DA3 depth, per frame.

    Parameters
    ----------
    stereo : (H,W) float array
        Metric stereo depth (metres). Invalid pixels encoded as 0 or NaN.
    da3 : (H,W) float array
        Metric monocular depth from DA3METRIC-LARGE (metres).
    conf : optional (H,W) uint8 or float array
        Stereo confidence. When absent, every stereo pixel is trusted.
    cfg : FusionConfig
    """
    cfg = cfg or FusionConfig()
    if stereo.shape != da3.shape:
        raise ValueError(
            f"stereo {stereo.shape} and DA3 {da3.shape} must share shape"
        )
    stereo_f = stereo.astype(np.float32)
    da3_f = da3.astype(np.float32)

    valid = _stereo_valid_mask(stereo_f)
    conf_mask = _confidence_mask(conf, stereo_f.shape, cfg)
    sample_mask = valid & conf_mask & np.isfinite(da3_f) & (da3_f > 0)
    num_stereo_valid = int(valid.sum())

    if int(sample_mask.sum()) < cfg.min_stereo_pixels:
        # Graceful fallback: not enough confident stereo to solve for
        # (s, t). Return DA3 as-is — callers see inliers == 0 and can
        # downgrade provenance accordingly.
        fused = np.where(valid, stereo_f, da3_f)
        return FusionResult(
            fused=fused, s=1.0, t=0.0, inliers=0, num_stereo_valid=num_stereo_valid
        )

    x = da3_f[sample_mask]
    y = stereo_f[sample_mask]

    s, t, inliers = _ransac_affine(x, y, cfg)
    if int(inliers.sum()) < cfg.min_inliers:
        # RANSAC did not lock on — fall back to full least-squares.
        s, t = _lsq_refit(x, y, np.ones_like(x, dtype=bool))
    else:
        s, t = _lsq_refit(x, y, inliers)

    aligned_da3 = s * da3_f + t
    fused = np.where(valid, stereo_f, aligned_da3)
    # If DA3 itself is invalid we keep stereo (or zero, same thing).
    fused = np.where(np.isfinite(fused), fused, 0.0)

    return FusionResult(
        fused=fused.astype(np.float32),
        s=float(s),
        t=float(t),
        inliers=int(inliers.sum()),
        num_stereo_valid=num_stereo_valid,
    )
