# ADR-004: Split physics engines (Rapier browser, MuJoCo export)

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
- **Secondary (export):** MuJoCo (`pip install mujoco`, v3.3.2+) as a headless batch runner for research use cases, generated from the scene spec via an exporter. MuJoCo is actively maintained, Apple-Silicon-native, and MJCF is already on our exporter list — no extra work. MJX-on-Metal is still experimental; stay on CPU MuJoCo.

The `scene.json` → Rapier path is the hot demo path. The `scene.json` → MuJoCo path is a write-once exporter.

## Alternatives Considered

- **PyBullet as the export engine.** Superseded April 2026: PyBullet's last release was April 2022; MuJoCo is actively maintained, Apple-Silicon-native, and we already emit MJCF. Stays a possible transitional option only.
- **PyBullet-only with WebSocket to Three.js.** Rejected: 30–80 ms round-trip latency kills the 60 FPS feel, and server processes make the demo fragile (port clashes, restarts at venue).
- **MJX-on-Metal as runtime.** Rejected for v1: still experimental on Apple Silicon (PRD §13). We run CPU MuJoCo for export; revisit MJX once the Metal backend stabilises.
- **Genesis.** Rejected: install friction on macOS (1–2 h burnt on first-run issues).
- **Isaac Sim.** Rejected: no Apple Silicon support at all (PRD §5 hardware constraints).

## Consequences

**Positive**
- 60 FPS interactive demo with zero backend risk — the demo page is a static site.
- Rapier loads our glTF scene directly with triangle-mesh colliders, matching the viewer's geometry exactly.
- MuJoCo export preserves a "serious simulation" story for robotics judges without putting MuJoCo on the demo critical path.
- Either engine can be validated against the other on identical `scene.json` fixtures.

**Negative**
- Two physics runtimes to keep in sync; behavioural drift between Rapier and MuJoCo is possible and must be documented.
- Rapier has fewer joint types than MuJoCo (not needed for v1 rigid-body scenes, but a limit for future articulated work).
- Rapier triangle-mesh colliders are primarily intended as **static** colliders; dynamic rigid bodies require convex decomposition (CoACD 1.0.10 — `pip install coacd`, CPU-only, collision-aware, fewer+tighter hulls than V-HACD) before reaching the viewer. Budget this step in the assembly stage (see PRD §15 open question 3).

**Neutral**
- Rapier's WASM bundle size is small (~1 MB), so the browser demo stays light.
- Verified April 2026 — SOTA check passed, see commit history.

## Open questions

- CoACD 1.0.10 per-object hull count tolerance by class (H10 decision point).
- MJX-on-Metal stability for v2 runtime migration.

## References

- PRD §7 Stage D (Interactive viewer)
- PRD §10 (Exporters)
- PRD §13 (Risks: MJX instability, Genesis install friction, Isaac unsupported)
- MuJoCo — mujoco.readthedocs.io (v3.3.2+)
- CoACD — github.com/SarahWeiii/CoACD
- Related: ADR-006 (browser-native viewer), ADR-001 (scene spec both engines consume), ADR-008 (excludes Isaac / Genesis).
