import type { ReactNode } from 'react';
import { motion } from 'framer-motion';

/**
 * Thin top-of-section status ribbon. Matches the footer's telemetry strip.
 * Use it at the top of a page section to establish the engineering/blueprint vibe.
 */
export function StatusRibbon({
  id,
  label,
  right,
}: {
  id: string;
  label: string;
  right?: ReactNode;
}) {
  return (
    <div className="relative w-full border border-border/60 bg-black/20 backdrop-blur-sm rounded-lg overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2 text-[10px] font-mono uppercase tracking-[0.18em] text-textSecondary">
        <div className="flex items-center gap-2">
          <span className="relative flex w-1.5 h-1.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
          </span>
          <span className="text-primary">[{id}]</span>
          <span>{label}</span>
        </div>
        {right && (
          <div className="flex items-center gap-5 text-textSecondary/80">{right}</div>
        )}
      </div>
      <motion.span
        initial={{ x: '-5%' }}
        animate={{ x: '105%' }}
        transition={{ duration: 9, repeat: Infinity, ease: 'linear' }}
        className="absolute top-0 block w-16 h-px bg-gradient-to-r from-transparent via-primary to-transparent"
      />
    </div>
  );
}

/** L-shaped corner marker. Rotate with `rot` (0 / 90 / 180 / 270). */
export function CornerMark({
  className = '',
  rot = 0,
  size = 16,
}: {
  className?: string;
  rot?: number;
  size?: number;
}) {
  return (
    <div
      className={`absolute pointer-events-none ${className}`}
      style={{ width: size, height: size, transform: `rotate(${rot}deg)` }}
    >
      <span className="absolute top-0 left-0 w-full h-px bg-primary/50" />
      <span className="absolute top-0 left-0 w-px h-full bg-primary/50" />
    </div>
  );
}

/** End-of-section divider with label plate. */
export function SectionDivider({ label }: { label: string }) {
  return (
    <div className="relative w-full my-12">
      <div className="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="flex items-center gap-3 px-4 bg-background/80 backdrop-blur-sm">
          <span className="block w-1 h-1 rounded-full bg-primary" />
          <span className="text-[10px] font-mono uppercase tracking-[0.3em] text-textSecondary">
            {label}
          </span>
          <span className="block w-1 h-1 rounded-full bg-primary" />
        </div>
      </div>
    </div>
  );
}
