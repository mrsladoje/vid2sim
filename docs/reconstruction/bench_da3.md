# DA3METRIC-LARGE bench on M3 Max (G0 artifact)

**ADR:** ADR-002. **Status:** placeholder — fill during G0 first-hour bench.

| Run | Frame | Resolution | MPS wall time | Mem peak | Note |
|---|---|---|---|---|---|
| smoke | synthetic checkerboard | 1920×1080 | _TBD_ | _TBD_ | DA3METRIC-LARGE via HF `depth-anything/DA3METRIC-LARGE` |

Acceptance: one frame completes on M3 Max MPS in under 2 s. If it does
not, the stage budget cannot close and we escalate per ADR-002 §open
questions.

Instructions for reproducing:

```bash
python scripts/bench_da3.py --image data/test/hero_01/frames/00000.rgb.jpg
```

This doc must be filled before G0 closes; numbers are what we commit to
for the per-frame fusion budget.
