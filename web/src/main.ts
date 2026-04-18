import { Viewer } from "./viewer";
import { Physics } from "./physics";
import { UI } from "./ui";
import { loadScene } from "./loader";

const SCENE_URLS: Record<string, string> = {
  example: "/spec/scene.example.json",
  stub: "/data/scenes/stub_01/scene.json",
  demo: "/data/scenes/demo_scene/scene.json",
};

async function bootstrap(): Promise<void> {
  const canvas = document.getElementById("viewer") as HTMLCanvasElement | null;
  if (!canvas) throw new Error("missing <canvas id='viewer'>");

  const viewer = new Viewer(canvas);
  const physics = new Physics(viewer);
  await physics.init();

  const ui = new UI(viewer, physics);

  async function loadAndBuild(key: string): Promise<void> {
    const url = SCENE_URLS[key] ?? SCENE_URLS.example;
    setStatus(`Loading ${key} scene…`);
    try {
      const spec = await loadScene(url);
      // baseUrl is the directory of the scene.json so that relative mesh
      // paths (`meshes/chair_01.glb`) resolve correctly when Person 3
      // ships real meshes alongside the spec.
      const baseUrl = new URL(url, window.location.href).toString();
      await viewer.loadSpec(spec, baseUrl);
      physics.buildWorld(spec);
      setStatus(`Loaded: ${key} (${spec.objects.length} objects)`);
      ui.refreshSelection();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatus(`Failed to load ${key}: ${msg}`);
      console.error(e);
    }
  }

  canvas.addEventListener("vid2sim:load-scene", (e: Event) => {
    const ce = e as CustomEvent<{ which: string }>;
    loadAndBuild(ce.detail.which);
  });

  // Initial scene.
  await loadAndBuild("example");

  // Expose hooks for headless tests and demo-laptop debugging.
  const anyWin = window as unknown as Record<string, unknown>;
  anyWin.__vid2sim = { viewer, physics, ui, loadScene: loadAndBuild };

  // Render + simulate loop.
  let last = performance.now();
  let fps = 60;
  function frame(now: number): void {
    const dt = Math.min((now - last) / 1000, 1 / 30);
    last = now;
    physics.step(dt);
    viewer.render();
    // Exponential-moving-average FPS.
    const instant = 1 / Math.max(dt, 1e-4);
    fps += 0.1 * (instant - fps);
    ui.updateHUD(fps);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function setStatus(msg: string): void {
  const el = document.getElementById("status");
  if (el) el.textContent = msg;
}

bootstrap().catch((e) => {
  console.error(e);
  setStatus(`Fatal: ${e instanceof Error ? e.message : String(e)}`);
});
