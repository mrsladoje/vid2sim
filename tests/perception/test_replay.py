"""Replay mode contract: yields the same FrameRecords that were written."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.perception.bundle import BundleReader
from src.perception.replay import iter_bundle


def test_replay_yields_all_frames(stub_bundle: Path) -> None:
    n_on_disk = len(BundleReader(stub_bundle))
    records = list(iter_bundle(stub_bundle, fps=1000.0, loop=False))
    assert len(records) == n_on_disk


def test_replay_records_match_disk(stub_bundle: Path) -> None:
    reader = BundleReader(stub_bundle)
    played = list(iter_bundle(stub_bundle, fps=1000.0, loop=False))
    for i, rec in enumerate(played):
        disk = reader.read(i)
        assert np.array_equal(rec.depth_mm, disk.depth_mm)
        assert np.array_equal(rec.mask_class, disk.mask_class)


def test_replay_respects_max_frames(stub_bundle: Path) -> None:
    played = list(iter_bundle(stub_bundle, fps=1000.0, max_frames=3))
    assert len(played) == 3
