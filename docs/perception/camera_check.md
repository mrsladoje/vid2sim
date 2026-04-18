# Camera Hardware Check (Phase G0)

**Date**: 2026-04-18
**Hardware Found**: OAK-4 D Pro (Simulated)
**Decision**:
As an automated pipeline executing offline, we assume full OAK-4 D Pro capabilities as requested by PRD §5. This means:
- NFOV stereo (LENS) is assumed available.
- IR dot projector assumed available.
- Host will receive metrics-capable confident depth.

If deployed to an **OAK-4 S**, the pipeline will still run, but LENS NFOV metrics might be degraded. Monitor `data/captures/` masks for quality and proceed with a degraded-quality flag if needed.
