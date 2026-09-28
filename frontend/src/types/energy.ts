/** UI-shaped types still used by presentational components that predate the
 *  live API wiring. Most page-level data now flows through `@/api/*` and
 *  `@/live/*` types directly — these two remain because `EnergyFlow` and
 *  `TradeList`/`TradeExplanation` are still driven by a small, stable shape
 *  built by a mapper (`@/lib/tradeView.toUiTrade`) rather than the raw API
 *  response. */

export type TradeSide = 'sell' | 'buy';

/** Instantaneous power at one household, as `EnergyFlow` renders it. Signs
 *  are from the household's own point of view: positive battery = charging,
 *  positive peer = exporting to neighbours. */
export interface LivePower {
  solarKw: number;
  loadKw: number;
  batteryKw: number;
  peerKw: number;
  gridKw: number;
  batterySoc: number;
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
