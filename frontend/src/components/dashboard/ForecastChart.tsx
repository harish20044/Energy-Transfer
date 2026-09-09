import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { forecast } from '@/data/mock';

/**
 * Next six hours of generation and load.
 *
 * The shaded band is the P10–P90 forecast interval, not a decoration: it is the
 * uncertainty the trading agent bids against. It widens with horizon because
 * confidence genuinely decays with distance.
 */
export function ForecastChart() {
  const data = forecast.map((point) => ({
    time: point.time,
    band: [point.genP10, point.genP90] as [number, number],
    generation: point.genP50,
    load: point.loadP50,
  }));

  return (
    <div className="h-[220px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
          <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="time"
            interval={5}
            tick={{ fontSize: 11, fill: '#78716c' }}
            tickLine={false}
            axisLine={{ stroke: '#e7e5e4' }}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#78716c' }}
            tickLine={false}
            axisLine={false}
            width={48}
            unit=" kW"
          />
          <Tooltip
            contentStyle={{
              borderRadius: 8,
              border: '1px solid #e7e5e4',
              fontSize: 12,
              boxShadow: '0 4px 12px rgb(0 0 0 / 0.06)',
            }}
            labelStyle={{ fontWeight: 600, color: '#1c1917' }}
          />
          <Area
            dataKey="band"
            stroke="none"
            fill="#f59e0b"
            fillOpacity={0.14}
            name="P10–P90"
            isAnimationActive={false}
          />
          <Line
            dataKey="generation"
            stroke="#d97706"
            strokeWidth={2}
            dot={false}
            name="Solar (P50)"
            isAnimationActive={false}
          />
          <Line
            dataKey="load"
            stroke="#4f46e5"
            strokeWidth={2}
            strokeDasharray="4 4"
            dot={false}
            name="Your load"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
