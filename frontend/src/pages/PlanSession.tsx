import { Bot, CloudSun, IndianRupee, Loader2, PlugZap, Sparkles, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { Horizon, HouseholdWhatIf, Scenario, SessionConfig } from '@/api/session';
import { fetchNetwork } from '@/api/simulation';
import { useAuth } from '@/auth/useAuth';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/cn';
import { dateLabel, hourLabel } from '@/lib/format';
import { householdLabel } from '@/lib/household';
import { HORIZONS, SCENARIOS } from '@/lib/session';
import { useLiveData } from '@/live/useLiveData';

interface HouseRow {
  guests: number;
  away: boolean;
  awayFrom: number; // clock hour from midnight of the start date
  awayTo: number;
  wfh: boolean;
  panels: number; // fraction lost: 0 clean ... 1 no panels
  battery: number | null; // null = the house's own
  startSoc: number | null; // null = left by the previous 24 hours
}

const PANEL_OPTIONS = [
  { value: 0, label: 'Clean' },
  { value: 0.2, label: 'Dusty (−20%)' },
  { value: 0.4, label: 'Very dusty (−40%)' },
  { value: 0.6, label: 'Shaded (−60%)' },
  { value: 1, label: 'No panels' },
];
const BATTERY_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: 'Own (10 units)' },
  { value: 0, label: 'None' },
  { value: 5, label: '5 units' },
  { value: 15, label: '15 units' },
];
const START_SOC_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: 'From yesterday' },
  ...[0.1, 0.25, 0.5, 0.75, 1].map((v) => ({ value: v, label: `${String(Math.round(v * 100))}%` })),
];

function defaultRow(startHour: number): HouseRow {
  return {
    guests: 0,
    away: false,
    awayFrom: Math.min(startHour + 3, 23),
    awayTo: Math.min(startHour + 3, 23) + 3,
    wfh: false,
    panels: 0,
    battery: null,
    startSoc: null,
  };
}

const selectClass =
  'rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-xs font-medium text-stone-700 outline-none focus:border-peer-400 disabled:opacity-40';
const inputClass =
  'w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm font-medium text-stone-800 outline-none focus:border-peer-400';

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-stone-600">{label}</span>
      {children}
      {hint !== undefined && <span className="text-[11px] text-stone-400">{hint}</span>}
    </label>
  );
}

export function PlanSession() {
  const { accessToken } = useAuth();
  const { session, loading, plan, busy, error } = useLiveData();
  const navigate = useNavigate();

  const [simDate, setSimDate] = useState('2026-05-15');
  const [startHour, setStartHour] = useState(14);
  const [horizon, setHorizon] = useState<Horizon>(12);
  const [scenario, setScenario] = useState<Scenario>('auto');
  const [retail, setRetail] = useState(10.5);
  const [feedIn, setFeedIn] = useState(3.61);
  const [surcharge, setSurcharge] = useState(0);
  const [cutOn, setCutOn] = useState(false);
  const [cutFrom, setCutFrom] = useState(19);
  const [cutTo, setCutTo] = useState(21);
  const [householdIds, setHouseholdIds] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, HouseRow>>({});
  const [initialised, setInitialised] = useState(false);

  // Start from the current session's setup, so "New session" tweaks the
  // last one rather than starting from scratch. This happens exactly once,
  // before the form is shown (see below): restoring later would overwrite
  // whatever the user had already changed.
  useEffect(() => {
    if (initialised) return;
    if (session === null) {
      // Nothing to restore once the first load has finished without one.
      if (!loading) setInitialised(true);
      return;
    }
    setInitialised(true);
    if (session.status === 'setup') return;
    setSimDate(session.sim_date);
    setStartHour(session.start_hour);
    if (HORIZONS.includes(session.horizon_hours as Horizon))
      setHorizon(session.horizon_hours as Horizon);
    setScenario(session.scenario);
    setRetail(session.retail_tariff);
    setFeedIn(session.feed_in_tariff);
    setSurcharge(session.peak_surcharge_pct);
    if (session.power_cut !== null) {
      setCutOn(true);
      setCutFrom(session.power_cut.start_hour);
      setCutTo(session.power_cut.end_hour);
    }
    const restored: Record<string, HouseRow> = {};
    for (const h of session.households) {
      restored[h.household_id] = {
        guests: h.guests,
        away: h.away_from !== null,
        awayFrom: h.away_from ?? session.start_hour + 3,
        awayTo: h.away_to ?? session.start_hour + 6,
        wfh: h.work_from_home,
        panels: h.panel_derate,
        battery: h.battery_capacity_kwh === 10 ? null : h.battery_capacity_kwh,
        startSoc: null,
      };
    }
    setRows(restored);
  }, [session, loading, initialised]);

  useEffect(() => {
    if (accessToken === null) return;
    const controller = new AbortController();
    fetchNetwork(accessToken, controller.signal)
      .then((feeder) => {
        setHouseholdIds(feeder.household_ids);
      })
      .catch(() => undefined);
    return () => {
      controller.abort();
    };
  }, [accessToken]);

  const row = (id: string): HouseRow => rows[id] ?? defaultRow(startHour);
  // Presets write one row per household, and the last session's setup is
  // restored when the session arrives; a preset applied before both have
  // loaded would be silently empty, or overwritten.
  const presetsReady = householdIds.length > 0 && initialised;
  const setRow = (id: string, patch: Partial<HouseRow>) => {
    setRows((current) => ({
      ...current,
      [id]: { ...(current[id] ?? defaultRow(startHour)), ...patch },
    }));
  };

  // Every clock hour in the session, counted from midnight of the start date.
  const sessionHours = useMemo(
    () => Array.from({ length: horizon + 1 }, (_, i) => startHour + i),
    [startHour, horizon],
  );

  function applyPreset(preset: 'identical' | 'mixed' | 'cut') {
    if (preset === 'identical') {
      setRows({});
      setCutOn(false);
      return;
    }
    if (preset === 'mixed') {
      const next: Record<string, HouseRow> = {};
      for (const id of householdIds) {
        const base = defaultRow(startHour);
        if (['h3', 'h5', 'h8'].includes(id)) next[id] = { ...base, panels: 1, battery: 0 };
        else if (['h2', 'h4', 'h9'].includes(id)) next[id] = { ...base, battery: 15 };
        else next[id] = base;
      }
      setRows(next);
      return;
    }
    setCutOn(true);
    setCutFrom(Math.max(startHour + 1, 19));
    setCutTo(Math.max(startHour + 3, 21));
  }

  async function submit() {
    const households: HouseholdWhatIf[] = householdIds.map((id) => {
      const r = row(id);
      return {
        household_id: id,
        guests: r.guests,
        away_from: r.away ? r.awayFrom : null,
        away_to: r.away ? r.awayTo : null,
        work_from_home: r.wfh,
        panel_derate: r.panels,
        battery_capacity_kwh: r.battery,
        battery_start_soc: r.startSoc,
      };
    });
    const config: SessionConfig = {
      sim_date: simDate,
      start_hour: startHour,
      horizon_hours: horizon,
      scenario,
      households,
      power_cut: cutOn ? { start_hour: cutFrom, end_hour: cutTo } : null,
      tariffs: { retail_tariff: retail, feed_in_tariff: feedIn, peak_surcharge_pct: surcharge },
    };
    if (await plan(config)) void navigate('/');
  }

  const scenarioInfo = SCENARIOS.find((s) => s.value === scenario);

  if (!initialised) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-stone-400">
        Loading your last session…
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card title="When" subtitle="Where the session starts, and how far ahead the agents trade">
          <div className="flex flex-col gap-4">
            <Field label="Date" hint={dateLabel(simDate)}>
              <input
                type="date"
                value={simDate}
                min="2000-01-01"
                max="2100-12-31"
                onChange={(e) => {
                  if (e.target.value) setSimDate(e.target.value);
                }}
                className={inputClass}
              />
            </Field>
            <Field label="Start time">
              <select
                value={startHour}
                onChange={(e) => {
                  setStartHour(Number(e.target.value));
                }}
                className={inputClass}
              >
                {Array.from({ length: 24 }, (_, h) => (
                  <option key={h} value={h}>
                    {hourLabel(h)}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="Predict and trade ahead"
              hint={`Until ${hourLabel(startHour + horizon)}${startHour + horizon >= 24 ? ' the next day' : ''}`}
            >
              <div className="grid grid-cols-4 gap-1.5">
                {HORIZONS.map((h) => (
                  <button
                    key={h}
                    type="button"
                    onClick={() => {
                      setHorizon(h);
                    }}
                    className={cn(
                      'rounded-lg py-2 text-sm font-semibold transition-colors',
                      horizon === h
                        ? 'bg-stone-900 text-white'
                        : 'bg-stone-100 text-stone-600 hover:bg-stone-200',
                    )}
                  >
                    {h} h
                  </button>
                ))}
              </div>
            </Field>
          </div>
        </Card>

        <Card
          title="Weather"
          subtitle="Chennai's own climate for the date, or a what-if"
          action={<CloudSun className="size-5 text-solar-500" aria-hidden="true" />}
        >
          <div className="flex flex-col gap-2">
            {SCENARIOS.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => {
                  setScenario(s.value);
                }}
                className={cn(
                  'rounded-lg border px-3 py-2.5 text-left transition-colors',
                  scenario === s.value
                    ? 'border-peer-500 bg-peer-50'
                    : 'border-stone-200 hover:bg-stone-50',
                )}
              >
                <p className="text-sm font-semibold text-stone-900">{s.label}</p>
                <p className="text-xs text-stone-500">{s.description}</p>
              </button>
            ))}
          </div>
          <p className="sr-only">{scenarioInfo?.description}</p>
        </Card>

        <Card
          title="EB tariffs and supply"
          subtitle="What the provider charges and pays — and whether it's there at all"
          action={<IndianRupee className="size-5 text-stone-400" aria-hidden="true" />}
        >
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="EB charges (₹/unit)" hint="TN 801–1000 slab: ₹10.50">
                <input
                  type="number"
                  step="0.05"
                  min={1}
                  max={30}
                  value={retail}
                  onChange={(e) => {
                    setRetail(Number(e.target.value));
                  }}
                  className={inputClass}
                />
              </Field>
              <Field label="EB pays (₹/unit)" hint="TNERC feed-in: ₹3.61">
                <input
                  type="number"
                  step="0.05"
                  min={0}
                  max={20}
                  value={feedIn}
                  onChange={(e) => {
                    setFeedIn(Number(e.target.value));
                  }}
                  className={inputClass}
                />
              </Field>
            </div>
            <Field label={`Evening peak surcharge (6–10 pm): ${String(surcharge)}%`}>
              <input
                type="range"
                min={0}
                max={50}
                step={5}
                value={surcharge}
                onChange={(e) => {
                  setSurcharge(Number(e.target.value));
                }}
                className="accent-peer-600"
              />
            </Field>
            <div className="rounded-lg border border-stone-200 p-3">
              <label className="flex items-center gap-2 text-sm font-semibold text-stone-800">
                <input
                  type="checkbox"
                  checked={cutOn}
                  onChange={(e) => {
                    setCutOn(e.target.checked);
                  }}
                  className="accent-grid-600"
                />
                <PlugZap className="size-4 text-grid-600" aria-hidden="true" />
                EB power cut
              </label>
              <div className="mt-2 flex items-center gap-2 text-xs text-stone-500">
                from
                <select
                  aria-label="Power cut from"
                  disabled={!cutOn}
                  value={cutFrom}
                  onChange={(e) => {
                    setCutFrom(Number(e.target.value));
                  }}
                  className={selectClass}
                >
                  {sessionHours.slice(0, -1).map((h) => (
                    <option key={h} value={h}>
                      {hourLabel(h)}
                    </option>
                  ))}
                </select>
                to
                <select
                  aria-label="Power cut to"
                  disabled={!cutOn}
                  value={cutTo}
                  onChange={(e) => {
                    setCutTo(Number(e.target.value));
                  }}
                  className={selectClass}
                >
                  {sessionHours
                    .slice(1)
                    .filter((h) => h > cutFrom)
                    .map((h) => (
                      <option key={h} value={h}>
                        {hourLabel(h)}
                      </option>
                    ))}
                </select>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <Card
        title="Each household's what-ifs"
        subtitle="Leave a row alone for an ordinary day. Every house has the same 4-bedroom design; these change who's home and what's on the roof."
        action={
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-medium text-stone-400">Presets:</span>
            <button
              type="button"
              disabled={!presetsReady}
              onClick={() => {
                applyPreset('identical');
              }}
              className="rounded-lg bg-stone-100 px-2.5 py-1 text-xs font-semibold text-stone-700 hover:bg-stone-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Identical homes
            </button>
            <button
              type="button"
              disabled={!presetsReady}
              onClick={() => {
                applyPreset('mixed');
              }}
              className="rounded-lg bg-stone-100 px-2.5 py-1 text-xs font-semibold text-stone-700 hover:bg-stone-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Mixed neighbourhood
            </button>
            <button
              type="button"
              disabled={!presetsReady}
              onClick={() => {
                applyPreset('cut');
              }}
              className="rounded-lg bg-stone-100 px-2.5 py-1 text-xs font-semibold text-stone-700 hover:bg-stone-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Evening power cut
            </button>
          </div>
        }
        contentClassName="p-0"
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead>
              <tr className="border-b border-stone-100 text-[11px] font-semibold tracking-wider text-stone-400 uppercase">
                <th className="px-5 py-2.5">House</th>
                <th className="px-2 py-2.5">
                  <Users className="inline size-3.5" aria-hidden="true" /> Guests
                </th>
                <th className="px-2 py-2.5">Family out</th>
                <th className="px-2 py-2.5">WFH</th>
                <th className="px-2 py-2.5">Panels</th>
                <th className="px-2 py-2.5">Battery</th>
                <th className="px-2 py-2.5">Starts at</th>
              </tr>
            </thead>
            <tbody>
              {householdIds.map((id) => {
                const r = row(id);
                return (
                  <tr key={id} className="border-b border-stone-50 last:border-b-0">
                    <td className="px-5 py-2 font-semibold text-stone-800">{householdLabel(id)}</td>
                    <td className="px-2 py-2">
                      <select
                        aria-label={`${householdLabel(id)} guests`}
                        value={r.guests}
                        onChange={(e) => {
                          setRow(id, { guests: Number(e.target.value) });
                        }}
                        className={selectClass}
                      >
                        {[0, 1, 2, 3, 4].map((g) => (
                          <option key={g} value={g}>
                            {g === 0 ? 'None' : `+${String(g)}`}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          aria-label={`${householdLabel(id)} family out`}
                          checked={r.away}
                          onChange={(e) => {
                            setRow(id, { away: e.target.checked });
                          }}
                          className="accent-peer-600"
                        />
                        <select
                          aria-label={`${householdLabel(id)} out from`}
                          disabled={!r.away}
                          value={r.awayFrom}
                          onChange={(e) => {
                            setRow(id, { awayFrom: Number(e.target.value) });
                          }}
                          className={selectClass}
                        >
                          {sessionHours
                            .slice(0, -1)
                            .filter((h) => h < 24)
                            .map((h) => (
                              <option key={h} value={h}>
                                {hourLabel(h)}
                              </option>
                            ))}
                        </select>
                        <span className="text-xs text-stone-400">–</span>
                        <select
                          aria-label={`${householdLabel(id)} out until`}
                          disabled={!r.away}
                          value={r.awayTo}
                          onChange={(e) => {
                            setRow(id, { awayTo: Number(e.target.value) });
                          }}
                          className={selectClass}
                        >
                          {sessionHours
                            .slice(1)
                            .filter((h) => h > r.awayFrom)
                            .map((h) => (
                              <option key={h} value={h}>
                                {hourLabel(h)}
                              </option>
                            ))}
                        </select>
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <input
                        type="checkbox"
                        aria-label={`${householdLabel(id)} works from home`}
                        checked={r.wfh}
                        onChange={(e) => {
                          setRow(id, { wfh: e.target.checked });
                        }}
                        className="accent-peer-600"
                      />
                    </td>
                    <td className="px-2 py-2">
                      <select
                        aria-label={`${householdLabel(id)} panels`}
                        value={r.panels}
                        onChange={(e) => {
                          setRow(id, { panels: Number(e.target.value) });
                        }}
                        className={selectClass}
                      >
                        {PANEL_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-2">
                      <select
                        aria-label={`${householdLabel(id)} battery`}
                        value={r.battery ?? 'own'}
                        onChange={(e) => {
                          setRow(id, {
                            battery: e.target.value === 'own' ? null : Number(e.target.value),
                          });
                        }}
                        className={selectClass}
                      >
                        {BATTERY_OPTIONS.map((o) => (
                          <option key={o.label} value={o.value ?? 'own'}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-2">
                      <select
                        aria-label={`${householdLabel(id)} starting charge`}
                        disabled={r.battery === 0}
                        value={r.startSoc ?? 'auto'}
                        onChange={(e) => {
                          setRow(id, {
                            startSoc: e.target.value === 'auto' ? null : Number(e.target.value),
                          });
                        }}
                        className={selectClass}
                      >
                        {START_SOC_OPTIONS.map((o) => (
                          <option key={o.label} value={o.value ?? 'auto'}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex flex-col items-end gap-2">
        {error !== null && (
          <p
            role="alert"
            className="rounded-lg bg-grid-50 px-3 py-2 text-sm font-medium text-grid-700"
          >
            {error}
          </p>
        )}
        <div className="flex items-center gap-4">
          <p className="max-w-xl text-right text-xs text-stone-500">
            <Bot className="mr-1 inline size-3.5" aria-hidden="true" />
            Every household&apos;s agent forecasts its next {horizon} hours, then trades each hour
            with its neighbours and the EB. Nothing runs until you press Next hour or Run to end.
          </p>
          <button
            type="button"
            disabled={busy || householdIds.length === 0}
            onClick={() => void submit()}
            className="flex items-center gap-2 rounded-lg bg-peer-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-peer-700 disabled:opacity-60"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles className="size-4" aria-hidden="true" />
            )}
            {busy ? `Forecasting and trading ${String(horizon)} hours…` : 'Predict & trade'}
          </button>
        </div>
      </div>
    </div>
  );
}
