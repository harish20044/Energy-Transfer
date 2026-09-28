import { useEffect, useState } from 'react';
import { Bot, ShieldCheck, TriangleAlert } from 'lucide-react';

import type { Curtailment } from '@/api/simulation';
import { fetchRecentCurtailments } from '@/api/simulation';
import { useAuth } from '@/auth/useAuth';
import { TradeList } from '@/components/dashboard/TradeList';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { inr, kwh } from '@/lib/format';
import { FEED_IN_TARIFF, RETAIL_TARIFF } from '@/lib/tariffs';
import { toUiTrade } from '@/lib/tradeView';
import { useLiveData } from '@/live/useLiveData';
import type { Trade } from '@/types/energy';

/** The explanation panel that satisfies objective O7: every trade carries both a
 *  machine-readable decision record and a rationale a homeowner can read. */
function TradeExplanation({ trade }: { trade: Trade }) {
  const isSell = trade.side === 'sell';
  const versusGrid = isSell ? trade.pricePerKwh - FEED_IN_TARIFF : RETAIL_TARIFF - trade.pricePerKwh;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-stone-400 tnum">{trade.id}</p>
          <h3 className="mt-1 text-lg font-bold text-stone-900">
            {isSell ? 'Sold to' : 'Bought from'} {trade.counterparty}
          </h3>
          <p className="font-mono text-sm text-stone-500 tnum">
            {trade.at} · {kwh(trade.kwh)} @ {inr(trade.pricePerKwh)}/kWh
          </p>
        </div>
        <Badge tone={isSell ? 'peer' : 'grid'}>{isSell ? 'Sale' : 'Purchase'}</Badge>
      </div>

      <div className="rounded-lg border border-peer-100 bg-peer-50/50 p-4">
        <p className="flex items-center gap-2 text-xs font-semibold text-peer-700">
          <Bot className="size-4" aria-hidden="true" />
          Why your agent did this
        </p>
        <p className="mt-2 text-sm leading-relaxed text-stone-700">{trade.rationale}</p>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <div>
          <dt className="text-xs font-medium text-stone-500">Total</dt>
          <dd className="font-mono text-sm font-bold text-stone-900 tnum">{inr(trade.totalInr)}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-stone-500">
            {isSell ? 'Better than feed-in by' : 'Cheaper than retail by'}
          </dt>
          <dd className="font-mono text-sm font-bold text-battery-600 tnum">
            {inr(versusGrid)}/kWh
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-stone-500">Mechanism</dt>
          <dd className="text-sm font-medium text-stone-900">Multi-round negotiation</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-stone-500">Grid check</dt>
          <dd className="text-sm font-medium text-stone-900">
            {trade.bindingConstraint === null ? 'Passed, unconstrained' : 'Curtailed'}
          </dd>
        </div>
      </dl>

      {trade.bindingConstraint === null ? (
        <div className="flex items-center gap-2 rounded-lg bg-battery-50 px-3 py-2.5 text-xs font-medium text-battery-700">
          <ShieldCheck className="size-4 shrink-0" aria-hidden="true" />
          Allocation was physically feasible — no curtailment needed.
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2.5 text-xs font-medium text-amber-800">
          <TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
          Binding constraint: {trade.bindingConstraint}
        </div>
      )}
    </div>
  );
}

export function Trades() {
  const { accessToken } = useAuth();
  const { household, trades, simulation } = useLiveData();
  const [curtailments, setCurtailments] = useState<Curtailment[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (accessToken === null) return;
    const controller = new AbortController();
    fetchRecentCurtailments(accessToken, 100, controller.signal)
      .then(setCurtailments)
      .catch(() => {
        // Curtailment annotation is a nice-to-have; the trade list still
        // works without it.
      });
    return () => {
      controller.abort();
    };
  }, [accessToken]);

  if (household === null) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-stone-400">
        Loading your household…
      </div>
    );
  }

  const tickMinutes = simulation?.tick_minutes ?? 15;
  const uiTrades = trades.map((trade) => {
    const curtailment = curtailments.find(
      (c) =>
        c.tick_index === trade.tick_index &&
        c.buyer_household_id === trade.buyer_household_id &&
        c.seller_household_id === trade.seller_household_id,
    );
    return toUiTrade(trade, household.id, tickMinutes, curtailment?.reason ?? null);
  });
  const selected = uiTrades.find((t) => t.id === selectedId) ?? uiTrades[0];

  return (
    <div className="mx-auto grid max-w-[1400px] grid-cols-1 gap-5 xl:grid-cols-5">
      <Card
        className="xl:col-span-3"
        title="This household's trades"
        subtitle="Select a trade to see the reasoning behind it"
        contentClassName="p-0"
      >
        {uiTrades.length > 0 && selected !== undefined ? (
          <TradeList
            trades={uiTrades}
            selectedId={selected.id}
            onSelect={(t) => {
              setSelectedId(t.id);
            }}
          />
        ) : (
          <p className="p-5 text-sm text-stone-400">No trades settled yet — press Play.</p>
        )}
      </Card>

      <Card className="xl:col-span-2" title="Decision record">
        {selected !== undefined ? (
          <TradeExplanation trade={selected} />
        ) : (
          <p className="text-sm text-stone-400">Nothing to show yet.</p>
        )}
      </Card>
    </div>
  );
}
