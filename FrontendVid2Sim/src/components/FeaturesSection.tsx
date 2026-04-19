import { motion } from 'framer-motion';
import { Camera, Layers, Zap, Glasses, Sparkles } from 'lucide-react';
import SectionHeader from './SectionHeader';
import { StatusRibbon, CornerMark, SectionDivider } from './SectionChrome';

interface FeaturesSectionProps {
  onStart: () => void;
}

const FEATURES = [
  {
    num: '01',
    tag: 'sensor.depth',
    title: 'Depth Perception',
    description:
      'Harness OAK-4 stereo depth to capture real-world geometry with accurate scale and proportion.',
    icon: Camera,
  },
  {
    num: '02',
    tag: 'mesh.stitch',
    title: 'Mesh Reconstruction',
    description:
      'Stitch 2D frames into watertight 3D meshes automatically, ready for physics interaction.',
    icon: Layers,
  },
  {
    num: '03',
    tag: 'physics.rt',
    title: 'Real-time Physics',
    description:
      'Apply gravity, friction, and collision on the fly with a multi-threaded WebAssembly engine.',
    icon: Zap,
  },
  {
    num: '04',
    tag: 'runtime.browser',
    title: 'Browser Native',
    description:
      'No installs, no plugins. Full reconstruction and playback run entirely in your browser.',
    icon: Glasses,
  },
];

export default function FeaturesSection({ onStart }: FeaturesSectionProps) {
  return (
    <div className="w-full flex flex-col items-center px-6 py-24 max-w-7xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full mb-10"
      >
        <StatusRibbon
          id="SYS·FEAT"
          label="capability manifest · /features"
          right={
            <>
              <span>4 modules</span>
              <span className="hidden md:inline">wasm·ready</span>
              <span className="text-primary">●</span>
            </>
          }
        />
      </motion.div>

      <SectionHeader
        eyebrow={{ icon: Sparkles, label: 'Capabilities' }}
        index="02"
        title={
          <>
            Everything you need to <br />
            <span className="primary-gradient">bridge reality and simulation</span>
          </>
        }
        subtitle="A sophisticated pipeline engineered for high-fidelity interactive conversion."
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 w-full">
        {FEATURES.map((feature, idx) => {
          const Icon = feature.icon;
          return (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: 'spring', delay: 0.15 + idx * 0.08 }}
              whileHover={{ y: -4 }}
              className="relative glass-panel p-8 group hover:border-primary/40 transition-colors overflow-hidden"
            >
              <CornerMark className="top-3 left-3" rot={0} size={12} />
              <CornerMark className="top-3 right-3" rot={90} size={12} />
              <CornerMark className="bottom-3 right-3" rot={180} size={12} />
              <CornerMark className="bottom-3 left-3" rot={270} size={12} />

              {/* Internal grid backdrop */}
              <div
                aria-hidden
                className="absolute inset-0 opacity-[0.06] pointer-events-none"
                style={{
                  backgroundImage:
                    'linear-gradient(to right, rgba(255,255,255,0.3) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.3) 1px, transparent 1px)',
                  backgroundSize: '24px 24px',
                }}
              />

              <div className="relative flex items-center justify-between mb-5">
                <div className="w-12 h-12 rounded-xl bg-surface border border-border flex items-center justify-center group-hover:bg-primary/10 group-hover:border-primary/30 transition-colors">
                  <Icon className="w-5 h-5 text-primary" />
                </div>
                <div className="flex flex-col items-end gap-1 font-mono">
                  <span className="text-[10px] uppercase tracking-[0.2em] text-textSecondary/70">
                    {feature.tag}
                  </span>
                  <span className="text-3xl font-black text-primary/15 leading-none tracking-tighter">
                    {feature.num}
                  </span>
                </div>
              </div>

              <h3 className="relative text-xl font-bold mb-3 flex items-baseline gap-2">
                <span className="text-primary/60 font-mono text-sm">[{feature.num}]</span>
                {feature.title}
              </h3>
              <p className="relative text-textSecondary leading-relaxed">
                {feature.description}
              </p>

              {/* Hover tracer line */}
              <motion.span
                className="absolute bottom-0 left-0 h-px bg-gradient-to-r from-primary via-primary/50 to-transparent"
                initial={{ width: 0 }}
                whileHover={{ width: '100%' }}
                transition={{ duration: 0.5 }}
              />
            </motion.div>
          );
        })}
      </div>

      <SectionDivider label="end·manifest" />

      <motion.button
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6 }}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={onStart}
        className="primary-button-solid text-sm px-7 py-3"
      >
        Start Exploring
      </motion.button>
    </div>
  );
}
