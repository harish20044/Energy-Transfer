import { CheckCircle2, Clock, PlugZap } from 'lucide-react';

import type { OwnSlot } from '@/api/session';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/cn';
import { hourLabel, kwh } from '@/lib/format';
import { strategyMeta } from '@/lib/session';

function Traded({ slot }: { slot: OwnSlot }) {
  const parts: string[] = [];
  if (slot.p2p_sold_kwh > 0.005) parts.push(`sold ${kwh(slot.p2p_sold_kwh)} to neighbours`);
  if (slot.p2p_bought_kwh > 0.005) parts.push(`bought ${kwh(slot.p2p_bought_kwh)} from neighbours`);
  if (slot.eb_bought_kwh > 0.005) parts.push(`${kwh(slot.eb_bought_kwh)} from the EB`);
  if (slot.eb_sold_kwh > 0.005) parts.push(`${kwh(slot.eb_sold_kwh)} to the EB`);
  return <span>{parts.length > 0 ? parts.join(' · ') : 'no trades'}</span>;
}

/** The agent's hour-by-hour plan: what it decided and said before each
 *  hour's market, how that market turned out, and — once delivered — what
 *  actually happened. */
export function AgentPlan({ slots, deliveredHours }: { slots: OwnSlot[]; deliveredHours: number }) {
  return (
    <ol className="divide-y divide-stone-100">
      {slots.map((slot) => {
        const decision = slot.decision;
        const meta = strategyMeta(decision?.strategy ?? 'idle');
        const current = slot.slot === deliveredHours;
        return (
          <li
            key={slot.slot}
            className={cn(
              'grid grid-cols-[72px_1fr] gap-4 px-5 py-3.5',
              current && 'bg-peer-50/50',
            )}
          >
            <div className="flex flex-col items-start gap-1">
              <span className="font-mono text-sm font-bold text-stone-900 tnum">
                {hourLabel(slot.hour_of_day)}
              </span>
              {slot.delivered ? (
                <span className="flex items-center gap-1 text-[11px] font-medium text-battery-600">
                  <CheckCircle2 className="size-3" aria-hidden="true" /> delivered
                </span>
              ) : current ? (
                <span className="flex items-center gap-1 text-[11px] font-medium text-peer-600">
                  <Clock className="size-3" aria-hidden="true" /> next
                </span>
              ) : null}
              {!slot.eb_available && (
                <span className="flex items-center gap-1 text-[11px] font-medium text-grid-600">
                  <PlugZap className="size-3" aria-hidden="true" /> EB cut
                </span>
              )}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={meta.tone}>{meta.label}</Badge>
                <span className="text-xs text-stone-500">
                  <Traded slot={slot} />
                </span>
              </div>
              {decision !== null && decision.message !== '' && (
                <p className="mt-1.5 text-sm leading-relaxed text-stone-700">{decision.message}</p>
              )}
              {decision !== null && decision.outcome !== '' && (
                <p className="mt-1 text-xs text-stone-500">→ {decision.outcome}</p>
              )}
              {slot.delivered && (
                <p className="mt-1.5 font-mono text-[11px] text-stone-500 tnum">
                  Actual: load {(slot.actual_consumption_kwh ?? 0).toFixed(2)} · solar{' '}
                  {(slot.actual_generation_kwh ?? 0).toFixed(2)} · EB in{' '}
                  {(slot.actual_eb_import_kwh ?? 0).toFixed(2)} / out{' '}
                  {(slot.actual_eb_export_kwh ?? 0).toFixed(2)}
                  {(slot.actual_unserved_kwh ?? 0) > 0.005 &&
                    ` · unserved ${(slot.actual_unserved_kwh ?? 0).toFixed(2)}`}
                  {slot.battery_soc_end !== null &&
                    ` · battery ${String(Math.round(slot.battery_soc_end * 100))}%`}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
