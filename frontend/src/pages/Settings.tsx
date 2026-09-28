import { BatteryCharging, Bot, Scale } from 'lucide-react';
import { useState } from 'react';

import { updateEveningReserve } from '@/api/household';
import { useAuth } from '@/auth/useAuth';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { inr, kw, kwh } from '@/lib/format';
import { FEED_IN_TARIFF, RETAIL_TARIFF } from '@/lib/tariffs';
import { useLiveData } from '@/live/useLiveData';

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
  const { accessToken } = useAuth();
  const { household, refreshHousehold } = useLiveData();
  const [saving, setSaving] = useState(false);
  const [draftReserve, setDraftReserve] = useState<number | null>(null);

  if (household === null) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-stone-400">
        Loading your household…
      </div>
    );
  }

  const reservePct = draftReserve ?? Math.round(household.evening_reserve * 100);

  async function commitReserve(pct: number): Promise<void> {
    if (accessToken === null) return;
    setSaving(true);
    try {
      await updateEveningReserve(accessToken, pct / 100);
      refreshHousehold();
    } finally {
      setSaving(false);
      setDraftReserve(null);
    }
  }

  return (
    <div className="mx-auto grid max-w-[1400px] grid-cols-1 gap-5 xl:grid-cols-2">
      <Card
        title="Battery policy"
        subtitle="What your agent may do with stored energy"
        action={
          <Badge tone="battery">
            <BatteryCharging className="size-3.5" aria-hidden="true" />
            {household.battery_capacity_kwh > 0 ? 'Active' : 'No battery'}
          </Badge>
        }
        contentClassName="px-5 py-1"
      >
        <div className="flex items-center justify-between gap-6 border-b border-stone-100 py-3.5">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-stone-900">Evening reserve</p>
            <p className="mt-0.5 text-xs text-stone-500">
              Charge held back once the sun goes down, never sold before then — read by your
              agent on every tick.
            </p>
            <input
              type="range"
              min={0}
              max={90}
              step={5}
              value={reservePct}
              disabled={saving || household.battery_capacity_kwh <= 0}
              onChange={(e) => {
                setDraftReserve(Number(e.target.value));
              }}
              onMouseUp={(e) => void commitReserve(Number(e.currentTarget.value))}
              onTouchEnd={(e) => void commitReserve(Number(e.currentTarget.value))}
              className="mt-3 w-full accent-battery-600 disabled:opacity-50"
            />
          </div>
          <span className="shrink-0 font-mono text-sm font-semibold text-stone-900 tnum">
            {reservePct}%
          </span>
        </div>
        <PreferenceRow
          label="Battery capacity"
          description="Total usable storage on this household's inverter"
          value={kwh(household.battery_capacity_kwh)}
        />
        <PreferenceRow
          label="Max charge / discharge rate"
          description="How fast the battery can absorb surplus or deliver stored energy"
          value={`${kw(household.battery_max_charge_kw)} / ${kw(household.battery_max_discharge_kw)}`}
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
          value={`${inr(FEED_IN_TARIFF)}/unit`}
        />
        <PreferenceRow
          label="Maximum purchase price"
          description="Your agent never pays more than the utility would charge"
          value={`${inr(RETAIL_TARIFF)}/unit`}
        />
        <PreferenceRow
          label="Household size"
          description="Scales how much this household typically consumes"
          value={`${String(household.member_count)} member${household.member_count === 1 ? '' : 's'}`}
        />
        <PreferenceRow
          label="Rooftop solar capacity"
          description="Installed generation capacity used to simulate this household's output"
          value={household.solar_capacity_kwp > 0 ? `${household.solar_capacity_kwp.toFixed(1)} kWp` : 'None'}
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
          description="Multi-round negotiation: each side concedes toward its reservation price until it crosses"
          value="Negotiated uniform price"
        />
        <PreferenceRow
          label="Tick length"
          description="How much simulated time one tick represents"
          value="15 minutes"
        />
        <PreferenceRow
          label="Grid safety"
          description="Every allocation is checked against thermal and voltage limits before it settles"
          value="Linearized DistFlow"
        />
      </Card>
    </div>
  );
}
