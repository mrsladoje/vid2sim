# FrontendVid2Sim/scripts

Host-side helpers for the presentation frontend.

## `oak_uvc.py` — OAK-as-webcam bridge

The browser's `getUserMedia()` can only see **UVC-compliant** video devices.
OAK cameras boot with DepthAI firmware by default and are NOT UVC-compliant
until a host pipeline activates the UVC output node.

### TL;DR

```bash
pip install depthai
python scripts/oak_uvc.py
```

Leave the script running. Open the frontend (`npm run dev`) → "Capture
Footage" → "live capture". The OAK auto-selects because the live-capture
component prefers devices whose label contains `oak` / `luxonis` / `depthai`.

### Flags

| Flag | What it does |
|---|---|
| *(none)* | Run UVC pipeline in-process. `Ctrl+C` stops; device stops streaming. |
| `--load-and-exit` | Load the pipeline then terminate the host. The OAK keeps streaming UVC until it's power-cycled. Good for "set and forget" demos. |
| `--flash-app` | Persist the UVC pipeline to the device's flash so it boots into UVC mode on every power-up. Older OAK devices only. |
| `--width W --height H` | Override the UVC output resolution (default 1920×1080 NV12). |

### OAK-4 / RVC4 note

OAK-4 uses DepthAI v3 and does **not** expose the legacy v2 `createUVC()`
node. If this script errors with "unknown node" / `AttributeError` on OAK-4,
take the v3 path instead:

1. Install DepthAI v3: `pip install --pre depthai`
2. Build a UVC OAK App — see the v3 docs.
3. Deploy with `oakctl app run ./uvc_app` — see
   <https://docs.luxonis.com/software-v3/oak-apps/oakctl/>.

Once the OAK App is running, the device appears in the browser's camera
picker exactly the same way as the v2 path, and the frontend auto-selects it
without any code changes.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Browser never shows the OAK | Is the script still running? A `Ctrl+C` cleanly stops the UVC stream. |
| `ImportError: depthai` | `pip install depthai` (or `pip install --pre depthai` for v3). |
| `AttributeError: 'Pipeline' object has no attribute 'createUVC'` | Your OAK is RVC4 (OAK-4). See the OAK-4 note above. |
| "Device is already in use" | Another process is holding the OAK. Close Luxonis Hub / oakctl / any DepthAI script. |
| Frontend picks the built-in FaceTime cam instead | Refresh the page after starting `oak_uvc.py`, or use the dropdown in the control strip to override. |
