# FrontendVid2Sim

Browser-native viewer for the Vid2Sim pipeline (Three.js + Rapier WASM).

## Scripts

| Command | What it does |
|---|---|
| `npm install` | Install dependencies (first time only). |
| `npm run dev` | Vite dev server with HMR. |
| `npm run build` | Type-check + production bundle to `dist/`. |
| `npm run typecheck` | `tsc -b --noEmit`. |
| `npm test` | Vitest unit tests. |

## Serving reconstructed scenes

The viewer resolves its scene source in three tiers, with automatic fallback:

1. **Stream 03 assembled** — `/scenes/rec_01_sf3d_assembled/scene.json`
   (per-object `meshes/<id>.glb` + CoACD hulls + authored physics)
2. **Stream 02 reconstructed** — `/scenes/rec_01_sf3d/reconstructed.json`
   (per-object raw SF3D GLBs + world-frame placement only)
3. **Synthetic demo** — built-in, badged as "demo data" in the viewer corner

Because `data/` lives outside `FrontendVid2Sim/`, symlink the bundles into
`public/` so Vite serves them:

```bash
# from FrontendVid2Sim/
mkdir -p public/scenes
ln -sfn ../../../data/scenes/rec_01_sf3d         public/scenes/rec_01_sf3d_assembled
ln -sfn ../../../data/reconstructed/rec_01_sf3d  public/scenes/rec_01_sf3d
```

`public/scenes/` is in `.gitignore` — don't commit the bundle into the frontend
tree.

### Why we avoid `scene.glb`

Stream 03 emits a composed `scene.glb` as a convenience artifact. The viewer
deliberately **does not** load it — loading one monolithic glTF would produce
one `Object3D` tree, and Rapier would weld every object into a single rigid
body. Instead, `SceneJsonSource` walks `scene.json` and loads each
`meshes/<id>.glb` separately, giving one `Object3D` + one rigid body per
object. Per-object picking, dragging, and impulse all work because each root
is tagged with `userData.objectId`.

## Adding a new scene source

`src/simulation/types.ts` exports the `SceneSource` interface. Drop a new
implementation next to `reconstructedSource.ts` (e.g. `sceneJsonSource.ts` for
Stream 03's `scene.gltf`) and `SimulationViewer.tsx` can select it without
touching `viewer.ts` or `physics.ts`.

## Using the OAK camera for live capture

The live-capture tab bridges an OAK camera into `getUserMedia()` semantics.
How the bridge works depends on how the OAK is connected:

| Transport | Path | What the frontend sees |
|---|---|---|
| USB | `scripts/oak_uvc.py` loads a UVC pipeline onto the device; the OAK enumerates as a UVC webcam | Standard `getUserMedia()` device; auto-selected by label match on `oak`/`luxonis`/`depthai` |
| Ethernet / TCP-IP (OAK-4 default) | `scripts/oak_uvc.py` runs an **MJPEG-over-HTTP bridge** on `http://127.0.0.1:8765` (UVC is USB-only, so there is no UVC option) | Frontend probes `/health`, then pulls the MJPEG into a hidden `<img>` + `<canvas>` and exposes a `MediaStream` via `canvas.captureStream(30)` to the existing record path |

Both paths converge on the same `MediaStream` plumbing in `UploadSection.tsx`
— the recording / review / process-capture UI doesn't know or care which
transport delivered the frames.

**This is automated.** A Vite plugin (`oakUvcBridge` in `vite.config.ts`)
spawns `scripts/oak_uvc.py` on `npm run dev` and tears it down on shutdown.
Look for `[oak-uvc]` prefixed lines in the terminal.

One-time setup:

```bash
pip install depthai opencv-python   # in the same venv your python resolves to
```

Then just:

```bash
npm run dev
```

### Env vars for the bridge

| Var | Meaning |
|---|---|
| `VITE_NO_OAK_UVC=1` | Disable auto-start. Use when you only have a built-in webcam. |
| `OAK_UVC_PYTHON=/path/to/python` | Override the Python interpreter (defaults to auto-detecting an adjacent `.venv`, then `python3` → `python` on PATH). |

### Why UVC doesn't work for network-attached OAK-4

UVC (USB Video Class) is, by name, a USB protocol. A network-attached
OAK-4 has no USB link for the browser to enumerate. Even if `oakctl app run
./uvc_app` were used, UVC output still requires USB. That's why
`scripts/oak_uvc.py` detects `protocol == tcp` and falls back to the MJPEG
bridge instead.

If you prefer UVC (smaller CPU footprint, no local HTTP server), plug the
OAK-4 in over USB-C.

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
