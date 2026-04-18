"""Assembler end-to-end on a synthetic stub session."""

from __future__ import annotations

from pathlib import Path

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
