import { motion } from 'framer-motion';
import { GitBranch, AtSign, Globe, ArrowUpRight } from 'lucide-react';
import Logo from './Logo';
import type { AppState } from '../App';

interface FooterProps {
  setAppState: (state: AppState) => void;
}

interface FooterLink {
  label: string;
  state?: AppState;
  href?: string;
}

const PRODUCT_LINKS: FooterLink[] = [
  { label: 'Features', state: 'features' },
  { label: 'How it Works', state: 'how-it-works' },
  { label: 'Launch App', state: 'upload' },
];

const SUPPORT_LINKS: FooterLink[] = [
  { label: 'FAQ', state: 'faq' },
  { label: 'Contact', state: 'contact' },
];

const RESOURCE_LINKS: FooterLink[] = [
  { label: 'Source', href: '#' },
  { label: 'Changelog', href: '#' },
  { label: 'Press kit', href: '#' },
];

const SOCIAL = [
  { icon: GitBranch, label: 'Source' },
  { icon: AtSign, label: 'Contact' },
  { icon: Globe, label: 'Web' },
];

const CURRENT_YEAR = new Date().getFullYear();
const BUILD_ID = 'V2S-0.1.4-β';

export default function Footer({ setAppState }: FooterProps) {
  return (
    <footer className="relative w-full mt-24 border-t border-border bg-surface/30 backdrop-blur-md overflow-hidden">
      {/* Top status ribbon */}
      <div className="relative border-b border-border/60">
        <div className="max-w-7xl mx-auto px-6 py-3 flex flex-wrap items-center justify-between gap-3 text-[10px] font-mono uppercase tracking-[0.18em] text-textSecondary">
          <div className="flex items-center gap-2">
            <span className="relative flex w-1.5 h-1.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
            </span>
            <span>System online · edge·eu-west·02</span>
          </div>
          <div className="hidden md:flex items-center gap-5">
            <span>lat 46.051 · lon 14.506</span>
            <span>gpu·webgpu ready</span>
            <span>rapier·wasm 0.13</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-primary">●</span> <span>v2.7 build {BUILD_ID}</span>
          </div>
        </div>
        {/* animated traveling dot */}
        <motion.span
          initial={{ x: '-5%' }}
          animate={{ x: '105%' }}
          transition={{ duration: 9, repeat: Infinity, ease: 'linear' }}
          className="absolute top-0 block w-16 h-px bg-gradient-to-r from-transparent via-primary to-transparent"
        />
      </div>

      <div className="relative max-w-7xl mx-auto px-6 pt-16 pb-32">
        <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr_1fr_1fr] gap-12">
          {/* Brand column */}
          <div className="flex flex-col">
            <div className="mb-5">
              <Logo onClick={() => setAppState('hero')} />
            </div>
            <p className="text-sm text-textSecondary leading-relaxed max-w-sm">
              Turn real-world footage into interactive, browser-native physics
              simulations — no plugins, no servers, no upload.
            </p>

            {/* Small "terminal" block */}
            <div className="mt-8 rounded-lg border border-border bg-black/30 font-mono text-[11px] leading-relaxed overflow-hidden max-w-md">
              <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-border bg-black/40">
                <span className="w-2 h-2 rounded-full bg-[#ff5f56]" />
                <span className="w-2 h-2 rounded-full bg-[#ffbd2e]" />
                <span className="w-2 h-2 rounded-full bg-[#27c93f]" />
                <span className="ml-2 text-textSecondary tracking-widest uppercase text-[9px]">
                  ~/vid2sim
                </span>
              </div>
              <div className="px-3 py-3 text-textSecondary">
                <div><span className="text-primary">$</span> reconstruct ./oak4_capture.mp4</div>
                <div className="text-emerald-400/80">→ 7 objects · 0.42 s · 60fps lock ✓</div>
              </div>
            </div>
          </div>

          {/* Link columns */}
          <LinkColumn
            index="01"
            title="Product"
            links={PRODUCT_LINKS}
            setAppState={setAppState}
          />
          <LinkColumn
            index="02"
            title="Support"
            links={SUPPORT_LINKS}
            setAppState={setAppState}
          />
          <LinkColumn
            index="03"
            title="Resources"
            links={RESOURCE_LINKS}
            setAppState={setAppState}
          />
        </div>

        {/* Divider */}
        <div className="relative mt-16 mb-6">
          <div className="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex items-center gap-3 px-4 bg-surface/80 backdrop-blur-sm">
              <span className="block w-1 h-1 rounded-full bg-primary" />
              <span className="text-[10px] font-mono uppercase tracking-[0.3em] text-textSecondary">
                end·of·transmission
              </span>
              <span className="block w-1 h-1 rounded-full bg-primary" />
            </div>
          </div>
        </div>

        {/* Bottom meta row */}
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex flex-col gap-1">
            <p className="text-xs text-textSecondary">
              © {CURRENT_YEAR} Vid2Sim. Built for OAK-4 and the open web.
            </p>
            <p className="text-[10px] font-mono uppercase tracking-widest text-textSecondary/60">
              Made with three.js · rapier · react
            </p>
          </div>

          <div className="flex items-center gap-2">
            {SOCIAL.map(({ icon: Icon, label }) => (
              <motion.a
                key={label}
                href="#"
                onClick={(e) => e.preventDefault()}
                aria-label={label}
                whileHover={{ y: -2 }}
                className="group w-10 h-10 rounded-md border border-border bg-surface/40 hover:border-primary/50 hover:bg-primary/10 hover:text-primary text-textSecondary flex items-center justify-center transition-colors relative overflow-hidden"
              >
                <Icon className="w-4 h-4 relative z-10" />
                <span className="absolute inset-0 bg-gradient-to-br from-primary/0 via-primary/0 to-primary/10 opacity-0 group-hover:opacity-100 transition-opacity" />
              </motion.a>
            ))}
          </div>
        </div>

        {/* Giant faded wordmark */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 -bottom-4 flex justify-center select-none"
        >
          <span
            className="font-black tracking-[-0.06em] leading-[0.8] text-transparent bg-clip-text bg-gradient-to-b from-primary/20 via-primary/5 to-transparent"
            style={{ fontSize: 'clamp(8rem, 18vw, 22rem)' }}
          >
            VID2SIM
          </span>
        </div>

        {/* Corner brackets inside footer */}
        <CornerMark className="top-4 left-4" rot={0} />
        <CornerMark className="top-4 right-4" rot={90} />
      </div>

      {/* Tiny hover "back to top" button */}
      <motion.button
        onClick={() => setAppState('hero')}
        whileHover={{ y: -3 }}
        whileTap={{ scale: 0.95 }}
        className="absolute bottom-6 right-6 z-10 group flex items-center gap-2 px-3 py-2 rounded-full border border-border bg-surface/80 backdrop-blur-md text-[10px] font-mono uppercase tracking-widest text-textSecondary hover:text-primary hover:border-primary/40 transition-colors"
      >
        Top
        <ArrowUpRight className="w-3 h-3 group-hover:rotate-45 transition-transform" />
      </motion.button>
    </footer>
  );
}

function LinkColumn({
  index,
  title,
  links,
  setAppState,
}: {
  index: string;
  title: string;
  links: FooterLink[];
  setAppState: (state: AppState) => void;
}) {
  return (
    <div className="flex flex-col">
      <div className="flex items-baseline gap-2 mb-5">
        <span className="text-[10px] font-mono text-primary/70">[{index}]</span>
        <h4 className="text-xs font-semibold uppercase tracking-[0.2em] text-white">
          {title}
        </h4>
      </div>
      <ul className="flex flex-col gap-2.5">
        {links.map((link) => (
          <li key={link.label}>
            <button
              onClick={() => {
                if (link.state) setAppState(link.state);
              }}
              className="group inline-flex items-center gap-2 text-sm text-textSecondary hover:text-white transition-colors"
            >
              <span className="w-3 h-px bg-border group-hover:w-5 group-hover:bg-primary transition-all" />
              {link.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CornerMark({ className, rot }: { className: string; rot: number }) {
  return (
    <div
      className={`absolute w-4 h-4 ${className}`}
      style={{ transform: `rotate(${rot}deg)` }}
    >
      <span className="absolute top-0 left-0 w-full h-px bg-primary/40" />
      <span className="absolute top-0 left-0 w-px h-full bg-primary/40" />
    </div>
  );
}
