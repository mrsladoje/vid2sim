import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { UploadCloud, FileVideo, X, ScanLine } from 'lucide-react';
import { StatusRibbon, CornerMark } from './SectionChrome';

interface UploadSectionProps {
  onUploadComplete: () => void;
}

export default function UploadSection({ onUploadComplete }: UploadSectionProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handlePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setFile(f);
    e.target.value = '';
  };

  const simulateUpload = () => {
    if (!file) return;
    onUploadComplete();
  };

  return (
    <div className="w-full flex-1 flex flex-col items-center justify-center relative px-4 py-16">
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-2xl mb-6"
      >
        <StatusRibbon
          id="SYS·SCAN"
          label="awaiting input · oak-4 capture"
          right={
            <>
              <span>max·2gb</span>
              <span className="hidden md:inline">codec·h264|h265</span>
              <span className="text-primary">●</span>
            </>
          }
        />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="relative w-full max-w-2xl glass-panel p-10 flex flex-col overflow-hidden"
      >
        <CornerMark className="top-3 left-3" rot={0} size={14} />
        <CornerMark className="top-3 right-3" rot={90} size={14} />
        <CornerMark className="bottom-3 right-3" rot={180} size={14} />
        <CornerMark className="bottom-3 left-3" rot={270} size={14} />

        <div className="flex items-baseline gap-3 mb-6">
          <span className="text-xs font-mono text-primary/70">[01]</span>
          <div>
            <h2 className="text-3xl font-bold">Upload Footage</h2>
            <p className="text-textSecondary mt-1">
              Drag and drop your OAK-4 capture in .mp4 format
            </p>
          </div>
        </div>

        {!file ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
            }}
            className={`
              relative w-full h-72 rounded-2xl border-2 border-dashed transition-all duration-300 flex flex-col items-center justify-center cursor-pointer overflow-hidden
              ${
                isDragging
                  ? 'border-primary bg-primary/5 scale-[1.02]'
                  : 'border-border bg-surface/30 hover:border-textSecondary/50'
              }
            `}
          >
            <input
              ref={inputRef}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={handlePick}
            />

            {/* Scanner grid backdrop */}
            <div
              aria-hidden
              className="absolute inset-0 opacity-[0.08] pointer-events-none"
              style={{
                backgroundImage:
                  'linear-gradient(to right, rgba(228,107,69,0.5) 1px, transparent 1px), linear-gradient(to bottom, rgba(228,107,69,0.5) 1px, transparent 1px)',
                backgroundSize: '20px 20px',
              }}
            />

            {/* Moving scan line */}
            <motion.div
              aria-hidden
              initial={{ y: '-100%' }}
              animate={{ y: '100%' }}
              transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
              className="absolute left-0 w-full h-12 bg-gradient-to-b from-transparent via-primary/15 to-transparent pointer-events-none"
            />

            <CornerMark className="top-3 left-3" rot={0} size={10} />
            <CornerMark className="top-3 right-3" rot={90} size={10} />
            <CornerMark className="bottom-3 right-3" rot={180} size={10} />
            <CornerMark className="bottom-3 left-3" rot={270} size={10} />

            <div className="relative w-16 h-16 rounded-full bg-surface border border-border flex items-center justify-center mb-4 shadow-lg">
              <UploadCloud
                className={`w-8 h-8 ${
                  isDragging ? 'text-primary' : 'text-textSecondary'
                }`}
              />
            </div>
            <p className="relative font-medium mb-1">
              Click to browse or drag file here
            </p>
            <p className="relative text-[10px] text-textSecondary uppercase tracking-[0.25em] font-mono flex items-center gap-2">
              <ScanLine className="w-3 h-3" />
              target zone · up to 2GB
            </p>
          </div>
        ) : (
          <div className="relative w-full h-72 rounded-2xl border border-border bg-surface/30 flex flex-col items-center justify-center">
            <motion.button
              whileHover={{ scale: 1.1, rotate: 90 }}
              whileTap={{ scale: 0.9 }}
              onClick={() => setFile(null)}
              className="absolute top-4 right-4 p-2 rounded-full hover:bg-white/10 transition-colors"
            >
              <X className="w-5 h-5 text-textSecondary" />
            </motion.button>

            <CornerMark className="top-3 left-3" rot={0} size={10} />
            <CornerMark className="top-3 right-3" rot={90} size={10} />
            <CornerMark className="bottom-3 right-3" rot={180} size={10} />
            <CornerMark className="bottom-3 left-3" rot={270} size={10} />

            <div className="w-16 h-16 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center mb-4 text-primary shadow-[0_0_20px_rgba(228,107,69,0.15)]">
              <FileVideo className="w-8 h-8" />
            </div>
            <p className="font-mono text-sm text-textSecondary mb-1">
              <span className="text-primary">file·</span>
              {file.name}
            </p>
            <p className="text-[10px] font-mono text-textSecondary/70 uppercase tracking-[0.2em] mb-6">
              {(file.size / (1024 * 1024)).toFixed(2)} MB · ready
            </p>

            <motion.button
              whileHover={{
                scale: 1.05,
                boxShadow: '0 0 20px rgba(228,107,69,0.3)',
              }}
              whileTap={{ scale: 0.95 }}
              onClick={simulateUpload}
              className="primary-button-solid text-sm px-7 py-3 font-mono"
            >
              <span className="opacity-70">./</span>process_video
            </motion.button>
          </div>
        )}

        {/* Bottom tech strip */}
        <div className="mt-5 pt-3 border-t border-dashed border-border/60 flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono uppercase tracking-[0.2em] text-textSecondary/60">
          <span>encoder·on-device</span>
          <span>pipeline·vid2sim-0.1</span>
          <span className="text-primary">●</span>
        </div>
      </motion.div>
    </div>
  );
}
