"""Shared fixtures for scene tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh

SPEC_DIR = Path(__file__).resolve().parents[2] / "spec"


@pytest.fixture()
def scene_example() -> dict:
    with (SPEC_DIR / "scene.example.json").open() as fh:
        return json.load(fh)


@pytest.fixture()
def scene_schema_dict() -> dict:
    with (SPEC_DIR / "scene.schema.json").open() as fh:
        return json.load(fh)


@pytest.fixture()
def fake_session(tmp_path: Path) -> Path:
    """A minimal Stream 02 session directory with one cube mesh."""
    session = tmp_path / "session"
    (session / "meshes").mkdir(parents=True)
    (session / "crops").mkdir()

    cube = trimesh.creation.box(extents=[0.5, 0.5, 0.5])
    cube.export(session / "meshes" / "box_01.glb")
    ball = trimesh.creation.icosphere(subdivisions=2, radius=0.12)
    ball.export(session / "meshes" / "ball_01.glb")

    # 1x1 RGB crop images
    from PIL import Image
    Image.new("RGB", (64, 64), (128, 90, 40)).save(session / "crops" / "box_01.png")
    Image.new("RGB", (64, 64), (30, 120, 200)).save(session / "crops" / "ball_01.png")

    manifest = {
        "objects": [
            {
                "id": "box_01",
                "class": "book",
                "mesh_path": "meshes/box_01.glb",
                "crop_image_path": "crops/box_01.png",
                "mesh_origin": "hunyuan3d_2.1",
                "center": [0.0, 0.25, 0.0],
                "rotation_quat": [0, 0, 0, 1],
                "bbox_min": [-0.25, 0.0, -0.25],
                "bbox_max": [0.25, 0.5, 0.25],
                "lowest_points": [
                    [-0.25, 0.0, -0.25], [0.25, 0.0, -0.25],
                    [0.25, 0.0, 0.25], [-0.25, 0.0, 0.25],
                ],
            },
            {
                "id": "ball_01",
                "class": "ball",
                "mesh_path": "meshes/ball_01.glb",
                "crop_image_path": "crops/ball_01.png",
                "mesh_origin": "identity",
                "center": [0.6, 0.12, 0.0],
                "rotation_quat": [0, 0, 0, 1],
                "bbox_min": [0.48, 0.0, -0.12],
                "bbox_max": [0.72, 0.24, 0.12],
                "lowest_points": [[0.6, 0.0, 0.0]],
            },
        ]
    }
    with (session / "reconstructed.json").open("w") as fh:
        json.dump(manifest, fh)
    return session
