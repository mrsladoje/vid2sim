import { motion } from 'framer-motion';

/**
 * Site-wide decorative layer. Pointer-events-none, fixed, below all content.
 *
 * Layers (back → front):
 *  1. Dot grid, radial-masked so edges fall off.
 *  2. Faint diagonal line stripes — blueprint vibe.
 *  3. Two soft glow orbs (warm orange + cool blue) for color depth.
 *  4. Center crosshair + corner brackets — engineering/viewfinder cues.
 *  5. Slow horizontal scan-sweep.
 */
export default function BackgroundFX() {
  return (
    <div
      aria-hidden
      className="fixed inset-0 -z-10 pointer-events-none overflow-hidden"
    >
      {/* 1. Dot grid */}
      <div
        className="absolute inset-0 opacity-[0.38]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.12) 1px, transparent 0)',
          backgroundSize: '28px 28px',
          maskImage:
            'radial-gradient(ellipse 85% 70% at 50% 45%, #000 25%, transparent 95%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 85% 70% at 50% 45%, #000 25%, transparent 95%)',
        }}
      />

      {/* 2. Diagonal line stripes */}
      <div
        className="absolute inset-0 opacity-[0.05]"
        style={{
          backgroundImage:
            'repeating-linear-gradient(120deg, transparent 0, transparent 52px, rgba(255,255,255,0.4) 52px, rgba(255,255,255,0.4) 53px)',
        }}
      />

      {/* 3a. Warm glow top-right */}
      <div className="absolute -top-[20%] -right-[12%] w-[720px] h-[720px] rounded-full bg-primary/15 blur-[140px]" />
      {/* 3b. Cool glow bottom-left */}
      <div className="absolute -bottom-[25%] -left-[15%] w-[620px] h-[620px] rounded-full bg-[#3b5bdb]/10 blur-[130px]" />

      {/* 4a. Center crosshair */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="relative w-0 h-0">
          <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 block w-px h-20 bg-gradient-to-b from-transparent via-primary/30 to-transparent" />
          <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 block h-px w-20 bg-gradient-to-r from-transparent via-primary/30 to-transparent" />
          <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 block w-1.5 h-1.5 rounded-full bg-primary/60 shadow-[0_0_12px_rgba(228,107,69,0.6)]" />
        </div>
      </div>

      {/* 4b. Corner brackets */}
      <CornerBracket className="top-6 left-6" rot={0} />
      <CornerBracket className="top-6 right-6" rot={90} />
      <CornerBracket className="bottom-6 right-6" rot={180} />
      <CornerBracket className="bottom-6 left-6" rot={270} />

      {/* 5. Slow horizontal scan-sweep */}
      <motion.div
        initial={{ y: '-20vh', opacity: 0 }}
        animate={{ y: '120vh', opacity: [0, 0.5, 0.5, 0] }}
        transition={{
          duration: 12,
          repeat: Infinity,
          ease: 'linear',
          times: [0, 0.1, 0.9, 1],
        }}
        className="absolute left-0 w-full h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent"
      />

      {/* Subtle top-edge highlight so nav blends in */}
      <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-background/80 via-background/30 to-transparent" />
    </div>
  );
}

function CornerBracket({ className, rot }: { className: string; rot: number }) {
  return (
    <div
      className={`absolute w-5 h-5 ${className}`}
      style={{ transform: `rotate(${rot}deg)` }}
    >
      <span className="absolute top-0 left-0 w-full h-px bg-primary/40" />
      <span className="absolute top-0 left-0 w-px h-full bg-primary/40" />
    </div>
  );
}
