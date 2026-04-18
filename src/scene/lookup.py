"""Class-label → physics lookup table.

Default path: `config/physics_lookup.yaml`. Returns a physics block suitable
for dropping into `scene.json.objects[i].physics`. Falls back to a neutral
"unknown" entry so the pipeline never crashes on an unseen class.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

LOOKUP_PATH = Path(__file__).resolve().parents[2] / "config" / "physics_lookup.yaml"


@lru_cache(maxsize=1)
def load_lookup(path: Path | None = None) -> dict:
    target = Path(path) if path else LOOKUP_PATH
    with target.open() as fh:
        return yaml.safe_load(fh)


def physics_for(class_name: str, path: Path | None = None) -> dict:
    table = load_lookup(path)
    entry = table.get(class_name) or table["__default__"]
    return {
        "mass_kg": float(entry["mass_kg"]),
        "friction": float(entry["friction"]),
        "restitution": float(entry["restitution"]),
        "is_rigid": bool(entry.get("is_rigid", True)),
    }


def material_for(class_name: str, path: Path | None = None) -> str:
    table = load_lookup(path)
    entry = table.get(class_name) or table["__default__"]
    return entry.get("material", "unknown")
