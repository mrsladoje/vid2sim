# RunPod Hunyuan3D / TripoSG bench (G0 hard gate)

**ADR:** ADR-009. **Status:** first numbers logged 2026-04-18.

Per-object end-to-end wall time laptop → pod → glb, measured on the
venue-proxy wifi, over the real FastAPI endpoint. This is the hard gate
for the per-object budget: if it busts, we escalate per ADR-009.

Pod hardware this session: RunPod A100-SXM4-80GB, ~$1.51/hr.
Pod endpoint: `https://melj7r6bqvfp7o-8000.proxy.runpod.net`
Crop used: `data/warmup/crop.jpg` (200×300 px from the demo_scene chair).

| Model | Crop | Round-trip | GLB size | Pod region | Note |
|---|---|---|---|---|---|
| Hunyuan3D 2.1 — cold (1st call, via SSH tunnel) | 200×300 | 3 min 43 s | 3.95 MB | EU | Includes one-time `/root/.cache/hy3dgen/` model download. With cache symlink to `/workspace/cache/`, subsequent restarts skip this. |
| Hunyuan3D 2.1 — warm (2nd call, via SSH tunnel) | 200×300 | **33.8 s** | 5.41 MB | EU | **Above ≤20 s target.** Mitigation options below. |
| TripoSG 1.5B — cold | 200×300 | _TBD_ | _TBD_ | EU | |
| TripoSG 1.5B — warm | 200×300 | _TBD_ | _TBD_ | EU | Target ≤15 s |
| Hunyuan3D 2.1 — warm over Cloudflare proxy | 200×300 | _TBD_ | _TBD_ | EU | Cloudflare free-tier 100 s cap; cold calls must use SSH tunnel. |

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
