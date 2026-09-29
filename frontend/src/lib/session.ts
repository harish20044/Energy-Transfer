/** Shared vocabulary for sessions and agent decisions — the one place that
 *  decides how a scenario or strategy reads to a person. */

import type { BadgeTone } from '@/components/ui/Badge';
import type { Horizon, Scenario } from '@/api/session';

export const HORIZONS: Horizon[] = [4, 8, 12, 24];

export const SCENARIOS: { value: Scenario; label: string; description: string }[] = [
  {
    value: 'auto',
    label: 'Typical for the date',
    description: "Chennai's own climatology for that day — sun, cloud and rain as it usually is.",
  },
  { value: 'clear', label: 'Clear sky', description: 'Full sun all day.' },
  {
    value: 'cloudy',
    label: 'Broken cloud',
    description: 'Patchy cloud — solar swings hour to hour.',
  },
  { value: 'rainy', label: 'Monsoon rain', description: 'Overcast and raining — little solar.' },
  {
    value: 'heatwave',
    label: 'Heatwave',
    description: 'IMD heatwave: +4.5 °C by day, warm nights — ACs run hard.',
  },
];

export function scenarioLabel(scenario: Scenario): string {
  return SCENARIOS.find((s) => s.value === scenario)?.label ?? scenario;
}

const STRATEGIES: Record<string, { label: string; tone: BadgeTone }> = {
  'sell-surplus': { label: 'Selling surplus', tone: 'solar' },
  'sell-stored': { label: 'Selling spare charge', tone: 'solar' },
  'buy-shortfall': { label: 'Buying shortfall', tone: 'grid' },
  'buy-to-store': { label: 'Buying to store', tone: 'peer' },
  'prepare-outage': { label: 'Preparing for power cut', tone: 'warning' },
  'self-sufficient': { label: 'Self-sufficient', tone: 'battery' },
  idle: { label: 'Balanced', tone: 'neutral' },
};

export function strategyMeta(strategy: string): { label: string; tone: BadgeTone } {
  return STRATEGIES[strategy] ?? { label: strategy, tone: 'neutral' };
}
