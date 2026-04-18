# backup_demo.mp4 — kill-switch clip

## Purpose

30-second screen recording of a working choreography run. Played if the live demo breaks on stage (PRD §13, plan §7 Risk table).

## Recording procedure (G3, H12–H18)

1. Launch viewer via `npm run build && npx serve web/dist` (production path — matches stage setup).
2. Open Chrome in Guest profile, resize to 1920×1080.
3. `cmd+shift+5` → "Record Selected Portion" → select the Chrome window.
4. Run the full choreography from `demo/choreography.md` timings.
5. Save the resulting file as `demo/backup_demo.mp4`.
6. Trim to ≤ 30 s with QuickTime (Edit → Trim…).
7. Verify it plays on the demo laptop *without opening any other app* — fullscreen via `F` in QuickTime.

## Acceptance

- [ ] ≤ 30 s.
- [ ] Shows at least 3 of 4 interaction modes.
- [ ] Audio optional — narration on top is fine.
- [ ] File size ≤ 100 MB (laptop transfer-safe).
- [ ] Plays on stage laptop from `demo/` directly.

(The actual `backup_demo.mp4` is recorded at G3, not checked in at scaffold time.)
