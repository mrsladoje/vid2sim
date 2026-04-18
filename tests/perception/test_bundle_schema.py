"""Validate a PerceptionFrame bundle against spec/perception_frame.md v1.0."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.perception.bundle import BundleReader, RGB_WIDTH, RGB_HEIGHT


REQUIRED_MANIFEST_KEYS = {
    "session_id", "device_serial", "firmware_version",
    "capture_fps", "frame_count", "class_prompts", "timebase_ns",
}
REQUIRED_INTRINSICS_KEYS = {"camera_matrix", "resolution", "baseline_m"}
FRAME_SUFFIXES = (
    ".rgb.jpg", ".depth.png", ".conf.png",
    ".mask_class.png", ".mask_track.png",
    ".pose.json", ".imu.jsonl", ".objects.json",
)


def test_manifest_has_required_keys(stub_bundle: Path) -> None:
    m = json.loads((stub_bundle / "capture_manifest.json").read_text())
    assert REQUIRED_MANIFEST_KEYS.issubset(m.keys())
    assert m["frame_count"] > 0
    assert m["capture_fps"] > 0
    assert isinstance(m["class_prompts"], list)


def test_intrinsics_has_required_keys(stub_bundle: Path) -> None:
    k = json.loads((stub_bundle / "intrinsics.json").read_text())
    assert REQUIRED_INTRINSICS_KEYS.issubset(k.keys())
    matrix = np.array(k["camera_matrix"])
    assert matrix.shape == (3, 3)
    assert k["resolution"] == [RGB_WIDTH, RGB_HEIGHT]
    assert k["baseline_m"] > 0


def test_every_frame_has_the_full_8_file_set(stub_bundle: Path) -> None:
    manifest = json.loads((stub_bundle / "capture_manifest.json").read_text())
    for i in range(manifest["frame_count"]):
        prefix = stub_bundle / "frames" / f"{i:05d}"
        for suffix in FRAME_SUFFIXES:
            p = prefix.with_suffix(suffix)
            assert p.exists(), f"missing {p.name}"
            assert p.stat().st_size > 0, f"{p.name} is empty"


@pytest.mark.parametrize("idx", [0])
def test_image_shapes_and_dtypes(stub_bundle: Path, idx: int) -> None:
    prefix = stub_bundle / "frames" / f"{idx:05d}"
    rgb = Image.open(prefix.with_suffix(".rgb.jpg"))
    depth = Image.open(prefix.with_suffix(".depth.png"))
    conf = Image.open(prefix.with_suffix(".conf.png"))
    mask_class = Image.open(prefix.with_suffix(".mask_class.png"))
    mask_track = Image.open(prefix.with_suffix(".mask_track.png"))
    assert rgb.size == (RGB_WIDTH, RGB_HEIGHT)
    assert rgb.mode == "RGB"
    assert depth.size == (RGB_WIDTH, RGB_HEIGHT)
    assert depth.mode == "I;16"
    assert conf.mode == "L"
    assert mask_class.mode == "L"
    assert mask_track.mode == "I;16"
    # Spec: JPEG, not a 1x1 stub blob.
    assert prefix.with_suffix(".rgb.jpg").stat().st_size > 5_000


def test_bundle_reader_round_trips(stub_bundle: Path) -> None:
    reader = BundleReader(stub_bundle)
    assert len(reader) > 0
    rec = reader.read(0)
    assert rec.rgb.shape == (RGB_HEIGHT, RGB_WIDTH, 3)
    assert rec.depth_mm.dtype == np.uint16
    assert rec.conf.dtype == np.uint8
    assert rec.mask_track.dtype == np.uint16
    assert isinstance(rec.imu, list) and len(rec.imu) > 0
    assert isinstance(rec.objects, list)
