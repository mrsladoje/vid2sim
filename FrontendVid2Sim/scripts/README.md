# FrontendVid2Sim/scripts

Host-side helpers for the presentation frontend.

## `oak_uvc.py` — OAK-to-browser bridge

Gets frames from an OAK camera into the browser's live-capture flow. The
script auto-detects the device's transport and picks the right path.

### Two paths, same outcome

| Transport | Path | Frontend consumption |
|---|---|---|
| USB | **UVC webcam mode** via depthai pipeline. The OAK enumerates as a UVC device. | `getUserMedia()` sees it, auto-selected by label match (oak/luxonis/depthai). |
| TCP/IP (ethernet) | **MJPEG-over-HTTP bridge** on `http://127.0.0.1:8765/stream.mjpg`. UVC requires USB and cannot work over IP. | Frontend probes `/health`, then pulls MJPEG → `<img>` → `<canvas>` → `MediaStream` via `canvas.captureStream(30)`. |

Both paths funnel into the same `MediaStream` handling, so
`MediaRecorder`, preview, and the `./process_capture` handoff work
identically regardless of transport.

### TL;DR

```bash
pip install depthai opencv-python
npm run dev   # Vite plugin auto-spawns this script
```

Keep the terminal open — `[oak-uvc]` lines tell you which path it picked.

### Flags

| Flag | What it does |
|---|---|
| *(none)* | Auto-detect transport, run UVC or MJPEG bridge. |
| `--force uvc` | Force UVC mode even over TCP (will fail — but useful for debugging). |
| `--force bridge` | Skip UVC, always run the MJPEG bridge. |
| `--width W --height H` | Override stream resolution (default 1280×720). |
| `--fps N` | Override stream FPS (default 30). |

### Endpoints (bridge mode only)

| URL | What |
|---|---|
| `GET http://127.0.0.1:8765/health` | JSON liveness check (`{"ok":true,"source":"oak-ip-bridge"}`). |
| `GET http://127.0.0.1:8765/stream.mjpg` | Multipart MJPEG stream of the color camera (JPEG quality 82). |

CORS headers are set to `*` so the frontend at any localhost port can
consume the stream without proxying.

### depthai version support

| API | Used for | Notes |
|---|---|---|
| v3 | OAK-4 / RVC4 (required), modern OAK-D on v3 | `pip install --pre depthai` until v3 goes stable. |
| v2 | Older OAK-D / OAK-D Lite / OAK-1 with UVC firmware | `pip install depthai`. |

The script prefers v3 and falls back to v2 when v3 primitives are missing.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `ImportError: depthai` | `pip install depthai` (or `pip install --pre depthai` for v3). |
| `ImportError: cv2` / "opencv-python required" | `pip install opencv-python` — needed for the MJPEG bridge path. |
| `error: no OAK device found` | Check the cable / the OAK's power LED / `169.254.x.x` IP auto-config. |
| "Pipeline node with name: 'UVC' doesn't exist" | The device is RVC4 but on USB — UVC runtime isn't present. The script now falls back to the bridge automatically on this error. |
| Bridge runs but stream doesn't show in browser | CORS: confirm the browser hits `http://127.0.0.1:8765` (not `localhost` — the bridge binds `127.0.0.1` explicitly). Open DevTools → Network to see the `stream.mjpg` request. |
| Port 8765 already in use | `lsof -ti:8765 \| xargs kill -9`, then restart `npm run dev`. |
