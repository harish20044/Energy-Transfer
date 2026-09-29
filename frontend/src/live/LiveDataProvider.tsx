import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { ApiError } from '@/api/client';
import {
  fetchOwnHousehold,
  fetchOwnReadings,
  fetchOwnTrades,
  type HouseholdProfile,
  type MeterReading,
} from '@/api/household';
import {
  fetchOverview,
  fetchOwnSession,
  fetchSession,
  nextHour as apiNextHour,
  planSession,
  type OwnSession,
  type Session,
  type SessionConfig,
  type SlotSummary,
} from '@/api/session';
import type { MarketTrade } from '@/api/simulation';
import { useAuth } from '@/auth/useAuth';
import { LiveDataContext, type LiveDataValue } from '@/live/context';

/** Nothing advances on its own; this only picks up changes made from
 *  another browser (there's one feeder and one session for everyone). */
const BACKGROUND_REFRESH_MS = 5000;
/** Pause between hours during "Run to end", so the play-out is watchable. */
const RUN_STEP_DELAY_MS = 700;

function describe(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong';
}

export function LiveDataProvider({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth();
  const [session, setSession] = useState<Session | null>(null);
  const [household, setHousehold] = useState<HouseholdProfile | null>(null);
  const [own, setOwn] = useState<OwnSession | null>(null);
  const [overview, setOverview] = useState<SlotSummary[]>([]);
  const [readings, setReadings] = useState<MeterReading[]>([]);
  const [trades, setTrades] = useState<MarketTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [householdRefreshCount, setHouseholdRefreshCount] = useState(0);
  const stopRequested = useRef(false);

  const refreshHousehold = useCallback(() => {
    setHouseholdRefreshCount((count) => count + 1);
  }, []);

  useEffect(() => {
    if (accessToken === null) return;
    let cancelled = false;
    fetchOwnHousehold(accessToken)
      .then((profile) => {
        if (!cancelled) setHousehold(profile);
      })
      .catch(() => {
        // An account without a household (e.g. an operator) has nothing
        // household-specific to show.
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, householdRefreshCount]);

  const refresh = useCallback(async () => {
    if (accessToken === null) return;
    const results = await Promise.allSettled([
      fetchSession(accessToken),
      fetchOwnSession(accessToken),
      fetchOverview(accessToken),
      fetchOwnReadings(accessToken, 200),
      fetchOwnTrades(accessToken, 500),
    ]);
    if (results[0].status === 'fulfilled') setSession(results[0].value);
    if (results[1].status === 'fulfilled') setOwn(results[1].value);
    if (results[2].status === 'fulfilled') setOverview(results[2].value);
    if (results[3].status === 'fulfilled') setReadings(results[3].value);
    if (results[4].status === 'fulfilled') setTrades(results[4].value);
    setLoading(false);
    setVersion((v) => v + 1);
  }, [accessToken]);

  useEffect(() => {
    if (accessToken === null) return;
    void refresh();
    const timer = setInterval(() => void refresh(), BACKGROUND_REFRESH_MS);
    return () => {
      clearInterval(timer);
    };
  }, [accessToken, refresh]);

  const plan = useCallback(
    async (config: SessionConfig) => {
      if (accessToken === null) return false;
      setBusy(true);
      setError(null);
      try {
        setSession(await planSession(accessToken, config));
        await refresh();
        return true;
      } catch (err) {
        setError(describe(err));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [accessToken, refresh],
  );

  const nextHour = useCallback(async () => {
    if (accessToken === null) return;
    setBusy(true);
    setError(null);
    try {
      setSession(await apiNextHour(accessToken));
      await refresh();
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  }, [accessToken, refresh]);

  const runToEnd = useCallback(async () => {
    if (accessToken === null) return;
    stopRequested.current = false;
    setRunning(true);
    setError(null);
    try {
      for (;;) {
        const state = await apiNextHour(accessToken);
        setSession(state);
        await refresh();
        if (state.status === 'complete' || stopRequested.current) break;
        await new Promise((resolve) => setTimeout(resolve, RUN_STEP_DELAY_MS));
        if (stopRequested.current) break;
      }
    } catch (err) {
      setError(describe(err));
    } finally {
      setRunning(false);
    }
  }, [accessToken, refresh]);

  const stop = useCallback(() => {
    stopRequested.current = true;
  }, []);

  const value = useMemo<LiveDataValue>(
    () => ({
      session,
      household,
      own,
      overview,
      readings,
      trades,
      loading,
      busy,
      running,
      version,
      error,
      refreshHousehold,
      refresh,
      plan,
      nextHour,
      runToEnd,
      stop,
    }),
    [
      session,
      household,
      own,
      overview,
      readings,
      trades,
      loading,
      busy,
      running,
      version,
      error,
      refreshHousehold,
      refresh,
      plan,
      nextHour,
      runToEnd,
      stop,
    ],
  );

  return <LiveDataContext.Provider value={value}>{children}</LiveDataContext.Provider>;
}
