# ADR-005: VLM-inferred physics properties with lookup fallback

- **Status:** Accepted
- **Date:** 2026-04-18
- **Deciders:** VID2SIM core team
- **Area:** Physics property inference (Stage C)

## Context

Every object in the reconstructed scene needs physics properties — at minimum mass, friction coefficient, restitution, material class, and a rigid/non-rigid flag — to be simulatable in Rapier and PyBullet (ADR-004). These values cannot be recovered directly from depth or RGB; they require world knowledge ("a wooden chair is ~5 kg; its friction against hardwood is ~0.5").

Three approaches are feasible in 24h: a static lookup table, a specialist learned model, or a VLM call (PRD §7 Stage C, §15 open question 2).

## Decision

For each segmented object in the scene:

1. Call a Vision-Language Model with the RGB crop, the predicted class label, and short room-context metadata. Primary: **Claude Opus 4.7**. Backup (on error/timeout): **Gemini 3.1**.
2. Require structured JSON output: `{mass_kg, friction_coeff, restitution, material_class, is_rigid, reasoning}`.
3. If the VLM call is low-confidence, fails schema validation, or times out, fall back to a **class-label lookup table** (e.g. `chair → 5 kg, μ=0.5, wood`).

The `reasoning` field is preserved in `scene.json` (ADR-001) for pitch and debugging.

## Alternatives Considered

- **Lookup table only.** Rejected: every chair gets the same mass, every table the same friction; there is no per-instance variation and the pitch ("the model noticed the chair is metal, not wood") collapses.
- **Specialised vision model (PhysObjects-style).** Rejected: no training or fine-tuning budget inside a 24h window; deployment would also add a second MPS-tuned inference stack.
- **Hand-tune per demo scene.** Rejected: kills the "any scene" claim and is not a scalable story.

## Consequences

**Positive**
- Per-object reasoning traces are pitch-worthy: "the VLM inferred this chair is wooden because of the visible grain."
- Graceful degradation: lookup table ensures the pipeline never blocks on VLM failures.
- Structured JSON output is directly diffable and testable against fixtures.
- Two VLM providers reduce single-vendor outage risk during the demo.

**Negative**
- VLM call latency eats into the 90-second reconstruction budget; we need a quick bench before committing to per-object calls (vs. one batched call).
- Accuracy on coarse categories is roughly 60–70% — good enough for demo visuals but not for engineering-grade simulation.
- Requires outbound network access for the VLM; captive venue networks are a risk (mitigated by lookup-table fallback).

**Neutral**
- Cost per scene is small (tens of calls at most per demo).

## References

- PRD §7 Stage C (Physics inference)
- PRD §15 open question 2 (VLM vs. lookup tradeoff)
- Related: ADR-001 (reasoning field stored in scene spec), ADR-004 (downstream physics engines consume these values).
