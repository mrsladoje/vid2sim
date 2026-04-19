import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, Database, Box, CheckCircle } from 'lucide-react';
import { StatusRibbon, CornerMark } from './SectionChrome';

interface ProcessingScreenProps {
  onComplete: () => void;
}

const STEPS = [
  { id: '01', tag: 'stage·depth', text: 'Analyzing depth maps…', icon: Database },
  { id: '02', tag: 'stage·mesh', text: 'Reconstructing 3D meshes…', icon: Box },
  { id: '03', tag: 'stage·physics', text: 'Building physics simulation…', icon: Loader2 },
];

const LOG_LINES = [
  '[00.12] oak-4 → rgb + depth streams aligned',
  '[00.48] depth-to-point cloud · 482k pts',
  '[01.02] mesh stitch · 7 candidates',
  '[01.41] material classifier · lookup table',
  '[01.98] rapier world · bodies wired',
];

export default function ProcessingScreen({ onComplete }: ProcessingScreenProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [visibleLogs, setVisibleLogs] = useState(0);

  useEffect(() => {
    let timeout: number;
    if (currentStep < STEPS.length) {
      timeout = window.setTimeout(() => setCurrentStep((p) => p + 1), 2000);
    } else {
      timeout = window.setTimeout(onComplete, 1000);
    }
    return () => clearTimeout(timeout);
  }, [currentStep, onComplete]);

  useEffect(() => {
    if (visibleLogs >= LOG_LINES.length) return;
    const t = window.setTimeout(
      () => setVisibleLogs((v) => v + 1),
      400 + Math.random() * 600,
    );
    return () => clearTimeout(t);
  }, [visibleLogs]);

  const progress = Math.min(Math.round((currentStep / STEPS.length) * 100), 100);
  const done = currentStep >= STEPS.length;

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
            label={done ? 'simulation ready · hand-off' : 'pipeline running · 3 stages'}
            right={
              <>
                <span>stage {Math.min(currentStep + 1, STEPS.length)} / {STEPS.length}</span>
                <span className="hidden md:inline">{progress}% complete</span>
                <span className={done ? 'text-emerald-400' : 'text-primary'}>●</span>
              </>
            }
          />
        </motion.div>

        <div className="relative glass-panel p-10 overflow-hidden">
          <CornerMark className="top-3 left-3" rot={0} size={14} />
          <CornerMark className="top-3 right-3" rot={90} size={14} />
          <CornerMark className="bottom-3 right-3" rot={180} size={14} />
          <CornerMark className="bottom-3 left-3" rot={270} size={14} />

          {/* Internal grid */}
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
              {/* ambient glow */}
              <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-full animate-pulse-slow" />
              <svg className="absolute inset-0 w-full h-full -rotate-90">
                <circle
                  cx="80" cy="80" r="72"
                  stroke="rgba(255,255,255,0.08)"
                  strokeWidth="6" fill="none"
                />
                <circle
                  cx="80" cy="80" r="72"
                  stroke="#E46B45"
                  strokeWidth="6" fill="none"
                  strokeDasharray={2 * Math.PI * 72}
                  strokeDashoffset={2 * Math.PI * 72 * (1 - progress / 100)}
                  style={{ transition: 'stroke-dashoffset 1.8s cubic-bezier(0.22,1,0.36,1)' }}
                  strokeLinecap="round"
                />
              </svg>
              <div className="flex flex-col items-center">
                <div className="text-3xl font-bold font-mono text-primary">
                  {progress}%
                </div>
                <div className="text-[9px] font-mono uppercase tracking-[0.25em] text-textSecondary mt-1">
                  pipeline
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                {STEPS.map((step, i) => {
                  const state =
                    i < currentStep ? 'done' : i === currentStep ? 'active' : 'pending';
                  const Icon = step.icon;
                  return (
                    <div
                      key={step.id}
                      className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-colors ${
                        state === 'active'
                          ? 'border-primary/40 bg-primary/5'
                          : state === 'done'
                          ? 'border-emerald-500/30 bg-emerald-500/5'
                          : 'border-border bg-surface/30'
                      }`}
                    >
                      <span
                        className={`text-[10px] font-mono shrink-0 ${
                          state === 'active'
                            ? 'text-primary'
                            : state === 'done'
                            ? 'text-emerald-400'
                            : 'text-textSecondary/60'
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
                            : 'text-textSecondary/60'
                        }`}
                      />
                      <span
                        className={`text-sm ${
                          state === 'pending'
                            ? 'text-textSecondary/60'
                            : 'text-white'
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
                    Handing off to simulation…
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Terminal log */}
          <div className="relative mt-8 rounded-lg border border-border bg-black/40 font-mono text-[11px] leading-relaxed overflow-hidden">
            <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-border bg-black/50">
              <span className="w-2 h-2 rounded-full bg-[#ff5f56]" />
              <span className="w-2 h-2 rounded-full bg-[#ffbd2e]" />
              <span className="w-2 h-2 rounded-full bg-[#27c93f]" />
              <span className="ml-2 text-textSecondary tracking-[0.2em] uppercase text-[9px]">
                vid2sim · pipeline.log
              </span>
            </div>
            <div className="px-3 py-3 text-textSecondary space-y-0.5 min-h-[96px]">
              {LOG_LINES.slice(0, visibleLogs).map((line) => (
                <motion.div
                  key={line}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="font-mono"
                >
                  <span className="text-primary">›</span>{' '}
                  <span className="text-textSecondary/90">{line}</span>
                </motion.div>
              ))}
              {visibleLogs < LOG_LINES.length && (
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
