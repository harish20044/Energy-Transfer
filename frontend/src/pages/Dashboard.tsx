import { BatteryCharging, IndianRupee, Leaf, Sun } from 'lucide-react';
import { Link } from 'react-router-dom';

import { EnergyFlow } from '@/components/dashboard/EnergyFlow';
import { PowerHistoryChart } from '@/components/dashboard/PowerHistoryChart';
import { TradeList } from '@/components/dashboard/TradeList';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { StatTile } from '@/components/ui/StatTile';
import { ownMarketKw, tradingPartnerCount } from '@/lib/energy';
import { inrWhole, kwh, percent } from '@/lib/format';
import { toUiTrade } from '@/lib/tradeView';
import { useLiveData } from '@/live/useLiveData';

export function Dashboard() {
  const { household, readings, trades, balance, simulation, loading } = useLiveData();

  if (loading || household === null) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-stone-400">
        Loading your household…
      </div>
    );
  }

  const latest = readings[0];
  const tickMinutes = simulation?.tick_minutes ?? 15;
  const durationH = tickMinutes / 60;

  const peerKw = latest !== undefined ? ownMarketKw(trades, household.id, latest.tick_index, tickMinutes) : 0;
  const peerCount = latest !== undefined ? tradingPartnerCount(trades, household.id, latest.tick_index) : 0;
  const gridKw = latest !== undefined ? latest.grid_kwh / durationH : 0;

  // Battery kW is derived from the change in state of charge between the two
  // most recent readings — there is no separate "battery power" reading, the
  // charge itself IS the evidence of how much power moved.
  const previous = readings[1];
  const batteryKw =
    latest !== undefined && previous !== undefined
      ? ((latest.battery_soc - previous.battery_soc) * household.battery_capacity_kwh) / durationH
      : 0;

  const livePower = {
    solarKw: latest?.generation_kw ?? 0,
    loadKw: latest?.consumption_kw ?? 0,
    batteryKw,
    peerKw,
    gridKw,
    batterySoc: (latest?.battery_soc ?? 0) * 100,
  };

  // Self-sufficiency over the fetched window: how much of this household's
  // consumption was met without importing from the grid.
  const totalConsumedKwh = readings.reduce((sum, r) => sum + r.consumption_kw * durationH, 0);
  const totalImportedKwh = readings.reduce((sum, r) => sum + Math.max(0, r.grid_kwh), 0);
  const selfSufficiency =
    totalConsumedKwh > 0 ? Math.min(100, (1 - totalImportedKwh / totalConsumedKwh) * 100) : 100;
  const gridAvoidedKwh = Math.max(0, totalConsumedKwh - totalImportedKwh);

  const uiTrades = trades.slice(0, 5).map((t) => toUiTrade(t, household.id, tickMinutes));

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Net balance"
          value={inrWhole(balance?.net_balance ?? 0)}
          caption="since the last reset"
          icon={IndianRupee}
          tone="battery"
        />
        <StatTile
          label="Sold to neighbours"
          value={kwh(balance?.total_sold_kwh ?? 0)}
          caption={peerKw > 0 ? `${kwh(peerKw)} right now` : 'nothing this tick'}
          icon={Sun}
          tone="solar"
        />
        <StatTile
          label="Bought from neighbours"
          value={kwh(balance?.total_bought_kwh ?? 0)}
          caption={peerKw < 0 ? `${kwh(-peerKw)} right now` : 'nothing this tick'}
          icon={BatteryCharging}
          tone="peer"
        />
        <StatTile
          label="Self-sufficiency"
          value={percent(selfSufficiency)}
          caption={`${kwh(gridAvoidedKwh)} not drawn from the grid`}
          icon={Leaf}
          tone="battery"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Energy flow"
          subtitle={`Live · tick ${String(latest?.tick_index ?? 0)}`}
          action={
            <Badge tone="peer">
              {peerCount === 0
                ? 'No neighbours this tick'
                : `Trading with ${String(peerCount)} neighbour${peerCount === 1 ? '' : 's'}`}
            </Badge>
          }
          contentClassName="p-2"
        >
          <EnergyFlow livePower={livePower} peerCount={peerCount} />
        </Card>

        <Card
          title="Recent trades"
          subtitle="Every trade carries a reason"
          action={
            <Link
              to="/trades"
              className="text-xs font-semibold text-peer-600 hover:text-peer-700 hover:underline"
            >
              View all
            </Link>
          }
          contentClassName="p-0"
        >
          {uiTrades.length > 0 ? (
            <TradeList trades={uiTrades} />
          ) : (
            <p className="p-5 text-sm text-stone-400">No trades settled yet — press Play.</p>
          )}
        </Card>
      </div>

      <Card
        title="Recent power"
        subtitle="Your own generation and consumption over recent ticks"
      >
        <PowerHistoryChart readings={readings} tickMinutes={tickMinutes} />
      </Card>
    </div>
  );
}
