import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { OwnSlot } from '@/api/session';
import { hourLabel } from '@/lib/format';

const SOLAR = '#d97706';
const LOAD = '#4f46e5';

/** The household's forecast for every hour of the session — the P50 line
 *  inside its P10–P90 band — with what actually happened plotted over it as
 *  each hour is delivered. */
export function ForecastChart({ slots }: { slots: OwnSlot[] }) {
  const data = slots.map((s) => ({
    hour: hourLabel(s.hour_of_day),
    loadBand: [s.forecast.consumption_p10, s.forecast.consumption_p90],
    solarBand: [s.forecast.generation_p10, s.forecast.generation_p90],
    load: s.forecast.consumption_p50,
    solar: s.forecast.generation_p50,
    actualLoad: s.actual_consumption_kwh,
    actualSolar: s.actual_generation_kwh,
  }));

  return (
    <div className="h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="hour"
            tick={{ fontSize: 11, fill: '#78716c' }}
            tickLine={false}
            axisLine={{ stroke: '#e7e5e4' }}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#78716c' }}
            tickLine={false}
            axisLine={false}
            width={44}
            label={{
              value: 'units / hour',
              angle: -90,
              position: 'insideLeft',
              offset: 18,
              fontSize: 11,
              fill: '#a8a29e',
            }}
          />
          <Tooltip
            contentStyle={{ borderRadius: 8, border: '1px solid #e7e5e4', fontSize: 12 }}
            formatter={(value: unknown, name: unknown) => {
              if (Array.isArray(value)) {
                const [lo, hi] = value as number[];
                return [`${(lo ?? 0).toFixed(2)} – ${(hi ?? 0).toFixed(2)}`, String(name)];
              }
              return [value === null ? '—' : Number(value).toFixed(2), String(name)];
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Area
            dataKey="loadBand"
            name="Load P10–P90"
            stroke="none"
            fill={LOAD}
            fillOpacity={0.12}
            isAnimationActive={false}
          />
          <Area
            dataKey="solarBand"
            name="Solar P10–P90"
            stroke="none"
            fill={SOLAR}
            fillOpacity={0.15}
            isAnimationActive={false}
          />
          <Line
            dataKey="load"
            name="Load forecast"
            stroke={LOAD}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="solar"
            name="Solar forecast"
            stroke={SOLAR}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Scatter
            dataKey="actualLoad"
            name="Load actual"
            fill={LOAD}
            shape="circle"
            isAnimationActive={false}
          />
          <Scatter
            dataKey="actualSolar"
            name="Solar actual"
            fill={SOLAR}
            shape="diamond"
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
