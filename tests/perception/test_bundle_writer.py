"""Unit tests for BundleWriter — exercised without depthai."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src.perception.bundle import (
    BundleWriter,
    FrameRecord,
    ImuSample,
    Intrinsics,
    Manifest,
    ObjectRecord,
    Pose,
    RGB_HEIGHT,
    RGB_WIDTH,
)


def _make_frame(i: int) -> FrameRecord:
    rgb = np.zeros((RGB_HEIGHT, RGB_WIDTH, 3), dtype=np.uint8)
    rgb[:, :, 1] = 120
    depth = np.full((RGB_HEIGHT, RGB_WIDTH), 1200, dtype=np.uint16)
    conf = np.full((RGB_HEIGHT, RGB_WIDTH), 200, dtype=np.uint8)
    mask_cls = np.zeros((RGB_HEIGHT, RGB_WIDTH), dtype=np.uint8)
    mask_trk = np.zeros((RGB_HEIGHT, RGB_WIDTH), dtype=np.uint16)
    return FrameRecord(
        index=i, rgb=rgb, depth_mm=depth, conf=conf,
        mask_class=mask_cls, mask_track=mask_trk,
        pose=Pose(),
        imu=[ImuSample(i * 1_000_000, (0, -9.8, 0), (0, 0, 0))],
        objects=[ObjectRecord(track_id=1, cls="chair", bbox2d=(10, 20, 30, 40), conf=0.9)],
    )


def test_writer_creates_manifest_and_frames(tmp_path: Path) -> None:
    writer = BundleWriter(
        tmp_path,
        Manifest("s", "dev", "fw", 15, 0, ["chair"], 0),
        Intrinsics([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], (RGB_WIDTH, RGB_HEIGHT), 0.075),
    )
    writer.write(_make_frame(0))
    writer.write(_make_frame(1))
    writer.close()

    m = json.loads((tmp_path / "capture_manifest.json").read_text())
    assert m["frame_count"] == 2
    assert (tmp_path / "frames" / "00000.rgb.jpg").exists()
    assert (tmp_path / "frames" / "00001.objects.json").exists()


def test_manifest_is_rewritten_on_every_frame(tmp_path: Path) -> None:
    writer = BundleWriter(
        tmp_path,
        Manifest("s", "dev", "fw", 15, 0, [], 0),
        Intrinsics([[1, 0, 0], [0, 1, 0], [0, 0, 1]], (RGB_WIDTH, RGB_HEIGHT), 0.075),
    )
    writer.write(_make_frame(0))
    manifest_mid = json.loads((tmp_path / "capture_manifest.json").read_text())
    assert manifest_mid["frame_count"] == 1  # interrupted capture still usable
    writer.write(_make_frame(1))
    manifest_end = json.loads((tmp_path / "capture_manifest.json").read_text())
    assert manifest_end["frame_count"] == 2
