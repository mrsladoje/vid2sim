# ADR-009: Run Stage B image-to-3D on RunPod remote GPU (persistent pod)

- **Status:** Accepted (supersedes compute-placement portion of ADR-003; updates ADR-007; narrows ADR-008 cloud exclusion)
- **Date:** 2026-04-18
- **Deciders:** VID2SIM core team
- **Area:** Compute placement / Stage B (geometry completion)

## Context

The pitch window at DragonHack is a single **two-minute** live demo slot. PRD §3 goal 2 targets a ≤90 s offline budget for a 3–5 object scene. With Hunyuan3D 2.1 running on M3 Max MPS via the `Brainkeys/Hunyuan3D-2.1-mac` fork, per-object wall time has been projected at **30–60+ s** in a cool state and substantially worse under thermal throttle. At 5 objects this can exceed the pitch slot entirely. The risk is not latency in the abstract — it is that a single hot laptop during a live demo ships a failure we cannot recover from on stage.

ADR-003 (2026-04-18) originally placed Stage B on M3 Max. ADR-007 listed "Not used: cloud inference." ADR-008 excluded cloud from scope. This ADR narrows all three: cloud is admitted **only** for the Stage B diffusion step, over a persistent pre-warmed pod, with a local fallback path.

## Decision

Run **Hunyuan3D 2.1** and **TripoSG 1.5B** on a **RunPod persistent pod** (A100 40GB baseline; H100 if available in-region) pre-warmed at least **10 minutes** before the pitch. The pod exposes a minimal FastAPI endpoint:

```
POST /mesh  body={rgb_crop: jpeg_bytes, mask: png_bytes, model: "hunyuan3d"|"triposg"}
      →    glb_bytes
```

Local M3 Max continues to run everything that is not a heavy diffusion forward-pass:

- DA3METRIC-LARGE depth (still local — fast enough, keeps Luxonis pitch honest)
- RANSAC stereo+DA3 fusion
- RTAB-Map VIO
- Back-projection + point clouds
- ICP scale/pose alignment
- Mesh decimation
- Scene assembly + exporters (Person 3)

**Fallback order** (per object):
1. RunPod Hunyuan3D (primary)
2. RunPod TripoSG 1.5B (in-pod fallback, same endpoint, different `model` arg)
3. **Local SF3D on M3 Max MPS** (absolute last resort — fires only if the pod is unreachable)
4. Stub primitive emitter (break-glass; preserves Person 3 unblocking path)

## Alternatives Considered

- **All-local on M3 Max (ADR-003 original).** Rejected now: live-demo thermal and wall-time risk is too high inside a 2-min pitch slot. Accepted initially because no bench existed; the bench projection above moves the risk from theoretical to concrete.
- **RunPod serverless endpoint.** Rejected: 30–90 s cold-start defeats the latency goal we are trying to achieve. Serverless only makes sense if we can tolerate a first-request penalty, which a live demo cannot.
- **Replicate / Modal / Fal.** Considered as RunPod substitutes. All acceptable; RunPod chosen for A100/H100 price and the team's existing account. Swap is a one-file change (`runpod_client.py`).
- **Larger model on the pod** (e.g. Hunyuan3D-2.1-Plus or an unreleased SOTA). Deferred: we keep 2.1 as the pinned primary to avoid compounding "new model + new host" in the same 24 h window. Room to upgrade post-hackathon.
- **Keep M3 Max as primary, RunPod as fallback.** Rejected: inverts the risk profile we are trying to correct. The whole point is to not gamble the pitch on local wall time.

## Consequences

**Positive**
- Per-object wall time drops from ~30–60 s (M3 Max MPS) to **~5–15 s** (A100) — the 90-s scene budget becomes comfortable, not aspirational.
- Eliminates the thermal-throttle risk mid-demo.
- Removes dependency on the `Brainkeys/Hunyuan3D-2.1-mac` community fork and PyTorch 2.5.1 pin — we run the stock CUDA build.
- Frees M3 Max CPU/GPU headroom for capture, fusion, and viewer — the laptop is no longer the bottleneck for anything.

**Negative**
- **Venue network is now in the critical path.** Mitigated by: tethering from a phone as the first backup link, and local SF3D + stub emitter as the second.
- **Cost:** ~$2–4/hr for a persistent A100. Trivial for one demo; the pod is spun down after.
- **New failure mode:** pod down / auth expired / region outage. Mitigated by a 10-minute pre-warm health-check ritual in the run-book.
- **Payload size:** mesh GLBs returned from the pod are 0.5–3 MB each; 5 objects × 3 MB ≈ 15 MB round-trip. Fine on tether; flag if venue wifi is worse than LTE.
- **Contradicts ADR-007's "Not used: cloud inference"** and **narrows ADR-008's cloud exclusion.** Noted in each; not an architectural regression — a deliberate exception for the one stage that actually benefits.

**Neutral**
- Person 3, Person 4, and the `ReconstructedObject` contract (ADR-001, `spec/reconstructed_object.md`) are unaffected. From their perspective this is purely an implementation change inside Stream 02.

## Operational run-book (day-of-demo)

- **T-60 min:** start pod; pull model weights into pod-local cache (persistent volume); run one warm-up inference.
- **T-10 min:** health-check endpoint (`GET /healthz`); confirm `< 300 ms` round-trip from laptop.
- **T-0 (pitch):** run scene end-to-end on cue.
- **Post-demo:** stop pod.

## Open questions

- Pod region vs. venue network latency (bench at H0–H2 from the DragonHack venue or a proxy network).
- Wire format for mesh return: raw `.glb` bytes vs. gzipped vs. a presigned S3 URL. Decide at H2.
- Whether to also proxy the VLM call (ADR-005) through the pod for a single egress point. Out of scope for this ADR; revisit at H10.

## References

- PRD §3 (goals, 90-s budget), §5 (hardware constraints), §7 Stage B, §13 (risks — Hunyuan3D MPS, thermal throttle), §15 open q 7 (per-object wall time).
- Supersedes compute-placement portion of ADR-003.
- Updates ADR-007 (cloud is now bounded-use, not zero-use).
- Narrows ADR-008 (cloud exclusion applies to everything except Stage B diffusion).
- RunPod persistent pod docs — https://docs.runpod.io/
