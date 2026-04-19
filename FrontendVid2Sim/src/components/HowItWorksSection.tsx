import { motion } from 'framer-motion';
import { Camera, Upload, Sparkles, ArrowRight, Cog } from 'lucide-react';
import SectionHeader from './SectionHeader';
import { StatusRibbon, CornerMark, SectionDivider } from './SectionChrome';

interface HowItWorksSectionProps {
  onStart: () => void;
}

const STEPS = [
  {
    num: '01',
    tag: 'stage·capture',
    title: 'Capture',
    text: 'Record your subject with the OAK-4 depth camera to get synchronized RGB and depth.',
    icon: Camera,
  },
  {
    num: '02',
    tag: 'stage·upload',
    title: 'Upload',
    text: 'Drag and drop the .mp4 into the engine. Reconstruction happens fully on-device.',
    icon: Upload,
  },
  {
    num: '03',
    tag: 'stage·interact',
    title: 'Interact',
    text: 'Tune gravity, friction, and mode. Watch the reconstructed object respond in real time.',
    icon: Sparkles,
  },
];

export default function HowItWorksSection({ onStart }: HowItWorksSectionProps) {
  return (
    <div className="w-full flex flex-col items-center px-6 py-24 max-w-6xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full mb-10"
      >
        <StatusRibbon
          id="SYS·PIPE"
          label="process pipeline · 3 stages"
          right={
            <>
              <span>on-device</span>
              <span className="hidden md:inline">latency·local</span>
              <span className="text-primary">●</span>
            </>
          }
        />
      </motion.div>

      <SectionHeader
        eyebrow={{ icon: Cog, label: 'Pipeline' }}
        index="03"
        title={
          <>
            Three steps. <span className="primary-gradient">Zero friction.</span>
          </>
        }
        subtitle="From raw footage to a playable simulation in minutes."
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 w-full relative">
        {/* Connecting rail (desktop only) */}
        <div
          aria-hidden
          className="hidden md:block absolute left-0 right-0 top-[4.25rem] h-px pointer-events-none"
        >
          <div className="h-full bg-gradient-to-r from-transparent via-primary/30 to-transparent" />
          <motion.span
            initial={{ x: '-5%' }}
            animate={{ x: '105%' }}
            transition={{ duration: 6, repeat: Infinity, ease: 'linear' }}
            className="block -mt-px w-8 h-px bg-primary shadow-[0_0_10px_rgba(228,107,69,0.8)]"
          />
        </div>

        {STEPS.map((step, idx) => {
          const Icon = step.icon;
          return (
            <motion.div
              key={step.num}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: 'spring', delay: 0.15 + idx * 0.1 }}
              className="relative glass-panel p-8 overflow-hidden group hover:border-primary/40 transition-colors"
            >
              <CornerMark className="top-3 left-3" rot={0} size={12} />
              <CornerMark className="top-3 right-3" rot={90} size={12} />
              <CornerMark className="bottom-3 right-3" rot={180} size={12} />
              <CornerMark className="bottom-3 left-3" rot={270} size={12} />

              {/* Step ID plate (above card, sits on the rail) */}
              <div className="relative mb-5 flex items-center justify-between">
                <div className="w-12 h-12 rounded-xl bg-primary/10 border border-primary/30 flex items-center justify-center relative z-10">
                  <Icon className="w-5 h-5 text-primary" />
                </div>
                <div className="flex flex-col items-end font-mono">
                  <span className="text-[10px] uppercase tracking-[0.2em] text-textSecondary/70">
                    {step.tag}
                  </span>
                  <span className="text-5xl font-black text-primary/10 leading-none tracking-tighter">
                    {step.num}
                  </span>
                </div>
              </div>

              <h3 className="text-xl font-bold mb-3 flex items-baseline gap-2">
                <span className="text-primary/60 font-mono text-sm">[{step.num}]</span>
                {step.title}
              </h3>
              <p className="text-textSecondary leading-relaxed">{step.text}</p>

              {/* Input/output pseudo labels */}
              <div className="mt-5 pt-4 border-t border-dashed border-border/60 flex items-center justify-between text-[10px] font-mono uppercase tracking-widest text-textSecondary/60">
                <span>
                  in ·{' '}
                  {idx === 0 ? 'sensor' : idx === 1 ? 'mp4' : 'scene'}
                </span>
                <ArrowRight className="w-3 h-3 text-primary/60" />
                <span>
                  out ·{' '}
                  {idx === 0 ? 'mp4' : idx === 1 ? 'scene' : 'physics'}
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>

      <SectionDivider label="end·pipeline" />

      <motion.button
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6 }}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={onStart}
        className="primary-button-solid text-sm px-7 py-3"
      >
        Try Demo Pipeline
        <ArrowRight className="w-4 h-4" />
      </motion.button>
    </div>
  );
}
