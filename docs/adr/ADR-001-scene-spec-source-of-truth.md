# ADR-001: Custom JSON scene spec as source of truth

- **Status:** Accepted
- **Date:** 2026-04-18
- **Deciders:** VID2SIM core team
- **Area:** Data model / interchange

## Context

VID2SIM produces an interactive physics simulation from a short RGB-D capture, and the same reconstructed scene must flow to multiple downstream consumers: a Three.js + Rapier WASM browser viewer, a MuJoCo headless runner (with optional PyBullet as transitional fallback per ADR-004), and — as a stretch — USD for Omniverse-style tooling (PRD §3 goals 4, §9, §10).

Picking one simulator's native format as the authoritative representation would couple the whole pipeline to that simulator's quirks. We need a representation that: (a) is stable to iterate on during the 24h build, (b) is trivial to unit-test with fixtures, and (c) can be fanned out to every required target without forcing a rewrite of the perception stages.

## Decision

Use a custom typed `scene.json` (JSON Schema draft 2020-12) as the single source of truth for a reconstructed scene. The schema owns geometry references, per-object transforms, collider definitions, physics properties (mass, friction, restitution, material class), and provenance metadata.

All simulator-specific formats — glTF (Three.js/Rapier), MJCF (MuJoCo), USD (Omniverse), and optional PyBullet `.py` — are **exporters** that read `scene.json` and emit their target format. The primary representation is never a simulator-native file.

## Alternatives Considered

- **USD directly as the source of truth.** Rejected: the Python USD API is heavy, its composition model has a steep learning curve, and fighting it in a 24h window is high risk. USD is retained only as a stretch export target.
- **glTF with `KHR_physics_rigid_bodies`.** Rejected: the extension is still provisional and browser loader support is poor. glTF remains the *transport* format for geometry into the viewer, but not the source of truth for physics.
- **MJCF directly.** Rejected: MJCF is MuJoCo-specific and does not travel cleanly to Three.js, Unity, or Isaac. Anchoring the pipeline to it would block the browser-first demo (ADR-006).

## Consequences

**Positive**
- Fast to iterate on: the schema is a plain JSON file, so every stage (perception, completion, VLM, assembly) can be tested against handwritten fixtures.
- Simple regression testing: golden `scene.json` files can be diffed in CI.
- Clean separation of concerns: every downstream simulator gets a dedicated exporter that is independently testable.
- Supports the browser-first demo (ADR-006) and the MuJoCo export path (ADR-004) from a single representation.

**Negative**
- We carry export code for each target (glTF, MJCF, USD, and optional PyBullet) instead of inheriting converters from an ecosystem.
- We do not get USD's composition, layering, or referencing features "for free"; if we ever need them, they must be added to the schema or the USD exporter.

**Neutral**
- `scene.json` is the only contract between pipeline stages, so stage authors must agree on schema changes before shipping them.

## References

- PRD §9 (Scene spec)
- PRD §10 (Exporters and target formats)
- Related: ADR-003 (image-to-3D outputs that feed into `scene.json`), ADR-004 (dual physics engines that consume it), ADR-006 (browser-native viewer).
