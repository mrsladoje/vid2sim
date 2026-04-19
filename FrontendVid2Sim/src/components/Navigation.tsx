import { Sparkles, LogOut } from 'lucide-react';
import { motion } from 'framer-motion';
import Logo from './Logo';
import { CornerMark } from './SectionChrome';
import { WORKSPACE_STATES } from '../App';
import type { AppState } from '../App';

interface NavigationProps {
  appState: AppState;
  setAppState: (state: AppState) => void;
}

const NAV_LINKS: { num: string; label: string; state: AppState }[] = [
  { num: '00', label: 'Home', state: 'hero' },
  { num: '01', label: 'Features', state: 'features' },
  { num: '02', label: 'How it Works', state: 'how-it-works' },
  { num: '03', label: 'FAQ', state: 'faq' },
  { num: '04', label: 'Contact', state: 'contact' },
];

export default function Navigation({ appState, setAppState }: NavigationProps) {
  const inAppWorkspace = WORKSPACE_STATES.includes(appState);

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30, delay: 0.1 }}
      className="fixed top-0 inset-x-0 z-50 bg-background/60 backdrop-blur-xl border-b border-border"
    >
      {/* Top thin telemetry strip */}
      <div className="hidden md:block relative border-b border-border/50 bg-black/20">
        <div className="max-w-7xl mx-auto px-6 py-1 flex items-center justify-between text-[9px] font-mono uppercase tracking-[0.25em] text-textSecondary/70">
          <div className="flex items-center gap-2">
            <span className="relative flex w-1 h-1">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
              <span className="relative inline-flex rounded-full h-1 w-1 bg-emerald-400" />
            </span>
            <span>online</span>
            <span className="text-textSecondary/40">·</span>
            <span>edge·eu-west·02</span>
          </div>
          <div className="flex items-center gap-4">
            <span>v0.1.4-β</span>
            <span className="text-textSecondary/40">·</span>
            <span>
              state · <span className="text-primary">{appState}</span>
            </span>
            <span className="text-textSecondary/40">·</span>
            <span>local</span>
          </div>
        </div>
        <motion.span
          initial={{ x: '-5%' }}
          animate={{ x: '105%' }}
          transition={{ duration: 9, repeat: Infinity, ease: 'linear' }}
          className="absolute top-0 block w-16 h-px bg-gradient-to-r from-transparent via-primary to-transparent"
        />
      </div>

      {/* Main nav bar */}
      <div className="relative max-w-7xl mx-auto px-6 h-16 flex items-center justify-between gap-6">
        <CornerMark className="top-1 left-1" rot={0} size={9} />
        <CornerMark className="bottom-1 left-1" rot={270} size={9} />
        <CornerMark className="top-1 right-1" rot={90} size={9} />
        <CornerMark className="bottom-1 right-1" rot={180} size={9} />

        <Logo onClick={() => setAppState('hero')} />

        {!inAppWorkspace && (
          <nav className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((link) => {
              const active = appState === link.state;
              return (
                <a
                  key={link.state}
                  onClick={(e) => {
                    e.preventDefault();
                    setAppState(link.state);
                  }}
                  className={`relative cursor-pointer px-3.5 py-2 rounded-full transition-colors ${
                    active ? 'text-primary' : 'text-textSecondary hover:text-white'
                  }`}
                >
                  {active && (
                    <motion.div
                      layoutId="nav-pill"
                      className="absolute inset-0 bg-primary/10 border border-primary/30 rounded-full shadow-[0_0_14px_rgba(228,107,69,0.15)]"
                      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                    />
                  )}
                  <span className="relative flex items-center gap-1.5 text-sm tracking-wide">
                    <span
                      className={`text-[9px] font-mono ${
                        active ? 'text-primary/80' : 'text-textSecondary/50'
                      }`}
                    >
                      {link.num}
                    </span>
                    {link.label}
                  </span>
                </a>
              );
            })}
          </nav>
        )}

        {/* Workspace breadcrumb (only in workspace states) */}
        {inAppWorkspace && (
          <div className="hidden md:flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.22em] text-textSecondary/80">
            <span className="text-primary/70">[ws]</span>
            <span>/</span>
            {WORKSPACE_STATES.map((state, i) => (
              <span key={state} className="flex items-center gap-1.5">
                <span
                  className={
                    state === appState ? 'text-primary' : 'text-textSecondary/50'
                  }
                >
                  {state}
                </span>
                {i < WORKSPACE_STATES.length - 1 && (
                  <span className="text-textSecondary/30">›</span>
                )}
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center shrink-0">
          {inAppWorkspace ? (
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              onClick={() => setAppState('hero')}
              className="group flex items-center gap-2 px-4 py-2 rounded-full border border-border hover:border-primary/50 bg-surface/60 hover:bg-primary/5 text-textSecondary hover:text-primary font-mono text-xs uppercase tracking-[0.2em] transition-colors"
            >
              <LogOut className="w-3 h-3" />
              <span>
                <span className="opacity-70">./</span>exit
              </span>
            </motion.button>
          ) : (
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              className="primary-button-solid text-sm px-5 py-2 font-mono"
              onClick={() => setAppState('upload')}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>
                <span className="opacity-70">./</span>launch
              </span>
            </motion.button>
          )}
        </div>
      </div>

      {/* Bottom edge scan-sweep */}
      <motion.span
        initial={{ x: '-10%' }}
        animate={{ x: '110%' }}
        transition={{ duration: 7, repeat: Infinity, ease: 'linear' }}
        className="absolute bottom-0 block w-24 h-px bg-gradient-to-r from-transparent via-primary/70 to-transparent"
      />
    </motion.header>
  );
}
