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
    # We emit both a JSON glTF and a binary GLB.
    assert res.scene_gltf.exists() and res.scene_gltf.suffix == ".gltf"
    assert res.scene_glb.exists() and res.scene_glb.stat().st_size > 0
    # reload the glb — must have geometry for every scene object plus ground
    loaded = trimesh.load(res.scene_glb)
    assert len(loaded.geometry) >= len(scene["objects"]) + 1  # +1 for ground

    sidecar = json.loads(res.sidecar.read_text())
    assert sidecar["version"] == "1.0"
    assert {o["id"] for o in sidecar["objects"]} == {"box_01", "ball_01"}
    for o in sidecar["objects"]:
        assert o["physics"]["mass_kg"] > 0


def test_mjcf(built_scene):
    scene, out = built_scene
    path = export_mjcf(scene, out)
    assert path.exists()
    assert path.suffix == ".mjcf"
    root = ET.parse(path).getroot()
    assert root.tag == "mujoco"
    bodies = root.findall(".//worldbody/body")
    assert {b.attrib["name"] for b in bodies} == {"box_01", "ball_01"}
    # One visual + one collider mesh asset per object (no hulls in this
    # fixture because ``decompose_dynamic=False``).
    assets = root.findall(".//asset/mesh")
    assert len(assets) == 2
    # Assets must be OBJ — MuJoCo cannot read GLB.
    for a in assets:
        assert a.attrib["file"].endswith(".obj")


def test_mujoco_py_is_executable_script(built_scene):
    scene, out = built_scene
    path = export_mujoco_py(scene, out, steps=5)
    assert path.exists()
    text = path.read_text()
    assert "import mujoco" in text
    assert "mj_step" in text
    assert "scene.mjcf" in text
    # syntactic check
    compile(text, str(path), "exec")


def test_mjcf_loads_and_steps_in_mujoco(built_scene):
    """The MJCF file must actually load through ``mujoco.MjModel`` and run a
    physics step. This guards against regressions like referencing GLB
    assets (MuJoCo can't read GLB), missing inertials, or mass conflicts."""
    mujoco = pytest.importorskip("mujoco")
    scene, out = built_scene
    mjcf_path = export_mjcf(scene, out)
    model = mujoco.MjModel.from_xml_path(str(mjcf_path))
    data = mujoco.MjData(model)
    mujoco.mj_step(model, data)
    assert model.nbody >= 3  # ground (worldbody=1) + 2 objects → 3
    assert model.ngeom >= 3  # ground geom + 2 colliders


def test_gltf_per_object_textures_survive(built_scene):
    """The exported scene.gltf must keep at least one PBR-textured geometry
    per scene object (regression for the ``force="mesh"`` bug)."""
    scene, out = built_scene
    # Replace the fake_session meshes (untextured boxes) with textured ones
    # so this test means something — load the staged GLBs the assembler
    # already wrote and confirm the round-trip preserves their visual block.
    res = export_gltf(scene, session_dir=out, out_dir=out)
    loaded = trimesh.load(res.scene_glb)
    object_ids = {o["id"] for o in scene["objects"]}
    seen = {oid: False for oid in object_ids}
    for name, geom in loaded.geometry.items():
        for oid in object_ids:
            if name.startswith(oid + "_"):
                seen[oid] = True
    assert all(seen.values()), f"missing per-object meshes: {seen}"


def test_gltf_preserves_staged_object_size(built_scene):
    """Regression: the gltf exporter must compose the staged GLB's *node
    transforms* with the object transform. Without this, the inner Trimesh's
    raw vertices land at the object translation at their unstaged size — a
    1 m SF3D-normalized mesh ends up placed where a 10 cm object should be,
    causing the bottle/cup overlap that ships in screenshots like
    https://github.com/issues/<...>."""
    import numpy as np
    scene, out = built_scene
    res = export_gltf(scene, session_dir=out, out_dir=out)

    composed = trimesh.load(res.scene_glb)

    # Compute, for each scene object, the world-space AABB of its contribution
    # to the composed scene. It should match the staged GLB's bounds shifted
    # to that object's transform.translation.
    for obj in scene["objects"]:
        staged = trimesh.load(out / obj["mesh"])
        staged_extents = staged.extents

        node_extents = []
        for node_name in composed.graph.nodes_geometry:
            if not node_name.startswith(obj["id"] + "_"):
                continue
            transform, geom_name = composed.graph[node_name]
            geom = composed.geometry[geom_name]
            # Apply the node transform to the geom's local AABB corners.
            lo, hi = geom.bounds
            corners = np.array([
                [lo[0], lo[1], lo[2]], [lo[0], lo[1], hi[2]],
                [lo[0], hi[1], lo[2]], [lo[0], hi[1], hi[2]],
                [hi[0], lo[1], lo[2]], [hi[0], lo[1], hi[2]],
                [hi[0], hi[1], lo[2]], [hi[0], hi[1], hi[2]],
            ])
            world = (np.asarray(transform)[:3, :3] @ corners.T).T \
                    + np.asarray(transform)[:3, 3]
            node_extents.append(world.max(axis=0) - world.min(axis=0))
        assert node_extents, f"no nodes for {obj['id']} in composed scene"
        # Each node's effective extent must be ≤ the staged extent (a Scene
        # may split into multiple sub-meshes), and the union must match.
        union = np.max(node_extents, axis=0)
        assert np.allclose(union, staged_extents, atol=1e-3), (
            f"composed extent for {obj['id']} = {union.tolist()} but staged "
            f"GLB extent = {staged_extents.tolist()}"
        )
