import type { LucideIcon } from 'lucide-react';

import { cn } from '@/lib/cn';

export type StatTone = 'solar' | 'battery' | 'peer' | 'grid' | 'neutral';

const TONES: Record<StatTone, string> = {
  solar: 'bg-solar-50 text-solar-600',
  battery: 'bg-battery-50 text-battery-600',
  peer: 'bg-peer-50 text-peer-600',
  grid: 'bg-grid-50 text-grid-600',
  neutral: 'bg-stone-100 text-stone-600',
};

interface StatTileProps {
  label: string;
  value: string;
  caption?: string;
  icon: LucideIcon;
  tone?: StatTone;
}

export function StatTile({ label, value, caption, icon: Icon, tone = 'neutral' }: StatTileProps) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-stone-200 bg-white p-4">
      <span
        className={cn('flex size-9 shrink-0 items-center justify-center rounded-lg', TONES[tone])}
      >
        <Icon className="size-[18px]" strokeWidth={2} aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium text-stone-500">{label}</p>
        <p className="mt-0.5 font-mono text-xl font-bold text-stone-900 tnum">{value}</p>
        {caption !== undefined && (
          <p className="mt-0.5 truncate text-xs text-stone-500">{caption}</p>
        )}
      </div>
    </div>
  );
}
