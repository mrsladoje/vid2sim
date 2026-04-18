"""Tests for the stub ReconstructedObject emitter.

Exercises the Person-3 contract: emitted artifacts load via
`src/scene/reconstructed.py:load_session` without modification.
"""

from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from reconstruction.stub_emitter import StubConfig, emit_stub

# Pull the Person-3 contract loader in to verify round-trip consumption.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def _write_capture(tmp_path: Path, objects: list[dict]) -> Path:
    cap = tmp_path / "captures" / "stub_01"
    (cap / "frames").mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (640, 480), color=(127, 127, 127))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    (cap / "frames" / "00000.rgb.jpg").write_bytes(buf.getvalue())

    (cap / "frames" / "00000.objects.json").write_text(json.dumps(objects))

    (cap / "intrinsics.json").write_text(json.dumps({
        "camera_matrix": [[500, 0, 320], [0, 500, 240], [0, 0, 1]],
        "resolution": [640, 480], "baseline_m": 0.075,
    }))
    (cap / "capture_manifest.json").write_text(json.dumps({
        "session_id": "stub_01", "capture_fps": 15, "frame_count": 1,
    }))
    return cap


def test_emit_stub_writes_contract_surface(tmp_path: Path) -> None:
    cap = _write_capture(tmp_path, [
        {"track_id": 1, "class": "chair",
         "bbox2d": [100, 80, 300, 400],
         "bbox3d": {"center": [0.5, 0.2, 1.2], "size": [0.5, 0.9, 0.5]},
         "conf": 0.92},
        {"track_id": 2, "class": "table",
         "bbox2d": [320, 100, 620, 470],
         "bbox3d": {"center": [-0.3, 0.0, 1.5], "size": [1.2, 0.8, 0.6]},
         "conf": 0.88},
    ])
    out_root = tmp_path / "recon"

    session = emit_stub(cap, "stub_01",
                       cfg=StubConfig(out_root=out_root))

    assert session == out_root / "stub_01"
    assert (session / "reconstructed.json").exists()
    assert (session / "world_pose.json").exists()

    idx = json.loads((session / "reconstructed.json").read_text())
    assert idx["session_id"] == "stub_01"
    assert len(idx["objects"]) == 2

    chair = [o for o in idx["objects"] if o["class"] == "chair"][0]
    assert chair["mesh_origin"] == "identity"
    assert (session / chair["mesh_path"]).exists()
    assert (session / chair["crop_image_path"]).exists()
    # bbox consistent
    assert chair["bbox_max"][1] > chair["bbox_min"][1]


def test_person_three_can_load_the_stub_session(tmp_path: Path) -> None:
    """The assembler contract must load our emitted session 1:1."""
    from scene.reconstructed import load_session  # type: ignore

    cap = _write_capture(tmp_path, [
        {"track_id": 7, "class": "cup",
         "bbox2d": [10, 20, 120, 180],
         "bbox3d": {"center": [0.1, 0.0, 0.5], "size": [0.1, 0.1, 0.1]}}
    ])
    out_root = tmp_path / "recon"
    session = emit_stub(cap, "t01", cfg=StubConfig(out_root=out_root))

    objs = load_session(session)
    assert len(objs) == 1
    obj = objs[0]
    assert obj.class_name == "cup"
    assert obj.mesh_origin == "identity"
    assert obj.id == "cup_07"


def test_missing_keyframe_raises(tmp_path: Path) -> None:
    cap = tmp_path / "captures" / "empty"
    (cap / "frames").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        emit_stub(cap, "x", cfg=StubConfig(out_root=tmp_path))


def test_bbox2d_clamped_to_image(tmp_path: Path) -> None:
    cap = _write_capture(tmp_path, [
        # Deliberately out-of-bounds crop coords; emitter must clamp.
        {"track_id": 1, "class": "oob",
         "bbox2d": [-50, -50, 10000, 10000],
         "bbox3d": {"center": [0, 0, 1], "size": [0.2, 0.2, 0.2]}}
    ])
    out = tmp_path / "recon"
    session = emit_stub(cap, "s", cfg=StubConfig(out_root=out))
    crop = (session / "objects" / "1_oob" / "crop.jpg").read_bytes()
    # Valid JPEG even under pathological bbox.
    assert crop.startswith(b"\xff\xd8")


def test_manifest_provenance_shape(tmp_path: Path) -> None:
    cap = _write_capture(tmp_path, [
        {"track_id": 3, "class": "chair",
         "bbox2d": [0, 0, 100, 100],
         "bbox3d": {"center": [0, 0, 1], "size": [0.3, 0.3, 0.3]}}
    ])
    session = emit_stub(cap, "s", cfg=StubConfig(out_root=tmp_path / "r"))
    m = json.loads((session / "objects" / "3_chair" / "object_manifest.json").read_text())
    for field in ("track_id", "class", "id", "mesh_path", "best_crop_path",
                  "transform_world", "bbox_world", "provenance"):
        assert field in m
    for field in ("depth_origin", "pose_origin", "mesh_origin",
                  "mesh_origin_detail", "icp_residual", "ran_on"):
        assert field in m["provenance"]
    assert m["provenance"]["mesh_origin_detail"] == "stub"
    assert m["provenance"]["mesh_origin"] == "identity"
