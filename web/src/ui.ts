import * as THREE from "three";
import { Viewer } from "./viewer";
import { Physics } from "./physics";
import { InteractionMode, SceneObject } from "./types/scene";

interface InfoPanelElements {
  id: HTMLElement;
  cls: HTMLElement;
  mass: HTMLElement;
  friction: HTMLElement;
  restitution: HTMLElement;
  material: HTMLElement;
  reasoning: HTMLElement;
  meshOrigin: HTMLElement;
  physicsOrigin: HTMLElement;
  empty: HTMLElement;
  populated: HTMLElement;
}

export class UI {
  mode: InteractionMode = "select";
  selectedId: string | null = null;

  private readonly canvas: HTMLCanvasElement;
  private readonly info: InfoPanelElements;
  private readonly modeLabel: HTMLElement;
  private readonly fpsLabel: HTMLElement;
  private readonly objectCountLabel: HTMLElement;

  private readonly draggingHeight = 1.2;
  private dragRecord: string | null = null;
  private applyForceStart: { clientX: number; clientY: number; id: string } | null = null;

  private orbit = {
    active: false,
    lastX: 0,
    lastY: 0,
    target: new THREE.Vector3(0, 0.4, 0),
    radius: 5.0,
    theta: Math.PI / 4,
    phi: Math.PI / 4,
  };

  constructor(
    private readonly viewer: Viewer,
    private readonly physics: Physics,
  ) {
    this.canvas = viewer.canvas;
    this.info = {
      id: requireEl("info-id"),
      cls: requireEl("info-class"),
      mass: requireEl("info-mass"),
      friction: requireEl("info-friction"),
      restitution: requireEl("info-restitution"),
      material: requireEl("info-material"),
      reasoning: requireEl("info-reasoning"),
      meshOrigin: requireEl("info-mesh-origin"),
      physicsOrigin: requireEl("info-physics-origin"),
      empty: requireEl("info-empty"),
      populated: requireEl("info-populated"),
    };
    this.modeLabel = requireEl("mode-label");
    this.fpsLabel = requireEl("fps");
    this.objectCountLabel = requireEl("body-count");

    this.initOrbitFromCamera();
    this.bindControls();
    this.bindModeRadios();
    this.bindButtons();
    this.bindCanvasMouse();
    this.bindKeyboard();
    this.renderInfoPanel();
    this.updateModeLabel();
  }

  private initOrbitFromCamera(): void {
    const cam = this.viewer.camera.position;
    const t = this.orbit.target;
    const dx = cam.x - t.x;
    const dy = cam.y - t.y;
    const dz = cam.z - t.z;
    this.orbit.radius = Math.max(Math.hypot(dx, dy, dz), 1.5);
    this.orbit.phi = Math.atan2(Math.hypot(dx, dz), dy);
    this.orbit.theta = Math.atan2(dx, dz);
    this.applyOrbit();
  }

  private applyOrbit(): void {
    const { radius, theta, phi, target } = this.orbit;
    const x = target.x + radius * Math.sin(phi) * Math.sin(theta);
    const y = target.y + radius * Math.cos(phi);
    const z = target.z + radius * Math.sin(phi) * Math.cos(theta);
    this.viewer.camera.position.set(x, y, z);
    this.viewer.camera.lookAt(target);
  }

  private bindControls(): void {
    // Right-drag or middle-drag orbits the camera. Wheel zooms.
    this.canvas.addEventListener("contextmenu", (e) => e.preventDefault());
    this.canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = Math.exp(e.deltaY * 0.001);
      this.orbit.radius = Math.min(Math.max(this.orbit.radius * factor, 1.0), 25);
      this.applyOrbit();
    }, { passive: false });
  }

  private bindModeRadios(): void {
    const radios = document.querySelectorAll<HTMLInputElement>("input[name='mode']");
    radios.forEach((r) => {
      r.addEventListener("change", () => {
        if (r.checked) {
          this.setMode(r.value as InteractionMode);
        }
      });
    });
  }

  private bindButtons(): void {
    requireEl("btn-reset").addEventListener("click", () => this.reset());
    requireEl("btn-load-example").addEventListener("click", () => {
      this.dispatchSceneLoad("example");
    });
    requireEl("btn-load-stub").addEventListener("click", () => {
      this.dispatchSceneLoad("stub");
    });
    requireEl("btn-load-demo").addEventListener("click", () => {
      this.dispatchSceneLoad("demo");
    });
  }

  private dispatchSceneLoad(which: string): void {
    this.canvas.dispatchEvent(
      new CustomEvent("vid2sim:load-scene", { detail: { which }, bubbles: true }),
    );
  }

  private bindCanvasMouse(): void {
    this.canvas.addEventListener("mousedown", (e) => this.onMouseDown(e));
    window.addEventListener("mousemove", (e) => this.onMouseMove(e));
    window.addEventListener("mouseup", (e) => this.onMouseUp(e));
  }

  private bindKeyboard(): void {
    window.addEventListener("keydown", (e) => {
      if (e.target && (e.target as HTMLElement).tagName === "INPUT") return;
      switch (e.key) {
        case "1":
          this.setMode("select");
          break;
        case "2":
          this.setMode("drag");
          break;
        case "3":
          this.setMode("drop_ball");
          break;
        case "4":
          this.setMode("apply_force");
          break;
        case "r":
        case "R":
          this.reset();
          break;
      }
    });
  }

  setMode(mode: InteractionMode): void {
    this.mode = mode;
    document
      .querySelectorAll<HTMLInputElement>("input[name='mode']")
      .forEach((r) => (r.checked = r.value === mode));
    this.updateModeLabel();
  }

  private updateModeLabel(): void {
    const labels: Record<InteractionMode, string> = {
      select: "Select (click object)",
      drag: "Drag (click + hold)",
      drop_ball: "Drop Ball (click to drop)",
      apply_force: "Apply Force (click + drag)",
    };
    this.modeLabel.textContent = labels[this.mode];
  }

  private onMouseDown(e: MouseEvent): void {
    if (e.button === 2 || e.button === 1) {
      this.orbit.active = true;
      this.orbit.lastX = e.clientX;
      this.orbit.lastY = e.clientY;
      return;
    }
    if (e.button !== 0) return;

    switch (this.mode) {
      case "select": {
        const rec = this.viewer.pick(e.clientX, e.clientY);
        this.selectedId = rec ? rec.id : null;
        this.viewer.setHighlight(this.selectedId);
        this.renderInfoPanel();
        break;
      }
      case "drag": {
        const rec = this.viewer.pick(e.clientX, e.clientY);
        if (rec) {
          this.dragRecord = rec.id;
          this.selectedId = rec.id;
          this.viewer.setHighlight(rec.id);
          this.renderInfoPanel();
        }
        break;
      }
      case "drop_ball": {
        const hit = this.viewer.planeIntersect(e.clientX, e.clientY, this.draggingHeight);
        if (hit) this.physics.dropBall(hit);
        break;
      }
      case "apply_force": {
        const rec = this.viewer.pick(e.clientX, e.clientY);
        if (rec) {
          this.applyForceStart = { clientX: e.clientX, clientY: e.clientY, id: rec.id };
          this.selectedId = rec.id;
          this.viewer.setHighlight(rec.id);
          this.renderInfoPanel();
        }
        break;
      }
    }
  }

  private onMouseMove(e: MouseEvent): void {
    if (this.orbit.active) {
      const dx = e.clientX - this.orbit.lastX;
      const dy = e.clientY - this.orbit.lastY;
      this.orbit.lastX = e.clientX;
      this.orbit.lastY = e.clientY;
      this.orbit.theta -= dx * 0.008;
      this.orbit.phi -= dy * 0.008;
      const eps = 0.05;
      this.orbit.phi = Math.max(eps, Math.min(Math.PI / 2 - eps, this.orbit.phi));
      this.applyOrbit();
      return;
    }
    if (this.mode === "drag" && this.dragRecord) {
      // Kinematic-style: move the body by setting its next translation.
      const hit = this.viewer.planeIntersect(e.clientX, e.clientY, this.draggingHeight);
      if (!hit) return;
      const body = this.physics.getBodyFor(this.dragRecord);
      if (!body) return;
      body.setTranslation({ x: hit.x, y: hit.y, z: hit.z }, true);
      body.setLinvel({ x: 0, y: 0, z: 0 }, true);
    }
  }

  private onMouseUp(e: MouseEvent): void {
    if (e.button === 2 || e.button === 1) {
      this.orbit.active = false;
      return;
    }
    if (e.button !== 0) return;

    if (this.mode === "drag" && this.dragRecord) {
      const body = this.physics.getBodyFor(this.dragRecord);
      if (body) body.setLinvel({ x: 0, y: 0, z: 0 }, true);
      this.dragRecord = null;
    }
    if (this.mode === "apply_force" && this.applyForceStart) {
      const start = this.applyForceStart;
      const dx = e.clientX - start.clientX;
      const dy = e.clientY - start.clientY;
      // Scale drag distance into an impulse. Roughly: 100 px ≈ 5 N·s.
      const scale = 0.05;
      // Build the impulse in world space from the camera's orientation so
      // that horizontal drag = horizontal impulse in view plane.
      const impulse = new THREE.Vector3();
      const right = new THREE.Vector3();
      const up = new THREE.Vector3();
      this.viewer.camera.matrixWorld.extractBasis(right, up, new THREE.Vector3());
      impulse
        .addScaledVector(right, dx * scale)
        .addScaledVector(up, -dy * scale);
      this.physics.applyImpulse(start.id, impulse);
      this.applyForceStart = null;
    }
  }

  private reset(): void {
    this.physics.reset();
    this.selectedId = null;
    this.viewer.clearHighlight();
    this.renderInfoPanel();
  }

  private renderInfoPanel(): void {
    if (!this.selectedId) {
      this.info.empty.style.display = "block";
      this.info.populated.style.display = "none";
      return;
    }
    const rec = this.viewer.objects.get(this.selectedId);
    if (!rec) {
      this.info.empty.style.display = "block";
      this.info.populated.style.display = "none";
      return;
    }
    this.info.empty.style.display = "none";
    this.info.populated.style.display = "block";
    const s: SceneObject = rec.spec;
    this.info.id.textContent = s.id;
    this.info.cls.textContent = s.class;
    this.info.mass.textContent = `${s.physics.mass_kg.toFixed(2)} kg`;
    this.info.friction.textContent = s.physics.friction.toFixed(2);
    this.info.restitution.textContent = s.physics.restitution.toFixed(2);
    this.info.material.textContent = s.material_class;
    this.info.reasoning.textContent = s.source?.vlm_reasoning ?? "—";
    this.info.meshOrigin.textContent = s.source?.mesh_origin ?? "—";
    this.info.physicsOrigin.textContent = s.source?.physics_origin ?? "—";
  }

  updateHUD(fps: number): void {
    this.fpsLabel.textContent = `${Math.round(fps)} fps`;
    this.objectCountLabel.textContent = `${this.physics.bodyCount()} bodies`;
  }

  /** Refresh the info panel if it's showing an object whose body was reset/rebuilt. */
  refreshSelection(): void {
    this.renderInfoPanel();
  }
}

function requireEl(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing required DOM element #${id}`);
  return el;
}
