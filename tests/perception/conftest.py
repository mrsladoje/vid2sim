"""Shared fixtures for the perception test suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.generate_perception_stub import generate_stub  # noqa: E402


@pytest.fixture(scope="session")
def stub_bundle(tmp_path_factory) -> Path:
    """A freshly generated 8-frame bundle used across tests."""
    outdir = tmp_path_factory.mktemp("bundle") / "stub"
    generate_stub(outdir, num_frames=8, fps=15)
    return outdir
