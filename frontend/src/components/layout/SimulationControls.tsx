import { Pause, Play, RotateCcw, StepForward } from 'lucide-react';
import { useState } from 'react';

import type { Scenario } from '@/api/simulation';
import { cn } from '@/lib/cn';
import { simClock } from '@/lib/format';
import { useLiveData } from '@/live/useLiveData';

const SCENARIOS: { value: Scenario; label: string }[] = [
  { value: 'clear', label: 'Clear day' },
  { value: 'cloudy', label: 'Cloudy day' },
  { value: 'heatwave', label: 'Heatwave' },
];

const SPEEDS: { value: number; label: string }[] = [
  { value: 2, label: '1×' },
  { value: 0.5, label: '4×' },
  { value: 0.15, label: '12×' },
];

/** The one control surface for the whole feeder's shared clock — every
 *  household watches and trades in the same ticks, so play/pause/reset here
 *  affects everyone's dashboard, not just the person who clicked it. */
export function SimulationControls() {
  const { simulation, play, pause, step, reset } = useLiveData();
  const [busy, setBusy] = useState(false);
  const [confirmingReset, setConfirmingReset] = useState(false);

  if (simulation === null) {
    return <div className="h-9 w-64 animate-pulse rounded-lg bg-stone-100" aria-hidden="true" />;
  }

  async function run(action: () => Promise<void>): Promise<void> {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <div className="hidden items-center gap-2 rounded-lg border border-stone-200 px-3 py-1.5 lg:flex">
        <span className="text-xs font-medium text-stone-500">Day {simulation.simulated_day + 1}</span>
        <span className="font-mono text-sm font-semibold text-stone-900 tnum">
          {simClock(simulation.simulated_hour)}
        </span>
        <span className="text-xs text-stone-400">· tick {simulation.tick_index}</span>
      </div>

      <select
        aria-label="Scenario"
        value={simulation.scenario}
        disabled={busy}
        onChange={(e) => void run(() => reset({ scenario: e.target.value as Scenario }))}
        className="hidden rounded-lg border border-stone-200 bg-white py-1.5 pr-7 pl-2.5 text-xs font-medium text-stone-700 outline-none focus:border-peer-400 md:block"
      >
        {SCENARIOS.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>

      <select
        aria-label="Speed"
        value={simulation.seconds_per_tick}
        disabled={busy}
        onChange={(e) => void run(() => play({ seconds_per_tick: Number(e.target.value) }))}
        className="hidden rounded-lg border border-stone-200 bg-white py-1.5 pr-7 pl-2.5 text-xs font-medium text-stone-700 outline-none focus:border-peer-400 sm:block"
      >
        {SPEEDS.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>

      <button
        type="button"
        disabled={busy}
        onClick={() => void run(() => step())}
        title="Advance one tick"
        aria-label="Advance one tick"
        className="flex size-9 items-center justify-center rounded-lg border border-stone-200 text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900 disabled:opacity-50"
      >
        <StepForward className="size-[18px]" aria-hidden="true" />
      </button>

      <button
        type="button"
        disabled={busy}
        onClick={() => void run(() => (simulation.running ? pause() : play()))}
        className={cn(
          'flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-sm font-semibold text-white transition-colors disabled:opacity-60',
          simulation.running ? 'bg-amber-600 hover:bg-amber-700' : 'bg-battery-600 hover:bg-battery-700',
        )}
      >
        {simulation.running ? (
          <Pause className="size-4" aria-hidden="true" />
        ) : (
          <Play className="size-4" aria-hidden="true" />
        )}
        {simulation.running ? 'Pause' : 'Play'}
      </button>

      {confirmingReset ? (
        <div className="flex items-center gap-1.5 rounded-lg border border-grid-200 bg-grid-50 px-2 py-1">
          <span className="text-xs font-medium text-grid-700">Wipe all history?</span>
          <button
            type="button"
            onClick={() => {
              setConfirmingReset(false);
              void run(() => reset());
            }}
            className="rounded bg-grid-600 px-2 py-1 text-xs font-semibold text-white hover:bg-grid-700"
          >
            Reset
          </button>
          <button
            type="button"
            onClick={() => {
              setConfirmingReset(false);
            }}
            className="rounded px-2 py-1 text-xs font-medium text-stone-500 hover:bg-stone-100"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setConfirmingReset(true);
          }}
          title="Reset to a fresh day"
          aria-label="Reset to a fresh day"
          className="flex size-9 items-center justify-center rounded-lg border border-stone-200 text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900 disabled:opacity-50"
        >
          <RotateCcw className="size-[18px]" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
