import { ArrowDownLeft, ArrowUpRight, TriangleAlert } from 'lucide-react';

import { cn } from '@/lib/cn';
import { inr, kwh } from '@/lib/format';
import type { Trade } from '@/types/energy';

interface TradeListProps {
  trades: Trade[];
  selectedId?: string;
  onSelect?: (trade: Trade) => void;
}

export function TradeList({ trades, selectedId, onSelect }: TradeListProps) {
  const interactive = onSelect !== undefined;

  return (
    <ul className="divide-y divide-stone-100">
      {trades.map((trade) => {
        const isSell = trade.side === 'sell';
        const Icon = isSell ? ArrowUpRight : ArrowDownLeft;

        return (
          <li key={trade.id}>
            <button
              type="button"
              disabled={!interactive}
              onClick={() => onSelect?.(trade)}
              className={cn(
                'flex w-full items-center gap-3 px-5 py-3 text-left transition-colors',
                interactive && 'hover:bg-stone-50',
                selectedId === trade.id && 'bg-peer-50/60',
                !interactive && 'cursor-default',
              )}
            >
              <span
                className={cn(
                  'flex size-8 shrink-0 items-center justify-center rounded-lg',
                  isSell ? 'bg-peer-50 text-peer-600' : 'bg-grid-50 text-grid-600',
                )}
              >
                <Icon className="size-4" strokeWidth={2.25} aria-hidden="true" />
              </span>

              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1.5 text-sm font-semibold text-stone-900">
                  {isSell ? 'Sold to' : 'Bought from'} {trade.counterparty}
                  {trade.bindingConstraint !== null && (
                    <TriangleAlert
                      className="size-3.5 text-amber-500"
                      aria-label="Partially curtailed by a grid constraint"
                    />
                  )}
                </p>
                <p className="font-mono text-xs text-stone-500 tnum">
                  {trade.at} · {kwh(trade.kwh)} @ {inr(trade.pricePerKwh)}
                </p>
              </div>

              <span
                className={cn(
                  'shrink-0 font-mono text-sm font-bold tnum',
                  isSell ? 'text-battery-600' : 'text-stone-700',
                )}
              >
                {isSell ? '+' : '−'}
                {inr(trade.totalInr)}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
