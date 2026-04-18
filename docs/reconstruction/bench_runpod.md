# RunPod Hunyuan3D / TripoSG bench (G0 hard gate)

**ADR:** ADR-009. **Status:** placeholder — fill during G0 first-hour bench.

Per-object end-to-end wall time laptop → pod → glb, measured on the
venue-proxy wifi, over the real FastAPI endpoint. This is the hard gate
for the per-object budget: if it busts, we escalate per ADR-009.

| Model | Crop res | Round-trip | Pod-side gen | Network | Mem peak | Pod region | Note |
|---|---|---|---|---|---|---|---|
| Hunyuan3D 2.1 | 512×512 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | must be ≤ 20 s |
| TripoSG 1.5B  | 512×512 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | must be ≤ 15 s |

Run with:

```bash
python scripts/bench_runpod.py --endpoint $RUNPOD_ENDPOINT \
    --crop data/test/hero_01/crop.jpg \
    --mask data/test/hero_01/mask.png
```

**If red after two honest attempts (H10 budget decision point):**

1. Try H100 pod in closer region.
2. Drop crop resolution 512→384.
3. Swap primary to TripoSG (faster).
4. Cap hero objects at 3.
5. As last resort: flip primary to local SF3D on MPS and cap objects at 2.

Write the blocker paragraph into `docs/reconstruction/blockers.md` and
page the Queen.
