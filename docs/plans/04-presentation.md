# Stream 04 — Presentation (Person 4)

> Bounded context: the **demo surface**. Everything a judge sees, clicks, or watches. Person 4 works entirely off the `scene.json` schema — they do **not need real data** and can work the full 24 h on polish, interactive UX, pretty-mode video, and pitch. Their time is fully loaded, not idle.

See also: [`../PHASED_PLAN.md`](../PHASED_PLAN.md), [`../adr/ADR-006-browser-native-viewer.md`](../adr/ADR-006-browser-native-viewer.md), [`../adr/ADR-004-dual-physics-engine.md`](../adr/ADR-004-dual-physics-engine.md), [`../VID2SIM_PRD.md`](../VID2SIM_PRD.md) §7 Stage D, §7 Stage E, §3 goal 3, §4.

---

## 1. Scope & bounded context

**Owns**
- Browser-native Three.js + Rapier WASM viewer (static web app, no backend).
- Scene loading: reads `scene.glb` + `scene.glb.physics.json` (+ optional `scene.json` for UI labels).
- Interactive physics UX: click-to-select, drag, drop ball from cursor, apply-force impulse, reset.
- On-screen info panel (object class, mass, friction, material, VLM reasoning).
- Performance budget: ≥60 FPS on M3 Max; graceful degradation on lower hardware.
- **Demo scene script / choreography** — the 90-second pitch interaction sequence.
- **Pretty-mode video** — pre-rendered clip via CogVideoX-Fun-V1.5-Control (primary) or Wan 2.5+VACE (stretch). Overnight render only.
- **Pitch deck** + dry-runs + backup demo video recording.

**Does not own**
- Scene data production — Person 3.
- Reconstruction — Person 2.
- Camera pipeline — Person 1.

---

## 2. Ubiquitous language (Presentation)

| Term | Meaning |
|---|---|
| **Viewer** | Static site at `web/` — `index.html` + ES-module JS bundle. |
| **Scene load** | Fetch `scene.glb` → parse → attach physics bodies from sidecar → start simulation loop. |
| **Interaction mode** | One of: `select`, `drag`, `drop_ball`, `apply_force`. Active one is UI radio. |
| **Pretty pass** | Post-hoc video prettification (depth → diffusion). Runs overnight on M3 Max; produces `demo_pretty.mp4`. |
| **Choreography** | The 90-s scripted interaction for the pitch: load → tumble chair → drop ball → reset → export. |
| **Kill-switch clip** | 30-s backup video (screen recording of a working run) played if the live demo breaks. |

---

## 3. External dependencies (consumed)

| From | What | Format |
|---|---|---|
| Person 3 | `spec/scene.schema.json` v1.0 | JSON Schema (available at H2) |
| Person 3 | `spec/scene.example.json` | Hand-crafted fixture (available at H2) — **this is how Person 4 starts coding immediately** |
| Person 3 | `data/scenes/demo_scene/` | Real scene at G3 (H18) |
| — | Three.js, Rapier3D WASM, `gltf-transform`, Vite/esbuild | npm |
| — | CogVideoX-Fun-V1.5-Control (or Wan 2.5+VACE stretch) | HuggingFace |

Anti-corruption layer: the viewer only touches glTF + sidecar. It does not reach into `data/reconstructed/` or `data/captures/`. Its type model (`SceneObject`, `PhysicsBody`) is its own, built by reading the schema — nothing leaks in from other streams' internals.

---

## 4. External deliverables (produced)

```
web/
  index.html
  src/                    # TypeScript
    main.ts               # bootstrap
    viewer.ts             # Three.js scene
    physics.ts            # Rapier wiring
    ui.ts                 # interaction modes, info panel
    loader.ts             # scene.glb + sidecar → internal model
  dist/                   # bundled static site
demo/
  choreography.md         # pitch-time script
  demo_pretty.mp4         # overnight-rendered clip
  backup_demo.mp4         # kill-switch screen recording
  pitch_deck.pdf          # slides
  README.md               # how to launch the demo
```

No downstream consumer other than the judges.

---

## 5. Phased tasks

| Phase | Window | Task | Subtask | Artifact |
|---|---|---|---|---|
| G0 | H0–H2 | Bootstrap web app | Vite + TS + Three.js + Rapier WASM; `npm run dev` serves a blank scene | `web/` skeleton |
| G0 | H0–H2 | Consume schema early | Write TS types by hand matching `spec/scene.schema.json`; fail-loud validator at load | `web/src/types/scene.ts` |
| G0 | H0–H2 | Hand-crafted example renders | Load `spec/scene.example.json` + its meshes; see chair + ball + ground with physics | working dev site |
| **G0 gate** | H2 | Schema known, example scene renders with physics in browser | — | — |
| G1 | H2–H6 | Interaction modes v1 | `select`, `drop_ball`, `apply_force`, `reset` wired to UI radio; click-to-select highlighting | `web/src/ui.ts` |
| G1 | H2–H6 | Info panel | Shows selected object's class, mass, friction, material, VLM reasoning | UI |
| G1 | H2–H6 | Load Person 3's stub scene | Swap `scene.example.json` for `data/scenes/stub_01/scene.glb` + sidecar — same code path | integration smoke |
| G1 | H2–H6 | Pretty-mode rendering harness scaffold | Script that takes a PyBullet/Rapier sim replay + depth buffer → CogVideoX-Fun call; no actual call yet | `demo/render_pretty.py` skeleton |
| **G1 gate** | H6 | Stub scene interactive; all 4 modes work; 60 FPS on M3 Max | — | — |
| G2 | H6–H12 | Choreography v1 | Write pitch script: load → interact → export; time it to 90 s | `demo/choreography.md` |
| G2 | H6–H12 | Load hero-object scene | Real `data/scenes/hero_01/scene.glb` loads | — |
| G2 | H6–H12 | Visual polish | Lighting (HDRI env map), shadows, post-processing (bloom, SSAO optional) | — |
| G2 | H6–H12 | Pitch deck v1 | 10-slide draft: problem, gap, pipeline, demo, sponsors, asks | `demo/pitch_deck.pdf` draft |
| G2 | H6–H12 | Kick off overnight pretty-mode bench | One short clip through CogVideoX-Fun-V1.5-Control to gauge wall time | `demo/bench_pretty.md` |
| **G2 gate** | H12 | Real hero scene interactive; 10-slide draft deck; pretty-mode harness benched | — | — |
| G3 | H12–H18 | Load full demo scene (3–5 objects) | Works in viewer at 60 FPS | integration smoke |
| G3 | H12–H18 | Choreography final | Timed to the second; rehearsed twice | `demo/choreography.md` v2 |
| G3 | H12–H18 | Pretty-mode overnight render | Kick off render of the choreography sequence at H16–H18; completes overnight | `demo/demo_pretty.mp4` (appears G4) |
| G3 | H12–H18 | Backup kill-switch clip | Screen-record a successful choreography run; keep on disk | `demo/backup_demo.mp4` |
| G3 | H12–H18 | Pitch deck final content | Real scene screenshots, metrics, sponsor mapping | — |
| **G3 gate** | H18 | Demo scene + choreography rehearsed; backup video recorded | — | — |
| G4 | H18–H22 | Dry-run #1 | Full pitch on a colleague | notes |
| G4 | H18–H22 | Dry-run #2 | On different laptop (judge's perspective) | notes |
| G4 | H18–H22 | Deck polish | Typography, clean screenshots, sponsor logos | `demo/pitch_deck.pdf` final |
| G4 | H18–H22 | Deploy static viewer to a URL | GitHub Pages or Vercel; also bundle for `file://` | `demo/README.md` with link |
| G4 | H18–H22 | Viewer tests | Headless-Chrome test: load scene, assert N rigid bodies, simulate 1 s, assert no errors | `tests/web/test_viewer.spec.ts` |
| **G4 gate** | H22 | Pretty-mode video complete; deck final; 2 dry-runs done; CI green | — | — |
| G5 | H22–H24 | Final dress rehearsal | Full pitch + demo with backup video primed | — |

---

## 6. Phase gates

| Gate | Automated check | Manual check | Artifact check | If red |
|---|---|---|---|---|
| G0 | `npm run build` green; viewer loads `scene.example.json` | Drag-rotate the camera; see chair + ball; drop a ball and watch it bounce | `web/dist/` produced | Schema not ready: push back on Person 3 hard; schema is G0 hard block |
| G1 | Headless test: load stub scene, simulate 1 s, no console errors; FPS probe ≥60 | All 4 interaction modes work; info panel populates | `web/src/` modules in place | Simplify to 2 interaction modes (`drop_ball`, `reset`); ship |
| G2 | Real hero scene loads with correct physics | Pitch deck draft reviewed by Queen | `demo/pitch_deck.pdf` draft; `bench_pretty.md` has wall-time number | Skip visual polish; keep functional |
| G3 | Full demo scene at 60 FPS; choreography runs twice without edits | Colleague thinks it's cool | `backup_demo.mp4` exists and plays | Drop pretty-mode render; backup video is enough for pitch |
| G4 | All tests green, lint green, deck PDF renders, video plays | Two dry-runs completed on time | `demo_pretty.mp4` present (if on schedule) | Skip pretty-mode final; use bench clip instead |
| G5 | — | Final rehearsal smooth; kill-switch tested | Everything staged on demo laptop | Ship backup video only |

---

## 7. Risk & fallback (stream-specific)

| Risk | Likelihood | Fallback |
|---|---|---|
| Rapier dynamic trimesh limitation | Known | Require Person 3 to provide convex decomposition; viewer refuses to make dynamic trimesh bodies. |
| WASM memory blows up on >8 objects | Low | Cap scene at 8 (matches NFR); decimate or drop. |
| Venue wifi blocks CDN fetch of Rapier WASM | Medium | Bundle Rapier WASM into `dist/`; serve fully offline from `file://`. |
| CogVideoX-Fun render takes >12 h overnight | High | Pre-record a shorter (5–10 s) clip; or skip pretty-mode and rely on live demo. Kick off at H16 to have the full night. |
| Live demo laptop crashes on stage | Low | `backup_demo.mp4` is the kill switch. Queen hits play. |
| Schema changes after Person 4 starts coding | Medium | **Enforce "no breaking changes after G1" rule** with Person 3; version bump requires explicit Queen signoff. |

---

## 8. Day-of-demo responsibilities

- **Operate the demo**: launch viewer, drive choreography live.
- **Narrate the interaction**: "I click, apply force, chair tips — no server, no backend, pure WASM."
- **Drive the deck**: advance slides in sync with pipeline narrative.
- **Kill-switch**: if live demo fails, cut to `backup_demo.mp4` within 5 s.
- **Pretty-mode** (if rendered): play `demo_pretty.mp4` in the pitch slot for "imagine this with video diffusion."

---

## 9. Definition of done

- [ ] Static web viewer loads any schema-valid `scene.glb` + sidecar at ≥60 FPS on M3 Max.
- [ ] All 4 interaction modes (`select`, `drop_ball`, `apply_force`, `reset`) work.
- [ ] Info panel shows class, mass, friction, material, VLM reasoning.
- [ ] Choreography script timed and rehearsed twice.
- [ ] Backup demo video recorded.
- [ ] Pitch deck final.
- [ ] Viewer deployed to a static URL + loadable from `file://`.
- [ ] Pretty-mode video rendered **if overnight budget permits** (stretch).
