import { Gauge, Scale, TrendingUp, Users } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { Curtailment, MarketTrade, NegotiationRound } from '@/api/simulation';
import { fetchNegotiation, fetchRecentCurtailments, fetchRecentTrades } from '@/api/simulation';
import { useAuth } from '@/auth/useAuth';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { StatTile } from '@/components/ui/StatTile';
import { cn } from '@/lib/cn';
import { inr, kwh } from '@/lib/format';
import { householdLabel } from '@/lib/household';
import { FEED_IN_TARIFF, RETAIL_TARIFF } from '@/lib/tariffs';
import { useLiveData } from '@/live/useLiveData';

const AUTO_ADVANCE_MS = 1400;

function OfferColumn({
  title,
  offers,
  tone,
  matchedIds,
}: {
  title: string;
  offers: { household_id: string; price: number; kwh: number }[];
  tone: 'ask' | 'bid';
  matchedIds: Set<string>;
}) {
  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-5 pb-2 text-[11px] font-semibold tracking-wider text-stone-400 uppercase">
        <span>{title}</span>
        <span>kWh @ ₹/kWh</span>
      </div>
      {offers.length === 0 ? (
        <p className="px-5 py-3 text-xs text-stone-400">Nobody on this side this tick.</p>
      ) : (
        <ul>
          {offers.map((offer) => {
            const matched = matchedIds.has(offer.household_id);
            return (
              <li
                key={offer.household_id}
                className={cn(
                  'flex items-center justify-between px-5 py-1.5 text-sm',
                  matched && 'bg-battery-50/60 font-semibold',
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
                  {matched && <span className="text-[10px] font-bold text-battery-600">✓</span>}
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
  const { simulation } = useLiveData();
  const [rounds, setRounds] = useState<NegotiationRound[]>([]);
  const [negotiationTick, setNegotiationTick] = useState<number | null>(null);
  const [selectedRound, setSelectedRound] = useState(0);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [recentTrades, setRecentTrades] = useState<MarketTrade[]>([]);
  const [curtailments, setCurtailments] = useState<Curtailment[]>([]);
  const lastLoadedTick = useRef<number | null>(null);

  const completedTick = simulation !== null && simulation.tick_index > 0 ? simulation.tick_index - 1 : null;

  // Load the latest completed tick's negotiation exactly once per tick, not
  // on every 1s poll — the round replay below owns its own pacing.
  useEffect(() => {
    if (accessToken === null || completedTick === null) return;
    if (lastLoadedTick.current === completedTick) return;
    lastLoadedTick.current = completedTick;

    fetchNegotiation(accessToken, completedTick)
      .then((data) => {
        setRounds(data.rounds);
        setNegotiationTick(data.tick_index);
        setSelectedRound(0);
      })
      .catch(() => {
        setRounds([]);
      });
  }, [accessToken, completedTick]);

  useEffect(() => {
    if (accessToken === null) return;
    const controller = new AbortController();
    fetchRecentTrades(accessToken, 60, controller.signal).then(setRecentTrades).catch(() => undefined);
    fetchRecentCurtailments(accessToken, 20, controller.signal).then(setCurtailments).catch(() => undefined);
    return () => {
      controller.abort();
    };
  }, [accessToken, simulation?.tick_index]);

  useEffect(() => {
    if (!autoAdvance || rounds.length <= 1) return;
    const timer = setInterval(() => {
      setSelectedRound((round) => (round + 1) % rounds.length);
    }, AUTO_ADVANCE_MS);
    return () => {
      clearInterval(timer);
    };
  }, [autoAdvance, rounds.length]);

  const current = rounds[selectedRound];
  const matchedIds = useMemo(() => {
    const ids = new Set<string>();
    for (const trade of current?.trades ?? []) {
      ids.add(trade.seller_household_id);
      ids.add(trade.buyer_household_id);
    }
    return ids;
  }, [current]);

  const thisTickTrades = recentTrades.filter((t) => t.tick_index === completedTick);
  const matchedKwh = thisTickTrades.reduce((sum, t) => sum + t.kwh, 0);
  const lastPrice = thisTickTrades.at(-1)?.price_per_kwh ?? null;
  const curtailedThisTick = curtailments
    .filter((c) => c.tick_index === completedTick)
    .reduce((sum, c) => sum + c.curtailed_kwh, 0);

  const priceHistory = recentTrades
    .slice()
    .reverse()
    .map((t, i) => ({ x: i, tick: t.tick_index, price: t.price_per_kwh }));

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Last clearing price"
          value={lastPrice !== null ? inr(lastPrice) : '—'}
          caption={`between ₹${FEED_IN_TARIFF.toFixed(2)} and ₹${RETAIL_TARIFF.toFixed(2)}`}
          icon={TrendingUp}
          tone="peer"
        />
        <StatTile
          label="Matched this tick"
          value={kwh(matchedKwh)}
          caption={negotiationTick !== null ? `Tick ${String(negotiationTick)}` : 'Waiting for a tick'}
          icon={Scale}
          tone="battery"
        />
        <StatTile
          label="Negotiating"
          value={String((current?.asks.length ?? 0) + (current?.bids.length ?? 0))}
          caption={`${String(current?.asks.length ?? 0)} sellers · ${String(current?.bids.length ?? 0)} buyers`}
          icon={Users}
          tone="neutral"
        />
        <StatTile
          label="Curtailed by safety"
          value={kwh(curtailedThisTick)}
          caption="grid safety veto, this tick"
          icon={Gauge}
          tone="grid"
        />
      </div>

      <Card
        title="Watch them negotiate"
        subtitle="Round 0 opens at each side's most favourable price; each round after, both sides concede toward their reservation price"
        action={
          rounds.length > 0 ? (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setAutoAdvance((v) => !v);
                }}
                className={cn(
                  'rounded-lg px-2.5 py-1 text-xs font-semibold',
                  autoAdvance ? 'bg-stone-900 text-white' : 'border border-stone-200 text-stone-600',
                )}
              >
                {autoAdvance ? 'Auto-playing' : 'Paused'}
              </button>
            </div>
          ) : undefined
        }
      >
        {rounds.length === 0 ? (
          <p className="py-8 text-center text-sm text-stone-400">
            No trading activity yet this tick — press Play or Step on a tick with real surplus or
            shortfall.
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-1.5">
              {rounds.map((round) => (
                <button
                  key={round.round_index}
                  type="button"
                  onClick={() => {
                    setAutoAdvance(false);
                    setSelectedRound(round.round_index);
                  }}
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors',
                    round.round_index === selectedRound
                      ? 'bg-peer-600 text-white'
                      : 'bg-stone-100 text-stone-600 hover:bg-stone-200',
                    round.trades.length > 0 && round.round_index !== selectedRound && 'ring-2 ring-battery-300',
                  )}
                >
                  Round {round.round_index + 1}
                  {round.trades.length > 0 ? ` · ${String(round.trades.length)} matched` : ''}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
              <OfferColumn title="Asks · sellers" offers={current?.asks ?? []} tone="ask" matchedIds={matchedIds} />
              <OfferColumn title="Bids · buyers" offers={current?.bids ?? []} tone="bid" matchedIds={matchedIds} />
            </div>

            {current !== undefined && current.trades.length > 0 && (
              <div className="rounded-lg bg-stone-900 px-4 py-3">
                <p className="text-xs font-semibold text-stone-300">Matched this round</p>
                <ul className="mt-1.5 flex flex-col gap-1">
                  {current.trades.map((trade, i) => (
                    <li key={i} className="flex items-center justify-between text-sm text-white">
                      <span>
                        {householdLabel(trade.seller_household_id)} → {householdLabel(trade.buyer_household_id)}
                      </span>
                      <span className="font-mono tnum">
                        {trade.kwh.toFixed(2)} kWh @ {inr(trade.price_per_kwh)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card
        title="Recent clearing prices"
        subtitle="Every settled trade across the whole feeder — no two trades have to settle at the same price anymore"
        action={<Badge tone="peer">Multi-round negotiation</Badge>}
      >
        <div className="h-[240px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={priceHistory} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
              <ReferenceArea y1={FEED_IN_TARIFF} y2={RETAIL_TARIFF} fill="#6366f1" fillOpacity={0.05} />
              <ReferenceLine
                y={RETAIL_TARIFF}
                stroke="#e11d48"
                strokeDasharray="4 4"
                label={{ value: `Retail ₹${RETAIL_TARIFF.toFixed(2)}`, position: 'insideTopRight', fontSize: 11, fill: '#e11d48' }}
              />
              <ReferenceLine
                y={FEED_IN_TARIFF}
                stroke="#059669"
                strokeDasharray="4 4"
                label={{ value: `Feed-in ₹${FEED_IN_TARIFF.toFixed(2)}`, position: 'insideBottomRight', fontSize: 11, fill: '#059669' }}
              />
              <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="tick"
                tick={{ fontSize: 11, fill: '#78716c' }}
                tickLine={false}
                axisLine={{ stroke: '#e7e5e4' }}
              />
              <YAxis domain={[2.5, 8.5]} tick={{ fontSize: 11, fill: '#78716c' }} tickLine={false} axisLine={false} width={48} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: '1px solid #e7e5e4', fontSize: 12 }}
                formatter={(value: unknown) => [inr(Number(value)), 'Price']}
                labelFormatter={(value: unknown) => `Tick ${String(value)}`}
              />
              <Line dataKey="price" stroke="#4f46e5" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
