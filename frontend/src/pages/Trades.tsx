import { useEffect, useState } from 'react';
import { Bot, ShieldCheck, TriangleAlert } from 'lucide-react';

import type { Curtailment } from '@/api/simulation';
import { fetchRecentCurtailments } from '@/api/simulation';
import { useAuth } from '@/auth/useAuth';
import { TradeList } from '@/components/dashboard/TradeList';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { inr, kwh } from '@/lib/format';
import { toUiTrade } from '@/lib/tradeView';
import { useLiveData } from '@/live/useLiveData';
import type { Trade } from '@/types/energy';

/** The explanation panel that satisfies objective O7: every trade carries both a
 *  machine-readable decision record and a rationale a homeowner can read. */
function TradeExplanation({
  trade,
  feedIn,
  retail,
  outcome,
}: {
  trade: Trade;
  feedIn: number;
  retail: number;
  outcome: string | null;
}) {
  const isSell = trade.side === 'sell';
  const versusGrid = isSell ? trade.pricePerKwh - feedIn : retail - trade.pricePerKwh;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-stone-900">
            {isSell ? 'Sold to' : 'Bought from'} {trade.counterparty}
          </h3>
          <p className="font-mono text-sm text-stone-500 tnum">
            {trade.at} · {kwh(trade.kwh)} @ {inr(trade.pricePerKwh)}/unit
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
        {outcome !== null && outcome !== '' && (
          <p className="mt-2 text-xs text-stone-500">→ {outcome}</p>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <div>
          <dt className="text-xs font-medium text-stone-500">Total</dt>
          <dd className="font-mono text-sm font-bold text-stone-900 tnum">{inr(trade.totalInr)}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-stone-500">
            {isSell
              ? `Better than the EB's ${inr(feedIn)} by`
              : `Cheaper than the EB's ${inr(retail)} by`}
          </dt>
          <dd className="font-mono text-sm font-bold text-battery-600 tnum">
            {inr(versusGrid)}/unit
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-stone-500">Mechanism</dt>
          <dd className="text-sm font-medium text-stone-900">Hourly ahead market, multi-round</dd>
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
  const { household, trades, session, own, version } = useLiveData();
  const [curtailments, setCurtailments] = useState<Curtailment[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (accessToken === null) return;
    const controller = new AbortController();
    fetchRecentCurtailments(accessToken, 200, controller.signal)
      .then(setCurtailments)
      .catch(() => {
        // Curtailment annotation is a nice-to-have; the list works without it.
      });
    return () => {
      controller.abort();
    };
  }, [accessToken, version]);

  if (household === null || session === null) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-stone-400">
        Loading your household…
      </div>
    );
  }

  const decisionFor = (slot: number) => own?.slots.find((s) => s.slot === slot)?.decision ?? null;
  const uiTrades = trades.map((trade) => {
    const curtailment = curtailments.find(
      (c) =>
        c.tick_index === trade.tick_index &&
        c.buyer_household_id === trade.buyer_household_id &&
        c.seller_household_id === trade.seller_household_id,
    );
    return toUiTrade(
      trade,
      household.id,
      session.start_hour,
      decisionFor(trade.tick_index)?.message ?? null,
      curtailment?.reason ?? null,
    );
  });
  const selected = uiTrades.find((t) => t.id === selectedId) ?? uiTrades[0];
  const selectedSlot =
    selected !== undefined ? own?.slots.find((s) => s.slot === selected.slot) : undefined;

  return (
    <div className="mx-auto grid max-w-[1400px] grid-cols-1 gap-5 xl:grid-cols-5">
      <Card
        className="xl:col-span-3"
        title="This household's neighbour trades"
        subtitle="Every trade this session — select one to see the reasoning behind it"
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
          <p className="p-5 text-sm text-stone-400">
            {session.status === 'setup'
              ? 'No session yet — plan one to let your agent trade.'
              : 'Your agent made no neighbour trades this session — see the dashboard for why, hour by hour.'}
          </p>
        )}
      </Card>

      <Card className="xl:col-span-2" title="Decision record">
        {selected !== undefined ? (
          <TradeExplanation
            trade={selected}
            feedIn={selectedSlot?.feed_in_tariff ?? session.feed_in_tariff}
            retail={selectedSlot?.retail_tariff ?? session.retail_tariff}
            outcome={selectedSlot?.decision?.outcome ?? null}
          />
        ) : (
          <p className="text-sm text-stone-400">Nothing to show yet.</p>
        )}
      </Card>
    </div>
  );
}
