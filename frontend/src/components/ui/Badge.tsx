import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

export type BadgeTone = 'neutral' | 'solar' | 'battery' | 'peer' | 'grid' | 'warning';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-stone-100 text-stone-700 ring-stone-200',
  solar: 'bg-solar-50 text-solar-700 ring-solar-200',
  battery: 'bg-battery-50 text-battery-700 ring-battery-200',
  peer: 'bg-peer-50 text-peer-700 ring-peer-200',
  grid: 'bg-grid-50 text-grid-700 ring-grid-200',
  warning: 'bg-amber-50 text-amber-800 ring-amber-200',
};

interface BadgeProps {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}

export function Badge({ tone = 'neutral', className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
