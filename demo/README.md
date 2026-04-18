# Demo launch book

**Audience:** Person 4 on stage at DragonHack 2026.

## Launching the viewer

### Option A — dev server (fast iteration)

```bash
npm install
npm run dev
```

Opens on `http://localhost:5173`. Hot-reload during rehearsals.

### Option B — built static site (stage mode)

```bash
npm run build
# dist at web/dist/
npx serve web/dist  # or any static server
```

### Option C — `file://` (venue wifi dead)

```bash
npm run build
open web/dist/index.html   # macOS
```

The dist bundle is fully self-contained: `spec/` and `data/` are copied into `web/dist/` at build time.

## Demo-time checklist

- [ ] Laptop on AC, thermal headroom verified (`powermetrics | head -20`).
- [ ] Browser: Chrome in Guest profile, window at 1920×1080, fullscreen ready (`F`).
- [ ] Second tab: `backup_demo.mp4` loaded and scrubbed to 0:00.
- [ ] Third tab: `pitch_deck.pdf` at slide 1.
- [ ] External display mirroring off — use extended display so presenter notes stay private.
- [ ] Sound off. (No audio in the viewer; avoids accidental feedback.)
- [ ] `npm run dev` running in a hidden iTerm tab (backup for crash-recovery).
- [ ] Phone tether pre-configured in case venue wifi collapses (VLM calls are already done; this is only if we want to live-load a new scene).

## Deployed URL

> Fill in after G4 deploy:
>
> - GitHub Pages: https://example-vid2sim.github.io/
> - Vercel preview: https://vid2sim-preview.vercel.app/

## Known issues

- Rapier WASM adds ~1.3 MB to first-load — preload the page at least once on venue wifi.
- `primitive:chair` is a placeholder until Person 3's Hunyuan3D meshes ship. Swap mesh path once `scene.glb` lands.
- Convex-decomposition fallback for `shape: mesh` uses an axis-aligned bbox. Safe for demo; not production.

## Kill-switch procedure

1. If viewer hangs > 3 s: Queen says "let me show you the recorded run."
2. Person 4 clicks the `backup_demo.mp4` tab and hits `F` for fullscreen, spacebar to play.
3. Continue narration over the video.

## Files in this directory

- `choreography.md` — 90-s timed pitch script.
- `backup_demo.mp4` — screen-recorded kill-switch clip (recorded at G3).
- `demo_pretty.mp4` — LTX-2 prettified clip (overnight render; may be absent).
- `pitch_deck.md` / `pitch_deck.pdf` — slides.
- `render_pretty.py` — overnight-render harness; see `bench_pretty.md` for wall time.
- `bench_pretty.md` — pretty-mode bench log.
