# VID2SIM 90-second Pitch Choreography

> Stream 04 — Presentation. Timed pitch script with narration beats, on-screen actions, and slide/demo transitions. Rehearse twice (G3 / G4). Play the kill-switch video if anything breaks on stage.

**Total time:** 90 s  
**Speaker:** Queen (team lead)  
**Operator:** Person 4  
**Backup:** `demo/backup_demo.mp4` loaded on a second tab, ready to play.

---

## Timing table

| t (s) | Action on screen | Narration beat |
|---|---|---|
| 0 | Slide 1 — problem statement | "Real-to-sim pipelines cost $50k or take a week. We rebuilt Polycam-for-physics in 24 hours." |
| 5 | Slide 2 — the gap | "Polycam has no physics. Omniverse has no Apple Silicon. Gaussian-splats don't simulate. The shipped product doesn't exist — so we made one." |
| 12 | Slide 3 — pipeline diagram | "OAK-4 on-device perception feeds an M3 Max pipeline of depth fusion, image-to-3D diffusion, and a VLM physics oracle. The output is one JSON file." |
| 22 | **Slot: pretty-mode clip** — play `demo_pretty.mp4` (10 s) | "This is the LTX-2 pretty-mode render of our demo scene — overnight, not live." |
| 32 | Slide 4 — scene spec example | "Every stage agrees on the same `scene.json`. This is Epilog-worthy plumbing." |
| 37 | **Switch to viewer** — open `http://localhost:5173` on projector | "And here is the output. Static web page. No server. Rapier WASM." |
| 40 | Click **Demo scene** button | "This is a real chair, table, mug, book, and rubber ball." |
| 44 | Switch to **Select mode**; click chair | "Each object carries its mass, friction, restitution — all inferred by a VLM with PhysQuantAgent visual prompting." |
| 50 | Switch to **Apply Force**; drag chair | "I can hit the chair." (chair tumbles) |
| 55 | Switch to **Drop Ball**; click above table | "I can drop a ball at a cursor position." (ball drops, bounces) |
| 62 | Switch to **Drag**; drag mug across table | "I can pick something up." |
| 67 | Press **R** to reset | "Reset." |
| 70 | Slide 5 — sponsor alignment (Luxonis, Guardiaris, Epilog, Preskok) | "On-device perception — Luxonis. Safety training — Guardiaris. Typed schema + CI + ≥80% coverage — Epilog." |
| 80 | Slide 6 — asks / close | "Funding for Luxonis D Pro units; pilot with Guardiaris. Thank you." |
| 90 | — | Done. |

---

## Beats: failure recovery

| Beat | If it breaks | Recovery |
|---|---|---|
| Viewer won't load | console shows schema error | Cut to `backup_demo.mp4`; narrate over the recorded video |
| FPS drops below ~30 | M3 Max thermals | Close other tabs; ratchet window size; skip the drop-ball beat |
| Pretty-mode clip missing | overnight render failed | Skip slot at t=22; add 10 s to the viewer demo |
| Wifi dead | can't reach deployed URL | Serve `web/dist/index.html` from `file://` (pre-tested) |
| Laptop crash | — | Queen plays `backup_demo.mp4` from the team iPad |

---

## Rehearsal log

- Rehearsal 1 — H18. Observer: _____________ . Notes: _____________
- Rehearsal 2 — H20. Observer: _____________ . Notes: _____________
- Dress rehearsal — H23. Notes: _____________

---

## Post-mortem checklist (during rehearsal)

- [ ] 90 s ± 5 s total runtime.
- [ ] Every interaction mode demonstrated.
- [ ] At least one VLM reasoning string read aloud.
- [ ] Sponsor alignment mentioned explicitly (3+ named).
- [ ] Close beat crisp; no trailing "um".
