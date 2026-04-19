import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, HelpCircle } from 'lucide-react';
import SectionHeader from './SectionHeader';
import { StatusRibbon, SectionDivider } from './SectionChrome';

const FAQS = [
  {
    q: 'What camera hardware do I need?',
    a: 'Vid2Sim is optimized for the Luxonis OAK-4 camera, which provides the stereo depth data required for accurate mesh reconstruction. Any other RGB-D source that exports standard depth maps will also work.',
  },
  {
    q: 'How long does it take to process a video?',
    a: 'A 30-second clip typically reconstructs in under two minutes on a modern laptop. Longer footage scales roughly linearly. All heavy computation runs locally in the browser via WebAssembly.',
  },
  {
    q: 'Is my footage uploaded to a server?',
    a: 'No. Everything happens on-device. Files you drop into the uploader never leave your machine, and the reconstructed scene lives in your browser memory only.',
  },
  {
    q: 'Can I export the physics scene?',
    a: 'Yes — reconstructed meshes can be exported as glTF, and the full physics configuration can be saved as a JSON preset that other Vid2Sim users can load.',
  },
  {
    q: 'Does it support soft-body simulation?',
    a: 'Soft-body is in preview. Rigid-body is fully supported today with gravity, friction, restitution, and collision-bound controls. Cloth and fluid are on the roadmap.',
  },
];

export default function FaqSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  return (
    <div className="w-full min-h-full flex flex-col items-center px-6 py-24 max-w-3xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full mb-10"
      >
        <StatusRibbon
          id="SYS·DOCS"
          label="knowledge base · faq"
          right={
            <>
              <span>{FAQS.length} entries</span>
              <span className="hidden md:inline">indexed·ok</span>
              <span className="text-primary">●</span>
            </>
          }
        />
      </motion.div>

      <SectionHeader
        eyebrow={{ icon: HelpCircle, label: 'FAQ' }}
        index="04"
        title={
          <>
            Frequently asked <span className="primary-gradient">questions</span>
          </>
        }
        subtitle="Everything you need to know about the pipeline, the hardware, and what runs where."
      />

      <div className="w-full flex flex-col gap-3">
        {FAQS.map((faq, idx) => {
          const isOpen = openIndex === idx;
          const num = String(idx + 1).padStart(2, '0');
          return (
            <motion.div
              key={faq.q}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + idx * 0.05 }}
              className={`glass-panel overflow-hidden transition-colors ${
                isOpen ? 'border-primary/40' : ''
              }`}
            >
              <button
                onClick={() => setOpenIndex(isOpen ? null : idx)}
                className="w-full px-6 py-5 flex items-center justify-between gap-4 text-left hover:bg-white/5 transition-colors"
              >
                <div className="flex items-baseline gap-3">
                  <span
                    className={`text-xs font-mono shrink-0 ${
                      isOpen ? 'text-primary' : 'text-primary/60'
                    }`}
                  >
                    [{num}]
                  </span>
                  <span className="font-semibold text-base md:text-lg">{faq.q}</span>
                </div>
                <motion.div
                  animate={{ rotate: isOpen ? 45 : 0 }}
                  transition={{ type: 'spring', stiffness: 300, damping: 20 }}
                  className={`w-8 h-8 rounded-full border flex items-center justify-center shrink-0 transition-colors ${
                    isOpen
                      ? 'border-primary/50 bg-primary/10'
                      : 'border-border bg-surface'
                  }`}
                >
                  <Plus className="w-4 h-4 text-primary" />
                </motion.div>
              </button>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25, ease: 'easeInOut' }}
                  >
                    <div className="px-6 pb-5 pt-4 border-t border-border/50 text-textSecondary leading-relaxed flex gap-3">
                      <span className="text-primary font-mono text-sm select-none mt-0.5">
                        &gt;
                      </span>
                      <p>{faq.a}</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>

      <SectionDivider label="end·knowledge" />
    </div>
  );
}
