import { defineConfig, type Plugin } from "vite";
import { resolve } from "node:path";
import {
  cpSync,
  createReadStream,
  existsSync,
  statSync,
} from "node:fs";

const projectRoot = resolve(__dirname, ".");

function mimeFor(path: string): string {
  if (path.endsWith(".json")) return "application/json";
  if (path.endsWith(".glb")) return "model/gltf-binary";
  if (path.endsWith(".gltf")) return "model/gltf+json";
  return "application/octet-stream";
}

function serveProjectAssets(): Plugin {
  const prefixes = ["/spec/", "/data/"];
  return {
    name: "vid2sim-serve-project-assets",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? "";
        const match = prefixes.find((p) => url.startsWith(p));
        if (!match) return next();
        const rel = url.split("?")[0];
        const filePath = resolve(projectRoot, "." + rel);
        if (!filePath.startsWith(projectRoot) || !existsSync(filePath)) {
          return next();
        }
        const st = statSync(filePath);
        if (!st.isFile()) return next();
        res.setHeader("Content-Type", mimeFor(filePath));
        createReadStream(filePath).pipe(res);
      });
    },
    closeBundle() {
      const distDir = resolve(projectRoot, "web/dist");
      for (const dir of ["spec", "data"]) {
        const src = resolve(projectRoot, dir);
        const dst = resolve(distDir, dir);
        if (existsSync(src)) cpSync(src, dst, { recursive: true });
      }
    },
  };
}

export default defineConfig({
  root: resolve(projectRoot, "web"),
  base: "./",
  publicDir: resolve(projectRoot, "web/public"),
  build: {
    outDir: resolve(projectRoot, "web/dist"),
    emptyOutDir: true,
    target: "es2022",
    sourcemap: true,
  },
  server: {
    port: 5173,
    open: false,
    fs: {
      allow: [projectRoot],
    },
  },
  resolve: {
    alias: {
      "@spec": resolve(projectRoot, "spec"),
      "@data": resolve(projectRoot, "data"),
    },
  },
  optimizeDeps: {
    exclude: ["@dimforge/rapier3d-compat"],
  },
  plugins: [serveProjectAssets()],
});
