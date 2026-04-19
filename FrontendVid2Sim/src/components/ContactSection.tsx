import { motion } from 'framer-motion';
import { Send, Mail, MessageSquare, Clock, MapPin } from 'lucide-react';
import SectionHeader from './SectionHeader';
import { StatusRibbon, CornerMark, SectionDivider } from './SectionChrome';

export default function ContactSection() {
  return (
    <div className="w-full flex flex-col items-center px-6 py-24 max-w-5xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full mb-10"
      >
        <StatusRibbon
          id="SYS·RELAY"
          label="signal channel · open"
          right={
            <>
              <span>SLA&nbsp;·&nbsp;48h</span>
              <span className="hidden md:inline">ch·secure</span>
              <span className="text-primary">●</span>
            </>
          }
        />
      </motion.div>

      <SectionHeader
        eyebrow={{ icon: MessageSquare, label: 'Contact' }}
        index="05"
        title={
          <>
            Get in <span className="primary-gradient">touch</span>
          </>
        }
        subtitle="Interested in Vid2Sim for your studio or research team? Send a note — we read every message."
      />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="grid grid-cols-1 md:grid-cols-[1fr_1.4fr] gap-5 w-full"
      >
        <div className="relative glass-panel p-8 flex flex-col gap-6 overflow-hidden">
          <CornerMark className="top-3 left-3" rot={0} size={12} />
          <CornerMark className="top-3 right-3" rot={90} size={12} />
          <CornerMark className="bottom-3 right-3" rot={180} size={12} />
          <CornerMark className="bottom-3 left-3" rot={270} size={12} />

          <InfoRow
            icon={Mail}
            tag="channel·email"
            title="Email us"
            body="For partnerships, press, and licensing."
            foot={
              <a
                href="mailto:hello@vid2sim.app"
                className="text-primary hover:text-primaryHover text-sm font-mono"
              >
                hello@vid2sim.app
              </a>
            }
          />
          <div className="border-t border-border/60 pt-6">
            <InfoRow
              icon={Clock}
              tag="channel·sla"
              title="Response time"
              body="We reply within two business days. Enterprise requests are prioritized."
            />
          </div>
          <div className="border-t border-border/60 pt-6">
            <InfoRow
              icon={MapPin}
              tag="channel·node"
              title="Based in"
              body="Ljubljana, SI · serving teams globally."
            />
          </div>

          {/* Telemetry footer */}
          <div className="mt-2 pt-4 border-t border-dashed border-border/60 flex items-center justify-between text-[10px] font-mono uppercase tracking-widest text-textSecondary/60">
            <span>relay·online</span>
            <span className="text-primary">●</span>
            <span>ping 42 ms</span>
          </div>
        </div>

        <form
          className="relative glass-panel p-8 flex flex-col gap-5 overflow-hidden"
          onSubmit={(e) => e.preventDefault()}
        >
          <CornerMark className="top-3 left-3" rot={0} size={12} />
          <CornerMark className="top-3 right-3" rot={90} size={12} />
          <CornerMark className="bottom-3 right-3" rot={180} size={12} />
          <CornerMark className="bottom-3 left-3" rot={270} size={12} />

          <div className="flex items-center justify-between pb-2 border-b border-dashed border-border/60">
            <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-textSecondary/70">
              compose · new_message.txt
            </span>
            <span className="text-[10px] font-mono text-primary/70">[DRAFT]</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FieldWrap index="01" label="Name">
              <input
                type="text"
                className="field-input"
                placeholder="Jane Doe"
              />
            </FieldWrap>
            <FieldWrap index="02" label="Email">
              <input
                type="email"
                className="field-input"
                placeholder="jane@studio.com"
              />
            </FieldWrap>
          </div>

          <FieldWrap index="03" label="Message">
            <textarea
              rows={5}
              className="field-input resize-none"
              placeholder="> How can we help?"
            />
          </FieldWrap>

          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            className="primary-button-solid text-sm px-6 py-3 mt-1 font-mono"
          >
            <span className="opacity-70">./</span>send_message
            <Send className="w-4 h-4" />
          </motion.button>
        </form>
      </motion.div>

      <SectionDivider label="end·channel" />

      <style>{`
        .field-input {
          width: 100%;
          background: rgba(18, 18, 22, 0.5);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 0.5rem;
          padding: 0.75rem 1rem;
          font-size: 0.875rem;
          color: #fff;
          transition: border-color 0.15s, background 0.15s;
          font-family: inherit;
        }
        .field-input::placeholder {
          color: rgba(255, 255, 255, 0.4);
        }
        .field-input:focus {
          outline: none;
          border-color: rgba(228, 107, 69, 0.5);
          background: rgba(18, 18, 22, 0.7);
        }
      `}</style>
    </div>
  );
}

function InfoRow({
  icon: Icon,
  tag,
  title,
  body,
  foot,
}: {
  icon: React.ComponentType<{ className?: string }>;
  tag: string;
  title: string;
  body: string;
  foot?: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/30 flex items-center justify-center text-primary">
          <Icon className="w-4 h-4" />
        </div>
        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-textSecondary/70">
          {tag}
        </span>
      </div>
      <h3 className="font-bold text-lg mb-1">{title}</h3>
      <p className="text-sm text-textSecondary mb-2 leading-relaxed">{body}</p>
      {foot}
    </div>
  );
}

function FieldWrap({
  index,
  label,
  children,
}: {
  index: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="flex items-center gap-2 text-xs font-semibold text-textSecondary uppercase tracking-wider">
        <span className="text-primary/70 font-mono text-[10px]">[{index}]</span>
        {label}
      </label>
      {children}
    </div>
  );
}
