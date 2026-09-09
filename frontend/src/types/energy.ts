/** Domain types shared across the dashboard. These mirror the API contracts
 *  the backend will serve in P1, so swapping mock data for live data is a
 *  change of source, not a change of shape. */

export type TradeSide = 'sell' | 'buy';
export type HouseholdRole = 'prosumer' | 'consumer';

/** Traffic-light state for a grid constraint. `violation` must never occur in a
 *  settled allocation — the safety layer curtails until it cannot (objective O4). */
export type ConstraintStatus = 'ok' | 'warning' | 'violation';

/** Instantaneous power at one household. Signs are from the household's view:
 *  positive battery = charging, positive peer = exporting to neighbours. */
export interface LivePower {
  solarKw: number;
  loadKw: number;
  batteryKw: number;
  peerKw: number;
  gridKw: number;
  batterySoc: number;
}

export interface DaySummary {
  savedInr: number;
  soldKwh: number;
  boughtKwh: number;
  selfSufficiency: number;
  gridAvoidedKwh: number;
}

/** One settled trade, carrying the rationale that satisfies objective O7. */
export interface Trade {
  id: string;
  at: string;
  counterparty: string;
  side: TradeSide;
  kwh: number;
  pricePerKwh: number;
  totalInr: number;
  rationale: string;
  bindingConstraint: string | null;
}

/** A forecast interval. P10/P90 are what make risk-aware bidding possible. */
export interface ForecastPoint {
  time: string;
  genP10: number;
  genP50: number;
  genP90: number;
  loadP50: number;
}

export interface OrderLevel {
  pricePerKwh: number;
  kwh: number;
  cumulativeKwh: number;
  households: number;
}

export interface PriceTick {
  time: string;
  clearingInr: number;
  volumeKwh: number;
}

export interface MarketState {
  tickNumber: number;
  gateClosesInSeconds: number;
  mechanism: string;
  clearingInr: number;
  matchedKwh: number;
  feedInTariff: number;
  retailTariff: number;
  participants: number;
  curtailedKwh: number;
}

export interface NetworkNode {
  id: string;
  label: string;
  bus: number;
  role: HouseholdRole;
  netKw: number;
  voltagePu: number;
  status: ConstraintStatus;
  x: number;
  y: number;
}

export interface NetworkLine {
  from: string;
  to: string;
  loadingPct: number;
  status: ConstraintStatus;
}
