# VID2SIM — Pitch deck (draft, 10 slides)

> Markdown draft. Export to PDF via `pandoc -t beamer demo/pitch_deck.md -o demo/pitch_deck.pdf` or Marp. Keep to 10 slides max. Final polish at G4.

---

## 1. Title

**VID2SIM**  
Polycam-for-physics. Point a camera at a room, get an interactive simulation in under a minute.

Team · DragonHack 2026 · Ljubljana

---

## 2. Problem

Creating a physics-ready digital twin today is:

- **Expensive** — NVIDIA Omniverse, enterprise RTX.
- **Manual** — Blender + hand-authored URDFs.
- **Incomplete** — Gaussian-splat research pipelines do not produce watertight meshes.

No shipped product does this on affordable hardware with browser-delivered output.

---

## 3. The gap (screenshot)

| Product | Edge capture? | Physics output? | Browser? |
|---|---|---|---|
| Polycam | ✓ | ✗ | partial |
| Omniverse | ✗ | ✓ | ✗ |
| Gaussian splats | ✓ | ✗ | ✓ (visual only) |
| **VID2SIM** | ✓ | ✓ | ✓ |

---

## 4. Pipeline

```
OAK-4 D Pro (LENS + YOLOE-26 + IMU)
   → host fusion (stereo + DA3 + RTAB-Map VIO)
   → Hunyuan3D 2.1 / TripoSG image-to-3D completion
   → Claude Opus 4.7 VLM physics oracle (PhysQuantAgent visual prompting)
   → scene.json (typed, versioned, tested)
   → glTF / MJCF / MuJoCo / USD exporters
   → Three.js + Rapier WASM browser viewer
```

The single contract is `scene.json`. Every stage is independently testable.

---

## 5. Pretty mode (LTX-2-19B video)

Drop in 10-second overnight-rendered clip here. "What the scan looks like once you run motion-preserving video diffusion on the depth buffers."

---

## 6. Live demo

Switch to the browser. Load the demo scene. Use all four interaction modes. Reset. Narrate the per-object VLM reasoning.

---

## 7. Scene spec (Epilog angle)

- JSON Schema draft 2020-12.
- ≥ 80% test coverage on exporters and fusion math.
- Typed Python + TypeScript clients.
- CI: ruff / black / mypy / pytest + GitHub Actions.
- Conventional commits.

`scene.json` is a plain file: diffable, fixture-able, golden-test-able.

---

## 8. Sponsors we hit

| Sponsor | How |
|---|---|
| **Luxonis** (Best Vision Hack) | LENS + YOLOE-26 + 3D tracker on NPU |
| **Guardiaris** (Most Innovative) | USD/MJCF export for training sims |
| **Preskok** (B2B) | Plug-and-play edge product, no CAD |
| **Zero Days** (Fun & scalable) | The browser demo itself |
| **Epilog** (Code quality) | Typed schema + exporter tests + CI |
| **Celtra** (API usage) | VLM + depth foundation model + image-to-3D |
| **HYCU** (Safer world) | Accident-site / training use cases |

---

## 9. Asks

- Luxonis OAK-4 D Pro hardware loan (production bench).
- Guardiaris pilot: one room captured, exported to their existing sim stack.
- Epilog engagement on typed schema review.

---

## 10. Thank you

vid2sim · github · contact

(Return to the browser for Q&A — judges will want to click things themselves.)
