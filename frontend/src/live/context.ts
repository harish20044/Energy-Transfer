import { createContext } from 'react';

import type { HouseholdProfile, MeterReading } from '@/api/household';
import type { OwnSession, Session, SessionConfig, SlotSummary } from '@/api/session';
import type { MarketTrade } from '@/api/simulation';

export interface LiveDataValue {
  session: Session | null;
  household: HouseholdProfile | null;
  /** This household's forecast, agent decisions, deliveries and money. */
  own: OwnSession | null;
  /** The whole feeder, hour by hour. */
  overview: SlotSummary[];
  /** Delivered 15-minute intervals, most recent first. */
  readings: MeterReading[];
  /** This household's own neighbour trades, in slot order. */
  trades: MarketTrade[];
  /** True only until the first load completes. */
  loading: boolean;
  /** A plan / next-hour / reset request is in flight. */
  busy: boolean;
  /** "Run to end" is stepping through the remaining hours. */
  running: boolean;
  /** Bumped after every refresh, so pages can refetch what depends on it. */
  version: number;
  error: string | null;
  refreshHousehold: () => void;
  refresh: () => Promise<void>;
  plan: (config: SessionConfig) => Promise<boolean>;
  nextHour: () => Promise<void>;
  runToEnd: () => Promise<void>;
  stop: () => void;
}

export const LiveDataContext = createContext<LiveDataValue | null>(null);
