import { CalendarPlus, CloudSun, Sunrise, Sunset, Thermometer } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import type { Family } from '@/api/family';
import { fetchOwnFamily } from '@/api/family';
import { useAuth } from '@/auth/useAuth';
import { AgentChat } from '@/components/dashboard/AgentChat';
import { AgentPlan } from '@/components/dashboard/AgentPlan';
import { EnergyFlow } from '@/components/dashboard/EnergyFlow';
import { FamilyPanel } from '@/components/dashboard/FamilyPanel';
import { ForecastChart } from '@/components/dashboard/ForecastChart';
import { MoneyCards } from '@/components/dashboard/MoneyCards';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { dateLabel, hourLabel, simClock } from '@/lib/format';
import { scenarioLabel } from '@/lib/session';
import { useLiveData } from '@/live/useLiveData';

export function Dashboard() {
  const { accessToken } = useAuth();
  const { session, household, own, readings, trades, loading, version } = useLiveData();
  const [family, setFamily] = useState<Family | null>(null);

  // Occupancy follows the session clock, so refetch whenever the session
  // changes (plan, next hour, reset) — not on a timer.
  useEffect(() => {
    if (accessToken === null) return;
    let cancelled = false;
    fetchOwnFamily(accessToken)
      .then((data) => {
        if (!cancelled) setFamily(data);
      })
      .catch(() => {
        // An account with no household has no family to show.
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, version]);

  if (loading || household === null || session === null) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-stone-400">
        Loading your household…
      </div>
    );
  }

  if (session.status === 'setup' || own === null) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col items-center gap-4 rounded-xl border border-stone-200 bg-white p-10 text-center">
        <CalendarPlus className="size-10 text-peer-500" aria-hidden="true" />
        <h2 className="text-lg font-bold text-stone-900">No session planned yet</h2>
        <p className="text-sm text-stone-500">
          Pick a date and start time, set the weather and any what-ifs, and every household&apos;s
          agent will forecast the hours ahead and trade them with its neighbours and the EB.
        </p>
        <Link
          to="/session"
          className="rounded-lg bg-peer-600 px-4 py-2 text-sm font-semibold text-white hover:bg-peer-700"
        >
          Plan a session
        </Link>
      </div>
    );
  }

  const statement = own.delivered ?? own.planned;
  const setup = session.households.find((h) => h.household_id === household.id);
  const capacity = setup?.battery_capacity_kwh ?? household.battery_capacity_kwh;
  const ticksPerHour = 60 / session.tick_minutes;
  const durationH = session.tick_minutes / 60;

  const latest = readings[0];
  const previous = readings[1];
  const currentSlot = latest !== undefined ? Math.floor(latest.tick_index / ticksPerHour) : 0;
  const slotNow = own.slots[currentSlot];
  const peerKw = slotNow !== undefined ? slotNow.p2p_sold_kwh - slotNow.p2p_bought_kwh : 0;
  const partners = new Set(
    trades
      .filter((t) => t.tick_index === currentSlot)
      .map((t) =>
        t.seller_household_id === household.id ? t.buyer_household_id : t.seller_household_id,
      ),
  );
  const startSoc = setup?.start_soc ?? 0;
  const batteryKw =
    latest !== undefined
      ? ((latest.battery_soc - (previous?.battery_soc ?? startSoc)) * capacity) / durationH
      : 0;
  const livePower = {
    solarKw: latest?.generation_kw ?? 0,
    loadKw: latest?.consumption_kw ?? 0,
    batteryKw,
    peerKw: latest !== undefined ? peerKw : 0,
    gridKw: latest !== undefined ? latest.grid_kwh / durationH : 0,
    batterySoc: (latest?.battery_soc ?? startSoc) * 100,
  };
  const weather = session.weather;

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm">
        <span className="font-semibold text-stone-900">
          {dateLabel(session.sim_date)} · {hourLabel(session.start_hour)} for{' '}
          {session.horizon_hours} h
        </span>
        <Badge tone="peer">
          <CloudSun className="size-3.5" aria-hidden="true" />
          {scenarioLabel(session.scenario)} · {weather.sky}
        </Badge>
        <Badge>
          <Thermometer className="size-3.5" aria-hidden="true" />
          {weather.temperature_now_c.toFixed(1)} °C now · {weather.t_min_c.toFixed(0)}–
          {weather.t_max_c.toFixed(0)} °C
        </Badge>
        <Badge>
          <Sunrise className="size-3.5" aria-hidden="true" />
          {simClock(weather.sunrise_h)}
          <Sunset className="ml-1 size-3.5" aria-hidden="true" />
          {simClock(weather.sunset_h)}
        </Badge>
        {session.power_cut !== null && (
          <Badge tone="grid">
            EB cut {hourLabel(session.power_cut.start_hour)}–{hourLabel(session.power_cut.end_hour)}
          </Badge>
        )}
        <span className="ml-auto text-xs text-stone-500">
          EB ₹{session.retail_tariff.toFixed(2)} in · ₹{session.feed_in_tariff.toFixed(2)} out
          {session.peak_surcharge_pct > 0 && ` · +${String(session.peak_surcharge_pct)}% 6–10 pm`}
        </span>
      </div>

      {statement !== null && <MoneyCards statement={statement} />}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Energy flow"
          subtitle={
            latest !== undefined
              ? `${hourLabel(session.start_hour + latest.tick_index * durationH)} · delivered`
              : 'Nothing delivered yet — press Next hour or Run to end'
          }
          action={
            <Badge tone="peer">
              {partners.size === 0
                ? 'No neighbours this hour'
                : `Trading with ${String(partners.size)} neighbour${partners.size === 1 ? '' : 's'}`}
            </Badge>
          }
          contentClassName="p-2"
        >
          <EnergyFlow livePower={livePower} peerCount={partners.size} />
        </Card>

        <Card title="Who's home" subtitle="What's actually driving your consumption right now">
          {family !== null ? (
            <FamilyPanel family={family} />
          ) : (
            <p className="text-sm text-stone-400">Loading your household&apos;s family…</p>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Forecast vs what happened"
          subtitle={`Your next ${String(session.horizon_hours)} hours — P50 inside the P10–P90 band, actuals as they're delivered`}
          action={
            <Badge>
              {own.model === 'lightgbm-quantile'
                ? 'LightGBM quantile + conformal'
                : 'Seasonal naive'}
            </Badge>
          }
        >
          <ForecastChart slots={own.slots} />
        </Card>

        <Card
          title="Talk to your agent"
          subtitle="It explains its real decisions — it never trades from chat"
        >
          <AgentChat />
        </Card>
      </div>

      <Card
        title="Your agent's plan, hour by hour"
        subtitle="What it decided before each hour's market, how the market went, and what actually happened"
        contentClassName="p-0"
      >
        <AgentPlan slots={own.slots} deliveredHours={session.hours_delivered} />
      </Card>
    </div>
  );
}
