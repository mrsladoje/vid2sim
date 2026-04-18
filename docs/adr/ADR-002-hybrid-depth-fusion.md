# ADR-002: Hybrid stereo + monocular depth fusion

- **Status:** Accepted
- **Date:** 2026-04-18
- **Deciders:** VID2SIM core team
- **Area:** Perception / geometry recovery (Stage A)

## Context

Stage A of the pipeline must produce a metrically-scaled, hole-free depth stream from the OAK-4 D Pro capture (PRD §7 Stage A). Two signals are available:

1. **Luxonis LENS on-device neural stereo depth**, running on the camera's NPU. Metric, real-time, spec'd at <1.5% NFOV error below 4 m on the OAK-4 D Pro, but unreliable on textureless or specular surfaces even with the IR dot projector.
2. **Depth Anything 3 `DA3METRIC-LARGE`** (`depth-anything/DA3METRIC-LARGE` on Hugging Face), an offline monocular depth foundation model running on M3 Max MPS. Metric depth recovered via `depth_m = focal_px · net_out / 300`. Per-frame throughput on M3 Max has not been benchmarked at the time of writing; first-hour bench drives the stage budget.

Using stereo alone fails on blank walls, glossy tables, and windows — common in indoor scenes. Using DA3 alone erodes the "only this stereo-IMU-NPU camera can do this" pitch, because pure-monocular pipelines already exist on phones (PRD §13 risks). We need both, fused.

## Decision

Fuse the two signals per frame using a simple, testable alignment pass:

1. Run LENS stereo on-device; run DA3 offline on the M3 Max.
2. On each frame, solve a per-frame least-squares alignment `stereo ≈ s · DA3 + t` using RANSAC over pixels where stereo is confident.
3. Use the aligned DA3 to **fill** stereo holes (low-confidence or missing pixels).
4. Use the aligned DA3 edge gradients to **sharpen** edges where stereo is noisy.

Stereo remains the **metric anchor** (it provides real scale). DA3 is the **fill** (it provides completeness and sharp discontinuities).

## Alternatives Considered

- **Stereo alone.** Rejected: fails on textureless surfaces (blank walls, monitors, glass) even with the IR dot projector. Produces holes that break downstream ICP and mesh completion.
- **DA3 alone.** Rejected: loses metric scale (DA3 is relative-then-calibrated), and more importantly erodes the edge-camera differentiation — pure-monocular pipelines exist on consumer phones, and the pitch would collapse.
- **Learned fusion network (trained end-to-end).** Rejected: a training budget is not available inside the 24h window; a classical RANSAC-based fit is predictable and debuggable.

## Consequences

**Positive**
- Robust on adversarial surfaces: blank walls, specular tables, and windows all get filled by DA3.
- Preserves the Luxonis narrative: stereo is the metric anchor, so the edge camera is essential — not merely convenient.
- Each pass is independently unit-testable with synthetic stereo / DA3 fixtures.
- Degrades gracefully: if DA3 is unavailable, stereo-only still runs (with worse hole filling).

**Negative**
- RANSAC fusion is new code that needs tests before the demo window opens.
- Adds one offline pass (DA3 on M3 Max MPS), which costs wall-clock time in the 90-second reconstruction budget; throughput must be measured before the budget is locked.
- Per-frame `(s, t)` parameters must be stored for provenance and debugging.

**Neutral**
- The fusion is deliberately simple (affine in depth space). If quality proves insufficient, the seam to swap in a richer model is narrow.

## References

- PRD §7 Stage A (Geometry recovery)
- PRD §13 (Risks: textureless surfaces, monocular-only differentiation)
- Related: ADR-007 (compute split — LENS on NPU, DA3 on M3 Max), ADR-003 (fused depth feeds mesh completion).
