# SF3D local last-resort bench (G0 artifact)

**ADR:** ADR-003 (retained as last-resort), ADR-009 (fallback role).
**Status:** placeholder — fill during G0 first-hour bench.

SF3D on M3 Max MPS is the emergency path: fires only if the RunPod pod is
unreachable. We only need to confirm it boots + produces one mesh — it
does not have to be fast.

| Run | Object | MPS wall time | Mem peak | Watertight? | Note |
|---|---|---|---|---|---|
| smoke | cached hero crop | _TBD_ | _TBD_ | _TBD_ | `stabilityai/stable-fast-3d` |

Acceptance: one mesh generates, even slowly. If MPS refuses to load the
model at all, flag it as a blocker and let the pod absorb the entire
load (no second safety net).
