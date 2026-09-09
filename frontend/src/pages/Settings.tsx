import { BatteryCharging, Bot, Scale } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { marketState } from '@/data/mock';
import { inr } from '@/lib/format';

interface PreferenceRowProps {
  label: string;
  description: string;
  value: string;
}

function PreferenceRow({ label, description, value }: PreferenceRowProps) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-stone-100 py-3.5 last:border-b-0">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-stone-900">{label}</p>
        <p className="mt-0.5 text-xs text-stone-500">{description}</p>
      </div>
      <span className="shrink-0 font-mono text-sm font-semibold text-stone-900 tnum">{value}</span>
    </div>
  );
}

export function Settings() {
  return (
    <div className="mx-auto grid max-w-[1400px] grid-cols-1 gap-5 xl:grid-cols-2">
      <Card
        title="Battery policy"
        subtitle="What your agent may do with stored energy"
        action={
          <Badge tone="battery">
            <BatteryCharging className="size-3.5" aria-hidden="true" />
            Active
          </Badge>
        }
        contentClassName="px-5 py-1"
      >
        <PreferenceRow
          label="Evening reserve"
          description="Charge held back for the 18:00–22:00 peak, never sold before it"
          value="40%"
        />
        <PreferenceRow
          label="Maximum depth of discharge"
          description="Protects cell life by limiting how far the battery is drained"
          value="80%"
        />
        <PreferenceRow
          label="Charge from neighbours"
          description="Buy peer energy when it is cheaper than the retail tariff"
          value="Enabled"
        />
      </Card>

      <Card
        title="Trading preferences"
        subtitle="The limits your agent bids within"
        action={
          <Badge tone="peer">
            <Bot className="size-3.5" aria-hidden="true" />
            Autonomous
          </Badge>
        }
        contentClassName="px-5 py-1"
      >
        <PreferenceRow
          label="Minimum sale price"
          description="Your agent never sells below this, so a trade always beats exporting"
          value={`${inr(marketState.feedInTariff)}/kWh`}
        />
        <PreferenceRow
          label="Maximum purchase price"
          description="Your agent never pays more than the utility would charge"
          value={`${inr(marketState.retailTariff)}/kWh`}
        />
        <PreferenceRow
          label="Risk posture"
          description="Sells against the P10 forecast, so surplus is never over-promised"
          value="Conservative"
        />
      </Card>

      <Card
        className="xl:col-span-2"
        title="Market rules"
        subtitle="Set by the microgrid operator — the same for every participant"
        action={
          <Badge>
            <Scale className="size-3.5" aria-hidden="true" />
            Read only
          </Badge>
        }
        contentClassName="px-5 py-1"
      >
        <PreferenceRow
          label="Clearing mechanism"
          description="All matched pairs trade at one price, set where supply crosses demand"
          value={marketState.mechanism}
        />
        <PreferenceRow
          label="Tick length"
          description="How often the market gate closes and clears"
          value="15 minutes"
        />
        <PreferenceRow
          label="Grid safety"
          description="Every allocation is checked against thermal, transformer and voltage limits"
          value="IEEE 33-bus"
        />
      </Card>
    </div>
  );
}
