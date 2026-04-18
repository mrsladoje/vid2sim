# ADR-006: Browser-native viewer, no backend

- **Status:** Accepted
- **Date:** 2026-04-18
- **Deciders:** VID2SIM core team
- **Area:** Demo delivery / viewer runtime

## Context

The primary demo artifact is the thing judges interact with (PRD §3 goal 3, §4 primary persona). Hackathon venue conditions are hostile: flaky wifi, captive portals, random ports blocked, last-minute hardware swaps. Anything more complex than a static web page is demo-fragile.

At the same time, we need true physics — not a pre-recorded video — because interactivity is the pitch.

## Decision

The demo artifact is a **static Three.js + Rapier WASM page** that loads a single `scene.glb` plus its physics JSON. No server, no WebSocket, no Python runtime on the demo laptop. The page can be served from `file://`, a local static server, or a CDN — whichever is most reliable at the venue.

Rapier runs client-side in WebAssembly. All physics interactions (drop ball, apply force, knock over) happen in-browser at 60 FPS.

## Alternatives Considered

- **Electron app.** Rejected: distribution complexity, larger binary, slower iteration, no real upside over a browser page.
- **Python web server streaming MuJoCo (or the previously-considered PyBullet) over WebSocket.** Rejected: demo-fragile (port clashes, server restarts, Python env drift), adds 30–80 ms of latency per interaction, and introduces a backend dependency that will fail at the worst moment. MuJoCo is still our export target (ADR-004); it just doesn't ride the demo wire.
- **Unity WebGL.** Rejected: build toolchain and project setup cost is too high for 24h; Unity's WebGL export is also heavyweight.

## Consequences

**Positive**
- Demo survives network flakiness at the venue; worst case the page is served from `file://` on the laptop.
- Deployable as a link — judges and jury can reopen it after the session.
- 60 FPS on any modern laptop (judges' machines included); no GPU requirement beyond WebGL.
- Zero backend means zero backend bugs.

**Negative**
- Constrained to Rapier's feature set (rigid bodies, basic joints); articulated or soft-body physics are not available (see ADR-008).
- All physics runs client-side, so very large scenes may hit a WASM memory ceiling. We cap at 8 objects per scene (NFR in PRD §8.1) and decimate Hunyuan3D meshes above ~50k tris to stay safe.
- `KHR_physics_rigid_bodies` is a *draft* glTF extension and not ratified; we ship a sidecar physics JSON alongside `.glb` to avoid coupling to a moving spec.

**Neutral**
- Static hosting is trivial; a GitHub Pages or Vercel deploy is fine.
- Verified April 2026 — SOTA check passed, see commit history.

## References

- PRD §3 (Goals and non-goals)
- PRD §7 Stage D (Interactive viewer)
- Related: ADR-004 (Rapier chosen as the browser engine), ADR-001 (scene spec exported to glTF for the viewer).
