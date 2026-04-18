"""Batch driver — produces the full demo-scene ReconstructedObject set."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def _write_synthetic_bundle(tmp_path: Path, objects: list[dict],
                            width: int = 640, height: int = 480) -> Path:
    """Emit a valid PerceptionFrame bundle with N objects masked in depth."""
    cap = tmp_path / "captures" / "demo_scene"
    frames = cap / "frames"
    frames.mkdir(parents=True)

    rgb = Image.new("RGB", (width, height), color=(120, 120, 120))
    rgb.save(frames / "00000.rgb.jpg", "JPEG", quality=85)

    depth = np.full((height, width), 3000, dtype=np.uint16)  # wall
    mask_track = np.zeros((height, width), dtype=np.uint16)
    for meta in objects:
        x0, y0, x1, y1 = (int(v) for v in meta["bbox2d"])
        z_mm = int(meta.get("distance_m", 1.5) * 1000)
        depth[y0:y1, x0:x1] = z_mm
        mask_track[y0:y1, x0:x1] = int(meta["track_id"])
    Image.fromarray(depth).save(frames / "00000.depth.png")
    Image.fromarray(mask_track).save(frames / "00000.mask_track.png")
    Image.fromarray(np.full((height, width), 255, dtype=np.uint8)).save(
        frames / "00000.conf.png"
    )
    Image.fromarray(np.zeros((height, width), dtype=np.uint8)).save(
        frames / "00000.mask_class.png"
    )

    (frames / "00000.pose.json").write_text(
        json.dumps({"translation": [0, 0, 0], "rotation_quat": [0, 0, 0, 1]})
    )
    (frames / "00000.imu.jsonl").write_text("")
    (frames / "00000.objects.json").write_text(json.dumps([
        {"track_id": m["track_id"], "class": m["class"],
         "bbox2d": m["bbox2d"],
         "bbox3d": m.get("bbox3d", {"center": [0, 0, 1.5],
                                    "size": [0.4, 0.6, 0.4]}),
         "conf": m.get("conf", 0.9)}
        for m in objects
    ]))

    (cap / "intrinsics.json").write_text(json.dumps({
        "camera_matrix": [[500, 0, width // 2], [0, 500, height // 2],
                          [0, 0, 1]],
        "resolution": [width, height], "baseline_m": 0.075,
    }))
    (cap / "capture_manifest.json").write_text(json.dumps({
        "session_id": "demo_scene", "frame_count": 1,
    }))
    return cap


def _box_glb(extents=(1, 1, 1)) -> bytes:
    m = trimesh.creation.box(extents=extents)
    buf = io.BytesIO()
    m.export(buf, file_type="glb")
    return buf.getvalue()


class _FakeClient:
    def __init__(self, glb_bytes: bytes) -> None:
        from reconstruction.runpod_client import MeshCall
        self._MeshCall = MeshCall
        self._glb = glb_bytes
        self.calls = 0

    def generate_mesh(self, rgb, mask, *, model="hunyuan3d"):
        self.calls += 1
        return self._MeshCall(
            glb_bytes=self._glb,
            mesh_origin_detail=f"runpod:{model}",
            mesh_origin=("hunyuan3d_2.1" if model == "hunyuan3d" else "triposg_1.5b"),
            ran_on="runpod",
            generation_s=0.01, pod_id="demo-pod", attempts=1,
        )


def test_batch_produces_three_objects(tmp_path: Path) -> None:
    from reconstruction.batch import reconstruct_session
    from reconstruction.hero_orchestrator import ReconstructorConfig

    cap = _write_synthetic_bundle(tmp_path, [
        {"track_id": 1, "class": "chair",
         "bbox2d": [50, 50, 200, 300],  "distance_m": 1.5},
        {"track_id": 2, "class": "table",
         "bbox2d": [250, 80, 500, 400], "distance_m": 2.0},
        {"track_id": 3, "class": "cup",
         "bbox2d": [520, 200, 620, 320], "distance_m": 1.2},
    ])
    client = _FakeClient(_box_glb())
    cfg = ReconstructorConfig(out_root=tmp_path / "recon")

    report = reconstruct_session(
        cap, "demo_scene",
        runpod_client=client, cfg=cfg, max_objects=5,
    )
    assert report.successes == 3
    assert report.total_objects == 3
    assert client.calls == 3
    assert all(o == "hunyuan3d_2.1" for o in report.mesh_origins)
    assert report.session_dir.exists()

    # Verify the full bundle layout
    idx = json.loads((report.session_dir / "reconstructed.json").read_text())
    assert len(idx["objects"]) == 3
    assert (report.session_dir / "world_pose.json").exists()

    # Every object has the required files
    for obj in idx["objects"]:
        assert (report.session_dir / obj["mesh_path"]).exists()
        assert (report.session_dir / obj["crop_image_path"]).exists()

    # Person 3 can load without error
    from scene.reconstructed import load_session
    objs = load_session(report.session_dir)
    assert len(objs) == 3


def test_batch_caps_at_max_objects(tmp_path: Path) -> None:
    from reconstruction.batch import reconstruct_session
    from reconstruction.hero_orchestrator import ReconstructorConfig

    objs = [
        {"track_id": i, "class": f"obj{i}",
         "bbox2d": [10 + i*40, 10, 40 + i*40, 100], "distance_m": 1.5}
        for i in range(1, 9)
    ]
    cap = _write_synthetic_bundle(tmp_path, objs)
    client = _FakeClient(_box_glb())

    report = reconstruct_session(
        cap, "demo_scene",
        runpod_client=client,
        cfg=ReconstructorConfig(out_root=tmp_path / "recon"),
        max_objects=3,
    )
    assert report.successes == 3


def test_batch_watchdog_is_polled(tmp_path: Path) -> None:
    """Polling every object keeps the pod status fresh."""
    from reconstruction.batch import reconstruct_session
    from reconstruction.hero_orchestrator import ReconstructorConfig

    cap = _write_synthetic_bundle(tmp_path, [
        {"track_id": 1, "class": "a", "bbox2d": [50, 50, 200, 200],
         "distance_m": 1.5},
        {"track_id": 2, "class": "b", "bbox2d": [220, 50, 400, 200],
         "distance_m": 1.5},
    ])
    client = _FakeClient(_box_glb())

    class _CountingWatchdog:
        def __init__(self): self.checks = 0; self._tripped = False
        def check_once(self): self.checks += 1
        def has_tripped(self): return self._tripped

    wd = _CountingWatchdog()
    reconstruct_session(
        cap, "demo_scene",
        runpod_client=client,
        watchdog=wd,
        cfg=ReconstructorConfig(out_root=tmp_path / "recon"),
    )
    # One pre-check + one after each object = 3
    assert wd.checks == 3
