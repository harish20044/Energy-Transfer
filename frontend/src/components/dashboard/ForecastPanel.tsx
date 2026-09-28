import { ArrowDownToLine, ArrowUpFromLine, Minus } from 'lucide-react';

import type { HourForecast, RecommendedAction } from '@/api/forecast';
import { Badge } from '@/components/ui/Badge';
import type { BadgeTone } from '@/components/ui/Badge';
import { cn } from '@/lib/cn';
import { kw, signed, simClock } from '@/lib/format';

const ACTION_LABEL: Record<RecommendedAction, string> = {
  sell: 'Sell',
  buy: 'Buy',
  hold: 'Hold',
};

const ACTION_TONE: Record<RecommendedAction, BadgeTone> = {
  sell: 'solar',
  buy: 'grid',
  hold: 'neutral',
};

function ActionIcon({ action }: { action: RecommendedAction }) {
  if (action === 'sell') return <ArrowUpFromLine className="size-4" aria-hidden="true" />;
  if (action === 'buy') return <ArrowDownToLine className="size-4" aria-hidden="true" />;
  return <Minus className="size-4" aria-hidden="true" />;
}

function HourCard({ hour }: { hour: HourForecast }) {
  // The worst and best plausible net positions this hour — least generation
  // paired with most consumption, and vice versa — giving the P10-P90 band
  // real content instead of a single point guess.
  const netWorst = hour.generation_p10 - hour.consumption_p90;
  const netBest = hour.generation_p90 - hour.consumption_p10;

  return (
    <div
      className={cn(
        'flex flex-col gap-2.5 rounded-lg border p-3.5',
        hour.recommended_action === 'sell' && 'border-solar-200 bg-solar-50/40',
        hour.recommended_action === 'buy' && 'border-grid-200 bg-grid-50/40',
        hour.recommended_action === 'hold' && 'border-stone-100',
      )}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-stone-500">
          +{hour.horizon_hours}h · {simClock(hour.hour_of_day)}
        </p>
        <Badge tone={ACTION_TONE[hour.recommended_action]}>
          <ActionIcon action={hour.recommended_action} />
          {ACTION_LABEL[hour.recommended_action]}
        </Badge>
      </div>

      <p className="text-lg font-semibold tnum text-stone-900">
        {signed(hour.net_p50_kw, kw)}
        <span className="ml-1 text-xs font-normal text-stone-400">net</span>
      </p>

      <p className="text-[11px] text-stone-500">
        Likely {signed(netWorst, kw)} to {signed(netBest, kw)}
      </p>
    </div>
  );
}

export function ForecastPanel({ hours, model }: { hours: HourForecast[]; model: string }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {hours.map((hour) => (
          <HourCard key={hour.horizon_hours} hour={hour} />
        ))}
      </div>
      <p className="text-[11px] text-stone-400">
        {model === 'lightgbm-quantile'
          ? 'LightGBM quantile forecast, trained on your household’s own consumption and generation patterns.'
          : 'Seasonal-naive fallback (same hour, yesterday) — the trained model isn’t available in this environment.'}{' '}
        Based on your battery’s current charge, not a projection of where it’ll be by then.
      </p>
    </div>
  );
}
