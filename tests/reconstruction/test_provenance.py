"""Provenance audit (plan §G4).

For any ReconstructedObject session on disk, every `object_manifest.json`
must have every provenance field populated AND the `mesh_origin` tag
must be one of the legal enum values in `spec/scene.schema.json`.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REQUIRED_MANIFEST_FIELDS = {
    "track_id", "class", "id", "best_crop_path", "mesh_path",
    "transform_world", "bbox_world", "provenance",
}
REQUIRED_PROVENANCE_FIELDS = {
    "depth_origin", "pose_origin",
    "mesh_origin_detail", "mesh_origin",
    "icp_residual", "s_stereo_da3", "t_stereo_da3",
    "ran_on", "pod_id", "generation_s", "alignment_s",
    "decimate_input_tris", "decimate_output_tris",
}
LEGAL_MESH_ORIGINS = {"hunyuan3d_2.1", "triposg_1.5b", "sf3d", "identity"}
LEGAL_DETAILS = {
    "runpod:hunyuan3d_2.1", "runpod:triposg_1.5b",
    "local:sf3d", "stub", "identity",
}
LEGAL_RAN_ON = {"runpod", "local", "stub"}


def _audit_session(session_dir: Path) -> None:
    """Run the gate checks; raise AssertionError on any violation."""
    reconstructed = session_dir / "reconstructed.json"
    assert reconstructed.exists(), f"missing reconstructed.json in {session_dir}"
    index = json.loads(reconstructed.read_text())
    assert index["objects"], f"empty object list in {reconstructed}"

    for o in index["objects"]:
        assert o["mesh_origin"] in LEGAL_MESH_ORIGINS, \
            f"illegal mesh_origin in session index: {o['mesh_origin']}"
        assert (session_dir / o["mesh_path"]).exists()
        assert (session_dir / o["crop_image_path"]).exists()

    for obj_dir in (session_dir / "objects").iterdir():
        if not obj_dir.is_dir():
            continue
        mpath = obj_dir / "object_manifest.json"
        assert mpath.exists(), f"missing manifest: {mpath}"
        m = json.loads(mpath.read_text())
        missing = REQUIRED_MANIFEST_FIELDS - set(m)
        assert not missing, f"{mpath} missing fields: {missing}"
        prov = m["provenance"]
        missing_p = REQUIRED_PROVENANCE_FIELDS - set(prov)
        assert not missing_p, f"{mpath} missing provenance: {missing_p}"
        assert prov["mesh_origin"] in LEGAL_MESH_ORIGINS, \
            f"{mpath}: mesh_origin={prov['mesh_origin']}"
        assert prov["mesh_origin_detail"] in LEGAL_DETAILS, \
            f"{mpath}: mesh_origin_detail={prov['mesh_origin_detail']}"
        assert prov["ran_on"] in LEGAL_RAN_ON, \
            f"{mpath}: ran_on={prov['ran_on']}"


def test_stub_session_provenance_audit(tmp_path: Path) -> None:
    from reconstruction.stub_emitter import emit_stub, StubConfig

    # Build a minimal capture on disk with one object.
    from PIL import Image
    cap = tmp_path / "captures" / "aud"
    (cap / "frames").mkdir(parents=True)
    Image.new("RGB", (64, 64)).save(cap / "frames" / "00000.rgb.jpg", "JPEG")
    (cap / "frames" / "00000.objects.json").write_text(json.dumps([
        {"track_id": 1, "class": "chair",
         "bbox2d": [5, 5, 50, 50],
         "bbox3d": {"center": [0, 0, 1], "size": [0.2, 0.3, 0.2]}},
    ]))
    (cap / "intrinsics.json").write_text(json.dumps({
        "camera_matrix": [[500, 0, 32], [0, 500, 32], [0, 0, 1]],
        "resolution": [64, 64], "baseline_m": 0.075,
    }))

    session = emit_stub(cap, "aud", cfg=StubConfig(out_root=tmp_path / "recon"))
    _audit_session(session)


def test_batch_session_provenance_audit(tmp_path: Path) -> None:
    """Full-pipeline session passes the same audit."""
    from reconstruction.batch import reconstruct_session
    from reconstruction.hero_orchestrator import ReconstructorConfig
    from reconstruction.runpod_client import MeshCall
    import numpy as np
    from PIL import Image

    # Synthetic bundle
    cap = tmp_path / "captures" / "bat"
    frames = cap / "frames"
    frames.mkdir(parents=True)
    w, h = 640, 480
    Image.new("RGB", (w, h), color=(127, 127, 127)).save(
        frames / "00000.rgb.jpg", "JPEG", quality=85)
    depth = np.full((h, w), 2000, dtype=np.uint16)
    mask = np.zeros((h, w), dtype=np.uint16)
    for tid, (x0, y0, x1, y1) in enumerate([(50, 50, 200, 300),
                                            (250, 80, 500, 400)],
                                           start=1):
        depth[y0:y1, x0:x1] = 1500
        mask[y0:y1, x0:x1] = tid
    Image.fromarray(depth).save(frames / "00000.depth.png")
    Image.fromarray(mask).save(frames / "00000.mask_track.png")
    Image.fromarray(np.full((h, w), 200, dtype=np.uint8)).save(
        frames / "00000.conf.png")
    Image.fromarray(np.zeros((h, w), dtype=np.uint8)).save(
        frames / "00000.mask_class.png")
    (frames / "00000.pose.json").write_text(
        json.dumps({"translation": [0, 0, 0], "rotation_quat": [0, 0, 0, 1]}))
    (frames / "00000.imu.jsonl").write_text("")
    (frames / "00000.objects.json").write_text(json.dumps([
        {"track_id": 1, "class": "chair",
         "bbox2d": [50, 50, 200, 300], "bbox3d": {"center": [0, 0, 1.5],
                                                   "size": [0.4, 0.6, 0.4]}},
        {"track_id": 2, "class": "table",
         "bbox2d": [250, 80, 500, 400], "bbox3d": {"center": [0, 0, 1.5],
                                                    "size": [0.8, 0.5, 0.5]}},
    ]))
    (cap / "intrinsics.json").write_text(json.dumps({
        "camera_matrix": [[500, 0, w / 2], [0, 500, h / 2], [0, 0, 1]],
        "resolution": [w, h], "baseline_m": 0.075,
    }))

    mesh = trimesh.creation.box(extents=(1, 1, 1))
    buf = io.BytesIO()
    mesh.export(buf, file_type="glb")
    glb = buf.getvalue()

    class _Fake:
        def generate_mesh(self, *_, model="hunyuan3d"):
            return MeshCall(
                glb_bytes=glb,
                mesh_origin_detail="runpod:hunyuan3d_2.1",
                mesh_origin="hunyuan3d_2.1",
                ran_on="runpod", generation_s=0.02, pod_id="p", attempts=1,
            )

    report = reconstruct_session(
        cap, "bat", runpod_client=_Fake(),
        cfg=ReconstructorConfig(out_root=tmp_path / "recon"),
    )
    assert report.successes == 2
    _audit_session(report.session_dir)


def test_audit_catches_manifest_with_missing_field(tmp_path: Path) -> None:
    """The audit is load-bearing — it must actually fail on bad data."""
    session = tmp_path / "bad"
    (session / "objects" / "1_chair").mkdir(parents=True)
    (session / "reconstructed.json").write_text(json.dumps({
        "session_id": "bad",
        "objects": [{
            "id": "chair_01", "class": "chair",
            "mesh_path": "objects/1_chair/mesh.glb",
            "crop_image_path": "objects/1_chair/crop.jpg",
            "mesh_origin": "identity",
            "center": [0, 0, 0], "rotation_quat": [0, 0, 0, 1],
            "bbox_min": [0, 0, 0], "bbox_max": [1, 1, 1],
            "lowest_points": [],
        }],
    }))
    (session / "objects" / "1_chair" / "mesh.glb").write_bytes(b"x")
    (session / "objects" / "1_chair" / "crop.jpg").write_bytes(b"x")
    (session / "objects" / "1_chair" / "object_manifest.json").write_text(
        json.dumps({"track_id": 1, "class": "chair"})  # missing fields
    )
    with pytest.raises(AssertionError):
        _audit_session(session)


def test_real_demo_scene_on_disk_if_present(tmp_path: Path) -> None:
    """If the committed demo_scene artifact exists, audit it."""
    p = Path(__file__).resolve().parents[2] / "data" / "reconstructed" / "demo_scene"
    if not p.exists():
        pytest.skip("demo_scene artifact not present in checkout")
    _audit_session(p)
