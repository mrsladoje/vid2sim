"""ICP scale+rotation+translation alignment of raw meshes to observed
point clouds (ADR-003, ADR-009 §Stage B output post-processing).

Hunyuan3D / TripoSG / SF3D all emit meshes normalised to a unit cube
`[-0.5, 0.5]^3`. Stage A / back-projection produces a partial point
cloud in world frame. This module finds the similarity transform
`(s, R, t)` that aligns the unit-cube mesh to the observed cloud.

Strategy (cheap + testable, no open3d dependency):

1. Seed translation from the cloud centroid (2D-bbox-centre-in-world).
2. Seed uniform scale from the cloud's principal-axis extent.
3. Seed rotation with an **azimuth sweep** (0/90/180/270 about +Y) —
   objects in the scene are almost always upright. This satisfies the
   plan's "class prior + azimuth-only search" requirement cheaply.
4. Run point-to-point ICP with scale for K iterations from each seed;
   keep the lowest-residual result.

Bounded iteration count + azimuth-only search covers the symmetric /
untextured failure mode from the PRD §13 risk row.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Array = np.ndarray


@dataclass(frozen=True)
class AlignConfig:
    max_iterations: int = 40
    tol: float = 1e-5
    azimuth_seeds_deg: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)
    max_cloud_points: int = 3000  # subsample for speed
    max_mesh_points: int = 1500   # subsample mesh vertices


@dataclass(frozen=True)
class AlignResult:
    scale: float
    rotation: Array          # (3,3)
    translation: Array       # (3,)
    residual: float          # mean nearest-neighbour distance, metres
    iterations: int
    azimuth_deg: float       # which seed won


def _yaw_matrix(deg: float) -> Array:
    rad = np.deg2rad(deg)
    c, s = float(np.cos(rad)), float(np.sin(rad))
    return np.array([
        [c, 0.0, s],
        [0.0, 1.0, 0.0],
        [-s, 0.0, c],
    ], dtype=np.float64)


def _subsample(points: Array, cap: int, rng: np.random.Generator) -> Array:
    if points.shape[0] <= cap:
        return points
    idx = rng.choice(points.shape[0], size=cap, replace=False)
    return points[idx]


def _nearest_neighbours(src: Array, dst: Array) -> tuple[Array, Array]:
    """Return indices into dst of the nearest neighbour of each src row,
    and the squared distances. Brute force, O(Ns*Nd*3).
    """
    # (Ns, Nd)
    diff = src[:, None, :] - dst[None, :, :]
    sq = np.sum(diff * diff, axis=2)
    idx = np.argmin(sq, axis=1)
    return idx, sq[np.arange(src.shape[0]), idx]


def _best_similarity(src: Array, dst: Array) -> tuple[float, Array, Array]:
    """Umeyama (1991) closed-form similarity transform src → dst.

    Returns (scale, R, t) minimising sum ||dst - (s·R·src + t)||^2.
    """
    mu_s = src.mean(axis=0)
    mu_d = dst.mean(axis=0)
    src_c = src - mu_s
    dst_c = dst - mu_d
    var_s = (src_c ** 2).sum() / src.shape[0]
    cov = (dst_c.T @ src_c) / src.shape[0]
    u, d, vt = np.linalg.svd(cov)
    s_sign = np.ones(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        s_sign[-1] = -1.0
    r = u @ np.diag(s_sign) @ vt
    scale = 1.0 / var_s * np.sum(d * s_sign) if var_s > 1e-12 else 1.0
    t = mu_d - scale * r @ mu_s
    return float(scale), r, t


def align(
    raw_vertices: Array,
    observed: Array,
    cfg: AlignConfig | None = None,
    rng_seed: int = 0,
) -> AlignResult:
    """Align a raw (unit-cube) mesh to an observed world-frame cloud.

    Parameters
    ----------
    raw_vertices : (Nv, 3) mesh vertices in unit-cube coordinates.
    observed : (No, 3) observed world-frame point cloud (e.g. from
        back-projection of the masked fused depth).
    cfg : AlignConfig
    """
    cfg = cfg or AlignConfig()
    if raw_vertices.size == 0 or observed.size == 0:
        # No data to align; return identity with large residual so the
        # caller can flag provenance.
        return AlignResult(
            scale=1.0,
            rotation=np.eye(3),
            translation=np.zeros(3),
            residual=float("inf"),
            iterations=0,
            azimuth_deg=0.0,
        )

    rng = np.random.default_rng(rng_seed)
    mesh_pts = _subsample(np.asarray(raw_vertices, dtype=np.float64),
                          cfg.max_mesh_points, rng)
    obs_pts = _subsample(np.asarray(observed, dtype=np.float64),
                         cfg.max_cloud_points, rng)

    # Seed scale: span of observed cloud / span of unit cube (≈ 1).
    obs_span = float(np.max(obs_pts.max(axis=0) - obs_pts.min(axis=0)))
    mesh_span = float(np.max(mesh_pts.max(axis=0) - mesh_pts.min(axis=0))) or 1.0
    seed_scale = obs_span / mesh_span
    obs_centroid = obs_pts.mean(axis=0)

    best: AlignResult | None = None
    for az in cfg.azimuth_seeds_deg:
        r = _yaw_matrix(az)
        s = seed_scale
        t = obs_centroid - s * r @ mesh_pts.mean(axis=0)

        prev_err = np.inf
        iters = 0
        for iters in range(1, cfg.max_iterations + 1):
            transformed = (s * mesh_pts @ r.T) + t
            idx, sq = _nearest_neighbours(transformed, obs_pts)
            err = float(np.sqrt(sq.mean()))
            if abs(prev_err - err) < cfg.tol:
                break
            prev_err = err
            correspondences = obs_pts[idx]
            new_s, new_r, new_t = _best_similarity(mesh_pts, correspondences)
            # Only accept if similarity is sane (non-inverting, positive scale).
            if new_s > 0 and np.linalg.det(new_r) > 0:
                s, r, t = new_s, new_r, new_t

        result = AlignResult(
            scale=float(s),
            rotation=r.copy(),
            translation=t.copy(),
            residual=float(prev_err),
            iterations=iters,
            azimuth_deg=float(az),
        )
        if best is None or result.residual < best.residual:
            best = result

    assert best is not None
    return best


def apply_similarity(vertices: Array, result: AlignResult) -> Array:
    """Apply (s, R, t) to a (N, 3) vertex array."""
    v = np.asarray(vertices, dtype=np.float64)
    return (result.scale * v @ result.rotation.T) + result.translation
