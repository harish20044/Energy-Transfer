import { Clock, Gauge, Scale, TrendingUp } from 'lucide-react';
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

import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { StatTile } from '@/components/ui/StatTile';
import { asks, bids, marketState, priceHistory, supplyDemandCurve } from '@/data/mock';
import { useCountdown } from '@/hooks/useCountdown';
import { cn } from '@/lib/cn';
import { countdown, inr, kwh } from '@/lib/format';
import type { OrderLevel } from '@/types/energy';

function OrderLadder({
  levels,
  side,
  maxKwh,
}: {
  levels: OrderLevel[];
  side: 'bid' | 'ask';
  maxKwh: number;
}) {
  const isBid = side === 'bid';

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-5 pb-2 text-[11px] font-semibold tracking-wider text-stone-400 uppercase">
        <span>{isBid ? 'Bids · buyers' : 'Asks · sellers'}</span>
        <span>kWh</span>
      </div>
      <ul>
        {levels.map((level) => {
          const isClearing = level.pricePerKwh === marketState.clearingInr;

          return (
            <li
              key={level.pricePerKwh}
              className={cn(
                'relative flex items-center justify-between px-5 py-1.5 text-sm',
                isClearing && 'bg-stone-900/[0.04] font-semibold',
              )}
            >
              {/* Depth bar: width encodes volume resting at this price. */}
              <span
                className={cn(
                  'absolute inset-y-0.5 rounded',
                  isBid ? 'left-0 bg-peer-100' : 'left-0 bg-solar-100',
                )}
                style={{ width: `${String((level.kwh / maxKwh) * 100)}%` }}
                aria-hidden="true"
              />
              <span
                className={cn(
                  'relative font-mono tnum',
                  isBid ? 'text-peer-700' : 'text-solar-700',
                )}
              >
                {inr(level.pricePerKwh)}
              </span>
              <span className="relative flex items-center gap-3">
                <span className="text-xs text-stone-400">{level.households}×</span>
                <span className="font-mono text-stone-700 tnum">{level.kwh.toFixed(1)}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function Market() {
  const secondsLeft = useCountdown(marketState.gateClosesInSeconds);
  const maxKwh = Math.max(...asks.map((a) => a.kwh), ...bids.map((b) => b.kwh));

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Clearing price"
          value={inr(marketState.clearingInr)}
          caption={`between ₹${marketState.feedInTariff.toFixed(2)} and ₹${marketState.retailTariff.toFixed(2)}`}
          icon={TrendingUp}
          tone="peer"
        />
        <StatTile
          label="Matched volume"
          value={kwh(marketState.matchedKwh)}
          caption={`${String(marketState.participants)} households in the market`}
          icon={Scale}
          tone="battery"
        />
        <StatTile
          label="Gate closes in"
          value={countdown(secondsLeft)}
          caption={`Tick #${String(marketState.tickNumber)} today`}
          icon={Clock}
          tone="neutral"
        />
        <StatTile
          label="Curtailed by safety"
          value={kwh(marketState.curtailedKwh)}
          caption="line 7→8 at 91% loading"
          icon={Gauge}
          tone="grid"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Clearing price"
          subtitle="Bounded to the tariff band, so both sides beat the utility"
          action={<Badge tone="peer">{marketState.mechanism}</Badge>}
        >
          <div className="h-[260px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={priceHistory} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                {/* The band between feed-in and retail is the whole value proposition:
                    any price inside it leaves buyer and seller better off than the grid. */}
                <ReferenceArea
                  y1={marketState.feedInTariff}
                  y2={marketState.retailTariff}
                  fill="#6366f1"
                  fillOpacity={0.05}
                />
                <ReferenceLine
                  y={marketState.retailTariff}
                  stroke="#e11d48"
                  strokeDasharray="4 4"
                  label={{
                    value: 'Retail ₹8.00',
                    position: 'insideTopRight',
                    fontSize: 11,
                    fill: '#e11d48',
                  }}
                />
                <ReferenceLine
                  y={marketState.feedInTariff}
                  stroke="#059669"
                  strokeDasharray="4 4"
                  label={{
                    value: 'Feed-in ₹3.00',
                    position: 'insideBottomRight',
                    fontSize: 11,
                    fill: '#059669',
                  }}
                />
                <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="time"
                  interval={3}
                  tick={{ fontSize: 11, fill: '#78716c' }}
                  tickLine={false}
                  axisLine={{ stroke: '#e7e5e4' }}
                />
                <YAxis
                  domain={[2.5, 8.5]}
                  tick={{ fontSize: 11, fill: '#78716c' }}
                  tickLine={false}
                  axisLine={false}
                  width={48}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 8,
                    border: '1px solid #e7e5e4',
                    fontSize: 12,
                  }}
                  formatter={(value: unknown) => [inr(Number(value)), 'Clearing']}
                />
                <Line
                  dataKey="clearingInr"
                  stroke="#4f46e5"
                  strokeWidth={2.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card
          title="Order book"
          subtitle={`Crosses at ${inr(marketState.clearingInr)} · ${kwh(marketState.matchedKwh)}`}
          contentClassName="p-0 py-4"
        >
          <div className="flex flex-col gap-5">
            <OrderLadder levels={[...asks].reverse()} side="ask" maxKwh={maxKwh} />
            <div className="mx-5 flex items-center justify-between rounded-lg bg-stone-900 px-3 py-2 text-white">
              <span className="text-xs font-medium text-stone-300">Clears at</span>
              <span className="font-mono text-sm font-bold tnum">
                {inr(marketState.clearingInr)}
              </span>
            </div>
            <OrderLadder levels={bids} side="bid" maxKwh={maxKwh} />
          </div>
        </Card>
      </div>

      <Card
        title="Supply and demand"
        subtitle="Where the curves cross is the clearing price — every trade to the left of it is mutually beneficial"
      >
        <div className="h-[280px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={supplyDemandCurve}
              margin={{ top: 8, right: 16, bottom: 4, left: -20 }}
            >
              <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" />
              <XAxis
                dataKey="price"
                type="number"
                domain={[3, 8]}
                tick={{ fontSize: 11, fill: '#78716c' }}
                tickLine={false}
                axisLine={{ stroke: '#e7e5e4' }}
                tickFormatter={(value: number) => `₹${value.toFixed(1)}`}
              />
              <YAxis
                tick={{ fontSize: 11, fill: '#78716c' }}
                tickLine={false}
                axisLine={false}
                width={48}
                unit=" kWh"
              />
              <ReferenceLine
                x={marketState.clearingInr}
                stroke="#1c1917"
                strokeDasharray="4 4"
                label={{ value: 'Clears ₹5.40', position: 'top', fontSize: 11, fill: '#1c1917' }}
              />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: '1px solid #e7e5e4', fontSize: 12 }}
                labelFormatter={(value: unknown) => `Price ₹${Number(value).toFixed(2)}`}
              />
              <Line
                dataKey="supply"
                stroke="#d97706"
                strokeWidth={2.5}
                dot={{ r: 3 }}
                name="Cumulative supply"
                isAnimationActive={false}
              />
              <Line
                dataKey="demand"
                stroke="#4f46e5"
                strokeWidth={2.5}
                dot={{ r: 3 }}
                name="Cumulative demand"
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
