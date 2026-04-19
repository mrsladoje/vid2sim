"""CoACD 1.0.10 convex decomposition pipeline.

For every dynamic, `mesh`-collider scene object, run CoACD to produce a
small set of convex hulls written beside the object's mesh. Results are
referenced from `collider.hull_paths`.

Per plan §7 risk row: cap at 8 hulls per object. Drop to a single hull if
over budget.

CoACD takes 5–30 s per mesh, so results are cached on disk by the SHA-256
of the input mesh's bytes plus a hash of the relevant ``DecompConfig``
fields. A repeat run on the same mesh skips CoACD entirely and just
re-emits hull files into the requested ``out_dir``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import trimesh

logger = logging.getLogger(__name__)

MAX_HULLS = 8

# Default cache root — overridable per-call via ``DecompConfig.cache_dir``.
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "vid2sim" / "coacd"


@dataclass(frozen=True)
class DecompConfig:
    threshold: float = 0.05
    max_convex_hull: int = MAX_HULLS
    preprocess_resolution: int = 30
    mcts_iterations: int = 100
    mcts_nodes: int = 20
    mcts_max_depth: int = 3
    seed: int = 0
    cache_dir: Path | None = None  # ``None`` → ``DEFAULT_CACHE_DIR``

    def cache_key(self) -> str:
        """Stable hash of every field that affects CoACD output."""
        params = {k: v for k, v in asdict(self).items() if k != "cache_dir"}
        blob = json.dumps(params, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def decompose(
    mesh_path: Path,
    out_dir: Path,
    config: DecompConfig | None = None,
) -> list[Path]:
    """Run CoACD on a mesh; return the written hull glTF paths.

    Caches by ``sha256(mesh_bytes) + cache_key(config)``. A cache hit
    copies the previously-computed hull GLBs into ``out_dir`` instead of
    re-running CoACD (which can take 5–30 s per mesh).
    """
    cfg = config or DecompConfig()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = mesh_path.stem

    cache_root = cfg.cache_dir or DEFAULT_CACHE_DIR
    mesh_hash = _sha256_file(mesh_path)
    cache_subdir = Path(cache_root) / f"{mesh_hash}_{cfg.cache_key()}"
    manifest_path = cache_subdir / "hulls.json"

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        cached_files = [cache_subdir / name for name in manifest["files"]]
        if all(p.exists() for p in cached_files):
            logger.info("CoACD cache hit for %s (%s)", stem, mesh_hash[:8])
            return _materialise_cache(cached_files, out_dir, stem)

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

    # Write to the cache first, then copy into the caller's out_dir.
    cache_subdir.mkdir(parents=True, exist_ok=True)
    cache_files: list[Path] = []
    for i, hull in enumerate(hulls):
        cache_file = cache_subdir / f"hull_{i:02d}.glb"
        hull.export(cache_file)
        cache_files.append(cache_file)
    manifest_path.write_text(json.dumps({
        "mesh_sha256": mesh_hash,
        "config_key": cfg.cache_key(),
        "files": [p.name for p in cache_files],
    }, indent=2))

    return _materialise_cache(cache_files, out_dir, stem)


def _materialise_cache(cache_files: list[Path], out_dir: Path,
                       stem: str) -> list[Path]:
    """Copy cached hull GLBs into ``out_dir`` under ``<stem>_hull_NN.glb``."""
    written: list[Path] = []
    for cache_file in cache_files:
        suffix = cache_file.stem.split("_")[-1]
        dest = out_dir / f"{stem}_hull_{suffix}.glb"
        shutil.copy2(cache_file, dest)
        written.append(dest)
    return written
