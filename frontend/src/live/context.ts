import { createContext } from 'react';

import type { HouseholdBalance, HouseholdProfile, MeterReading } from '@/api/household';
import type { MarketTrade, PlayOptions, SimulationState } from '@/api/simulation';

export interface LiveDataValue {
  simulation: SimulationState | null;
  household: HouseholdProfile | null;
  /** Most recent tick first. */
  readings: MeterReading[];
  /** This household's own trades, most recent first. */
  trades: MarketTrade[];
  balance: HouseholdBalance | null;
  /** True only until the first successful load of every resource. */
  loading: boolean;
  refreshHousehold: () => void;
  play: (options?: PlayOptions) => Promise<void>;
  pause: () => Promise<void>;
  step: () => Promise<void>;
  reset: (options?: PlayOptions) => Promise<void>;
}

export const LiveDataContext = createContext<LiveDataValue | null>(null);
