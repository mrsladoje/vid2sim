# Pretty-mode bench log

> Stream 04 — Presentation. Overnight-render wall-time measurement log.
> Primary model: **LTX-2-19B + IC-LoRA-Depth-Control** (Lightricks, Mar 2026)  
> Fallback (same family): `Lightricks/LTX-Video-ICLoRA-depth-13b-0.9.7`  
> Safety net: **CogVideoX-Fun-V1.5-Control** (known to boot on MPS)  
> Stretch: Wan 2.2 Fun Control GGUF (MPS flaky)

PRD §15.9 blocks Stage E on actually benching this on M3 Max MPS. Fill in after G2 (H6–H12).

## Expected budgets (from PRD)

- 30–90 s wall time per 1 s of output video.
- Overnight window: ~8 h (H16 → H0) → usable output ≤ 320 s at best-case 90 s/s.
- Demo slot length: 10 s of output.

## G2 bench (H6–H12, target)

| Model | Frames | Resolution | Output seconds | Wall time | Notes |
|---|---|---|---|---|---|
| ltx2 | — | — | — | — | _run at G2_ |
| ltx2-fallback | — | — | — | — | _run only if ltx2 OOMs_ |
| cogvideox-fun | — | — | — | — | _run only if both LTX-2 variants fail_ |

## G3 overnight render (H16–H22, target)

- [ ] Kick off at H16.
- [ ] Monitor `powermetrics` for thermal throttling.
- [ ] Output: `demo/demo_pretty.mp4` — 10 s clip at 720p.
- [ ] If wall-time > 12 h: fall back to 5 s clip, drop to 480p.
- [ ] If both fail: skip pretty-mode slot in the pitch, extend live demo by 10 s.

## Learnings (fill in post-render)

_To be written after first real run._
