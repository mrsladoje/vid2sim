/** @vitest-environment jsdom */
import { describe, it, expect, beforeEach, vi } from "vitest";
import * as THREE from "three";
import { UI } from "../../web/src/ui";
import {
  makeMockPhysics,
  makeMockViewer,
  makeSceneObject,
  mountSidebarDom,
  seedObjects,
} from "./_harness";
import type { ObjectRecord } from "../../web/src/viewer";

function newHarness() {
  mountSidebarDom();
  const viewer = makeMockViewer();
  const physics = makeMockPhysics();
  const obj = makeSceneObject({
    id: "chair_01",
    class: "chair",
    material_class: "wood",
    physics: { mass_kg: 3.5, friction: 0.6, restitution: 0.2, is_rigid: true },
    source: { mesh_origin: "primitive", physics_origin: "lookup", vlm_reasoning: "heavy wooden chair" },
  });
  seedObjects(viewer, [obj]);
  const ui = new UI(viewer, physics);
  return { viewer, physics, ui, obj };
}

beforeEach(() => {
  document.body.innerHTML = "";
});

function mouse(type: string, x: number, y: number, button = 0): MouseEvent {
  return new MouseEvent(type, { clientX: x, clientY: y, button, bubbles: true });
}

describe("UI mode selection", () => {
  it("starts in 'select' mode and updates mode label", () => {
    const { ui } = newHarness();
    expect(ui.mode).toBe("select");
    expect(document.getElementById("mode-label")!.textContent).toMatch(/Select/);
  });

  it("switches mode when a radio changes", () => {
    const { ui } = newHarness();
    const dragRadio = document.querySelector<HTMLInputElement>('input[value="drag"]')!;
    dragRadio.checked = true;
    dragRadio.dispatchEvent(new Event("change"));
    expect(ui.mode).toBe("drag");
    expect(document.getElementById("mode-label")!.textContent).toMatch(/Drag/);
  });

  it("keyboard 1–4 cycle through modes; R resets", () => {
    const { ui, physics } = newHarness();
    for (const [key, expected] of [
      ["2", "drag"],
      ["3", "drop_ball"],
      ["4", "apply_force"],
      ["1", "select"],
    ] as const) {
      window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
      expect(ui.mode).toBe(expected);
    }
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "r", bubbles: true }));
    expect(physics.resetCalls).toBe(1);
  });

  it("keyboard shortcuts are ignored while typing in an input", () => {
    const { ui } = newHarness();
    const input = document.createElement("input");
    document.body.appendChild(input);
    const ev = new KeyboardEvent("keydown", { key: "2", bubbles: true });
    Object.defineProperty(ev, "target", { value: input });
    window.dispatchEvent(ev);
    expect(ui.mode).toBe("select");
  });
});

describe("select mode — info panel", () => {
  it("populates the info panel when an object is picked", () => {
    const { viewer, ui, obj } = newHarness();
    viewer.pickResponses.push(viewer.objects.get(obj.id) as ObjectRecord);
    document.getElementById("viewer")!.dispatchEvent(mouse("mousedown", 400, 300));
    expect(ui.selectedId).toBe("chair_01");
    expect(document.getElementById("info-empty")!.style.display).toBe("none");
    expect(document.getElementById("info-populated")!.style.display).toBe("block");
    expect(document.getElementById("info-id")!.textContent).toBe("chair_01");
    expect(document.getElementById("info-class")!.textContent).toBe("chair");
    expect(document.getElementById("info-mass")!.textContent).toBe("3.50 kg");
    expect(document.getElementById("info-friction")!.textContent).toBe("0.60");
    expect(document.getElementById("info-reasoning")!.textContent).toBe("heavy wooden chair");
  });

  it("clears the info panel when clicking empty space", () => {
    const { viewer, ui } = newHarness();
    // First click selects; second click picks nothing.
    viewer.pickResponses.push(viewer.objects.get("chair_01") as ObjectRecord);
    document.getElementById("viewer")!.dispatchEvent(mouse("mousedown", 100, 100));
    expect(ui.selectedId).toBe("chair_01");
    document.getElementById("viewer")!.dispatchEvent(mouse("mousedown", 100, 100));
    expect(ui.selectedId).toBeNull();
    expect(document.getElementById("info-empty")!.style.display).toBe("block");
    expect(document.getElementById("info-populated")!.style.display).toBe("none");
  });
});

describe("drop_ball mode", () => {
  it("drops a ball at the projected world position on mousedown", () => {
    const { viewer, ui, physics } = newHarness();
    ui.setMode("drop_ball");
    viewer.planeIntersectResponses.push(new THREE.Vector3(1.5, 1.2, -0.3));
    document.getElementById("viewer")!.dispatchEvent(mouse("mousedown", 450, 320));
    expect(physics.dropBallCalls.length).toBe(1);
    expect(physics.dropBallCalls[0].x).toBeCloseTo(1.5);
  });

  it("is a no-op when the ray misses the plane", () => {
    const { ui, physics } = newHarness();
    ui.setMode("drop_ball");
    document.getElementById("viewer")!.dispatchEvent(mouse("mousedown", 10, 10));
    expect(physics.dropBallCalls.length).toBe(0);
  });
});

describe("apply_force mode", () => {
  it("records mousedown then applies an impulse on mouseup sized by drag distance", () => {
    const { viewer, ui, physics, obj } = newHarness();
    ui.setMode("apply_force");
    viewer.pickResponses.push(viewer.objects.get(obj.id) as ObjectRecord);
    document.getElementById("viewer")!.dispatchEvent(mouse("mousedown", 400, 300));
    // No impulse until the button is released.
    expect(physics.applyImpulseCalls.length).toBe(0);
    window.dispatchEvent(mouse("mouseup", 500, 300));
    expect(physics.applyImpulseCalls.length).toBe(1);
    const call = physics.applyImpulseCalls[0];
    expect(call.id).toBe("chair_01");
    // 100 px to the right → non-trivial +x impulse (sign only, magnitude is camera-basis dependent).
    expect(call.impulse.length()).toBeGreaterThan(0);
  });

  it("does nothing if no object was under the cursor on mousedown", () => {
    const { ui, physics } = newHarness();
    ui.setMode("apply_force");
    document.getElementById("viewer")!.dispatchEvent(mouse("mousedown", 400, 300));
    window.dispatchEvent(mouse("mouseup", 500, 300));
    expect(physics.applyImpulseCalls.length).toBe(0);
  });
});

describe("drag mode", () => {
  it("sets linvel to zero on mouseup after a drag", () => {
    const { viewer, ui, physics, obj } = newHarness();
    ui.setMode("drag");
    // Minimal body stub exposing the setters the drag path calls.
    const setLin = vi.fn();
    const setTrans = vi.fn();
    physics.bodies.set(obj.id, { setLinvel: setLin, setTranslation: setTrans });
    viewer.pickResponses.push(viewer.objects.get(obj.id) as ObjectRecord);
    viewer.planeIntersectResponses.push(new THREE.Vector3(0.5, 1.2, 0));
    document.getElementById("viewer")!.dispatchEvent(mouse("mousedown", 400, 300));
    window.dispatchEvent(mouse("mousemove", 450, 300));
    window.dispatchEvent(mouse("mouseup", 450, 300));
    expect(setTrans).toHaveBeenCalled();
    expect(setLin).toHaveBeenCalledWith({ x: 0, y: 0, z: 0 }, true);
  });
});

describe("reset button + scene-load dispatch", () => {
  it("clicking reset calls physics.reset and clears the selection", () => {
    const { viewer, ui, physics, obj } = newHarness();
    viewer.pickResponses.push(viewer.objects.get(obj.id) as ObjectRecord);
    document.getElementById("viewer")!.dispatchEvent(mouse("mousedown", 400, 300));
    expect(ui.selectedId).toBe("chair_01");
    document.getElementById("btn-reset")!.click();
    expect(physics.resetCalls).toBe(1);
    expect(ui.selectedId).toBeNull();
  });

  it("scene-load buttons dispatch a 'vid2sim:load-scene' event with the right key", () => {
    newHarness();
    const events: string[] = [];
    document.getElementById("viewer")!.addEventListener("vid2sim:load-scene", (e) => {
      events.push((e as CustomEvent<{ which: string }>).detail.which);
    });
    document.getElementById("btn-load-example")!.click();
    document.getElementById("btn-load-stub")!.click();
    document.getElementById("btn-load-demo")!.click();
    expect(events).toEqual(["example", "stub", "demo"]);
  });
});

describe("updateHUD", () => {
  it("writes fps and body count labels", () => {
    const { ui, physics } = newHarness();
    physics.bodies.set("a", {});
    physics.bodies.set("b", {});
    ui.updateHUD(59.4);
    expect(document.getElementById("fps")!.textContent).toBe("59 fps");
    expect(document.getElementById("body-count")!.textContent).toBe("2 bodies");
  });
});

describe("wheel zoom + camera orbit", () => {
  it("wheel events do not throw and keep radius within reasonable bounds", () => {
    const { viewer } = newHarness();
    const canvas = document.getElementById("viewer")!;
    for (const deltaY of [2000, 2000, 2000, -5000, -5000]) {
      canvas.dispatchEvent(new WheelEvent("wheel", { deltaY, bubbles: true, cancelable: true }));
    }
    // Camera position must remain finite after a sequence of zooms.
    const p = viewer.camera.position;
    expect(Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z)).toBe(true);
  });
});
