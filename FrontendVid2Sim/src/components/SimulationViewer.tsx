import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Box as BoxIcon,
  MousePointer2,
  Move3d,
  CircleDot,
  Zap,
  RefreshCcw,
  Play,
  Pause,
  Settings2,
  Info,
  AlertTriangle,
} from 'lucide-react';
import { motion } from 'framer-motion';
import * as THREE from 'three';
import { Viewer } from '../simulation/viewer';
import { Physics } from '../simulation/physics';
import { ExampleSceneSource } from '../simulation/exampleScene';
import {
  ReconstructedFetchError,
  ReconstructedJsonSource,
} from '../simulation/reconstructedSource';
import { SceneJsonSource } from '../simulation/sceneJsonSource';
import type {
  InteractionMode,
  LoadedMesh,
  LoadedScene,
  SceneSource,
} from '../simulation/types';

const MODE_OPTIONS: {
  value: InteractionMode;
  label: string;
  hint: string;
  icon: typeof MousePointer2;
  shortcut: string;
}[] = [
  { value: 'select', label: 'Select', hint: 'click to inspect', icon: MousePointer2, shortcut: '1' },
  { value: 'drag', label: 'Drag', hint: 'hold + move', icon: Move3d, shortcut: '2' },
  { value: 'drop_ball', label: 'Drop Ball', hint: 'click to spawn', icon: CircleDot, shortcut: '3' },
  { value: 'apply_force', label: 'Force', hint: 'drag to push', icon: Zap, shortcut: '4' },
];

const BALL_RADIUS = 0.08;
const BALL_SPAWN_OFFSET = BALL_RADIUS + 0.02;
const CACHED_SCENE_JSON_URL = '/scenes/rec_01_sf3d_assembled/scene.json';
const DEFAULT_RECONSTRUCTED_URL = '/scenes/rec_01_sf3d/reconstructed.json';

/**
 * Probe-fetch a manifest with Accept: application/json. Vite's SPA fallback
 * would otherwise serve index.html with HTTP 200 when the symlink is missing,
 * so we check content-type rather than trusting the status code.
 */
async function probeManifest(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!res.ok) return false;
    const ct = res.headers.get('content-type') ?? '';
    if (!ct.includes('json')) return false;
    await res.text();
    return true;
  } catch {
    return false;
  }
}

/**
 * Source resolution:
 *   1. If a live pipeline ran, load its fresh scene.json at
 *      /scenes/<sessionId>_assembled/scene.json. Never falls back on 404
 *      for a live session — the user should see the error, not a stale
 *      cached scene.
 *   2. Otherwise, prefer the cached Stream 03 scene (rec_01_sf3d_assembled)
 *      → Stream 02 raw reconstruction → synthetic demo with badge.
 */
async function resolvePrimarySource(sessionId: string | null): Promise<{
  source: SceneSource;
  tier: 'live' | 'scene' | 'recon' | 'demo';
  sceneUrl: string | null;
}> {
  if (sessionId) {
    const liveUrl = `/scenes/${sessionId}_assembled/scene.json`;
    return {
      source: new SceneJsonSource({
        manifestUrl: liveUrl,
        displayName: `Live · ${sessionId}`,
      }),
      tier: 'live',
      sceneUrl: liveUrl,
    };
  }
  if (await probeManifest(CACHED_SCENE_JSON_URL)) {
    return {
      source: new SceneJsonSource({ manifestUrl: CACHED_SCENE_JSON_URL }),
      tier: 'scene',
      sceneUrl: CACHED_SCENE_JSON_URL,
    };
  }
  if (await probeManifest(DEFAULT_RECONSTRUCTED_URL)) {
    return {
      source: new ReconstructedJsonSource({ manifestUrl: DEFAULT_RECONSTRUCTED_URL }),
      tier: 'recon',
      sceneUrl: DEFAULT_RECONSTRUCTED_URL,
    };
  }
  return { source: new ExampleSceneSource(undefined, true), tier: 'demo', sceneUrl: null };
}

interface SelectedInfo {
  id: string;
  label: string;
  classification: string;
  meshOrigin: string;
  bboxSize: THREE.Vector3;
  bboxMin: THREE.Vector3;
  bboxMax: THREE.Vector3;
  legacyVlmReasoning?: string;
  legacyMass?: number;
  legacyFriction?: number;
  legacyRestitution?: number;
  legacyMaterial?: string;
}

function toSelectedInfo(m: LoadedMesh): SelectedInfo {
  const size = m.bboxWorld.getSize(new THREE.Vector3());
  return {
    id: m.id,
    label: m.label,
    classification: m.classification,
    meshOrigin: m.meshOrigin,
    bboxSize: size,
    bboxMin: m.bboxWorld.min.clone(),
    bboxMax: m.bboxWorld.max.clone(),
    legacyVlmReasoning: m.legacySpec?.source?.vlm_reasoning,
    legacyMass: m.legacySpec?.physics.mass_kg,
    legacyFriction: m.legacySpec?.physics.friction,
    legacyRestitution: m.legacySpec?.physics.restitution,
    legacyMaterial: m.legacySpec?.material_class,
  };
}

interface SimulationViewerProps {
  /**
   * Optional session id from a fresh pipeline run. When present the viewer
   * loads /scenes/<sessionId>_assembled/scene.json; when null it falls
   * back through the cached scene → raw reconstruction → demo chain.
   */
  sessionId?: string | null;
}

export default function SimulationViewer({ sessionId = null }: SimulationViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const physicsRef = useRef<Physics | null>(null);

  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isFallback, setIsFallback] = useState(false);
  const [sceneName, setSceneName] = useState<string>('');
  const [mode, setMode] = useState<InteractionMode>('select');
  const [selected, setSelected] = useState<SelectedInfo | null>(null);
  const [fps, setFps] = useState(60);
  const [bodyCount, setBodyCount] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [gravity, setGravity] = useState(-9.81);
  const [frictionScale, setFrictionScale] = useState(1.0);

  const modeRef = useRef(mode);
  const isPlayingRef = useRef(isPlaying);
  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { isPlayingRef.current = isPlaying; }, [isPlaying]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let rafId = 0;
    let disposed = false;
    const viewer = new Viewer(canvas);
    const physics = new Physics(viewer);
    viewerRef.current = viewer;
    physicsRef.current = physics;

    (async () => {
      await physics.init();
      if (disposed) return;

      const resolved = await resolvePrimarySource(sessionId);
      let source: SceneSource = resolved.source;
      if (resolved.tier === 'live') {
        console.info(
          `[SimulationViewer] live session ${sessionId} → ${resolved.sceneUrl}`,
        );
      } else if (resolved.tier !== 'scene') {
        console.info(
          `[SimulationViewer] using tier=${resolved.tier} (cached scene unavailable)`,
        );
      }

      let loaded: LoadedScene;
      try {
        loaded = await source.load();
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (err instanceof ReconstructedFetchError) {
          console.error('[SimulationViewer] manifest fetch failed', err);
        } else {
          console.error('[SimulationViewer] primary source failed, falling back to demo scene', err);
        }
        setLoadError(msg);
        source = new ExampleSceneSource(undefined, true);
        loaded = await source.load();
      }
      if (disposed) return;

      viewer.loadScene(loaded);
      physics.buildWorld(loaded);
      setIsFallback(loaded.isFallback);
      setSceneName(loaded.displayName);
      setGravity(loaded.gravityY);
      setBodyCount(physics.bodyCount());
      setReady(true);

      let last = performance.now();
      let emaFps = 60;
      const frame = (now: number) => {
        const dt = Math.min((now - last) / 1000, 1 / 30);
        last = now;
        if (isPlayingRef.current) physics.step(dt);
        viewer.render();
        const instant = 1 / Math.max(dt, 1e-4);
        emaFps += 0.1 * (instant - emaFps);
        setFps(emaFps);
        setBodyCount(physics.bodyCount());
        rafId = requestAnimationFrame(frame);
      };
      rafId = requestAnimationFrame(frame);
    })();

    const ro = new ResizeObserver(() => viewer.resize());
    if (wrapperRef.current) ro.observe(wrapperRef.current);

    return () => {
      disposed = true;
      cancelAnimationFrame(rafId);
      ro.disconnect();
      viewer.dispose();
      physics.teardown();
      viewerRef.current = null;
      physicsRef.current = null;
    };
    // Re-run when the live pipeline hands off a new sessionId so the fresh
    // scene replaces the cached one in-place.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const viewer = viewerRef.current;
    const physics = physicsRef.current;
    if (!canvas || !viewer || !physics) return;

    const orbit = initOrbit(viewer.camera.position, viewer.currentScene());
    const applyOrbit = () => {
      const { radius, theta, phi, target } = orbit;
      const x = target.x + radius * Math.sin(phi) * Math.sin(theta);
      const y = target.y + radius * Math.cos(phi);
      const z = target.z + radius * Math.sin(phi) * Math.cos(theta);
      viewer.camera.position.set(x, y, z);
      viewer.camera.lookAt(target);
    };
    applyOrbit();

    let dragId: string | null = null;
    let dragPlaneHeight: number | null = null;
    let forceStart: { x: number; y: number; id: string } | null = null;

    const onContextMenu = (e: MouseEvent) => e.preventDefault();
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const factor = Math.exp(e.deltaY * 0.001);
      orbit.radius = Math.min(Math.max(orbit.radius * factor, 0.3), 30);
      applyOrbit();
    };

    const handlePickForInspector = (rec: ReturnType<typeof viewer.pick>) => {
      viewer.setHighlight(rec?.id ?? null);
      setSelected(rec ? toSelectedInfo(rec.loaded) : null);
    };

    const onMouseDown = (e: MouseEvent) => {
      if (e.button === 2 || e.button === 1 || (e.button === 0 && e.shiftKey)) {
        orbit.active = true;
        orbit.lastX = e.clientX;
        orbit.lastY = e.clientY;
        return;
      }
      if (e.button !== 0) return;

      const m = modeRef.current;
      if (m === 'select') {
        const rec = viewer.pick(e.clientX, e.clientY);
        if (rec) {
          handlePickForInspector(rec);
        } else {
          // Left-drag on empty space orbits — matches the "mouse-drag rotates" acceptance criterion.
          orbit.active = true;
          orbit.lastX = e.clientX;
          orbit.lastY = e.clientY;
        }
      } else if (m === 'drag') {
        const rec = viewer.pick(e.clientX, e.clientY);
        if (rec) {
          const planeHeight = physics.startDrag(rec.id);
          if (planeHeight === null) return;
          dragId = rec.id;
          dragPlaneHeight = planeHeight;
          handlePickForInspector(rec);
        }
      } else if (m === 'drop_ball') {
        const hit = viewer.surfaceIntersect(e.clientX, e.clientY);
        if (hit) {
          const spawn = hit.point.clone();
          spawn.y += BALL_SPAWN_OFFSET;
          physics.dropBall(spawn, BALL_RADIUS);
        }
      } else if (m === 'apply_force') {
        const rec = viewer.pick(e.clientX, e.clientY);
        if (rec) {
          forceStart = { x: e.clientX, y: e.clientY, id: rec.id };
          handlePickForInspector(rec);
        }
      }
    };

    const onMouseMove = (e: MouseEvent) => {
      if (orbit.active) {
        const dx = e.clientX - orbit.lastX;
        const dy = e.clientY - orbit.lastY;
        orbit.lastX = e.clientX;
        orbit.lastY = e.clientY;
        orbit.theta -= dx * 0.008;
        orbit.phi -= dy * 0.008;
        const eps = 0.05;
        orbit.phi = Math.max(eps, Math.min(Math.PI / 2 - eps, orbit.phi));
        applyOrbit();
        return;
      }
      if (modeRef.current === 'drag' && dragId && dragPlaneHeight !== null) {
        const hit = viewer.planeIntersect(e.clientX, e.clientY, dragPlaneHeight);
        if (!hit) return;
        physics.moveDrag(dragId, hit);
      }
    };

    const onMouseUp = (e: MouseEvent) => {
      if (orbit.active) {
        orbit.active = false;
        if (e.button === 0) return;
      }
      if (e.button !== 0) return;

      if (modeRef.current === 'drag' && dragId) {
        physics.endDrag(dragId);
        dragId = null;
        dragPlaneHeight = null;
      }
      if (modeRef.current === 'apply_force' && forceStart) {
        const dx = e.clientX - forceStart.x;
        const dy = e.clientY - forceStart.y;
        const scale = 0.05;
        const right = new THREE.Vector3();
        const up = new THREE.Vector3();
        viewer.camera.matrixWorld.extractBasis(right, up, new THREE.Vector3());
        const impulse = new THREE.Vector3()
          .addScaledVector(right, dx * scale)
          .addScaledVector(up, -dy * scale);
        physics.applyImpulse(forceStart.id, impulse);
        forceStart = null;
      }
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target && (e.target as HTMLElement).tagName === 'INPUT') return;
      if (e.key === '1') setMode('select');
      else if (e.key === '2') setMode('drag');
      else if (e.key === '3') setMode('drop_ball');
      else if (e.key === '4') setMode('apply_force');
      else if (e.key === 'r' || e.key === 'R') handleReset();
    };

    canvas.addEventListener('contextmenu', onContextMenu);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('keydown', onKeyDown);

    return () => {
      canvas.removeEventListener('contextmenu', onContextMenu);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [ready]);

  const handleReset = () => {
    const physics = physicsRef.current;
    const viewer = viewerRef.current;
    if (!physics || !viewer) return;
    physics.reset();
    viewer.clearHighlight();
    setSelected(null);
  };

  const handleGravity = (v: number) => {
    setGravity(v);
    physicsRef.current?.setGravity(v);
  };

  const handleFriction = (v: number) => {
    setFrictionScale(v);
    physicsRef.current?.setFrictionScale(v);
    viewerRef.current?.clearHighlight();
    setSelected(null);
  };

  const inspectorRows = useMemo(() => {
    if (!selected) return null;
    const dim = (v: number) => `${(v * 100).toFixed(1)} cm`;
    const rows: Array<readonly [string, string]> = [
      ['Class', selected.classification],
      ['ID', selected.id],
      ['Mesh origin', selected.meshOrigin],
      [
        'AABB size',
        `${dim(selected.bboxSize.x)} × ${dim(selected.bboxSize.y)} × ${dim(selected.bboxSize.z)}`,
      ],
      ['AABB min', `${fmt(selected.bboxMin.x)}, ${fmt(selected.bboxMin.y)}, ${fmt(selected.bboxMin.z)}`],
      ['AABB max', `${fmt(selected.bboxMax.x)}, ${fmt(selected.bboxMax.y)}, ${fmt(selected.bboxMax.z)}`],
    ];
    if (selected.legacyMaterial) rows.push(['Material', selected.legacyMaterial]);
    if (selected.legacyMass !== undefined) rows.push(['Mass', `${selected.legacyMass.toFixed(2)} kg`]);
    if (selected.legacyFriction !== undefined)
      rows.push(['Friction (μ)', selected.legacyFriction.toFixed(2)]);
    if (selected.legacyRestitution !== undefined)
      rows.push(['Restitution', selected.legacyRestitution.toFixed(2)]);
    return rows;
  }, [selected]);

  return (
    <div className="w-full flex-1 flex flex-col md:flex-row p-6 gap-6 h-[calc(100vh-5.25rem)] max-h-[calc(100vh-5.25rem)]">
      <motion.aside
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.15 }}
        className="w-full md:w-80 glass-panel flex flex-col hide-scrollbar overflow-y-auto"
      >
        <div className="p-6 border-b border-border flex items-center justify-between sticky top-0 bg-surface/80 backdrop-blur-md z-10">
          <h3 className="font-semibold text-lg flex items-center gap-2">
            <Settings2 className="w-5 h-5 text-primary" />
            Parameters
          </h3>
          <motion.button
            whileHover={{ scale: 1.1, rotate: 180 }}
            whileTap={{ scale: 0.9 }}
            onClick={handleReset}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
            title="Reset scene (R)"
          >
            <RefreshCcw className="w-4 h-4 text-textSecondary" />
          </motion.button>
        </div>

        <div className="p-6 space-y-6">
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-sm font-medium text-textSecondary">Gravity</label>
              <span className="text-xs font-mono bg-surfaceHover px-2 py-1 rounded">
                {gravity.toFixed(2)} m/s²
              </span>
            </div>
            <input
              type="range" min="-20" max="5" step="0.1"
              value={gravity}
              onChange={(e) => handleGravity(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-surfaceHover rounded-lg appearance-none cursor-pointer accent-primary"
            />
          </div>

          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-sm font-medium text-textSecondary">Friction scale</label>
              <span className="text-xs font-mono bg-surfaceHover px-2 py-1 rounded">
                ×{frictionScale.toFixed(2)}
              </span>
            </div>
            <input
              type="range" min="0" max="2" step="0.05"
              value={frictionScale}
              onChange={(e) => handleFriction(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-surfaceHover rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <p className="text-[10px] text-textSecondary/70 leading-relaxed">
              Rebuilds the world. Selection resets.
            </p>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-border/50">
            <div className="flex items-center gap-2 text-primary font-mono text-sm">
              <Activity className={`w-4 h-4 ${isPlaying ? 'animate-pulse' : 'opacity-50'}`} />
              <span>{isPlaying ? 'Running' : 'Paused'}</span>
            </div>
            <motion.button
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.92 }}
              onClick={() => setIsPlaying((p) => !p)}
              className="w-11 h-11 rounded-full bg-primary/20 text-primary flex items-center justify-center hover:bg-primary/30 transition-colors border border-primary/30 shadow-[0_0_15px_rgba(228,107,69,0.15)]"
            >
              {isPlaying ? <Pause className="fill-current w-4 h-4" /> : <Play className="fill-current w-4 h-4 ml-0.5" />}
            </motion.button>
          </div>
        </div>

        <div className="px-6 pb-6 pt-2 border-t border-border/60">
          <h4 className="text-xs font-semibold tracking-[0.08em] uppercase text-textSecondary mb-3">
            Interaction mode
          </h4>
          <div className="grid grid-cols-2 gap-2">
            {MODE_OPTIONS.map((opt) => {
              const active = mode === opt.value;
              const Icon = opt.icon;
              return (
                <button
                  key={opt.value}
                  onClick={() => setMode(opt.value)}
                  className={[
                    'group flex flex-col items-start gap-1 p-3 rounded-lg border text-left transition-all',
                    active
                      ? 'bg-primary/15 border-primary/40 text-primary shadow-[0_0_18px_rgba(228,107,69,0.15)]'
                      : 'bg-surfaceHover/40 border-border hover:border-primary/30 text-textSecondary hover:text-white',
                  ].join(' ')}
                >
                  <div className="flex items-center justify-between w-full">
                    <Icon className="w-4 h-4" />
                    <kbd className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-black/30 border border-border">
                      {opt.shortcut}
                    </kbd>
                  </div>
                  <div className="text-xs font-semibold">{opt.label}</div>
                  <div className="text-[10px] text-textSecondary/80 group-hover:text-textSecondary">
                    {opt.hint}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="px-6 pb-6 pt-2 border-t border-border/60">
          <h4 className="text-xs font-semibold tracking-[0.08em] uppercase text-textSecondary mb-3 flex items-center gap-2">
            <Info className="w-3 h-3" />
            Inspector
          </h4>
          {!selected ? (
            <div className="text-xs text-textSecondary/80 bg-black/20 border border-border rounded-lg p-3 leading-relaxed">
              Pick <span className="text-primary font-medium">Select</span> and click an object in
              the scene to read its class, AABB, and mesh origin.
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-baseline justify-between">
                <span className="text-base font-semibold text-white">{selected.label}</span>
                <span className="text-[10px] font-mono text-primary/80 uppercase tracking-wider">
                  {selected.meshOrigin}
                </span>
              </div>
              {inspectorRows?.map(([label, value]) => (
                <div key={label} className="flex justify-between items-baseline text-xs border-b border-dashed border-border/60 pb-1.5">
                  <span className="text-textSecondary/70">{label}</span>
                  <span className="font-mono text-white text-right">{value}</span>
                </div>
              ))}
              {selected.legacyVlmReasoning && (
                <div className="mt-3 p-3 rounded-lg bg-primary/5 border border-primary/20 text-[11px] leading-relaxed text-textSecondary">
                  <div className="text-[10px] uppercase tracking-wider text-primary/80 mb-1">
                    VLM reasoning
                  </div>
                  {selected.legacyVlmReasoning}
                </div>
              )}
            </div>
          )}
        </div>
      </motion.aside>

      <motion.div
        ref={wrapperRef}
        initial={{ opacity: 0, scale: 0.985 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2 }}
        className="flex-1 glass-panel relative overflow-hidden"
      >
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full block cursor-crosshair"
        />

        <div className="absolute top-4 left-4 z-10 flex gap-2 pointer-events-none">
          <div className="px-3 py-1.5 rounded-md bg-surface/80 backdrop-blur-md border border-border text-xs font-mono text-textSecondary flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isPlaying ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`} />
            {Math.round(fps)} FPS
          </div>
          <div className="px-3 py-1.5 rounded-md bg-surface/80 backdrop-blur-md border border-border text-xs font-mono text-textSecondary flex items-center gap-2">
            <BoxIcon className="w-3 h-3" />
            {bodyCount} bodies
          </div>
          {sceneName && (
            <div className="px-3 py-1.5 rounded-md bg-surface/80 backdrop-blur-md border border-border text-xs font-mono text-textSecondary">
              {sceneName}
            </div>
          )}
        </div>

        {isFallback && (
          <div className="absolute top-4 right-4 z-10 pointer-events-none">
            <div className="px-3 py-1.5 rounded-md bg-yellow-500/15 backdrop-blur-md border border-yellow-500/40 text-[11px] font-mono text-yellow-200 flex items-center gap-2">
              <AlertTriangle className="w-3 h-3" />
              demo data
              {loadError && (
                <span className="ml-1 text-yellow-200/70 truncate max-w-[18rem]" title={loadError}>
                  · {loadError}
                </span>
              )}
            </div>
          </div>
        )}

        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 px-3 py-1.5 rounded-md bg-surface/70 backdrop-blur-md border border-border text-[11px] font-mono text-textSecondary pointer-events-none">
          drag orbit · wheel zoom ·{' '}
          <kbd className="px-1 py-0.5 rounded bg-black/40 border border-border text-[10px]">1–4</kbd>{' '}
          mode ·{' '}
          <kbd className="px-1 py-0.5 rounded bg-black/40 border border-border text-[10px]">R</kbd>{' '}
          reset
        </div>

        {!ready && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-background/60 backdrop-blur-sm">
            <div className="flex items-center gap-3 text-sm text-textSecondary">
              <Activity className="w-4 h-4 text-primary animate-pulse" />
              Booting physics world…
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}

function fmt(v: number): string {
  return v.toFixed(2);
}

interface Orbit {
  active: boolean;
  lastX: number;
  lastY: number;
  target: THREE.Vector3;
  radius: number;
  theta: number;
  phi: number;
}

function initOrbit(cam: THREE.Vector3, scene: LoadedScene | null): Orbit {
  let targetVec = new THREE.Vector3(0, 0.4, 0);
  if (scene?.cameraHint) {
    const t = scene.cameraHint.target;
    targetVec = new THREE.Vector3(t[0], t[1], t[2]);
  }
  const dx = cam.x - targetVec.x;
  const dy = cam.y - targetVec.y;
  const dz = cam.z - targetVec.z;
  return {
    active: false,
    lastX: 0,
    lastY: 0,
    target: targetVec,
    radius: Math.max(Math.hypot(dx, dy, dz), 0.8),
    theta: Math.atan2(dx, dz),
    phi: Math.atan2(Math.hypot(dx, dz), dy),
  };
}
