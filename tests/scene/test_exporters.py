"""Golden-fixture round-trip tests for the 3 required exporters.

We build a scene from the stub session, run each exporter, and then do a
shallow re-load to prove the output is valid for its target loader.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import trimesh

from scene.assembler import AssemblerConfig, SceneAssembler
from scene.exporters import export_gltf, export_mjcf, export_mujoco_py


class _FakeVLM:
    def infer(self, class_name, image_bytes):
        return {
            "mass_kg": 1.5, "friction": 0.5, "restitution": 0.2,
            "material": "wood", "is_rigid": True, "reasoning": "",
        }


@pytest.fixture()
def built_scene(fake_session: Path, tmp_path: Path):
    out = tmp_path / "scenes" / "demo"
    cfg = AssemblerConfig(decompose_dynamic=False)
    scene = SceneAssembler(cfg, vlm_client=_FakeVLM()).assemble(fake_session, out)
    return scene, out


def test_gltf_and_sidecar(built_scene):
    scene, out = built_scene
    res = export_gltf(scene, session_dir=out, out_dir=out)
    assert res.scene_glb.exists() and res.scene_glb.stat().st_size > 0
    # reload the glb — must have geometry
    loaded = trimesh.load(res.scene_glb)
    assert len(loaded.geometry) >= 1

    sidecar = json.loads(res.sidecar.read_text())
    assert sidecar["version"] == "1.0"
    assert {o["id"] for o in sidecar["objects"]} == {"box_01", "ball_01"}
    for o in sidecar["objects"]:
        assert o["physics"]["mass_kg"] > 0


def test_mjcf(built_scene):
    scene, out = built_scene
    path = export_mjcf(scene, out)
    assert path.exists()
    root = ET.parse(path).getroot()
    assert root.tag == "mujoco"
    bodies = root.findall(".//worldbody/body")
    assert {b.attrib["name"] for b in bodies} == {"box_01", "ball_01"}
    assets = root.findall(".//asset/mesh")
    assert len(assets) == 2


def test_mujoco_py_is_executable_script(built_scene):
    scene, out = built_scene
    path = export_mujoco_py(scene, out, steps=5)
    assert path.exists()
    text = path.read_text()
    assert "import mujoco" in text
    assert "mj_step" in text
    # syntactic check
    compile(text, str(path), "exec")
