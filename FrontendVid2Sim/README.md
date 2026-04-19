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

The live-capture tab auto-selects an OAK camera when one is detectable over
UVC, but OAKs do NOT expose themselves as UVC webcams by default — they need
a host-side pipeline to activate the UVC node. Start it before recording:

```bash
pip install depthai                  # one-time
python scripts/oak_uvc.py            # keep running
```

Then refresh the frontend; the OAK appears in the camera picker and the
live-capture tab auto-selects it (matches labels containing `oak`, `luxonis`,
or `depthai`). For OAK-4 / RVC4 use the v3 `oakctl app run ./uvc_app` path —
see [`scripts/README.md`](scripts/README.md) for details.

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
