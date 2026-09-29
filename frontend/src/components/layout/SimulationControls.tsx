import { CalendarPlus, FastForward, Loader2, Square, StepForward } from 'lucide-react';
import { Link } from 'react-router-dom';

import { dateLabel, hourLabel } from '@/lib/format';
import { useLiveData } from '@/live/useLiveData';

/** The one control surface for the shared planning session. Nothing runs on
 *  its own: you plan a session, then deliver it an hour at a time or run it
 *  to the end — and it always stops at the horizon. */
export function SimulationControls() {
  const { session, busy, running, nextHour, runToEnd, stop } = useLiveData();

  if (session === null) {
    return <div className="h-9 w-64 animate-pulse rounded-lg bg-stone-100" aria-hidden="true" />;
  }

  const newSession = (
    <Link
      to="/session"
      className="flex items-center gap-1.5 rounded-lg border border-stone-200 px-3 py-1.5 text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-100"
    >
      <CalendarPlus className="size-4" aria-hidden="true" />
      New session
    </Link>
  );

  if (session.status === 'setup') {
    return (
      <Link
        to="/session"
        className="flex items-center gap-1.5 rounded-lg bg-peer-600 px-3.5 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-peer-700"
      >
        <CalendarPlus className="size-4" aria-hidden="true" />
        Plan a session
      </Link>
    );
  }

  const done = session.hours_delivered;
  const total = session.horizon_hours;
  const complete = session.status === 'complete';

  return (
    <div className="flex items-center gap-2">
      <div
        className="hidden min-w-[200px] flex-col gap-1 rounded-lg border border-stone-200 px-3 py-1.5 lg:flex"
        title={`${dateLabel(session.sim_date)}, from ${hourLabel(session.start_hour)} for ${String(total)} hours`}
      >
        <div className="flex items-center justify-between gap-3 text-xs">
          <span className="font-medium text-stone-500">
            {complete
              ? 'Session complete'
              : `${dateLabel(session.weather.date)} · ${hourLabel(session.clock_hours)}`}
          </span>
          <span className="font-mono font-semibold text-stone-900 tnum">
            {done}/{total} h
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
          <div
            className="h-full rounded-full bg-battery-500 transition-all"
            style={{ width: `${String((done / total) * 100)}%` }}
          />
        </div>
      </div>

      {!complete && (
        <>
          <button
            type="button"
            disabled={busy || running}
            onClick={() => void nextHour()}
            className="flex items-center gap-1.5 rounded-lg border border-stone-200 px-3 py-1.5 text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-100 disabled:opacity-50"
          >
            {busy && !running ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <StepForward className="size-4" aria-hidden="true" />
            )}
            Next hour
          </button>
          {running ? (
            <button
              type="button"
              onClick={stop}
              className="flex items-center gap-1.5 rounded-lg bg-amber-600 px-3.5 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-amber-700"
            >
              <Square className="size-4" aria-hidden="true" />
              Stop
            </button>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => void runToEnd()}
              className="flex items-center gap-1.5 rounded-lg bg-battery-600 px-3.5 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-battery-700 disabled:opacity-60"
            >
              <FastForward className="size-4" aria-hidden="true" />
              Run to end
            </button>
          )}
        </>
      )}
      {newSession}
    </div>
  );
}
