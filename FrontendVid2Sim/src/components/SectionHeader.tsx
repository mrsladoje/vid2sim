import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import type { LucideIcon } from 'lucide-react';

interface SectionHeaderProps {
  eyebrow?: { icon?: LucideIcon; label: string };
  index?: string;
  title: ReactNode;
  subtitle?: ReactNode;
  align?: 'center' | 'left';
  maxWidth?: string;
}

export default function SectionHeader({
  eyebrow,
  index,
  title,
  subtitle,
  align = 'center',
  maxWidth = 'max-w-3xl',
}: SectionHeaderProps) {
  const Icon = eyebrow?.icon;
  const alignClass =
    align === 'center' ? 'text-center mx-auto items-center' : 'text-left items-start';

  return (
    <div className={`mb-14 flex flex-col ${alignClass} ${maxWidth}`}>
      {eyebrow && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="inline-flex items-center gap-2.5 px-3.5 py-1.5 rounded-full border border-primary/30 bg-primary/10 backdrop-blur-sm mb-6"
        >
          {index && (
            <span className="text-[10px] font-mono text-primary/70">[{index}]</span>
          )}
          {Icon && <Icon className="w-3.5 h-3.5 text-primary" />}
          <span className="text-xs font-semibold text-primary uppercase tracking-widest">
            {eyebrow.label}
          </span>
        </motion.div>
      )}

      <motion.h2
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring' }}
        className="text-4xl md:text-5xl font-bold mb-4 tracking-tight leading-[1.1]"
      >
        {title}
      </motion.h2>

      {/* Accent underscore */}
      <motion.div
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.7, delay: 0.15, ease: 'easeOut' }}
        className={`h-px w-24 bg-gradient-to-r from-primary/80 to-transparent mb-5 ${
          align === 'center' ? 'origin-center' : 'origin-left'
        }`}
      />

      {subtitle && (
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', delay: 0.1 }}
          className="text-lg text-textSecondary leading-relaxed"
        >
          {subtitle}
        </motion.p>
      )}
    </div>
  );
}
