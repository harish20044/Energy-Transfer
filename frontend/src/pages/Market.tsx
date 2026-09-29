import { Bot, Landmark, PlugZap, Scale, TrendingUp, Zap } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { Offer, SlotMarket } from '@/api/session';
import { fetchSlotMarket } from '@/api/session';
import { useAuth } from '@/auth/useAuth';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { StatTile } from '@/components/ui/StatTile';
import { cn } from '@/lib/cn';
import { hourLabel, inr, kwh } from '@/lib/format';
import { householdLabel } from '@/lib/household';
import { strategyMeta } from '@/lib/session';
import { useLiveData } from '@/live/useLiveData';

function OfferColumn({
  title,
  offers,
  tone,
  matchedIds,
}: {
  title: string;
  offers: Offer[];
  tone: 'ask' | 'bid';
  matchedIds: Set<string>;
}) {
  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-1 pb-2 text-[11px] font-semibold tracking-wider text-stone-400 uppercase">
        <span>{title}</span>
        <span>Units @ ₹/unit</span>
      </div>
      {offers.length === 0 ? (
        <p className="px-1 py-3 text-xs text-stone-400">Nobody on this side in this round.</p>
      ) : (
        <ul>
          {offers.map((offer) => {
            const matched = matchedIds.has(offer.household_id);
            return (
              <li
                key={offer.household_id}
                className={cn(
                  'flex items-center justify-between rounded px-1 py-1.5 text-sm',
                  matched && 'bg-battery-50 font-semibold',
                )}
              >
                <span className="text-stone-700">{householdLabel(offer.household_id)}</span>
                <span className="flex items-center gap-3">
                  <span className="font-mono text-stone-500 tnum">{offer.kwh.toFixed(2)}</span>
                  <span
                    className={cn(
                      'font-mono tnum',
                      tone === 'ask' ? 'text-solar-700' : 'text-peer-700',
                    )}
                  >
                    {inr(offer.price)}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function Market() {
  const { accessToken } = useAuth();
  const { session, overview, version } = useLiveData();
  const [slot, setSlot] = useState(0);
  const [market, setMarket] = useState<SlotMarket | null>(null);
  const [round, setRound] = useState(0);

  useEffect(() => {
    if (accessToken === null || overview.length === 0) {
      setMarket(null);
      return;
    }
    const controller = new AbortController();
    fetchSlotMarket(accessToken, Math.min(slot, overview.length - 1), controller.signal)
      .then((data) => {
        setMarket(data);
        setRound(Math.max(0, data.rounds.length - 1));
      })
      .catch(() => {
        setMarket(null);
      });
    return () => {
      controller.abort();
    };
  }, [accessToken, slot, overview.length, version]);

  const chartData = useMemo(
    () =>
      overview.map((row) => ({
        hour: hourLabel(row.hour_of_day),
        p2p: row.p2p_kwh,
        ebIn: row.eb_bought_kwh,
        ebOut: row.eb_sold_kwh,
        price: row.p2p_avg_price,
      })),
    [overview],
  );

  if (session === null || session.status === 'setup' || overview.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 text-sm text-stone-400">
        No market yet — plan a session first.
        <Link to="/session" className="rounded-lg bg-peer-600 px-3 py-1.5 font-semibold text-white">
          Plan a session
        </Link>
      </div>
    );
  }

  const row = overview[Math.min(slot, overview.length - 1)];
  const current = market?.rounds[round];
  const matchedIds = new Set<string>();
  for (const t of current?.trades ?? []) {
    matchedIds.add(t.seller_household_id);
    matchedIds.add(t.buyer_household_id);
  }
  const totalP2p = overview.reduce((s, r) => s + r.p2p_kwh, 0);
  const totalEbIn = overview.reduce((s, r) => s + r.eb_bought_kwh, 0);

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <Card
        title="The whole feeder, hour by hour"
        subtitle={`${kwh(totalP2p)} traded between neighbours · ${kwh(totalEbIn)} bought from the EB over the session`}
        action={<Badge tone="peer">Click an hour for its market</Badge>}
      >
        <div className="h-[240px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={chartData}
              margin={{ top: 8, right: 8, bottom: 0, left: -12 }}
              onClick={(state) => {
                const index = Number(state.activeTooltipIndex);
                if (Number.isFinite(index)) setSlot(index);
              }}
            >
              <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="hour" tick={{ fontSize: 11, fill: '#78716c' }} tickLine={false} />
              <YAxis
                yAxisId="units"
                tick={{ fontSize: 11, fill: '#78716c' }}
                tickLine={false}
                axisLine={false}
                width={40}
              />
              <YAxis
                yAxisId="price"
                orientation="right"
                domain={[0, 'auto']}
                tick={{ fontSize: 11, fill: '#78716c' }}
                tickLine={false}
                axisLine={false}
                width={40}
              />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: '1px solid #e7e5e4', fontSize: 12 }}
                formatter={(value: unknown, name: unknown) => [
                  name === 'P2P price' ? inr(Number(value)) : kwh(Number(value)),
                  String(name),
                ]}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar
                yAxisId="units"
                dataKey="p2p"
                name="Between neighbours"
                stackId="a"
                fill="#4f46e5"
              />
              <Bar
                yAxisId="units"
                dataKey="ebIn"
                name="Bought from EB"
                stackId="a"
                fill="#e11d48"
              />
              <Bar yAxisId="units" dataKey="ebOut" name="Sold to EB" fill="#d97706" />
              <Line
                yAxisId="price"
                dataKey="price"
                name="P2P price"
                stroke="#059669"
                strokeWidth={2}
                connectNulls={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {overview.map((r) => (
            <button
              key={r.slot}
              type="button"
              onClick={() => {
                setSlot(r.slot);
              }}
              className={cn(
                'rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors',
                r.slot === slot
                  ? 'bg-stone-900 text-white'
                  : 'bg-stone-100 text-stone-600 hover:bg-stone-200',
                !r.eb_available && r.slot !== slot && 'ring-2 ring-grid-200',
              )}
            >
              {hourLabel(r.hour_of_day)}
              {r.delivered ? ' ✓' : ''}
            </button>
          ))}
        </div>
      </Card>

      {row !== undefined && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile
            label={`Neighbour trades · ${hourLabel(row.hour_of_day)}`}
            value={kwh(row.p2p_kwh)}
            caption={
              row.p2p_avg_price !== null
                ? `at ${inr(row.p2p_avg_price)} average`
                : 'no match this hour'
            }
            icon={Scale}
            tone="peer"
          />
          <StatTile
            label="Bought from the EB"
            value={kwh(row.eb_bought_kwh)}
            caption={`at ${inr(row.retail_tariff)}/unit`}
            icon={Zap}
            tone="grid"
          />
          <StatTile
            label="Sold to the EB"
            value={kwh(row.eb_sold_kwh)}
            caption={`at ${inr(row.feed_in_tariff)}/unit`}
            icon={Landmark}
            tone="solar"
          />
          <StatTile
            label="Feeder forecast"
            value={`${kwh(row.forecast_need_kwh)} short`}
            caption={`${kwh(row.forecast_spare_kwh)} spare · ${row.eb_available ? 'EB up' : 'EB power cut'}`}
            icon={row.eb_available ? TrendingUp : PlugZap}
            tone={row.eb_available ? 'neutral' : 'grid'}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <Card
          className="xl:col-span-3"
          title={`Watch them negotiate · ${row !== undefined ? hourLabel(row.hour_of_day) : ''}`}
          subtitle="Each round, sellers come down and buyers come up toward their limits; whatever crosses trades"
        >
          {market === null || market.rounds.length === 0 ? (
            <p className="py-8 text-center text-sm text-stone-400">
              No neighbour negotiation this hour — nobody needed to buy, or nobody had any to spare.
            </p>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap gap-1.5">
                {market.rounds.map((r) => (
                  <button
                    key={r.round_index}
                    type="button"
                    onClick={() => {
                      setRound(r.round_index);
                    }}
                    className={cn(
                      'rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors',
                      r.round_index === round
                        ? 'bg-peer-600 text-white'
                        : 'bg-stone-100 text-stone-600 hover:bg-stone-200',
                    )}
                  >
                    Round {r.round_index + 1}
                    {r.trades.length > 0 ? ` · ${String(r.trades.length)} matched` : ''}
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                <OfferColumn
                  title="Asks · sellers"
                  offers={current?.asks ?? []}
                  tone="ask"
                  matchedIds={matchedIds}
                />
                <OfferColumn
                  title="Bids · buyers"
                  offers={current?.bids ?? []}
                  tone="bid"
                  matchedIds={matchedIds}
                />
              </div>
              {current !== undefined && current.trades.length > 0 && (
                <div className="rounded-lg bg-stone-900 px-4 py-3">
                  <p className="text-xs font-semibold text-stone-300">Matched this round</p>
                  <ul className="mt-1.5 flex flex-col gap-1">
                    {current.trades.map((t, i) => (
                      <li key={i} className="flex items-center justify-between text-sm text-white">
                        <span>
                          {householdLabel(t.seller_household_id)} →{' '}
                          {householdLabel(t.buyer_household_id)}
                        </span>
                        <span className="font-mono tnum">
                          {kwh(t.kwh)} @ {inr(t.price_per_kwh)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          {market !== null && market.eb_flows.length > 0 && (
            <div className="mt-4 rounded-lg border border-stone-200 p-3">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-stone-600">
                <Landmark className="size-3.5" aria-hidden="true" /> The EB covered the rest
              </p>
              <ul className="mt-1.5 flex flex-col gap-0.5">
                {market.eb_flows.map((f, i) => (
                  <li key={i} className="flex justify-between text-xs text-stone-600">
                    <span>
                      {householdLabel(f.household_id)}{' '}
                      {f.side === 'bid' ? 'bought from' : 'sold to'} the EB
                    </span>
                    <span className="font-mono tnum">
                      {kwh(f.kwh)} @ {inr(f.price)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>

        <Card
          className="xl:col-span-2"
          title="What the agents said"
          subtitle="Each household's agent, before and after this hour's market"
          contentClassName="p-0"
        >
          <ul className="max-h-[560px] divide-y divide-stone-100 overflow-y-auto">
            {(market?.agents ?? []).map((a) => {
              const meta = strategyMeta(a.strategy);
              return (
                <li key={a.household_id} className="px-5 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-sm font-semibold text-stone-900">
                      <Bot className="size-4 text-peer-500" aria-hidden="true" />
                      {a.display_name}
                    </span>
                    <Badge tone={meta.tone}>{meta.label}</Badge>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-stone-600">{a.message}</p>
                  {a.outcome !== '' && (
                    <p className="mt-1 text-xs font-medium text-stone-800">→ {a.outcome}</p>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      </div>
    </div>
  );
}
