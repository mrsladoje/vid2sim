"""ReconstructedObject contract (consumed from Stream 02).

The anti-corruption boundary: the assembler only touches these fields.
Stream 02 writes `reconstructed.json` per session directory; this module
loads and validates the shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MeshOrigin = Literal["hunyuan3d_2.1", "triposg_1.5b", "sf3d", "identity"]


@dataclass(frozen=True)
class ReconstructedObject:
    id: str
    class_name: str
    mesh_path: str
    crop_image_path: str
    mesh_origin: MeshOrigin
    center: tuple[float, float, float]
    rotation_quat: tuple[float, float, float, float]
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    lowest_points: list[tuple[float, float, float]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "ReconstructedObject":
        return cls(
            id=data["id"],
            class_name=data["class"],
            mesh_path=data["mesh_path"],
            crop_image_path=data["crop_image_path"],
            mesh_origin=data["mesh_origin"],
            center=tuple(data["center"]),
            rotation_quat=tuple(data["rotation_quat"]),
            bbox_min=tuple(data["bbox_min"]),
            bbox_max=tuple(data["bbox_max"]),
            lowest_points=[tuple(p) for p in data.get("lowest_points", [])],
        )


def load_session(session_dir: Path) -> list[ReconstructedObject]:
    """Load every ReconstructedObject from a Stream 02 session directory.

    Expects `session_dir/reconstructed.json` with a top-level `objects` array.
    """
    manifest = session_dir / "reconstructed.json"
    with manifest.open() as fh:
        payload = json.load(fh)
    objects = [ReconstructedObject.from_dict(o) for o in payload["objects"]]
    for obj in objects:
        mesh = session_dir / obj.mesh_path
        if not mesh.exists():
            raise FileNotFoundError(f"Mesh missing for {obj.id}: {mesh}")
    return objects
