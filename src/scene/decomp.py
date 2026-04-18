"""CoACD 1.0.10 convex decomposition pipeline.

For every dynamic, `mesh`-collider scene object, run CoACD to produce a
small set of convex hulls written beside the object's mesh. Results are
referenced from `collider.hull_paths`.

Per plan §7 risk row: cap at 8 hulls per object. Drop to a single hull if
over budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

logger = logging.getLogger(__name__)

MAX_HULLS = 8


@dataclass(frozen=True)
class DecompConfig:
    threshold: float = 0.05
    max_convex_hull: int = MAX_HULLS
    preprocess_resolution: int = 30
    mcts_iterations: int = 100
    mcts_nodes: int = 20
    mcts_max_depth: int = 3
    seed: int = 0


def decompose(
    mesh_path: Path,
    out_dir: Path,
    config: DecompConfig | None = None,
) -> list[Path]:
    """Run CoACD on a mesh; return the written hull glTF paths.

    Caps the hull count at `config.max_convex_hull`; if CoACD over-produces
    we keep the largest-volume `N` hulls and drop the rest.
    """
    cfg = config or DecompConfig()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = mesh_path.stem

    import coacd  # lazy so unit tests without the native lib still import

    tm = trimesh.load(mesh_path, force="mesh")
    verts = np.asarray(tm.vertices, dtype=np.float64)
    faces = np.asarray(tm.faces, dtype=np.int32)
    coacd_mesh = coacd.Mesh(verts, faces)

    parts = coacd.run_coacd(
        coacd_mesh,
        threshold=cfg.threshold,
        max_convex_hull=cfg.max_convex_hull,
        preprocess_resolution=cfg.preprocess_resolution,
        mcts_iterations=cfg.mcts_iterations,
        mcts_nodes=cfg.mcts_nodes,
        mcts_max_depth=cfg.mcts_max_depth,
        seed=cfg.seed,
    )
    hulls = [trimesh.Trimesh(vertices=v, faces=f) for v, f in parts]

    if len(hulls) > cfg.max_convex_hull:
        hulls.sort(key=lambda h: h.volume, reverse=True)
        hulls = hulls[: cfg.max_convex_hull]
        logger.warning(
            "CoACD returned %d hulls for %s; capped at %d",
            len(parts), stem, cfg.max_convex_hull,
        )

    written: list[Path] = []
    for i, hull in enumerate(hulls):
        path = out_dir / f"{stem}_hull_{i:02d}.glb"
        hull.export(path)
        written.append(path)
    return written
