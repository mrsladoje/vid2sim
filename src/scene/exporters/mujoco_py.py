"""MuJoCo headless `.py` exporter.

Emits a runnable Python script that drives the scene through `mujoco`
v3.3.2+. The script assumes `scene.xml` (MJCF) and `meshes/` live next to
it, which is what the assembler lays down.

Stay on CPU MuJoCo per plan §1 — MJX-on-Metal is experimental.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent


SCRIPT = '''\
"""Headless MuJoCo runner for a VID2SIM scene (exported by Stream 03)."""

from pathlib import Path

import mujoco


SCENE_XML = Path(__file__).with_name("scene.mjcf")


def run(steps: int = {steps}) -> None:
    model = mujoco.MjModel.from_xml_path(str(SCENE_XML))
    data = mujoco.MjData(model)
    for _ in range(steps):
        mujoco.mj_step(model, data)
    print(f"ran {{steps}} steps on model with {{model.nbody}} bodies")


if __name__ == "__main__":
    run()
'''


def export_mujoco_py(scene: dict, out_dir: Path, steps: int = 1000) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "scene.py"
    out.write_text(dedent(SCRIPT.format(steps=steps)))
    return out
