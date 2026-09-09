import { Bell } from 'lucide-react';
import { useLocation } from 'react-router-dom';

import { PAGE_META } from '@/components/layout/navigation';
import { marketState } from '@/data/mock';
import { useApiHealth } from '@/hooks/useApiHealth';
import { useCountdown } from '@/hooks/useCountdown';
import { cn } from '@/lib/cn';
import { countdown, inr } from '@/lib/format';

const API_LABELS = {
  checking: 'Connecting',
  online: 'Live',
  offline: 'Offline',
} as const;

const API_DOTS = {
  checking: 'bg-stone-400',
  online: 'bg-battery-500',
  offline: 'bg-grid-500',
} as const;

export function TopBar() {
  const { pathname } = useLocation();
  const meta = PAGE_META[pathname] ?? PAGE_META['/'];
  const secondsLeft = useCountdown(marketState.gateClosesInSeconds);
  const apiHealth = useApiHealth();

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-6 border-b border-stone-200 bg-white px-6">
      <div className="min-w-0">
        <h1 className="truncate text-base font-bold tracking-tight text-stone-900">
          {meta?.title}
        </h1>
        <p className="truncate text-xs text-stone-500">{meta?.subtitle}</p>
      </div>

      <div className="flex items-center gap-3">
        <div
          className="hidden items-center gap-2 rounded-lg border border-stone-200 px-3 py-1.5 md:flex"
          title={`Backend API: ${API_LABELS[apiHealth]}`}
        >
          <span className={cn('size-2 rounded-full', API_DOTS[apiHealth])} aria-hidden="true" />
          <span className="text-xs font-medium text-stone-600">{API_LABELS[apiHealth]}</span>
        </div>

        <div className="hidden items-center gap-2 rounded-lg border border-stone-200 px-3 py-1.5 lg:flex">
          <span className="text-xs font-medium text-stone-500">Clearing price</span>
          <span className="font-mono text-sm font-semibold text-stone-900 tnum">
            {inr(marketState.clearingInr)}
          </span>
          <span className="text-xs text-stone-400">/kWh</span>
        </div>

        <div className="flex items-center gap-2 rounded-lg bg-stone-900 px-3 py-1.5 text-white">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-2 animate-ping rounded-full bg-battery-500 opacity-75" />
            <span className="relative inline-flex size-2 rounded-full bg-battery-500" />
          </span>
          <span className="text-xs font-medium text-stone-300">Gate closes</span>
          <span className="font-mono text-sm font-semibold tnum">{countdown(secondsLeft)}</span>
        </div>

        <button
          type="button"
          aria-label="Notifications"
          className="relative flex size-9 items-center justify-center rounded-lg border border-stone-200 text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900"
        >
          <Bell className="size-[18px]" aria-hidden="true" />
          <span className="absolute top-2 right-2 size-1.5 rounded-full bg-grid-500" />
        </button>
      </div>
    </header>
  );
}
