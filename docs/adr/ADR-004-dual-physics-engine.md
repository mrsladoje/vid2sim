# ADR-004: Split physics engines (Rapier browser, PyBullet export)

- **Status:** Accepted
- **Date:** 2026-04-18
- **Deciders:** VID2SIM core team
- **Area:** Physics runtime / simulation backends (Stage D)

## Context

VID2SIM has two very different consumers of its physics scene:

1. **Hackathon judges** clicking around a scene in a browser at 60 FPS (PRD §3 goal 3, §7 Stage D).
2. **Robotics researchers** wanting headless, scriptable, batch simulation for real-to-sim policy work (PRD §4 users).

No single physics engine is optimal for both. A browser-native demo cannot afford backend latency; a serious research simulation cannot live inside a WASM sandbox.

## Decision

Use two physics runtimes, both fed from the same `scene.json` (ADR-001):

- **Primary (demo):** Rapier compiled to WASM, running in the browser alongside Three.js. No backend, no WebSocket, no Python on the demo laptop.
- **Secondary (export):** PyBullet as a headless batch runner for research use cases, generated from the scene spec via an exporter.

The `scene.json` → Rapier path is the hot demo path. The `scene.json` → PyBullet path is a write-once exporter.

## Alternatives Considered

- **PyBullet-only with WebSocket to Three.js.** Rejected: 30–80 ms round-trip latency kills the 60 FPS feel, and server processes make the demo fragile (port clashes, restarts at venue).
- **MuJoCo / MJX only.** Rejected: MJX on Apple Silicon is unstable (PRD §13), and hand-authoring MJCF has a steep learning curve for a 24h window. MJCF remains an export target (ADR-001) but not a runtime.
- **Genesis.** Rejected: install friction on macOS (1–2 h burnt on first-run issues).
- **Isaac Sim.** Rejected: no Apple Silicon support at all (PRD §5 hardware constraints).

## Consequences

**Positive**
- 60 FPS interactive demo with zero backend risk — the demo page is a static site.
- Rapier loads our glTF scene directly with triangle-mesh colliders, matching the viewer's geometry exactly.
- PyBullet export preserves a "serious simulation" story for robotics judges without putting PyBullet on the demo critical path.
- Either engine can be validated against the other on identical `scene.json` fixtures.

**Negative**
- Two physics runtimes to keep in sync; behavioural drift between Rapier and PyBullet is possible and must be documented.
- Rapier has fewer joint types than MuJoCo/PyBullet (not needed for v1 rigid-body scenes, but a limit for future articulated work).
- Rapier triangle-mesh colliders are primarily intended as **static** colliders; dynamic rigid bodies require convex decomposition (V-HACD or similar) before reaching the viewer. Budget this step in the assembly stage (see PRD §15 open question 3).

**Neutral**
- Rapier's WASM bundle size is small (~1 MB), so the browser demo stays light.

## References

- PRD §7 Stage D (Interactive viewer)
- PRD §10 (Exporters)
- PRD §13 (Risks: MJX instability, Genesis install friction, Isaac unsupported)
- Related: ADR-006 (browser-native viewer), ADR-001 (scene spec both engines consume), ADR-008 (excludes Isaac / Genesis).
