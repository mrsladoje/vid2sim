# Stream 03 — Scene Assembly (Person 3)

> Bounded context: the heart of the project. Person 3 **owns the published contract `scene.json`** (ADR-001) and all exporters that fan it out to downstream simulators. This is the most important hand-off in the project: freezing the schema by **G0 (H2)** unblocks Person 4 for the full 24 h.

See also: [`../PHASED_PLAN.md`](../PHASED_PLAN.md), [`../adr/ADR-001-scene-spec-source-of-truth.md`](../adr/ADR-001-scene-spec-source-of-truth.md), [`../adr/ADR-005-vlm-physics-inference.md`](../adr/ADR-005-vlm-physics-inference.md), [`../VID2SIM_PRD.md`](../VID2SIM_PRD.md) §7 Stage C, §7 Stage D, §9, §10.

---

## 1. Scope & bounded context

**Owns**
- `spec/scene.schema.json` — the JSON Schema (draft 2020-12) for `scene.json`. **Frozen at G0; versioned; breaking changes require queen sign-off + notify all streams.**
- VLM physics-property inference (Claude Opus 4.7 primary, Gemini 3.1 fallback) with structured JSON output.
- Class-label lookup-table fallback (`{chair: {mass: 5, μ: 0.5, material: wood, rigid: true}, ...}`).
- Scene assembler: reads `ReconstructedObject` set + ground estimate → emits `scene.json` + `meshes/*.glb`.
- V-HACD convex decomposition pipeline (`trimesh.decomposition.convex_decomposition` or `coacd` wrapper) — runs in the assembler, results written into collider sub-object.
- Exporters: **glTF+sidecar physics JSON** (primary), **MJCF** (required), **PyBullet `.py`** (required), **USD** (stretch).
- Canonical `scene.json` fixtures for CI regression.

**Does not own**
- Anything upstream of ReconstructedObject — Persons 1, 2.
- Browser viewer runtime — Person 4 (consumes the glTF + sidecar).

---

## 2. Ubiquitous language (Scene)

| Term | Meaning |
|---|---|
| **SceneSpec** | The abstract concept; concrete form is one `scene.json` file + a `meshes/` dir. |
| **Scene object** | An entry in `scene.json.objects[]`: id, class, mesh, transform, collider, physics, material_class, source. |
| **Ground estimate** | A plane fit to the lowest-points of reconstructed objects; becomes `scene.json.ground`. |
| **Convex decomposition** | A mesh's collision proxy as N convex hulls, required for **dynamic** Rapier bodies. |
| **Physics block** | `{mass_kg, friction, restitution, is_rigid}` attached to a scene object. |
| **Provenance (scene level)** | Per-object `source` block tracking which model produced the mesh and where physics came from. |
| **Sidecar physics JSON** | A `.physics.json` file next to `scene.glb` — avoids the unratified `KHR_physics_rigid_bodies` extension. |
| **Lookup table** | `config/physics_lookup.yaml` — class → default physics block. |

---

## 3. External dependencies (consumed)

| From | What | Format |
|---|---|---|
| Person 2 | ReconstructedObject set | `data/reconstructed/<session>/` per `spec/reconstructed_object.md` |
| — | VLM API (Claude Opus 4.7 / Gemini 3.1) | HTTPS, structured JSON output |
| — | V-HACD or CoACD | Python package |

Anti-corruption layer: the assembler only touches the ReconstructedObject contract fields. It does not import anything from `src/reconstruction/`. It does not read `PerceptionFrame` files.

---

## 4. External deliverables (produced)

```
data/scenes/<session_id>/
  scene.json              # spec/scene.schema.json (v1.0)
  scene.glb               # concatenated/linked meshes + ground
  scene.glb.physics.json  # sidecar with mass/friction/restitution per object
  scene.xml               # MJCF
  scene.py                # PyBullet headless script
  scene.usd               # stretch
  meshes/                 # per-object glTFs (referenced by scene.json)
spec/
  scene.schema.json       # the FROZEN contract (v1.0)
  scene.example.json      # hand-crafted demo fixture (3 objects)
```

Consumers:
- **Person 4** reads `scene.glb` + `scene.glb.physics.json` + `scene.json` for UI labels. No other contract.
- Judges with MuJoCo / PyBullet installs read `scene.xml` / `scene.py`.

---

## 5. Phased tasks

| Phase | Window | Task | Subtask | Artifact |
|---|---|---|---|---|
| G0 | H0–H2 | **Freeze `scene.schema.json` v1.0** | Copy PRD §9 example, convert to JSON Schema draft 2020-12, circulate to all 3 other streams, collect signoffs | `spec/scene.schema.json` v1.0 |
| G0 | H0–H2 | Publish canonical fixture | Hand-craft a 3-object scene (chair + ball + ground); validate against schema; hand to Person 4 | `spec/scene.example.json` |
| G0 | H0–H2 | Scaffold assembler package | `src/scene/` with `assembler.py`, `vlm.py`, `exporters/` | green CI |
| G0 | H0–H2 | Contract review with Person 2 | Walk through `ReconstructedObject` → `scene.json` mapping | `spec/reconstructed_object.md` co-signed |
| **G0 gate** | H2 | Schema frozen; example validates; Person 4 has a fixture to render | — | — |
| G1 | H2–H6 | Assembler v0 (stub-data) | Reads ReconstructedObject stubs from Person 2 → emits valid `scene.json` with lookup-table physics | `data/scenes/stub_01/scene.json` |
| G1 | H2–H6 | Lookup-table fallback | Hand-author `config/physics_lookup.yaml` for ~15 common indoor classes | `config/physics_lookup.yaml` |
| G1 | H2–H6 | glTF + sidecar exporter v0 | Packages per-object meshes into `scene.glb`; writes `scene.glb.physics.json` | `src/scene/exporters/gltf.py` |
| G1 | H2–H6 | MJCF exporter v0 | Template-driven, rigid bodies only | `src/scene/exporters/mjcf.py` |
| **G1 gate** | H6 | Stub `scene.json` + `.glb` end-to-end valid; Person 4 loads them in viewer | — | — |
| G2 | H6–H12 | VLM physics inference | `vlm.py`: structured JSON, batched request, schema validation on response, timeout → lookup fallback | `src/scene/vlm.py` |
| G2 | H6–H12 | Convex decomposition pipeline | Per scene object, run V-HACD; write hulls into collider block (or cache side-by-side) | `src/scene/decomp.py` |
| G2 | H6–H12 | Ground plane estimator | Fit plane to lowest 10% of reconstructed points; emit `ground` block | `src/scene/ground.py` |
| G2 | H6–H12 | End-to-end on hero object | Read `data/reconstructed/hero_01/` → emit full `scene.json` + exports | `data/scenes/hero_01/` |
| G2 | H6–H12 | PyBullet exporter | Template emits a runnable `scene.py` that loads all meshes + physics | `src/scene/exporters/pybullet.py` |
| **G2 gate** | H12 | Hero object → scene.json + 3 exporter outputs; Person 4 loads `scene.glb` with physics | — | — |
| G3 | H12–H18 | Full demo scene | Run on `data/reconstructed/demo_scene/` (3–5 objects) | `data/scenes/demo_scene/` |
| G3 | H12–H18 | USD exporter (stretch) | `usd-core` + `UsdPhysics` schema; skip if behind | `src/scene/exporters/usd.py` |
| G3 | H12–H18 | Exporter round-trip tests | Golden fixtures: load `scene.example.json`, export, diff | `tests/scene/test_exporters.py` |
| G3 | H12–H18 | Feature freeze | No schema changes after H18 | — |
| **G3 gate** | H18 | Full demo scene exports to glTF+MJCF+PyBullet; USD if possible | — | — |
| G4 | H18–H22 | Tests to 80% on exporters | Canonical fixtures, schema-validation tests, round-trip | pytest coverage report |
| G4 | H18–H22 | Schema docs | `docs/scene/README.md` with example JSON and field semantics | docs |
| **G4 gate** | H22 | CI green; ≥80% coverage on exporters (per PRD NFR); schema validator green | — | — |
| G5 | H22–H24 | Demo standby | Pre-built `data/scenes/demo_scene/` staged, backup `stub_01` warm | — |

---

## 6. Phase gates

| Gate | Automated check | Manual check | Artifact check | If red |
|---|---|---|---|---|
| G0 | `ajv validate` passes `spec/scene.example.json` against `spec/scene.schema.json` | Each of Persons 1, 2, 4 has read the schema and has no blocking objections | `spec/scene.schema.json` checked in; `spec/scene.example.json` checked in | **BLOCKS ALL STREAMS.** Work intensively to resolve; escalate to Queen within 30 min. |
| G1 | `scene.json` emitted from stubs validates against schema; glTF loads in Three.js headless test | Person 4 opens `stub_01/scene.glb` in viewer, sees shapes | `data/scenes/stub_01/` complete | Emit a hand-fixed scene from `scene.example.json` so Person 4 is unblocked; fix assembler async |
| G2 | VLM call returns schema-valid JSON on 3-object test set; fallback fires on simulated timeout | Open `hero_01/scene.json`, eyeball physics values for plausibility | `data/scenes/hero_01/` has all 4 primary artifacts | VLM schema violation: fall back to lookup; flag coverage gap and continue |
| G3 | All 3 required exporters produce files that load in their respective loaders (headless) | Person 4 drops demo scene's ball, it bounces on chair | `data/scenes/demo_scene/` complete | Drop USD; cap scene to 3 objects; keep MJCF+glTF+PyBullet |
| G4 | `pytest --cov=src/scene/exporters` ≥80%; `ajv` validates all fixtures | — | `docs/scene/README.md` present | Drop PyBullet coverage target; focus on glTF+MJCF as hard 80% |
| G5 | — | Two clean dry-runs from ReconstructedObject → browser viewer | Backup `stub_01` scene still loads | Ship backup; continue |

---

## 7. Risk & fallback (stream-specific)

| Risk | Likelihood | Fallback |
|---|---|---|
| Schema slip — someone proposes a breaking change mid-day | Medium | **Rule: no breaking changes after G1.** Additive-only after H6. Version field `"1.0"` is load-bearing. Use `"1.0.1"` for additive fields. |
| VLM network blocked at venue | Medium | Tether via phone; else lookup table fully covers the demo classes. |
| V-HACD produces too many hulls → Rapier slows | Low | Cap hulls at 8 per object; drop to a single convex hull if over budget. Decision at H10 (PRD §15 open q 3). |
| MJCF exporter behaviour drifts from Rapier's rigid-body semantics | Medium | Document the known drift (ADR-004); don't try to unify. MuJoCo is export-only. |
| USD exporter steals critical-path time | High | Treat as stretch; cut at G3 if not clean in 30 min. |
| `KHR_physics_rigid_bodies` landing draft changes | Low | We use sidecar JSON, not the extension. No action. |

---

## 8. Day-of-demo responsibilities

- **Before pitch**: run the full pipeline end-to-end from `data/reconstructed/demo_scene/` once, verify output opens in Person 4's viewer.
- **During pitch**: if a live scene is requested, press the button; otherwise show the pre-built demo scene.
- **Talking points**: "the same `scene.json` emits to glTF for the browser, MJCF for MuJoCo, PyBullet for robotics — one spec, four consumers."
- Keep `scene.example.json` demo-loadable as a backup if the live scene breaks.

---

## 9. Definition of done

- [ ] `spec/scene.schema.json` v1.0 frozen; `scene.example.json` validates.
- [ ] VLM + lookup both wired; VLM failure falls back silently.
- [ ] glTF + sidecar, MJCF, PyBullet exporters each have ≥80% test coverage.
- [ ] Demo scene exports cleanly to all 3 (+USD stretch).
- [ ] V-HACD pipeline active; per-object hull count ≤8.
- [ ] `docs/scene/README.md` explains the schema and run-book.
