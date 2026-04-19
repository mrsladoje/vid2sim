import { Sparkles } from 'lucide-react';

interface LogoProps {
  onClick?: () => void;
  interactive?: boolean;
}

export default function Logo({ onClick, interactive = true }: LogoProps) {
  const badge = (
    <div className={`w-8 h-8 rounded-lg bg-gradient-to-br from-primaryHover to-primary flex items-center justify-center shadow-[0_0_12px_rgba(228,107,69,0.4)] ${interactive ? 'group-hover:shadow-[0_0_20px_rgba(228,107,69,0.6)] transition-shadow' : ''}`}>
      <Sparkles className="w-4 h-4 text-white" />
    </div>
  );

  if (!onClick) {
    return (
      <div className="flex items-center gap-2.5">
        {badge}
        <span className="font-bold text-lg tracking-tight">Vid2Sim</span>
      </div>
    );
  }

  return (
    <button onClick={onClick} className="flex items-center gap-2.5 group shrink-0">
      {badge}
      <span className="font-bold text-lg tracking-tight">Vid2Sim</span>
    </button>
  );
}
