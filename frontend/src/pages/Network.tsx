import { useEffect, useState } from 'react';
import { Gauge, Route, ShieldCheck, TriangleAlert, Zap } from 'lucide-react';

import type { Curtailment, Feeder } from '@/api/simulation';
import { fetchNetwork, fetchRecentCurtailments } from '@/api/simulation';
import { useAuth } from '@/auth/useAuth';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { StatTile } from '@/components/ui/StatTile';
import { kwh } from '@/lib/format';
import { householdLabel } from '@/lib/household';

const LANE_Y = [90, 220, 350];
const SUBSTATION_X = 50;
const SUBSTATION_Y = 220;
const STEP_X = 130;
const START_X = 190;

interface LayoutNode {
  id: string;
  label: string;
  x: number;
  y: number;
  flagged: boolean;
}

/** Lays the feeder out client-side, mirroring the backend's own
 *  `default_feeder`: household N (1-indexed position in the sorted list)
 *  goes on lateral `position % 3`, chained outward from the substation. */
function layoutFeeder(feeder: Feeder, flaggedIds: Set<string>): LayoutNode[] {
  const laneCounts = [0, 0, 0];
  return feeder.household_ids.map((id, index) => {
    const lane = index % 3;
    const position = laneCounts[lane] ?? 0;
    laneCounts[lane] = position + 1;
    return {
      id,
      label: householdLabel(id),
      x: START_X + position * STEP_X,
      y: LANE_Y[lane] ?? SUBSTATION_Y,
      flagged: flaggedIds.has(id),
    };
  });
}

export function Network() {
  const { accessToken } = useAuth();
  const [feeder, setFeeder] = useState<Feeder | null>(null);
  const [curtailments, setCurtailments] = useState<Curtailment[]>([]);

  useEffect(() => {
    if (accessToken === null) return;
    const controller = new AbortController();
    fetchNetwork(accessToken, controller.signal).then(setFeeder).catch(() => undefined);
    return () => {
      controller.abort();
    };
  }, [accessToken]);

  useEffect(() => {
    if (accessToken === null) return;
    const timer = setInterval(() => {
      fetchRecentCurtailments(accessToken, 30).then(setCurtailments).catch(() => undefined);
    }, 2000);
    fetchRecentCurtailments(accessToken, 30).then(setCurtailments).catch(() => undefined);
    return () => {
      clearInterval(timer);
    };
  }, [accessToken]);

  if (feeder === null) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-stone-400">
        Loading the feeder…
      </div>
    );
  }

  const flaggedIds = new Set<string>();
  for (const c of curtailments) {
    flaggedIds.add(c.buyer_household_id);
    flaggedIds.add(c.seller_household_id);
  }
  const nodes = layoutFeeder(feeder, flaggedIds);
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const laterals = Math.min(3, feeder.household_ids.length);
  const totalCurtailedKwh = curtailments.reduce((sum, c) => sum + c.curtailed_kwh, 0);

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
          label="Households on feeder"
          value={String(feeder.household_ids.length)}
          caption={`across ${String(laterals)} laterals`}
          icon={Route}
          tone="neutral"
        />
        <StatTile
          label="Thermal limit per line"
          value={`${String(feeder.lines[0]?.thermal_limit_kw ?? 0)} kW`}
          caption="calibrated so a heatwave scenario breaches it"
          icon={Zap}
          tone="peer"
        />
        <StatTile
          label="Recently curtailed"
          value={kwh(totalCurtailedKwh)}
          caption={`${String(curtailments.length)} trade${curtailments.length === 1 ? '' : 's'} cut back`}
          icon={TriangleAlert}
          tone="solar"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Feeder topology"
          subtitle="Three laterals from one substation — a household flagged amber has been curtailed recently"
          action={
            <div className="flex items-center gap-3 text-xs text-stone-500">
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-stone-400" /> Normal
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-amber-500" /> Recently curtailed
              </span>
            </div>
          }
        >
          <div className="w-full overflow-x-auto">
            <svg viewBox="0 0 540 440" className="h-[400px] w-full min-w-[520px]">
              {feeder.lines.map((line) => {
                const from = line.from_bus === 'substation' ? null : nodeById.get(line.from_bus);
                const to = nodeById.get(line.to_bus);
                if (to === undefined) return null;
                const fromX = from?.x ?? SUBSTATION_X;
                const fromY = from?.y ?? SUBSTATION_Y;

                return (
                  <line
                    key={line.id}
                    x1={line.from_bus === 'substation' ? SUBSTATION_X : fromX}
                    y1={line.from_bus === 'substation' ? SUBSTATION_Y : fromY}
                    x2={to.x}
                    y2={to.y}
                    stroke={to.flagged ? '#f59e0b' : '#d6d3d1'}
                    strokeWidth={to.flagged ? 3.5 : 2.5}
                    strokeLinecap="round"
                  />
                );
              })}

              <g>
                <circle cx={SUBSTATION_X} cy={SUBSTATION_Y} r={20} fill="#1c1917" />
                <text x={SUBSTATION_X} y={SUBSTATION_Y + 4} textAnchor="middle" className="fill-white text-[10px] font-bold">
                  SUB
                </text>
              </g>

              {nodes.map((node) => (
                <g key={node.id}>
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={15}
                    fill={node.flagged ? '#f59e0b' : '#6366f1'}
                    fillOpacity={0.16}
                    stroke={node.flagged ? '#d97706' : '#4f46e5'}
                    strokeWidth={2}
                  />
                  <text x={node.x} y={node.y + 4} textAnchor="middle" className="fill-stone-700 text-[10px] font-bold">
                    {node.id}
                  </text>
                  <text x={node.x} y={node.y + 15 + 14} textAnchor="middle" className="fill-stone-500 text-[10px] font-medium">
                    {node.label}
                  </text>
                </g>
              ))}
            </svg>
          </div>
        </Card>

        <Card title="Constraint watch" subtitle="What the safety layer has had to cut back" contentClassName="p-0">
          <ul className="divide-y divide-stone-100">
            {curtailments.slice(0, 12).map((c, i) => (
              <li key={i} className="flex items-start gap-3 px-5 py-3.5">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                  <Gauge className="size-4" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-stone-900">
                    {householdLabel(c.seller_household_id)} → {householdLabel(c.buyer_household_id)}
                  </p>
                  <p className="text-xs text-stone-500">
                    <span className="font-mono font-semibold text-amber-700 tnum">{kwh(c.curtailed_kwh)}</span>{' '}
                    cut back — {c.reason}, tick {c.tick_index}
                  </p>
                </div>
              </li>
            ))}

            {curtailments.length === 0 && (
              <li className="px-5 py-3.5">
                <Badge tone="battery">
                  <ShieldCheck className="size-3.5" aria-hidden="true" />
                  No curtailments recorded yet
                </Badge>
              </li>
            )}
          </ul>
        </Card>
      </div>
    </div>
  );
}
