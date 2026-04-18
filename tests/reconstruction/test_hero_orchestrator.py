"""End-to-end tests for the hero orchestrator (G2).

Uses a synthetic capture bundle (fabricated stereo depth with a
rectangular chair-like object) and a synthetic Hunyuan3D-style glb
(a simple unit-cube mesh). Runs the whole pipeline and asserts the
ReconstructedObject set is well-formed, loadable by Person 3, and has
every provenance field populated.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

# Make Stream 03's contract loader importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def _write_rgb(path: Path, size=(640, 480)) -> None:
    img = Image.new("RGB", size, color=(128, 128, 128))
    img.save(path, format="JPEG", quality=85)


def _write_depth(path: Path, shape=(480, 640), chair_bbox=(100, 100, 300, 400),
                 chair_dist=1500, wall_dist=3000) -> None:
    """Write a uint16 mm depth image with a chair-shaped rectangle at 1.5m
    and the rest at 3.0m."""
    h, w = shape
    depth = np.full((h, w), wall_dist, dtype=np.uint16)
    x0, y0, x1, y1 = chair_bbox
    depth[y0:y1, x0:x1] = chair_dist
    Image.fromarray(depth, mode="I;16").save(path)


def _write_conf(path: Path, shape=(480, 640)) -> None:
    Image.fromarray(np.full(shape, 255, dtype=np.uint8), mode="L").save(path)


def _write_mask_track(path: Path, shape=(480, 640), bbox=(100, 100, 300, 400),
                      track_id=7) -> None:
    mask = np.zeros(shape, dtype=np.uint16)
    x0, y0, x1, y1 = bbox
    mask[y0:y1, x0:x1] = track_id
    Image.fromarray(mask, mode="I;16").save(path)


def _write_mask_class(path: Path, shape=(480, 640)) -> None:
    Image.fromarray(np.zeros(shape, dtype=np.uint8), mode="L").save(path)


def _make_capture(tmp_path: Path, track_id: int = 7,
                  class_name: str = "chair") -> Path:
    cap = tmp_path / "captures" / "hero_01"
    frames = cap / "frames"
    frames.mkdir(parents=True)
    _write_rgb(frames / "00000.rgb.jpg")
    _write_depth(frames / "00000.depth.png")
    _write_conf(frames / "00000.conf.png")
    _write_mask_track(frames / "00000.mask_track.png", track_id=track_id)
    _write_mask_class(frames / "00000.mask_class.png")
    (frames / "00000.pose.json").write_text(
        json.dumps({"translation": [0, 0, 0], "rotation_quat": [0, 0, 0, 1]})
    )
    (frames / "00000.imu.jsonl").write_text("")
    (frames / "00000.objects.json").write_text(json.dumps([
        {"track_id": track_id, "class": class_name,
         "bbox2d": [100, 100, 300, 400],
         "bbox3d": {"center": [0, 0, 1.5], "size": [0.5, 0.9, 0.5]},
         "conf": 0.95},
    ]))
    (cap / "intrinsics.json").write_text(json.dumps({
        "camera_matrix": [[500, 0, 320], [0, 500, 240], [0, 0, 1]],
        "resolution": [640, 480], "baseline_m": 0.075,
    }))
    (cap / "capture_manifest.json").write_text(json.dumps({
        "session_id": "hero_01", "frame_count": 1,
    }))
    return cap


def _box_glb_bytes(extents=(1.0, 1.0, 1.0)) -> bytes:
    mesh = trimesh.creation.box(extents=extents)
    buf = io.BytesIO()
    mesh.export(buf, file_type="glb")
    return buf.getvalue()


class _FakeClient:
    """Stands in for RunPodClient without any HTTP."""

    def __init__(self, glb_bytes: bytes,
                 origin: str = "hunyuan3d_2.1",
                 detail: str = "runpod:hunyuan3d_2.1",
                 ran_on: str = "runpod") -> None:
        from reconstruction.runpod_client import MeshCall
        self._MeshCall = MeshCall
        self._glb = glb_bytes
        self._origin = origin
        self._detail = detail
        self._ran_on = ran_on
        self.calls = 0

    def generate_mesh(self, rgb, mask, *, model="hunyuan3d"):
        self.calls += 1
        return self._MeshCall(
            glb_bytes=self._glb,
            mesh_origin_detail=self._detail,
            mesh_origin=self._origin,
            ran_on=self._ran_on,
            generation_s=0.01,
            pod_id="fake-pod",
            attempts=1,
        )


def test_hero_end_to_end_produces_contract_compliant_bundle(tmp_path: Path) -> None:
    from reconstruction.hero_orchestrator import (
        ReconstructorConfig, reconstruct_one_object, write_session_index,
    )
    from reconstruction.vio import single_keyframe_pose

    cap = _make_capture(tmp_path, track_id=7, class_name="chair")
    client = _FakeClient(_box_glb_bytes(extents=(1, 1, 1)))
    world = single_keyframe_pose(cap, 0)
    cfg = ReconstructorConfig(out_root=tmp_path / "recon")

    obj_dir = reconstruct_one_object(
        cap, "hero_01", frame=0, track_id=7, class_name="chair",
        bbox2d=[100, 100, 300, 400],
        runpod_client=client, world=world, cfg=cfg,
    )

    assert (obj_dir / "mesh.glb").exists()
    assert (obj_dir / "crop.jpg").exists()
    m = json.loads((obj_dir / "object_manifest.json").read_text())
    assert m["id"] == "chair_07"
    assert m["provenance"]["mesh_origin"] == "hunyuan3d_2.1"
    assert m["provenance"]["mesh_origin_detail"] == "runpod:hunyuan3d_2.1"
    assert m["provenance"]["ran_on"] == "runpod"
    # ICP should have locked on fairly well (synthetic depth is clean).
    assert m["provenance"]["icp_residual"] >= 0.0
    assert m["provenance"]["decimate_output_tris"] > 0
    # Mesh tris under cap.
    assert m["provenance"]["decimate_output_tris"] <= 50_000

    # write the session index and check Person 3 can load it
    session_dir = write_session_index("hero_01", [(7, "chair", obj_dir)],
                                      world, out_root=tmp_path / "recon")
    from scene.reconstructed import load_session
    objs = load_session(session_dir)
    assert len(objs) == 1
    assert objs[0].mesh_origin == "hunyuan3d_2.1"


def test_hero_uses_fallback_provenance_when_client_returns_stub(tmp_path: Path) -> None:
    from reconstruction.hero_orchestrator import (
        ReconstructorConfig, reconstruct_one_object,
    )
    from reconstruction.vio import single_keyframe_pose

    cap = _make_capture(tmp_path, track_id=3, class_name="table")
    # Stub payload must not crash the pipeline — emulate the
    # stub-on-double-failure branch.
    client = _FakeClient(
        b"glTF" + b"\x00" * 8,
        origin="identity",
        detail="stub",
        ran_on="stub",
    )
    world = single_keyframe_pose(cap, 0)
    cfg = ReconstructorConfig(out_root=tmp_path / "recon")

    obj_dir = reconstruct_one_object(
        cap, "s", frame=0, track_id=3, class_name="table",
        bbox2d=[100, 100, 300, 400],
        runpod_client=client, world=world, cfg=cfg,
    )
    m = json.loads((obj_dir / "object_manifest.json").read_text())
    assert m["provenance"]["mesh_origin"] == "identity"
    assert m["provenance"]["mesh_origin_detail"] == "stub"
    assert m["provenance"]["ran_on"] == "stub"


def test_fused_depth_for_frame_stereo_only(tmp_path: Path) -> None:
    from reconstruction.hero_orchestrator import fused_depth_for_frame

    cap = _make_capture(tmp_path)
    r = fused_depth_for_frame(cap, 0, da3_fn=None)
    # Stereo-only path → s=1, t=0 (no DA3 to fit).
    assert r.s == pytest.approx(1.0)
    assert r.t == pytest.approx(0.0)
    # Chair pixels at 1.5 m.
    chair_px = r.fused[200, 200]
    assert 1.4 < chair_px < 1.6


def test_observed_cloud_coverage(tmp_path: Path) -> None:
    from reconstruction.backproject import Intrinsics
    from reconstruction.hero_orchestrator import (
        fused_depth_for_frame, observed_cloud,
    )

    cap = _make_capture(tmp_path, track_id=7)
    r = fused_depth_for_frame(cap, 0, da3_fn=None)
    mask = np.zeros_like(r.fused, dtype=bool)
    mask[100:400, 100:300] = True
    intr = Intrinsics(fx=500, fy=500, cx=320, cy=240)
    cloud = observed_cloud(r.fused, mask, intr, np.eye(4))
    assert cloud.shape[0] > 100
    assert cloud.shape[1] == 3
