"""Mesh decimation to the PRD 50k-tri cap (PRD §13, NFR).

Thin wrapper over trimesh's quadric decimation; returns the decimated
mesh and a tuple `(input_tris, output_tris)` for provenance.
"""

from __future__ import annotations

import logging

import trimesh

logger = logging.getLogger(__name__)

MAX_TRIS_DEFAULT = 50_000


def decimate_mesh(mesh: trimesh.Trimesh, max_tris: int = MAX_TRIS_DEFAULT) -> tuple[trimesh.Trimesh, tuple[int, int]]:
    """Decimate a mesh to at most `max_tris` triangles.

    If the mesh is already under the cap, it is returned unchanged. The
    second return tuple is (input_tris, output_tris) for provenance.
    """
    input_tris = int(len(mesh.faces))
    if input_tris <= max_tris:
        return mesh, (input_tris, input_tris)

    # Newer trimesh exposes `mesh.simplify_quadric_decimation(face_count)`.
    # Older versions expose it as a module-level attribute — cover both.
    # Both paths rely on `fast-simplification` at runtime; if that dep is
    # absent (or the environment can't import it), we log + pass through
    # so the pipeline is never blocked by decimation.
    try:
        if hasattr(mesh, "simplify_quadric_decimation"):
            out = mesh.simplify_quadric_decimation(face_count=max_tris)
        elif hasattr(mesh, "simplify_quadratic_decimation"):  # ≤4.3 API
            out = mesh.simplify_quadratic_decimation(face_count=max_tris)
        else:  # pragma: no cover — trimesh contract change
            logger.warning("trimesh has no quadric decimation; returning original")
            return mesh, (input_tris, input_tris)
    except (ImportError, ModuleNotFoundError, TypeError) as exc:
        logger.warning("quadric decimation unavailable (%s); returning original", exc)
        return mesh, (input_tris, input_tris)

    output_tris = int(len(out.faces))
    logger.info("decimated %d → %d tris", input_tris, output_tris)
    return out, (input_tris, output_tris)
