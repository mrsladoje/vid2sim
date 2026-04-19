import { motion } from 'framer-motion';
import type { Variants } from 'framer-motion';
import { Sparkles, ArrowRight, Play, Cpu, Camera, ChevronDown } from 'lucide-react';
import { StatusRibbon, CornerMark } from './SectionChrome';

interface HeroSectionProps {
  onStart: () => void;
}

const STATS = [
  { num: '01', tag: 'fps·render', value: '60 FPS', label: 'Browser playback' },
  { num: '02', tag: 't·reconstruct', value: '<2 min', label: 'Avg reconstruction time' },
  { num: '03', tag: 'net·zero', value: '100%', label: 'On-device, zero upload' },
];

const CONTAINER_VARS: Variants = {
  initial: { opacity: 0 },
  enter: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.2 },
  },
};

const ITEM_VARS: Variants = {
  initial: { opacity: 0, y: 40, scale: 0.95 },
  enter: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: 'spring', stiffness: 200, damping: 18 },
  },
};

export default function HeroSection({ onStart }: HeroSectionProps) {
  return (
    <div className="w-full min-h-full flex flex-col items-center relative px-4 pt-10 pb-16">
      {/* Perspective grid + glow layer (unchanged dramatic backdrop). */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none perspective-1000 flex items-center justify-center">
        <motion.div
          initial={{ rotateX: 60, y: 150, opacity: 0 }}
          animate={{ rotateX: 60, y: 100, opacity: 0.32 }}
          transition={{ duration: 1.5, ease: 'easeOut' }}
          className="absolute w-[200vw] h-[200vh] bg-[linear-gradient(to_right,rgba(228,107,69,0.1)_1px,transparent_1px),linear-gradient(to_bottom,rgba(228,107,69,0.1)_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_20%,transparent_100%)]"
        />
        <motion.div
          animate={{ y: [0, -20, 0], opacity: [0.3, 0.55, 0.3] }}
          transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
          className="absolute top-1/4 left-1/4 w-32 h-32 bg-primary/30 rounded-full blur-[60px]"
        />
        <motion.div
          animate={{ y: [0, 30, 0], opacity: [0.2, 0.45, 0.2] }}
          transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut', delay: 1 }}
          className="absolute bottom-1/4 right-1/4 w-64 h-64 bg-primary/20 rounded-full blur-[80px]"
        />
      </div>

      {/* Top status ribbon */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative z-10 w-full max-w-5xl mb-10"
      >
        <StatusRibbon
          id="SYS·CORE"
          label="vid2sim · realtime reconstruction engine"
          right={
            <>
              <span>cam·oak-4</span>
              <span className="hidden md:inline">gpu·webgpu</span>
              <span className="hidden md:inline">wasm·rapier</span>
              <span className="text-primary">●</span>
            </>
          }
        />
      </motion.div>

      {/* Floating HUD badges (desktop only, flanking the headline) */}
      <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.5, duration: 0.6 }}
        className="hidden lg:block absolute left-10 top-52 z-10 pointer-events-none"
      >
        <HudBadge tag="[01]" title="CAM·OAK-4" value="stereo depth · 30hz" icon={Camera} />
      </motion.div>
      <motion.div
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.6, duration: 0.6 }}
        className="hidden lg:block absolute right-10 top-52 z-10 pointer-events-none"
      >
        <HudBadge tag="[02]" title="GPU·WEBGPU" value="60 fps · rapier wasm" icon={Cpu} />
      </motion.div>

      <motion.div
        variants={CONTAINER_VARS}
        initial="initial"
        animate="enter"
        className="relative z-10 max-w-5xl mx-auto flex flex-col items-center text-center"
      >
        <motion.div
          variants={ITEM_VARS}
          className="inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full border border-primary/30 bg-primary/10 backdrop-blur-md mb-8"
        >
          <span className="text-[10px] font-mono text-primary/70">[00]</span>
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-semibold text-primary uppercase tracking-widest">
            Vid2Sim · Beta
          </span>
          <span className="block w-1 h-1 rounded-full bg-primary/70" />
          <span className="text-[10px] font-mono text-primary/70">build·0.1.4</span>
        </motion.div>

        <motion.h1
          variants={ITEM_VARS}
          className="text-5xl md:text-7xl lg:text-8xl font-black tracking-tighter mb-4 leading-[1.05]"
        >
          Turn real video <br className="hidden md:block" />
          into <span className="primary-gradient pb-2 inline-block">physics.</span>
        </motion.h1>

        {/* Title accent */}
        <motion.div
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ delay: 0.5, duration: 0.8, ease: 'easeOut' }}
          className="origin-center h-px w-40 bg-gradient-to-r from-transparent via-primary/70 to-transparent mb-7"
        />

        <motion.p
          variants={ITEM_VARS}
          className="text-lg md:text-xl text-textSecondary max-w-2xl font-light mb-10 leading-relaxed"
        >
          Upload footage captured with your OAK-4 camera and interact with
          reconstructed objects in a browser-native simulation engine.
        </motion.p>

        <motion.div
          variants={ITEM_VARS}
          className="flex flex-col sm:flex-row items-center gap-4 mb-14"
        >
          <motion.button
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
            onClick={onStart}
            className="primary-button-solid text-base px-7 py-3.5 font-mono"
          >
            <span className="opacity-70">./</span>init_engine
            <ArrowRight className="w-4 h-4" />
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
            className="flex items-center gap-3 text-white hover:text-primary transition-colors py-3 px-5 font-medium group"
          >
            <div className="w-10 h-10 rounded-full border border-border group-hover:border-primary flex items-center justify-center bg-surface/80 transition-colors">
              <Play className="w-3.5 h-3.5 ml-0.5" />
            </div>
            Watch Demo
          </motion.button>
        </motion.div>

        {/* Pipeline ready-check strip */}
        <motion.div
          variants={ITEM_VARS}
          className="flex flex-wrap items-center justify-center gap-2 md:gap-3 mb-10 text-[10px] font-mono uppercase tracking-[0.25em] text-textSecondary/80"
        >
          <ReadyPill label="depth" />
          <Dots />
          <ReadyPill label="mesh" />
          <Dots />
          <ReadyPill label="physics" />
          <Dots />
          <ReadyPill label="runtime" />
        </motion.div>

        <motion.div
          variants={ITEM_VARS}
          className="relative grid grid-cols-3 gap-0 w-full max-w-3xl rounded-xl border border-border bg-surface/40 backdrop-blur-sm overflow-hidden"
        >
          <CornerMark className="top-2 left-2" rot={0} size={10} />
          <CornerMark className="top-2 right-2" rot={90} size={10} />
          <CornerMark className="bottom-2 right-2" rot={180} size={10} />
          <CornerMark className="bottom-2 left-2" rot={270} size={10} />

          {STATS.map((stat, i) => (
            <div
              key={stat.label}
              className={`flex flex-col items-center text-center px-4 py-6 ${
                i < STATS.length - 1 ? 'border-r border-border/60' : ''
              }`}
            >
              <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.2em] text-textSecondary/70 mb-2">
                <span className="text-primary/70">[{stat.num}]</span>
                <span>{stat.tag}</span>
              </div>
              <div className="text-2xl md:text-4xl font-bold primary-gradient leading-none">
                {stat.value}
              </div>
              <div className="text-xs md:text-sm text-textSecondary mt-2">
                {stat.label}
              </div>
            </div>
          ))}
        </motion.div>

        {/* Scroll cue */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
          className="mt-14 flex flex-col items-center gap-2"
        >
          <span className="text-[10px] font-mono uppercase tracking-[0.3em] text-textSecondary/60">
            scroll · init pipeline
          </span>
          <motion.div
            animate={{ y: [0, 6, 0], opacity: [0.4, 0.9, 0.4] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
            className="text-primary/70"
          >
            <ChevronDown className="w-4 h-4" />
          </motion.div>
        </motion.div>
      </motion.div>
    </div>
  );
}

function HudBadge({
  tag,
  title,
  value,
  icon: Icon,
}: {
  tag: string;
  title: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="relative rounded-lg border border-border bg-surface/70 backdrop-blur-md px-3 py-2 font-mono text-left overflow-hidden">
      <CornerMark className="top-1 left-1" rot={0} size={8} />
      <CornerMark className="top-1 right-1" rot={90} size={8} />
      <CornerMark className="bottom-1 right-1" rot={180} size={8} />
      <CornerMark className="bottom-1 left-1" rot={270} size={8} />
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[9px] text-primary/70">{tag}</span>
        <Icon className="w-3 h-3 text-primary" />
        <span className="text-[10px] uppercase tracking-[0.2em] text-white">
          {title}
        </span>
      </div>
      <div className="text-[10px] text-textSecondary/80 lowercase">{value}</div>
    </div>
  );
}

function ReadyPill({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border bg-surface/50">
      <span className="block w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
      {label}
    </span>
  );
}

function Dots() {
  return <span className="text-primary/40">/</span>;
}
