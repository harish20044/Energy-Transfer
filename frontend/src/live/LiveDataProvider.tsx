import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import {
  fetchOwnBalance,
  fetchOwnHousehold,
  fetchOwnReadings,
  fetchOwnTrades,
  type HouseholdBalance,
  type HouseholdProfile,
  type MeterReading,
} from '@/api/household';
import {
  fetchSimulationState,
  pause as apiPause,
  play as apiPlay,
  reset as apiReset,
  step as apiStep,
  type MarketTrade,
  type PlayOptions,
  type SimulationState,
} from '@/api/simulation';
import { useAuth } from '@/auth/useAuth';
import { LiveDataContext, type LiveDataValue } from '@/live/context';

/** How often every live resource is refetched. Polling rather than a
 *  WebSocket, on purpose (see docs/adr — a 1s poll gives the same live feel
 *  with far fewer failure modes, and the tick engine itself only advances a
 *  couple of times a second at most anyway). */
const POLL_MS = 1000;

export function LiveDataProvider({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth();
  const [simulation, setSimulation] = useState<SimulationState | null>(null);
  const [household, setHousehold] = useState<HouseholdProfile | null>(null);
  const [readings, setReadings] = useState<MeterReading[]>([]);
  const [trades, setTrades] = useState<MarketTrade[]>([]);
  const [balance, setBalance] = useState<HouseholdBalance | null>(null);
  const [loading, setLoading] = useState(true);
  const [householdRefreshCount, setHouseholdRefreshCount] = useState(0);

  const refreshHousehold = useCallback(() => {
    setHouseholdRefreshCount((count) => count + 1);
  }, []);

  // The household's own configuration rarely changes, so it's fetched once
  // (and again whenever refreshHousehold() is called after an edit) rather
  // than on every poll tick.
  useEffect(() => {
    if (accessToken === null) return;
    let cancelled = false;

    fetchOwnHousehold(accessToken)
      .then((profile) => {
        if (!cancelled) setHousehold(profile);
      })
      .catch(() => {
        // Not every account is linked to a household (e.g. an operator) —
        // there's simply nothing household-specific to show for it.
      });

    return () => {
      cancelled = true;
    };
  }, [accessToken, householdRefreshCount]);

  useEffect(() => {
    if (accessToken === null) return;
    let cancelled = false;

    async function poll(): Promise<void> {
      const results = await Promise.allSettled([
        fetchSimulationState(accessToken as string),
        fetchOwnReadings(accessToken as string),
        fetchOwnTrades(accessToken as string),
        fetchOwnBalance(accessToken as string),
      ]);
      if (cancelled) return;
      if (results[0].status === 'fulfilled') setSimulation(results[0].value);
      if (results[1].status === 'fulfilled') setReadings(results[1].value);
      if (results[2].status === 'fulfilled') setTrades(results[2].value);
      if (results[3].status === 'fulfilled') setBalance(results[3].value);
      setLoading(false);
    }

    void poll();
    const timer = setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [accessToken]);

  const play = useCallback(
    async (options?: PlayOptions) => {
      if (accessToken === null) return;
      setSimulation(await apiPlay(accessToken, options));
    },
    [accessToken],
  );

  const pause = useCallback(async () => {
    if (accessToken === null) return;
    setSimulation(await apiPause(accessToken));
  }, [accessToken]);

  const step = useCallback(async () => {
    if (accessToken === null) return;
    setSimulation(await apiStep(accessToken));
  }, [accessToken]);

  const reset = useCallback(
    async (options?: PlayOptions) => {
      if (accessToken === null) return;
      setSimulation(await apiReset(accessToken, options));
      setReadings([]);
      setTrades([]);
      setBalance(null);
    },
    [accessToken],
  );

  const value = useMemo<LiveDataValue>(
    () => ({
      simulation,
      household,
      readings,
      trades,
      balance,
      loading,
      refreshHousehold,
      play,
      pause,
      step,
      reset,
    }),
    [simulation, household, readings, trades, balance, loading, refreshHousehold, play, pause, step, reset],
  );

  return <LiveDataContext.Provider value={value}>{children}</LiveDataContext.Provider>;
}
