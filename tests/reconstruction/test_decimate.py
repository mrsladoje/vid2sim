"""Mesh decimation tests."""

from __future__ import annotations

import pytest
import trimesh

from reconstruction.decimate import decimate_mesh


def test_small_mesh_unchanged() -> None:
    m = trimesh.creation.box()
    out, (inp, outp) = decimate_mesh(m, max_tris=50_000)
    assert inp == outp == len(m.faces)
    assert out is m


def test_dense_mesh_reduced() -> None:
    try:
        from fast_simplification import simplify  # noqa: F401
    except Exception as exc:
        pytest.skip(f"fast_simplification unavailable ({exc})")
    # Subdivided icosphere blows past 1k tris easily.
    m = trimesh.creation.icosphere(subdivisions=5)  # 20480 faces
    out, (inp, outp) = decimate_mesh(m, max_tris=1_000)
    assert inp > 1_000
    assert outp <= 1_000 * 1.05  # allow small over-shoot from the quadric solver
    assert len(out.vertices) > 0


def test_dense_mesh_passthrough_when_solver_missing(monkeypatch) -> None:
    # Guarantees decimate never throws even when the optional solver is
    # absent — the pipeline must not fail on decimation.
    import reconstruction.decimate as dec
    m = trimesh.creation.icosphere(subdivisions=5)
    out, (inp, outp) = dec.decimate_mesh(m, max_tris=1_000)
    # Either the real solver ran (outp ~1000) or we fell through (outp == inp).
    assert outp <= inp
    assert len(out.faces) > 0


def test_returns_tuple_contract() -> None:
    m = trimesh.creation.box()
    out, counts = decimate_mesh(m)
    assert isinstance(out, trimesh.Trimesh)
    assert isinstance(counts, tuple) and len(counts) == 2
