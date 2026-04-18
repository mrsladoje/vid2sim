# ADR-008: Scope exclusions (no Gaussian splats, no Isaac, no Genesis, no critical-path video diffusion)

- **Status:** Accepted — **narrowed by ADR-009** (cloud GPU is now admitted for Stage B diffusion on a pre-warmed persistent pod; all other cloud exclusions still stand).
- **Date:** 2026-04-18
- **Deciders:** VID2SIM core team
- **Area:** Scope / risk management

## Context

The 24h hackathon window is the hardest constraint. Every technology choice has integration cost, and several attractive options would each cost 2–6 hours of setup or integration work on Apple Silicon without adding demoable value. PRD §3.2 non-goals and §13 risks flag these explicitly, but we want one ADR that makes the exclusions loud and reviewable.

## Decision

The following are **explicitly out of scope for v1**:

- **Gaussian-splatting representations** (3DGS, PhysGaussian, etc.) as the geometric primitive.
- **NVIDIA Isaac Sim** as a physics/runtime target.
- **Genesis** as a physics engine.
- **Video diffusion on the critical path** (LTX-2-19B + IC-LoRA-Depth-Control, CogVideoX-Fun-V1.5-Control, etc.).
- **Deformables, soft bodies, fluids.**
- **Outdoor capture** and **dynamic-scene capture** (moving objects during recording).

Video diffusion may still be used **off the critical path** as a pre-recorded "pretty mode" clip in the pitch, rendered ahead of time.

## Alternatives Considered

Each excluded item was a real candidate; this section records why each one is out:

- **Gaussian splats.** Any GS pipeline would need a custom collider path to integrate with Rapier/MuJoCo (ADR-004), and the browser demo (ADR-006) loads glTF meshes, not splats. The cost of building a splat-to-mesh or splat-collider bridge exceeds the benefit.
- **Isaac Sim.** No Apple Silicon support (PRD §5). A remote Linux+CUDA box is not a demo surface we can reliably present.
- **Genesis.** 1–2 h of install friction on macOS historically; even with a clean run, it duplicates the role Rapier already fills for us.
- **Video diffusion (LTX-2-19B + IC-LoRA-Depth-Control, CogVideoX-Fun-V1.5-Control) on the critical path.** Costs 30–90 s per second of output — overnight work at best. Cannot be inside the 90 s per-scene reconstruction budget (PRD §3 goal 2).

## Consequences

**Positive**
- Removes 4–6 high-risk integrations from the 24h window in one explicit decision.
- Forces focus on the pipeline that actually demos: OAK capture → fused depth → Hunyuan3D → VLM physics → `scene.json` → Three.js/Rapier.
- Makes "why not X?" conversations with judges/mentors short and referable.

**Negative**
- We do not get splat-quality photorealism; Three.js rendering of PBR meshes is good but not research-tier.
- Video diffusion "pretty mode" is only available as a pre-recorded clip in the pitch, not as a live render.
- Future extensions (articulated bodies, deformables, outdoor capture) are deferred to a v2 scope.

**Neutral**
- Every exclusion is reversible post-hackathon; this ADR is a scope fence, not a permanent architectural rejection.

## References

- PRD §3.2 (Non-goals)
- PRD §10 (Target simulator formats)
- PRD §13 (Risks)
- Related: ADR-003 (chose mesh diffusion over splats), ADR-004 (chose Rapier + MuJoCo over Isaac / Genesis / pure-PyBullet runtime), ADR-007 (compute split), **ADR-009 (narrows the cloud-exclusion to admit a persistent RunPod pod for Stage B diffusion only)**.
