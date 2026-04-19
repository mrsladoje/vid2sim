import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, Database, Box, CheckCircle, AlertTriangle } from 'lucide-react';
import { StatusRibbon, CornerMark } from './SectionChrome';

interface ProcessingScreenProps {
  /** Job ID from `POST /pipeline/run`; null means we're in the stub path. */
  jobId: string | null;
  /** Called when the pipeline finishes (session_id is null for the stub path). */
  onComplete: (sessionId: string | null) => void;
}

const STUB_STEPS = [
  { id: '01', tag: 'stage·depth', text: 'Analyzing depth maps…', icon: Database },
  { id: '02', tag: 'stage·mesh', text: 'Reconstructing 3D meshes…', icon: Box },
  { id: '03', tag: 'stage·physics', text: 'Building physics simulation…', icon: Loader2 },
];

const STUB_LOG_LINES = [
  '[stub] drag-and-drop path cannot feed Stream 01 (no depth/IMU).',
  '[stub] falling back to the cached rec_01_sf3d scene.',
  '[stub] use the live-capture tab with an OAK to run the real pipeline.',
];

/** Maps the server's state string to a user-facing step index. */
function stageToStep(state: string, stage: string): number {
  if (state === 'capturing') return 0;
  if (state === 'reconstructing') return 1;
  if (state === 'assembling') return 2;
  if (state === 'done') return 3;
  if (state === 'failed') {
    if (stage === 'capture') return 0;
    if (stage === 'reconstruct') return 1;
    if (stage === 'assemble') return 2;
  }
  return 0;
}

const REAL_STEPS = [
  { id: '01', tag: 'stage·capture', text: 'Capturing RGB + depth + masks…', icon: Database },
  { id: '02', tag: 'stage·reconstruct', text: 'Per-object mesh reconstruction…', icon: Box },
  { id: '03', tag: 'stage·assemble', text: 'CoACD decomposition + scene package…', icon: Loader2 },
];

interface JobStatus {
  job_id: string;
  session_id: string;
  state: 'queued' | 'capturing' | 'reconstructing' | 'assembling' | 'done' | 'failed';
  stage: string;
  error: string | null;
  elapsed_s: number;
  scene_url: string | null;
  log_lines: string[];
  duration_s: number;
}

export default function ProcessingScreen({ jobId, onComplete }: ProcessingScreenProps) {
  const isReal = jobId !== null;

  // --- stub path (drag-and-drop) -------------------------------------
  const [stubStep, setStubStep] = useState(0);
  const [stubLogs, setStubLogs] = useState(0);
  useEffect(() => {
    if (isReal) return;
    let t: number;
    if (stubStep < STUB_STEPS.length) {
      t = window.setTimeout(() => setStubStep((s) => s + 1), 2000);
    } else {
      t = window.setTimeout(() => onComplete(null), 1000);
    }
    return () => clearTimeout(t);
  }, [isReal, stubStep, onComplete]);
  useEffect(() => {
    if (isReal) return;
    if (stubLogs >= STUB_LOG_LINES.length) return;
    const t = window.setTimeout(
      () => setStubLogs((v) => v + 1),
      400 + Math.random() * 600,
    );
    return () => clearTimeout(t);
  }, [isReal, stubLogs]);

  // --- real path — poll the job server --------------------------------
  const [job, setJob] = useState<JobStatus | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const terminatedRef = useRef(false);

  useEffect(() => {
    if (!isReal) return;
    let cancelled = false;
    terminatedRef.current = false;

    const tick = async () => {
      try {
        const res = await fetch(`http://127.0.0.1:8765/pipeline/status/${jobId}`, {
          cache: 'no-store',
        });
        if (!res.ok) throw new Error(`status HTTP ${res.status}`);
        const body = (await res.json()) as JobStatus;
        if (cancelled) return;
        setJob(body);
        setPollError(null);
        if ((body.state === 'done' || body.state === 'failed') && !terminatedRef.current) {
          terminatedRef.current = true;
          if (body.state === 'done') {
            // Small grace delay so the user sees the "done" state flash.
            setTimeout(() => { if (!cancelled) onComplete(body.session_id); }, 600);
          }
        }
      } catch (err) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        setPollError(`Could not reach job server: ${msg}`);
      }
    };

    void tick();
    const interval = window.setInterval(() => void tick(), 800);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [isReal, jobId, onComplete]);

  // Unified view model.
  const steps = isReal ? REAL_STEPS : STUB_STEPS;
  const currentStep = isReal ? stageToStep(job?.state ?? 'queued', job?.stage ?? '') : stubStep;
  const done = isReal ? (job?.state === 'done') : (stubStep >= STUB_STEPS.length);
  const failed = isReal ? (job?.state === 'failed') : false;
  const progress = Math.min(Math.round((currentStep / steps.length) * 100), 100);
  const visibleLogs: string[] = isReal
    ? (job?.log_lines ?? []).slice(-14)
    : STUB_LOG_LINES.slice(0, stubLogs);

  const headerLabel = failed
    ? 'pipeline failed · check logs'
    : done
      ? 'simulation ready · hand-off'
      : isReal
        ? 'live pipeline · 3 stages'
        : 'pipeline running · 3 stages (stub)';

  return (
    <div className="w-full flex-1 flex flex-col items-center justify-center relative py-16 min-h-[calc(100vh-5.25rem)] px-4">
      <div className="w-full max-w-3xl flex flex-col">
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6"
        >
          <StatusRibbon
            id="SYS·PROC"
            label={headerLabel}
            right={
              <>
                <span>stage {Math.min(currentStep + 1, steps.length)} / {steps.length}</span>
                <span className="hidden md:inline">{progress}% complete</span>
                <span className={failed ? 'text-red-400' : done ? 'text-emerald-400' : 'text-primary'}>●</span>
              </>
            }
          />
        </motion.div>

        <div className="relative glass-panel p-10 overflow-hidden">
          <CornerMark className="top-3 left-3" rot={0} size={14} />
          <CornerMark className="top-3 right-3" rot={90} size={14} />
          <CornerMark className="bottom-3 right-3" rot={180} size={14} />
          <CornerMark className="bottom-3 left-3" rot={270} size={14} />

          <div
            aria-hidden
            className="absolute inset-0 opacity-[0.05] pointer-events-none"
            style={{
              backgroundImage:
                'linear-gradient(to right, rgba(255,255,255,0.4) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.4) 1px, transparent 1px)',
              backgroundSize: '24px 24px',
            }}
          />

          <div className="relative grid grid-cols-1 md:grid-cols-[auto_1fr] gap-10 items-center">
            <div className="relative w-40 h-40 flex items-center justify-center mx-auto">
              <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-full animate-pulse-slow" />
              <svg className="absolute inset-0 w-full h-full -rotate-90">
                <circle cx="80" cy="80" r="72" stroke="rgba(255,255,255,0.08)" strokeWidth="6" fill="none" />
                <circle
                  cx="80" cy="80" r="72"
                  stroke={failed ? '#f87171' : '#E46B45'}
                  strokeWidth="6" fill="none"
                  strokeDasharray={2 * Math.PI * 72}
                  strokeDashoffset={2 * Math.PI * 72 * (1 - progress / 100)}
                  style={{ transition: 'stroke-dashoffset 1.8s cubic-bezier(0.22,1,0.36,1)' }}
                  strokeLinecap="round"
                />
              </svg>
              <div className="flex flex-col items-center">
                <div className={`text-3xl font-bold font-mono ${failed ? 'text-red-300' : 'text-primary'}`}>
                  {progress}%
                </div>
                <div className="text-[9px] font-mono uppercase tracking-[0.25em] text-textSecondary mt-1">
                  pipeline
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                {steps.map((step, i) => {
                  const state =
                    failed && i === currentStep ? 'failed'
                    : i < currentStep ? 'done'
                    : i === currentStep ? 'active'
                    : 'pending';
                  const Icon = step.icon;
                  return (
                    <div
                      key={step.id}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-colors ${
                        state === 'active'
                          ? 'border-primary/40 bg-primary/5'
                          : state === 'done'
                            ? 'border-emerald-500/30 bg-emerald-500/5'
                            : state === 'failed'
                              ? 'border-red-500/40 bg-red-500/10'
                              : 'border-border bg-surface/30'
                      }`}
                    >
                      <span
                        className={`text-[10px] font-mono shrink-0 ${
                          state === 'active' ? 'text-primary' :
                          state === 'done' ? 'text-emerald-400' :
                          state === 'failed' ? 'text-red-300' :
                          'text-textSecondary/60'
                        }`}
                      >
                        [{step.id}]
                      </span>
                      <Icon
                        className={`w-4 h-4 shrink-0 ${
                          state === 'active'
                            ? 'text-primary ' + (step.icon === Loader2 ? 'animate-spin' : '')
                            : state === 'done'
                              ? 'text-emerald-400'
                              : state === 'failed'
                                ? 'text-red-300'
                                : 'text-textSecondary/60'
                        }`}
                      />
                      <span
                        className={`text-sm ${
                          state === 'pending' ? 'text-textSecondary/60' : 'text-white'
                        }`}
                      >
                        {step.text}
                      </span>
                      <span className="ml-auto text-[10px] font-mono uppercase tracking-[0.2em] text-textSecondary/60">
                        {step.tag}
                      </span>
                    </div>
                  );
                })}
              </div>

              <AnimatePresence>
                {done && (
                  <motion.div
                    key="done"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex items-center gap-2 text-emerald-400 font-medium"
                  >
                    <CheckCircle className="w-5 h-5" />
                    {isReal && job?.session_id
                      ? `Session ${job.session_id} ready — handing off…`
                      : 'Handing off to simulation…'}
                  </motion.div>
                )}
                {failed && (
                  <motion.div
                    key="failed"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex items-start gap-2 text-red-300"
                  >
                    <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
                    <div className="flex flex-col gap-1">
                      <span className="font-medium">Pipeline failed</span>
                      <span className="text-xs text-red-300/80">{job?.error ?? 'unknown error'}</span>
                      <button
                        onClick={() => onComplete(null)}
                        className="self-start mt-2 px-3 py-1 rounded border border-border bg-black/30 text-[11px] font-mono hover:bg-white/5"
                      >
                        continue with cached scene
                      </button>
                    </div>
                  </motion.div>
                )}
                {pollError && !failed && (
                  <motion.div
                    key="pollErr"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex items-center gap-2 text-yellow-300 text-xs font-mono"
                  >
                    <AlertTriangle className="w-4 h-4" />
                    {pollError}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          <div className="relative mt-8 rounded-lg border border-border bg-black/40 font-mono text-[11px] leading-relaxed overflow-hidden">
            <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-border bg-black/50">
              <span className="w-2 h-2 rounded-full bg-[#ff5f56]" />
              <span className="w-2 h-2 rounded-full bg-[#ffbd2e]" />
              <span className="w-2 h-2 rounded-full bg-[#27c93f]" />
              <span className="ml-2 text-textSecondary tracking-[0.2em] uppercase text-[9px]">
                vid2sim · pipeline.log {isReal && job ? `· ${job.session_id}` : '· stub'}
              </span>
              {isReal && job && (
                <span className="ml-auto text-[9px] text-textSecondary/70">
                  {job.elapsed_s.toFixed(1)}s
                </span>
              )}
            </div>
            <div className="px-3 py-3 text-textSecondary space-y-0.5 min-h-[160px] max-h-[240px] overflow-y-auto">
              {visibleLogs.length === 0 && (
                <div className="text-textSecondary/50 italic">waiting for first log line…</div>
              )}
              {visibleLogs.map((line, i) => (
                <div key={`${line}-${i}`} className="font-mono whitespace-pre-wrap break-all">
                  <span className="text-primary">›</span>{' '}
                  <span className="text-textSecondary/90">{line}</span>
                </div>
              ))}
              {!done && !failed && (
                <div className="flex items-center gap-1 text-primary">
                  <span className="animate-pulse">▋</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
