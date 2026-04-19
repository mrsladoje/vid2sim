<div align="center">

# VID2SIM

### From a video to an interactive physics simulator in 60 seconds.

**A novel pipeline that nobody has shipped.**

[![DragonHack](https://img.shields.io/badge/DragonHack-2026-red?style=for-the-badge)](https://dragonhack.si)
[![Luxonis](https://img.shields.io/badge/Luxonis-OAK--4%20D%20Pro-00B4D8?style=for-the-badge)](https://www.luxonis.com)
[![Three.js](https://img.shields.io/badge/Three.js-Rapier%20WASM-000000?style=for-the-badge&logo=three.js)](https://threejs.org)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org)

</div>

---

## The pitch

Creating simulatable digital twins of real environments is either **expensive** (NVIDIA Omniverse + enterprise RTX), **manual** (Blender + hand-authored URDFs), or **incomplete** (Gaussian-splat pipelines produce no watertight mesh for conventional physics).

**No shipped product does all three:** run on an affordable edge camera, produce mesh-based simulator-portable output, and deliver an interactive result in a browser with zero backend compute.

VID2SIM does. Point an OAK-4 D Pro at a room for 15 seconds, and under a minute later a judge is dropping balls on your chairs in a browser tab.

---

## How it works

```
   ┌──────── OAK-4 D Pro (edge NPU) ────────┐
   │  LENS stereo depth + IMU                │
   │  YOLOv8 hero-object segmentation        │
   │  ObjectTracker 3D + SpatialLocationCalc │
   └──────────────────┬──────────────────────┘
                      │ USB-C
                      ▼
   ┌──────── M3 Max (offline, local) ───────┐
   │  A. Geometry recovery (depth + VIO)     │
   │  B. SF3D mesh completion + textures     │
   │  C. Physics inference (VLM → props)     │
   │  D. scene.json + glTF / MJCF exporters  │
   └──────────────────┬──────────────────────┘
                      │
                      ▼
   ┌──────── Browser (Three.js) ────────────┐
   │  Rapier WASM · 60 FPS · no backend      │
   │  Click, drop, throw, knock over         │
   └─────────────────────────────────────────┘
```

### The four stages

| Stage | What happens | Tech |
|---|---|---|
| **A — Perception** | On-device depth + segmentation on the OAK NPU | LENS stereo, YOLOv8, ObjectTracker 3D |
| **B — Completion** | Feed-forward image-to-3D fills the unseen back of each object | **SF3D** (watertight + baked textures) |
| **C — Physics** | VLM infers `{mass, friction, restitution, material}` per object | Claude Opus 4.7 + PhysQuantAgent visual prompting |
| **D — Delivery** | Typed `scene.json` → glTF + MJCF → browser viewer | Three.js + Rapier WASM |

---

## Why this is hard

- **The camera only sees the front of every object.** A physics engine needs a closed mesh. SF3D hallucinates the back; the depth camera anchors scale and pose via ICP. Neither alone is enough — their composition is the engineering contribution.
- **Depth has to be metric.** Stereo is noisy on thin / low-texture surfaces; monocular foundation models are smooth but scale-free. We fuse both.
- **Physics has to be plausible.** Mass and friction aren't in the pixels. A VLM with visual-prompting reads material cues off the crop and emits structured JSON.
- **The demo has to survive a flaky venue network.** Zero-backend browser runtime. Nothing phones home once the scene is built.

---

## Tech feedback (for the sponsors)

### SF3D — Stable Fast 3D ([Stability AI](https://huggingface.co/stabilityai/stable-fast-3d))

We used SF3D, a feed-forward network for mesh generation, to fill out the unseen parts of the hero objects. We tried **Hunyuan3D 2.1** and **TripoSG 1.5B** as alternatives. SF3D won on three axes:

- **Speed** — feed-forward single pass, meaningfully quicker per object than the diffusion-based alternatives.
- **Integrated texture** — SF3D bakes PBR textures in the same forward pass. Hunyuan3D needs a separate Paint 2.1 stage; TripoSG outputs untextured geometry.
- **Mesh quality** — near-parity with Hunyuan3D on our indoor-object test set. The quality gap did not justify the wall-time + pipeline-complexity cost.

SF3D is what made the 60-second budget achievable.

---

## Repo layout

```
.
├── src/               # Python pipeline (capture → scene.json)
├── FrontendVid2Sim/   # React + Three.js + Rapier browser viewer
├── spec/              # scene.json JSON Schema + fixtures
├── scripts/           # OAK UVC bridge, capture helpers
├── docs/
│   ├── VID2SIM_PRD.md        # Full product requirements
│   ├── adr/                  # 9 architecture decision records
│   └── plans/                # Per-stage implementation plans
├── tests/             # pytest (fusion math + exporters)
└── data/captures/     # Recorded OAK sessions
```

---

## Run it

### Backend — capture + reconstruct

```bash
# One-time
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Run the pipeline on a capture
python -m src.vid2sim.cli --capture data/captures/<session_id>
```

### Frontend — browser viewer

```bash
cd FrontendVid2Sim
npm install
npm run dev
```

The Vite plugin auto-starts the OAK UVC bridge for live capture.

---

## Sponsor alignment

| Sponsor | Category | What we shipped |
|---|---|---|
| **Luxonis** | Best Vision Hack | On-device LENS + YOLOv8 + ObjectTracker on the OAK-4 NPU |
| **Guardiaris** | Most Innovative | Capture-to-trainer pipeline with MJCF export |
| **Preskok** | B2B | Plug-and-play, no CAD, no consultant |
| **Zero Days** | Fun & Scalable | Click in a browser, watch physics |
| **Epilog** | Code Quality | Typed `scene.json`, exporter tests, CI, ADRs |
| **Celtra** | Best API Use | VLM + depth foundation model + multi-stage ML pipeline |

---

## Documentation

- [Product Requirements Document](docs/VID2SIM_PRD.md)
- [Architecture Decision Records](docs/adr/README.md) — 9 accepted ADRs
- [Phased Plan](docs/PHASED_PLAN.md)
- [Scene specification](docs/scene/README.md)

---

<div align="center">

**Built in 24 hours at DragonHack 2026 · Ljubljana**

</div>
