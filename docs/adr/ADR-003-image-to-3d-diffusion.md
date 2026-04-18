# ADR-003: Hunyuan3D 2.1 for geometry completion, SF3D fallback

- **Status:** Accepted
- **Date:** 2026-04-18
- **Deciders:** VID2SIM core team
- **Area:** Geometry completion (Stage B)

## Context

Stage B must turn per-object RGB crops + partial point clouds into watertight, UV-mapped, PBR-textured meshes ready for Rapier/PyBullet collision (PRD §7 Stage B). A single camera only sees one side of every object, so the back, bottom, and occluded faces have to be hallucinated.

Constraints: M3 Max, no CUDA, 90-second total reconstruction budget (PRD §3 goal 2), and the completion step must plug into the `scene.json` source of truth (ADR-001) without bespoke per-object hand work.

## Decision

Use **Hunyuan3D 2.1 (Tencent)** as the primary image-to-3D model. Its shape DiT produces a watertight mesh; Paint 2.1 adds PBR textures with UV maps. For throughput and for objects that Hunyuan3D fails on (thin structures, repeated retries), fall back to **Stable Fast 3D (SF3D)**, which is faster but lower-fidelity.

Output meshes are unit-cube-normalised by design. We rescale and pose-align each generated mesh to its observed partial point cloud from Stage A using ICP, then write the result into `scene.json` (ADR-001).

## Alternatives Considered

- **TRELLIS (Microsoft).** Rejected: its sparse-convolution operators fall back to CPU on MPS, taking ~3–5 minutes per asset — well outside the per-object budget.
- **TripoSG.** Acceptable quality, but newer and with less community validation on MPS; kept as a future option, not the primary.
- **Gaussian-splatting pipelines (PhysGaussian etc.).** Rejected: splats do not integrate cleanly with mesh-based physics (Rapier / PyBullet) and would break the browser demo (ADR-006). See also ADR-008.
- **Skip completion, use convex hulls of the observed point cloud.** Rejected: destroys the novel-engineering pitch and produces bad physics (coffee cups become coffee bricks).

## Consequences

**Positive**
- Watertight, PBR-textured, UV-mapped meshes suitable for physics and rendering without post-processing.
- Strong pitch story: "diffusion hallucinates the occluded geometry; depth anchors the scale."
- Two-tier fallback (Hunyuan3D → SF3D) means one model's failure does not stall the whole scene.

**Negative**
- Hunyuan3D per-object wall time on M3 Max MPS is **not yet benchmarked** — the `Brainkeys/Hunyuan3D-2.1-mac` fork claims feasibility but publishes no hard number. An H0–H2 bench on one asset is a hard gate before the 90 s scene budget is locked. If sustained wall time exceeds ~60 s/object, we cap hero objects at 2 and push the rest to SF3D.
- Uses the community `Brainkeys/Hunyuan3D-2.1-mac` fork: replaces flash-attn with SDPA, strips CUDA deps, requires PyTorch 2.5.1. One-off setup, but a third-party dependency we do not control.
- Back-to-back runs risk thermal throttling on M3 Max; mitigate with serial execution and cooldown gaps (see PRD §13).
- Output is unit-cube-normalised, so we carry ICP rescale/align code and its failure modes (wrong pose, stuck in local minima on symmetric / untextured objects).

**Neutral**
- Texture quality depends on input crop quality; low-res or motion-blurred crops produce muddy PBR maps.

## References

- PRD §7 Stage B (Geometry completion)
- PRD §13 (Hunyuan risk, MPS compatibility)
- Related: ADR-001 (outputs land in `scene.json`), ADR-002 (provides anchoring point cloud), ADR-008 (explicit exclusion of Gaussian-splat pipelines).
