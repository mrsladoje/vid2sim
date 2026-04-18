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
| Hunyuan3D 2.1 — warm, trivial input (grey rect) | 200×300 | 33.8 s | 5.41 MB | EU | Misleading low number — input was uniform grey so model produced a near-cuboid. |
| Hunyuan3D 2.1 — warm, **real input** (penguin demo.png) | 1024×1024 | **65.5 s** | 12.86 MB | EU | **Realistic bench.** Above ≤20 s ADR-009 target. Mitigations: drop `octree_resolution` 256→128, switch primary to TripoSG, cap scene at 3 objects. |
| TripoSG 1.5B — cold | _TBD_ | _TBD_ | _TBD_ | EU | Blocked: `diso` needed (build-isolation issue). |
| TripoSG 1.5B — warm | _TBD_ | _TBD_ | _TBD_ | EU | Target ≤15 s. |
| Hunyuan3D 2.1 — warm over Cloudflare proxy | _TBD_ | _TBD_ | _TBD_ | EU | Cloudflare free-tier 100 s cap; cold + slow calls must use SSH tunnel. |

## Decision (G0 hard gate)

- **Target**: ≤ 20 s/object on Hunyuan3D for live demo of 3-5 objects within the 90 s scene budget.
- **Reality**: 65 s/object on Hunyuan3D 2.1 default settings (`octree_resolution=256`, A100 80GB).
- **Action**: per ADR-009 risk row, fall back to TripoSG once it loads + lower `octree_resolution=128` on Hunyuan3D as a fast-mode flag. Cap demo scene at 3 objects either way → realistic 30 s × 3 = 90 s total scene wall time.
- **Pod cost during build**: A100 80GB at $1.51/hr; total session ≈ 4 hr ≈ $6.

Mesh quality observation: shape only, no PBR textures (Paint pipeline disabled — bpy/Blender X11 deps missing). Acceptable for VID2SIM physics — ICP cares about geometry, not textures.

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
