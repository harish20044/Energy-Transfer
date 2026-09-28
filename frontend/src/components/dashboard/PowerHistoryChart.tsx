import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { MeterReading } from '@/api/household';
import { simClock } from '@/lib/format';

/**
 * This household's actual generation and consumption over its recent
 * ticks — real readings, not a forecast. There is no quantile forecaster in
 * this build (see the project's build order), so this shows what actually
 * happened rather than fabricating a prediction band for it.
 */
export function PowerHistoryChart({
  readings,
  tickMinutes,
}: {
  readings: MeterReading[];
  tickMinutes: number;
}) {
  // readings arrive most-recent-first; the chart reads left-to-right in time.
  const data = [...readings]
    .reverse()
    .map((reading) => ({
      time: simClock((reading.tick_index * tickMinutes) / 60),
      generation: Number(reading.generation_kw.toFixed(2)),
      consumption: Number(reading.consumption_kw.toFixed(2)),
    }));

  return (
    <div className="h-[220px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
          <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="time"
            interval="preserveStartEnd"
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
          <Line
            dataKey="generation"
            stroke="#d97706"
            strokeWidth={2}
            dot={false}
            name="Solar"
            isAnimationActive={false}
          />
          <Line
            dataKey="consumption"
            stroke="#4f46e5"
            strokeWidth={2}
            strokeDasharray="4 4"
            dot={false}
            name="Your load"
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
