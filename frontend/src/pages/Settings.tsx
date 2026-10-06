import { BatteryCharging, Bot, Brain, Scale } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { fetchOwnAgent, type AgentMemory } from '@/api/agents';

import { updateEveningReserve } from '@/api/household';
import { useAuth } from '@/auth/useAuth';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { hourLabel, inr, kw, kwh, percent } from '@/lib/format';
import { useLiveData } from '@/live/useLiveData';

/** How long the reserve slider waits after the last change before saving. */
const RESERVE_SAVE_DELAY_MS = 400;

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
  const { household, session, refreshHousehold, version } = useLiveData();
  const [agent, setAgent] = useState<AgentMemory | null>(null);

  useEffect(() => {
    if (accessToken === null) return;
    const controller = new AbortController();
    fetchOwnAgent(accessToken, controller.signal)
      .then(setAgent)
      .catch(() => undefined);
    return () => {
      controller.abort();
    };
  }, [accessToken, version]);
  const feedIn = session?.feed_in_tariff ?? 3.61;
  const retail = session?.retail_tariff ?? 10.5;
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [draftReserve, setDraftReserve] = useState<number | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savedReserve = household?.evening_reserve;

  // Once the saved value comes back (from this page, or from the agent chat),
  // show it rather than a stale draft.
  useEffect(() => {
    setDraftReserve(null);
  }, [savedReserve]);

  useEffect(
    () => () => {
      if (saveTimer.current !== null) clearTimeout(saveTimer.current);
    },
    [],
  );

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
    setSaveError(null);
    try {
      await updateEveningReserve(accessToken, pct / 100);
      refreshHousehold();
    } catch {
      setSaveError('Couldn’t save the reserve. Check your connection and move the slider again.');
      setDraftReserve(null);
    } finally {
      setSaving(false);
    }
  }

  // Saves a moment after the last change, so dragging, tapping and arrow
  // keys all save the same way, once.
  function changeReserve(pct: number): void {
    setDraftReserve(pct);
    if (saveTimer.current !== null) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      saveTimer.current = null;
      void commitReserve(pct);
    }, RESERVE_SAVE_DELAY_MS);
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
            <label htmlFor="battery-reserve" className="text-sm font-semibold text-stone-900">
              Battery reserve
            </label>
            <p id="battery-reserve-help" className="mt-0.5 text-xs text-stone-500">
              The charge level your agent never sells below. It still uses the battery for your own
              home; this only protects stored charge from being sold. Applies from the next session
              you plan.
            </p>
            <input
              id="battery-reserve"
              type="range"
              min={0}
              max={90}
              step={5}
              value={reservePct}
              aria-describedby="battery-reserve-help"
              aria-valuetext={`${String(reservePct)}%`}
              disabled={household.battery_capacity_kwh <= 0}
              onChange={(e) => {
                changeReserve(Number(e.target.value));
              }}
              className="mt-3 w-full accent-battery-600 disabled:opacity-50"
            />
            <p className="mt-1 h-4 text-xs" aria-live="polite">
              {saveError !== null ? (
                <span className="text-grid-700">{saveError}</span>
              ) : saving ? (
                <span className="text-stone-500">Saving…</span>
              ) : null}
            </p>
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
          description="The EB's feed-in rate (TNERC) — your agent never sells below it, so a trade always beats exporting"
          value={`${inr(feedIn)}/unit`}
        />
        <PreferenceRow
          label="Maximum purchase price"
          description="The EB's retail rate for your slab — your agent never pays neighbours more than this"
          value={`${inr(retail)}/unit`}
        />
        <PreferenceRow
          label="Household size"
          description="Your family — who is home when is what drives consumption"
          value={`${String(household.member_count)} member${household.member_count === 1 ? '' : 's'}`}
        />
        <PreferenceRow
          label="Rooftop solar capacity"
          description="Installed generation capacity used to simulate this household's output"
          value={
            household.solar_capacity_kwp > 0
              ? `${household.solar_capacity_kwp.toFixed(1)} kWp`
              : 'None'
          }
        />
      </Card>

      <Card
        className="xl:col-span-2"
        title="What your agent has learned"
        subtitle="Its own price forecast, learned from every hour it has traded or watched — kept across sessions"
        action={
          <Badge tone="peer">
            <Brain className="size-3.5" aria-hidden="true" />
            {agent !== null ? agent.graph_nodes.join(' → ') : 'LangGraph agent'}
          </Badge>
        }
      >
        {agent === null ? (
          <p className="text-sm text-stone-400">Loading what your agent knows…</p>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div>
                <p className="text-xs text-stone-500">Opens sales above its floor by</p>
                <p className="font-mono text-sm font-bold text-stone-900 tnum">
                  {percent(agent.sell_margin * 100)}
                </p>
              </div>
              <div>
                <p className="text-xs text-stone-500">Opens bids below its ceiling by</p>
                <p className="font-mono text-sm font-bold text-stone-900 tnum">
                  {percent(agent.buy_margin * 100)}
                </p>
              </div>
              <div>
                <p className="text-xs text-stone-500">Neighbour trades so far</p>
                <p className="font-mono text-sm font-bold text-stone-900 tnum">
                  {agent.trades} · {kwh(agent.units_sold + agent.units_bought)}
                </p>
              </div>
              <div>
                <p className="text-xs text-stone-500">Saved vs the EB, all sessions</p>
                <p className="font-mono text-sm font-bold text-battery-600 tnum">
                  {inr(agent.savings_inr)}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-6 gap-1.5 sm:grid-cols-12">
              {agent.price_by_hour.map((price, hour) => (
                <div
                  key={hour}
                  className={`rounded-md px-1 py-1.5 text-center ${price === null ? 'bg-stone-50' : 'bg-peer-50'}`}
                  title={price === null ? 'Not seen yet' : `Learned price at ${hourLabel(hour)}`}
                >
                  <p className="text-[10px] text-stone-500">{hourLabel(hour)}</p>
                  <p className="font-mono text-[11px] font-semibold text-stone-800 tnum">
                    {price === null ? '—' : `₹${price.toFixed(1)}`}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
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
          description="One auction per hour of the session, cleared in time order before delivery; each side concedes over rounds, and the EB takes whatever is left"
          value="Hourly ahead market"
        />
        <PreferenceRow
          label="Delivery"
          description="Each hour is delivered in 15-minute intervals; the battery absorbs forecast errors first, then the EB"
          value="15-minute metering"
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
