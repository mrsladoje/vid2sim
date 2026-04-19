"""Tests for the CoACD decomposition cache.

CoACD itself is exercised by the real-fixture assembler tests; here we
focus on the cache layer because it's the cheap-to-test, expensive-to-skip
behaviour. We mock CoACD with a stub function to keep the test offline
and fast.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh

from scene import decomp


class _StubCoACD:
    """Drop-in for the ``coacd`` Python module that just returns two convex
    pieces split along the X axis. Tracks how many times ``run_coacd`` is
    called so we can assert cache hits skip the work."""

    call_count = 0

    class Mesh:
        def __init__(self, verts, faces):
            self.verts = verts
            self.faces = faces

    @classmethod
    def run_coacd(cls, mesh, **_kwargs):
        cls.call_count += 1
        # Two trivial hulls so downstream code has something to write.
        a = trimesh.creation.box(extents=[0.1, 0.1, 0.1])
        b = trimesh.creation.box(extents=[0.05, 0.05, 0.05])
        return [(a.vertices, a.faces), (b.vertices, b.faces)]


@pytest.fixture()
def stub_coacd(monkeypatch):
    _StubCoACD.call_count = 0
    monkeypatch.setitem(__import__("sys").modules, "coacd", _StubCoACD)
    return _StubCoACD


def test_cache_hit_skips_coacd(stub_coacd, tmp_path: Path):
    mesh_path = tmp_path / "mesh.glb"
    trimesh.creation.box(extents=[0.2, 0.2, 0.2]).export(mesh_path)

    cache_dir = tmp_path / "cache"
    out_dir_a = tmp_path / "hulls_a"
    out_dir_b = tmp_path / "hulls_b"
    cfg = decomp.DecompConfig(cache_dir=cache_dir)

    a = decomp.decompose(mesh_path, out_dir_a, cfg)
    assert len(a) == 2
    assert stub_coacd.call_count == 1

    # Second call on the same mesh + config must be a cache hit.
    b = decomp.decompose(mesh_path, out_dir_b, cfg)
    assert len(b) == 2
    assert stub_coacd.call_count == 1, "cache miss caused a re-run"
    # Files should be present in the second directory too.
    for hull_path in b:
        assert hull_path.exists()


def test_cache_invalidated_by_config_change(stub_coacd, tmp_path: Path):
    mesh_path = tmp_path / "mesh.glb"
    trimesh.creation.box(extents=[0.2, 0.2, 0.2]).export(mesh_path)
    cache_dir = tmp_path / "cache"

    decomp.decompose(mesh_path, tmp_path / "h1",
                     decomp.DecompConfig(cache_dir=cache_dir, threshold=0.05))
    assert stub_coacd.call_count == 1
    decomp.decompose(mesh_path, tmp_path / "h2",
                     decomp.DecompConfig(cache_dir=cache_dir, threshold=0.10))
    assert stub_coacd.call_count == 2, "config change should invalidate cache"


def test_cache_manifest_records_inputs(stub_coacd, tmp_path: Path):
    mesh_path = tmp_path / "mesh.glb"
    trimesh.creation.box(extents=[0.2, 0.2, 0.2]).export(mesh_path)
    cache_dir = tmp_path / "cache"
    cfg = decomp.DecompConfig(cache_dir=cache_dir)
    decomp.decompose(mesh_path, tmp_path / "h", cfg)
    manifests = list(cache_dir.glob("*/hulls.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text())
    assert "mesh_sha256" in manifest
    assert "config_key" in manifest
    assert manifest["files"]
