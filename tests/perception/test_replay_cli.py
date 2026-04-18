"""Exercise replay.main via argparse for CLI coverage."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.perception import replay


def test_main_runs_on_a_real_bundle(stub_bundle: Path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="src.perception.replay")
    rc = replay.main(["--bundle", str(stub_bundle), "--fps", "1000", "--max-frames", "3"])
    assert rc == 0


def test_main_errors_on_missing_bundle(tmp_path: Path, caplog) -> None:
    rc = replay.main(["--bundle", str(tmp_path / "nope"), "--fps", "1000"])
    assert rc == 2


def test_iter_bundle_empty_raises(tmp_path: Path) -> None:
    from src.perception.bundle import Manifest, Intrinsics, BundleWriter
    bw = BundleWriter(tmp_path, Manifest("s", "d", "f", 15, 0, [], 0),
                      Intrinsics([[1, 0, 0], [0, 1, 0], [0, 0, 1]], (1920, 1080), 0.075))
    bw.close()
    # No frames were written; iter_bundle must error.
    with pytest.raises(RuntimeError):
        next(replay.iter_bundle(tmp_path, fps=1000))
