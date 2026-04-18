# Stream 03 — Scene Assembly

The frozen `scene.json` contract (ADR-001) is the single source of truth that
Person 4's browser viewer, MuJoCo judges, and any robotics/sim pipeline all
consume. This module owns it and every exporter that fans it out.

See: [`../plans/03-scene-assembly.md`](../plans/03-scene-assembly.md),
[`../adr/ADR-001-scene-spec-source-of-truth.md`](../adr/ADR-001-scene-spec-source-of-truth.md),
[`../../spec/scene.schema.json`](../../spec/scene.schema.json),
[`../../spec/scene.example.json`](../../spec/scene.example.json).

## Pipeline

```
Stream 02 ReconstructedObject set
            │
            ▼
      SceneAssembler
      ├── ground plane estimator (ground.py)
      ├── VLM physics inference  (vlm.py)   ──► lookup table fallback (lookup.py + config/physics_lookup.yaml)
      └── CoACD convex decomposition (decomp.py)
            │
            ▼
        scene.json  ◄── validated against spec/scene.schema.json
        meshes/*.glb
        hulls/*.glb
            │
            ▼
     ┌──────┼──────┬──────┐
     ▼      ▼      ▼      ▼
   glTF   MJCF  MuJoCo  USD
   +sidecar      .py    (stretch)
```

## Schema semantics (v1.0)

| Field | Meaning |
|---|---|
| `version` | Frozen at `"1.0"`. Any breaking change requires queen sign-off (plan §7). Additive bumps: `"1.0.1"`. |
| `world.gravity` | 3-vector, m/s². |
| `world.up_axis` | `"y"` (default) or `"z"`. |
| `world.unit` | Always `"meters"`. |
| `ground.type` | `"plane"` only in v1.0. |
| `ground.normal` | Unit vector, world frame. |
| `ground.material` | `{friction, restitution}`. |
| `objects[]` | Up to 8 scene objects. |
| `objects[].id` | Unique across the scene. |
| `objects[].class` | Semantic label (e.g. `chair`). Used to look up physics when VLM falls back. |
| `objects[].mesh` | Relative path to a glTF under the scene directory. |
| `objects[].transform` | World-space `{translation, rotation_quat, scale}`. Quaternion is `xyzw`. |
| `objects[].collider` | `{shape, convex_decomposition?, hull_paths?, radius?, half_extents?}`. `shape` is one of `mesh`, `sphere`, `box`, `capsule`. |
| `objects[].physics` | `{mass_kg, friction, restitution, is_rigid}`. `restitution ∈ [0, 1]`. |
| `objects[].material_class` | Free-form (VLM returns one of 10 canonical materials). |
| `objects[].source` | Provenance: mesh origin (`hunyuan3d_2.1` \| `triposg_1.5b` \| `sf3d` \| `identity`), physics origin (`vlm` \| `lookup` \| `manual`), optional `vlm_reasoning`. |
| `camera_pose` | The reference camera pose (Person 4 uses it as the default viewer pose). |

## Run-book

### Install

```bash
pip install -e .[dev]            # core + tests
pip install -e .[dev,usd]        # + stretch USD exporter
pip install -e .[dev,gemini]     # + Gemini 3.1 Pro backup VLM
pip install -e .[dev,qwen]       # + Qwen3-VL cheap-path VLM
```

### Assemble a scene from a Stream 02 session

```python
from pathlib import Path
from scene import SceneAssembler, AssemblerConfig
from scene.exporters import export_gltf, export_mjcf, export_mujoco_py

session = Path("data/reconstructed/demo_scene")
out     = Path("data/scenes/demo_scene")

scene = SceneAssembler(AssemblerConfig()).assemble(session, out)

export_gltf(scene, session_dir=out, out_dir=out)   # → scene.glb + scene.glb.physics.json
export_mjcf(scene, out)                            # → scene.xml
export_mujoco_py(scene, out)                       # → scene.py
```

### Choose a VLM

```bash
export VID2SIM_VLM=claude     # default — Claude Opus 4.7
export VID2SIM_VLM=gemini     # Gemini 3.1 Pro (requires google-genai)
export VID2SIM_VLM=qwen       # Qwen3-VL-30B-A3B-Instruct (requires OpenAI-compatible endpoint)
```

VLM failures (timeout, schema violation, network) silently fall back to
`config/physics_lookup.yaml`. Source provenance (`source.physics_origin`)
records which path produced the numbers.

### CI / gate checks

```bash
pytest --cov=src/scene/exporters tests/scene
python -m jsonschema -i spec/scene.example.json spec/scene.schema.json
```

- **G0 gate**: `spec/scene.example.json` validates against
  `spec/scene.schema.json`.
- **G4 gate**: ≥ 80% exporter coverage (`--cov=src/scene/exporters`).

## Physics lookup table

`config/physics_lookup.yaml` covers the 15 demo classes (chair, table,
sofa, bed, bookshelf, book, mug, cup, bottle, ball, laptop, lamp, plant,
apple, orange) plus a `__default__` entry so unknown classes never crash
the pipeline. Edit this file when adding a new demo class; tests lock
the `__default__` entry.

## CoACD (convex decomposition)

CoACD 1.0.10, CPU-only. Invoked only for objects whose `class_name` is in
`AssemblerConfig.dynamic_classes` and whose `decompose_dynamic` is `True`.
Hulls are capped at 8 per object (plan §7 risk row); if CoACD produces
more, we keep the largest-volume ones and drop the rest. Outputs live
under `scene_out/hulls/` and are referenced by relative path from
`collider.hull_paths`.

## VLM visual prompting (PhysQuantAgent-style)

Before the VLM sees a crop we overlay:

- a green bbox rectangle,
- a green centroid dot,
- a red reference ruler whose pixel length encodes the real-world longest
  bbox side in meters (so the VLM can calibrate its mass estimate).

This is arXiv 2603.16958's technique, independent of the VLM backend.
See `scene/vlm.py:prepare_visual_prompt`.

## Day-of-demo

1. Pre-build `data/scenes/demo_scene/` before the pitch.
2. Keep `spec/scene.example.json` demo-loadable as a backup.
3. Talking point: *"the same `scene.json` emits to glTF for the browser,
   MJCF and MuJoCo `.py` for robotics/sim, USD for DCC pipelines — one
   spec, four consumers."*
