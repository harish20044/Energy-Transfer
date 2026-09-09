import { Gauge, ShieldCheck, TriangleAlert, Zap } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { StatTile } from '@/components/ui/StatTile';
import { networkLines, networkNodes, transformerLoadingPct } from '@/data/mock';
import { cn } from '@/lib/cn';
import { kw, percent, perUnit } from '@/lib/format';
import type { ConstraintStatus } from '@/types/energy';

const STATUS_STROKE: Record<ConstraintStatus, string> = {
  ok: '#d6d3d1',
  warning: '#f59e0b',
  violation: '#e11d48',
};

const nodeById = new Map(networkNodes.map((node) => [node.id, node]));

export function Network() {
  const constrained = networkLines.filter((line) => line.status !== 'ok');
  const lowVoltage = networkNodes.filter((node) => node.status !== 'ok');

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Constraint violations"
          value="0"
          caption="after the safety layer — always"
          icon={ShieldCheck}
          tone="battery"
        />
        <StatTile
          label="Transformer loading"
          value={percent(transformerLoadingPct)}
          caption="250 kW capacity"
          icon={Gauge}
          tone="neutral"
        />
        <StatTile
          label="Lines near limit"
          value={String(constrained.length)}
          caption="above 90% thermal rating"
          icon={TriangleAlert}
          tone="solar"
        />
        <StatTile
          label="Voltage band"
          value="0.979–1.043"
          caption="statutory limits 0.95–1.05 pu"
          icon={Zap}
          tone="peer"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Feeder topology"
          subtitle="Node colour is net position; line colour is thermal headroom"
          action={
            <div className="flex items-center gap-3 text-xs text-stone-500">
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-solar-500" /> Exporting
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-peer-500" /> Importing
              </span>
            </div>
          }
        >
          <div className="w-full overflow-x-auto">
            <svg viewBox="0 0 540 420" className="h-[400px] w-full min-w-[520px]">
              {networkLines.map((line) => {
                const from = nodeById.get(line.from);
                const to = nodeById.get(line.to);
                if (!from || !to) return null;

                return (
                  <g key={`${line.from}-${line.to}`}>
                    <line
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      stroke={STATUS_STROKE[line.status]}
                      strokeWidth={line.status === 'ok' ? 2.5 : 4}
                      strokeLinecap="round"
                    />
                    {line.status !== 'ok' && (
                      <text
                        x={(from.x + to.x) / 2}
                        y={(from.y + to.y) / 2 - 8}
                        textAnchor="middle"
                        className="fill-amber-600 text-[10px] font-semibold"
                      >
                        {percent(line.loadingPct)}
                      </text>
                    )}
                  </g>
                );
              })}

              {networkNodes.map((node) => {
                const exporting = node.netKw > 0;
                const isSubstation = node.id === 'sub';
                const radius = isSubstation ? 20 : 15;

                return (
                  <g key={node.id}>
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={radius}
                      fill={isSubstation ? '#1c1917' : exporting ? '#f59e0b' : '#6366f1'}
                      fillOpacity={isSubstation ? 1 : 0.16}
                      stroke={isSubstation ? '#1c1917' : exporting ? '#d97706' : '#4f46e5'}
                      strokeWidth={2}
                    />
                    <text
                      x={node.x}
                      y={node.y + 4}
                      textAnchor="middle"
                      className={cn(
                        'text-[10px] font-bold',
                        isSubstation ? 'fill-white' : 'fill-stone-700',
                      )}
                    >
                      {isSubstation ? 'SUB' : String(node.bus)}
                    </text>
                    <text
                      x={node.x}
                      y={node.y + radius + 14}
                      textAnchor="middle"
                      className="fill-stone-500 text-[10px] font-medium"
                    >
                      {isSubstation ? 'Transformer' : kw(node.netKw)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </Card>

        <Card
          title="Constraint watch"
          subtitle="What the safety layer is holding back"
          contentClassName="p-0"
        >
          <ul className="divide-y divide-stone-100">
            {constrained.map((line) => {
              const from = nodeById.get(line.from);
              const to = nodeById.get(line.to);

              return (
                <li key={`${line.from}-${line.to}`} className="flex items-start gap-3 px-5 py-3.5">
                  <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                    <TriangleAlert className="size-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-stone-900">
                      {from?.label} → {to?.label}
                    </p>
                    <p className="text-xs text-stone-500">
                      Thermal loading at{' '}
                      <span className="font-mono font-semibold text-amber-700 tnum">
                        {percent(line.loadingPct)}
                      </span>
                      . 0.4 kWh curtailed this tick.
                    </p>
                  </div>
                </li>
              );
            })}

            {lowVoltage.map((node) => (
              <li key={node.id} className="flex items-start gap-3 px-5 py-3.5">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-stone-100 text-stone-600">
                  <Zap className="size-4" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-stone-900">{node.label}</p>
                  <p className="text-xs text-stone-500">
                    Voltage{' '}
                    <span className="font-mono font-semibold text-stone-700 tnum">
                      {perUnit(node.voltagePu)}
                    </span>{' '}
                    — within limits, but the lowest on the feeder.
                  </p>
                </div>
              </li>
            ))}

            <li className="px-5 py-3.5">
              <Badge tone="battery">
                <ShieldCheck className="size-3.5" aria-hidden="true" />
                No violations in the settled allocation
              </Badge>
            </li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
