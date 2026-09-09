import { BatteryCharging, IndianRupee, Leaf, Sun } from 'lucide-react';
import { Link } from 'react-router-dom';

import { EnergyFlow } from '@/components/dashboard/EnergyFlow';
import { ForecastChart } from '@/components/dashboard/ForecastChart';
import { TradeList } from '@/components/dashboard/TradeList';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { StatTile } from '@/components/ui/StatTile';
import { daySummary, marketState, recentTrades } from '@/data/mock';
import { inr, inrWhole, kwh, percent } from '@/lib/format';

export function Dashboard() {
  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Saved today"
          value={inrWhole(daySummary.savedInr)}
          caption="vs. buying from the utility"
          icon={IndianRupee}
          tone="battery"
        />
        <StatTile
          label="Sold to neighbours"
          value={kwh(daySummary.soldKwh)}
          caption={`at ${inr(marketState.clearingInr)}/kWh now`}
          icon={Sun}
          tone="solar"
        />
        <StatTile
          label="Bought from neighbours"
          value={kwh(daySummary.boughtKwh)}
          caption="before sunrise"
          icon={BatteryCharging}
          tone="peer"
        />
        <StatTile
          label="Self-sufficiency"
          value={percent(daySummary.selfSufficiency)}
          caption={`${kwh(daySummary.gridAvoidedKwh)} not drawn from the grid`}
          icon={Leaf}
          tone="battery"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Energy flow"
          subtitle="Live · updates every 15 minutes"
          action={<Badge tone="peer">Exporting to 3 neighbours</Badge>}
          contentClassName="p-2"
        >
          <EnergyFlow />
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
          <TradeList trades={recentTrades} />
        </Card>
      </div>

      <Card
        title="Forecast · next 6 hours"
        subtitle="Shaded band is the P10–P90 interval your agent bids against"
        action={
          <div className="flex items-center gap-4 text-xs text-stone-500">
            <span className="flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded bg-solar-600" />
              Solar
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded bg-peer-600" />
              Your load
            </span>
          </div>
        }
      >
        <ForecastChart />
      </Card>
    </div>
  );
}
