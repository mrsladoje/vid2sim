"""Assembler end-to-end on a synthetic stub session."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scene import schema
from scene.assembler import AssemblerConfig, SceneAssembler


class _FakeVLM:
    def infer(self, class_name, image_bytes):
        return {
            "mass_kg": 2.0,
            "friction": 0.5,
            "restitution": 0.3,
            "material": "plastic",
            "is_rigid": True,
            "reasoning": "synthetic",
        }


def test_assemble_stub(fake_session: Path, tmp_path: Path):
    out = tmp_path / "scenes/stub_01"
    cfg = AssemblerConfig(decompose_dynamic=False)
    scene = SceneAssembler(cfg, vlm_client=_FakeVLM()).assemble(fake_session, out)

    schema.validate(scene)
    assert len(scene["objects"]) == 2
    ids = {o["id"] for o in scene["objects"]}
    assert ids == {"box_01", "ball_01"}

    ball = next(o for o in scene["objects"] if o["id"] == "ball_01")
    assert ball["collider"]["shape"] == "sphere"
    assert ball["collider"]["radius"] > 0

    box = next(o for o in scene["objects"] if o["id"] == "box_01")
    assert box["collider"]["shape"] == "mesh"

    assert (out / "scene.json").exists()
    assert (out / "meshes" / "box_01.glb").exists()
    assert (out / "meshes" / "ball_01.glb").exists()


def test_assemble_without_vlm_uses_lookup(fake_session: Path, tmp_path: Path):
    out = tmp_path / "scenes/stub_02"
    cfg = AssemblerConfig(use_vlm=False, decompose_dynamic=False)
    scene = SceneAssembler(cfg).assemble(fake_session, out)
    for o in scene["objects"]:
        assert o["source"]["physics_origin"] == "lookup"


def test_assemble_full_emits_all_artifacts(fake_session: Path, tmp_path: Path):
    """``assemble_full`` must produce scene.json + glTF + MJCF + scene.py +
    PROVENANCE in one shot — that's what the CLI relies on."""
    out = tmp_path / "scenes/full"
    cfg = AssemblerConfig(use_vlm=False, decompose_dynamic=False)
    result = SceneAssembler(cfg).assemble_full(fake_session, out, run_exporters=True)

    assert result.scene["version"] == "1.0"
    assert result.wall_time_s >= 0
    for key in ("scene_json", "scene_gltf", "scene_glb",
                "scene_mjcf", "scene_py", "sidecar", "provenance"):
        assert key in result.artifacts, f"missing artifact: {key}"
        assert result.artifacts[key].exists()

    provenance_text = (out / "PROVENANCE.md").read_text()
    assert "session_id" in provenance_text
    assert "Wall time" in provenance_text


def test_snap_to_ground_places_objects_above_floor(fake_session: Path,
                                                   tmp_path: Path):
    """With ``snap_to_ground=True`` (the default), every object's translation
    along the up-axis must be ≥ ground.offset (objects sit on or above the
    floor, never below)."""
    out = tmp_path / "scenes/snap"
    cfg = AssemblerConfig(use_vlm=False, decompose_dynamic=False)
    scene = SceneAssembler(cfg).assemble(fake_session, out)
    # The fake_session doesn't carry a ground offset in scene.ground, but the
    # convention is "y" up-axis with a ground at y≈0 (the box sits at y=0).
    for o in scene["objects"]:
        assert o["transform"]["translation"][1] >= -1e-6


def test_baked_rotation_quat_is_identity(fake_session: Path, tmp_path: Path):
    """The assembler bakes Stream 02's world rotation into the staged mesh,
    so scene.json's per-object rotation_quat must be identity to avoid
    double-rotation in the renderer."""
    out = tmp_path / "scenes/rot"
    cfg = AssemblerConfig(use_vlm=False, decompose_dynamic=False)
    scene = SceneAssembler(cfg).assemble(fake_session, out)
    for o in scene["objects"]:
        assert o["transform"]["rotation_quat"] == [0.0, 0.0, 0.0, 1.0]


# --------------------------------------------------------------------------
# Regression tests against the real Stream 02 ``rec_01_sf3d`` fixture.
# These exercise the SF3D-specific code paths (textured PBR atlases,
# embedded node transforms, broken bbox metadata) that the synthetic
# fake_session can't exercise.
# --------------------------------------------------------------------------

REC_01_PATH = Path(__file__).resolve().parents[2] / "data" / "reconstructed" / "rec_01_sf3d"


@pytest.mark.skipif(not REC_01_PATH.exists(),
                    reason="rec_01_sf3d fixture missing")
def test_assemble_rec_01_sf3d_textures_preserved(tmp_path: Path):
    """End-to-end on the real SF3D reconstruction: every staged mesh must
    keep its PBR base-color texture."""
    import trimesh

    out = tmp_path / "scenes/rec_01_sf3d"
    cfg = AssemblerConfig(use_vlm=False, decompose_dynamic=False)
    SceneAssembler(cfg).assemble(REC_01_PATH, out)

    for staged in (out / "meshes").glob("*.glb"):
        loaded = trimesh.load(staged)
        # Must be a Scene (textures only survive when not flattened).
        assert isinstance(loaded, trimesh.Scene), f"{staged} flattened"
        any_textured = False
        for inner in loaded.geometry.values():
            mat = getattr(getattr(inner, "visual", None), "material", None)
            if mat is not None and getattr(mat, "baseColorTexture", None) is not None:
                any_textured = True
                break
        assert any_textured, f"{staged} lost its baseColorTexture"


@pytest.mark.skipif(not REC_01_PATH.exists(),
                    reason="rec_01_sf3d fixture missing")
def test_rec_01_sf3d_objects_above_ground(tmp_path: Path):
    """Snap-to-ground must put SF3D objects above the ground plane even when
    Stream 02's bbox metadata is degenerate (sub-cm)."""
    out = tmp_path / "scenes/rec_01_sf3d"
    cfg = AssemblerConfig(use_vlm=False, decompose_dynamic=False)
    scene = SceneAssembler(cfg).assemble(REC_01_PATH, out)
    # Ground.offset isn't in the schema, but estimate_ground for this fixture
    # falls back to min(bbox_min_y) ≈ 0.088 m. Bottle/cup must be above that.
    for o in scene["objects"]:
        assert o["transform"]["translation"][1] > 0.05, (
            f"{o['id']} sits at y={o['transform']['translation'][1]}; "
            f"snap-to-ground failed"
        )
